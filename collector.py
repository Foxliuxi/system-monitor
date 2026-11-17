#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collector.py —— 指标采集层
职责单一：从操作系统读取网络 / 硬件 / 链路指标，不做任何业务判断。
所有判断逻辑归 analyzer.py，这里只负责"读得准"。

依赖：psutil（唯一三方依赖）
"""
import json
import platform
import re
import socket
import subprocess
import threading
import time
from collections import deque

import psutil

# ---------------------------------------------------------------- 基础工具

_VIRTUAL_NIC_HINTS = (
    "virtual", "vmware", "vbox", "virtualbox", "tap", "loopback", "bluetooth",
    "teredo", "isatap", "hyper-v", "veth", "docker", "wsl", "npcap", "zerotier",
)


def decode(raw: bytes, prefer=None) -> str:
    """
    Windows 中文系统命令输出多为 GBK，但 PowerShell 经 UTF-8 重定向后是 UTF-8。
    顺序讲究：先严格 UTF-8（GBK 汉字几乎必然 UTF-8 解码失败），失败再退 GBK。
    顺序反了会把 UTF-8 中文解成乱码而"假装成功"，这是最常见的隐性 Bug。
    """
    encs = ([prefer] if prefer else []) + ["utf-8", "gbk", "cp936"]
    for enc in encs:
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def _run(cmd, timeout=6.0, prefer=None):
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=timeout,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return decode(cp.stdout, prefer), decode(cp.stderr, prefer)
    except Exception:
        return "", ""


def _num(text):
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(text))
    return float(m.group(1)) if m else None


def _parse_speed(text):
    """'150 Mbps' -> 150.0, '1 Gbps' -> 1000.0"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    v = _num(text)
    if v is None:
        return None
    return v * 1000 if "gbps" in str(text).lower() else v


def _ps_json(script, timeout=25):
    """
    PowerShell 单语句查询并输出 JSON。
    强制 UTF-8 输出 + json 解析，避免 Format-Table 表格解析的脆弱性和中文列错位。
    """
    full = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;" + script
    out, _ = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", full],
                  timeout=timeout, prefer="utf-8")
    txt = out.strip()
    if not txt:
        return []
    try:
        data = json.loads(txt)
    except Exception:
        # 偶发混入警告行，从首个 [ 或 { 截断重试
        idx = [p for p in (txt.find("["), txt.find("{")) if p >= 0]
        if not idx:
            return []
        try:
            data = json.loads(txt[min(idx):])
        except Exception:
            return []
    return data if isinstance(data, list) else [data]


# ---------------------------------------------------------------- 静态硬件画像

def _cpu_from_registry():
    """CPU 型号/标称主频：注册表直读，零子进程、零编码问题"""
    info = {}
    try:
        import winreg
    except ImportError:
        return info
    path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            try:
                info["cpu_model"] = str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
            except Exception:
                pass
            try:
                info["cpu_max_mhz"] = float(winreg.QueryValueEx(k, "~MHz")[0])
            except Exception:
                pass
    except Exception:
        pass
    return info


def _nominal_speed(desc, link_speed):
    """
    网卡未连接时 LinkSpeed 返回 0，不能用它判断硬件能力。
    这里从型号描述推断标称速率，才能回答"这块口值不值得插网线"。
    """
    if link_speed and link_speed > 0:
        return link_speed
    d = (desc or "").lower()
    if any(k in d for k in ("2.5g", "2.5 g", "i225", "i226", "r8125", "2.5gbe")):
        return 2500.0
    if any(k in d for k in ("10g", "x550", "x540", "aquantia")):
        return 10000.0
    if any(k in d for k in ("gbe", "gigabit", "1000", "i210", "i211", "i219", "r8168", "r8169")):
        return 1000.0
    if "fast ethernet" in d:
        return 100.0
    if any(k in d for k in ("wireless", "wi-fi", "wlan", "802.11")):
        return None  # 无线速率由协商决定，不做猜测
    return 1000.0  # 现代板载网卡默认按千兆估计


def hardware_profile():
    """开机采一次即可的静态信息"""
    prof = {
        "cpu_model": "未知",
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "cpu_max_mhz": None,
        "mem_total_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        "os": None,
        "nics": [],
        "disks": [],
    }
    prof.update(_cpu_from_registry())

    # 操作系统
    try:
        prof["os"] = f"Windows {platform.release()}"
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            name = str(winreg.QueryValueEx(k, "ProductName")[0])
            build = str(winreg.QueryValueEx(k, "CurrentBuildNumber")[0])
            ver = str(winreg.QueryValueEx(k, "DisplayVersion")[0])
            # 微软历史遗留：Win11 的 ProductName 仍写 "Windows 10"，按 build 号纠正
            if build.isdigit() and int(build) >= 22000:
                name = name.replace("Windows 10", "Windows 11")
            prof["os"] = f"{name} {ver} (Build {build})"
    except Exception:
        pass

    # 网卡（含未连接的口，才能指出"千兆口空置"）
    adapters = _ps_json(
        "Get-NetAdapter | Select-Object Name,InterfaceDescription,LinkSpeed,Status,MacAddress "
        "| ConvertTo-Json -Compress"
    )
    for a in adapters:
        if not isinstance(a, dict):
            continue
        desc = str(a.get("InterfaceDescription") or "")
        link = _parse_speed(a.get("LinkSpeed"))
        prof["nics"].append({
            "name": a.get("Name"),
            "desc": desc,
            "link_speed_mbps": link,
            "nominal_speed_mbps": _nominal_speed(desc, link),
            "status": a.get("Status"),
            "mac": a.get("MacAddress"),
            "is_wireless": any(k in desc.lower() for k in
                               ("wireless", "wi-fi", "wlan", "802.11", "wireless lan")),
        })

    # 物理磁盘
    for d in _ps_json("Get-PhysicalDisk | Select-Object FriendlyName,MediaType,Size "
                      "| ConvertTo-Json -Compress"):
        if not isinstance(d, dict):
            continue
        size = d.get("Size")
        prof["disks"].append({
            "name": d.get("FriendlyName"),
            "media": d.get("MediaType") or "未知",
            "size_gb": round(_num(size) / 1024 ** 3) if size else None,
        })
    return prof


def default_gateway():
    """
    读 IPv4 路由表取默认网关。
    不用 ipconfig：当接口同时有 IPv6 链路本地网关时，ipconfig 会把 IPv4 网关挤到续行，
    标签只出现一次，正则极易误抓到本机地址（实测踩过）。
    """
    out, _ = _run(["route", "print", "-4"], timeout=8)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
            ip = parts[2]
            if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip) and ip != "0.0.0.0":
                return ip
    # 兜底：ipconfig 里"默认网关"行后紧跟的 IPv4
    out, _ = _run(["ipconfig"], timeout=8)
    m = re.search(r"(?:Default Gateway|默认网关)[\s.:]*((?:\d{1,3}\.){3}\d{1,3})", out)
    return m.group(1) if m else None


# ---------------------------------------------------------------- 链路探测

# 回复行：IPv4 是 "时间=12ms TTL=65"，IPv6 是 "时间=1233ms"（没有 TTL 字段）
_re_rtt = re.compile(r"(?:time|时间)\s*[=<]\s*(\d+(?:\.\d+)?)\s*ms", re.I)
# 统计汇总行：中英文、IPv4/IPv6、成功失败都一定会打印
_re_recv = re.compile(r"(?:Received|已接收)\s*=\s*(\d+)", re.I)
_re_lost = re.compile(r"(?:Lost|丢失)\s*=\s*(\d+)", re.I)
# 非超时类失败：解析不到主机、无路由、TTL 过期等，这些不能算"丢包"
_re_ping_err = re.compile(
    r"(传输失败|常见故障|一般故障|无法访问目标主机|找不到主机|传输中过期|"
    r"General failure|could not find host|Destination host unreachable|"
    r"TTL expired|not known|Name or service not known)", re.I)


def ping_once(host, timeout_ms=4000):
    """
    单次 ICMP 探测。返回结构化结果，把三种情况分开——这是关键：
      ok       收到回应（rtt 毫秒）
      timeout  发出去了但没回来 —— 这才是"丢包"
      error    根本没发出去 / 解析失败 / 无路由 —— 不算丢包，单独统计
    历史上把后两者混为一谈，导致"域名解析到 IPv6 但没 IPv6 路由"也会被算成 100% 丢包。
    """
    res = {"status": "error", "rtt": None, "detail": ""}
    if not host:
        res["detail"] = "未配置探测目标"
        return res
    try:
        cp = subprocess.run(
            ["ping", "-n", "1", "-w", str(int(timeout_ms)), host],
            capture_output=True, timeout=timeout_ms / 1000.0 + 4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        res.update(status="timeout", detail="ping 进程未在超时内返回")
        return res
    except Exception as e:
        res["detail"] = f"{type(e).__name__}: {e}"
        return res

    out = (decode(cp.stdout) + "\n" + decode(cp.stderr)).strip()

    # 汇总行是最可靠的判据：不依赖 TTL 字样（IPv6 回复没有 TTL），也不依赖语言
    recv = _re_recv.search(out)
    if recv:
        if int(recv.group(1)) > 0:
            m = _re_rtt.search(out)
            res["status"] = "ok"
            # "<1ms" 实际小于 1，记为 1：略高估，但比记 0 更诚实
            res["rtt"] = float(m.group(1)) if m else None
            return res
        lost = _re_lost.search(out)
        res["status"] = "timeout"
        res["detail"] = ("请求超时，未收到回应"
                         + (f"（丢失 {lost.group(1)} 个）" if lost else ""))
        return res

    # 没有汇总行 → 命令本身失败。挑最后一行非空文本作为原因
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    res["detail"] = lines[-1][:90] if lines else "ping 无输出"
    if _re_ping_err.search(out):
        res["status"] = "error"
    elif not lines:
        res["status"] = "error"
    else:
        res["status"] = "error"     # 无法归类的一律按 error，绝不默认算丢包
    return res


def ping_host(host, timeout_ms=4000):
    """兼容旧调用：只要 RTT，失败返回 None。新代码请用 ping_once 区分失败原因"""
    return ping_once(host, timeout_ms).get("rtt")


def dns_latency(host="www.baidu.com"):
    t = time.perf_counter()
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return round((time.perf_counter() - t) * 1000, 1)
    except Exception:
        return None


def tcp_handshake(host="223.5.5.5", port=53, timeout=1.5):
    t = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return round((time.perf_counter() - t) * 1000, 1)
    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass


class Pinger:
    """
    链路探测独立线程。

    为什么必须独立：单次 ping 最坏要等满超时窗口（4 秒），DNS/TCP 探测各要 1.5 秒。
    放在 1 秒采样循环里同步跑，采样节奏会被拖成 2-6 秒一次，
    丢包率的分母（探测次数）也随之失真。现在探测与采样彻底解耦：
    采样只读最近一次探测结果，永不阻塞。
    """

    def __init__(self, gateway, host, timeout_ms=4000, interval=1.0, maxlen=240):
        self.gateway = gateway
        self.host = host
        self.timeout_ms = int(timeout_ms)
        self.interval = interval
        self.log = {"gateway": deque(maxlen=maxlen), "public": deque(maxlen=maxlen)}
        self._latest = {
            "gateway": None, "public": None,
            "dns_ms": None, "tcp_ms": None,
            "target": host, "timeout_ms": self.timeout_ms,
        }
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # ---------------------------------------------------------- 线程
    def start(self):
        self._thread = threading.Thread(target=self._run, name="pinger", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        last_slow = 0.0
        while not self._stop.is_set():
            t0 = time.time()
            try:
                gw = ping_once(self.gateway, self.timeout_ms) if self.gateway else \
                    {"status": "error", "rtt": None, "detail": "网关未知"}
                pub = ping_once(self.host, self.timeout_ms)

                # DNS / TCP 建连很慢（各最多 1.5s），5 秒一次就够
                dns = tcp = None
                if t0 - last_slow >= 5.0:
                    dns = dns_latency(self.host if self.host and not _is_ip(self.host)
                                      else "www.baidu.com")
                    last_slow = t0

                with self._lock:
                    self.log["gateway"].append({"t": t0, **gw})
                    self.log["public"].append({"t": t0, **pub})
                    self._latest = {
                        "gateway": gw.get("rtt"),
                        "public": pub.get("rtt"),
                        "dns_ms": dns if dns is not None else self._latest.get("dns_ms"),
                        "tcp_ms": tcp if tcp is not None else self._latest.get("tcp_ms"),
                        "target": self.host,
                        "timeout_ms": self.timeout_ms,
                        "probe_ts": t0,
                        "gw_status": gw.get("status"),
                        "pub_status": pub.get("status"),
                        "gw_detail": gw.get("detail") or "",
                        "pub_detail": pub.get("detail") or "",
                    }
            except Exception:
                pass
            elapsed = time.time() - t0
            self._stop.wait(max(0.1, self.interval - elapsed))

    # ---------------------------------------------------------- 读取
    def latency(self):
        """供采样循环读取，非阻塞"""
        with self._lock:
            return dict(self._latest)

    def stats(self, window=60):
        """
        统计口径写清楚，避免"看起来像丢包"：
          - 分母只算真正发出去的探测（error 不计入）
          - loss = timeout / 有效探测数
          - error 单独报数量，不混进丢包率
        """
        out = {}
        with self._lock:
            for key in ("gateway", "public"):
                recs = list(self.log[key])[-window:]
                ok = [r["rtt"] for r in recs if r["status"] == "ok" and r["rtt"] is not None]
                to = sum(1 for r in recs if r["status"] == "timeout")
                err = sum(1 for r in recs if r["status"] == "error")
                valid = len(recs) - err
                diffs = [abs(b - a) for a, b in zip(ok, ok[1:])]
                out[key] = {
                    "attempts": len(recs),
                    "valid": valid,
                    "ok": len(ok),
                    "timeout": to,
                    "error": err,
                    "loss_pct": round(to / valid * 100, 1) if valid else None,
                    "avg": round(sum(ok) / len(ok), 1) if ok else None,
                    "min": round(min(ok), 1) if ok else None,
                    "max": round(max(ok), 1) if ok else None,
                    "jitter": round(sum(diffs) / len(diffs), 1) if len(diffs) >= 2 else None,
                    "last_detail": (recs[-1].get("detail") if recs else "") or "",
                }
        return out


def _is_ip(text):
    try:
        socket.inet_pton(socket.AF_INET, text)
        return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, text)
        return True
    except OSError:
        return False


def wifi_info():
    """仅无线网卡可用；有线环境返回 None"""
    out, _ = _run(["netsh", "wlan", "show", "interfaces"], timeout=8)
    if not out:
        return None
    low = out.lower()
    if "已连接" not in out and "connected" not in low:
        return None

    kv = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k:
            kv[k] = v

    def pick(*keys):
        for k in keys:  # 先精确，再模糊
            if k in kv:
                return kv[k]
        for k in keys:
            for kk, vv in kv.items():
                if k.lower() in kk.lower():
                    return vv
        return None

    sig = pick("信号", "Signal")
    return {
        "ssid": pick("SSID"),
        "signal_pct": _num(re.sub(r"[^\d]", "", sig) if sig else None),
        "rx_mbps": _num(pick("接收速率", "Receive rate")),
        "tx_mbps": _num(pick("传输速率", "Transmit rate")),
        "radio": pick("无线电类型", "Radio type"),
        "band": pick("波段", "Band"),
        "channel": pick("通道", "Channel"),
    }


def power_plan():
    out, _ = _run(["powercfg", "/getactivescheme"], timeout=6)
    m = re.search(r"\(([^)]+)\)\s*$", out.strip())
    if m:
        return m.group(1).strip()
    for kw in ("卓越性能", "高性能", "平衡", "节能", "Ultimate", "High performance", "Balanced", "Power saver"):
        if kw in out:
            return kw
    return None


# ---------------------------------------------------------------- 主网卡选择

def pick_primary_nic():
    """按累计流量选出真正承载业务的网卡，避免被虚拟网卡带偏"""
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)
    best = None
    for name, c in counters.items():
        st = stats.get(name)
        if not st or not st.isup:
            continue
        if any(h in name.lower() for h in _VIRTUAL_NIC_HINTS):
            continue
        if c.bytes_recv + c.bytes_sent < 1_000_000:  # 累计不足 1MB 视作无业务
            continue
        score = c.bytes_recv + c.bytes_sent
        if best is None or score > best[1]:
            best = (name, score)
    if best:
        st = stats.get(best[0])
        return {"name": best[0], "speed_mbps": getattr(st, "speed", None)}
    # 兜底：随便找一块 up 的物理网卡
    for name, st in stats.items():
        if st.isup and not any(h in name.lower() for h in _VIRTUAL_NIC_HINTS):
            return {"name": name, "speed_mbps": getattr(st, "speed", None)}
    return {"name": None, "speed_mbps": None}


# ---------------------------------------------------------------- 实时采样器

class Sampler:
    """
    有状态采样器：网络速率、包速率、错误增量都依赖前后两次快照的差值。
    第一次调用只建立基线，速率返回 0。
    """

    def __init__(self, public_host="223.5.5.5", dns_host="www.baidu.com",
                 pinger=None):
        self.nic = None
        self._last_io = None
        self._last_t = None
        self._last_disk = None
        self.conns = None
        self._last_conn_t = 0
        self.gw = None
        # 探测目标可配：默认阿里 DNS（国内延迟低、稳定），换网络环境时可改
        self.public_host = public_host
        self.dns_host = dns_host
        # 有 pinger 时探测在独立线程跑，这里只读结果，绝不阻塞采样
        self.pinger = pinger

    def sample(self, probe=True, do_wifi=False):
        now = time.time()
        data = {
            "ts": now,
            "net": {},
            "hardware": {},
            "latency": {},
            "wifi": None,
            "conns": None,
        }

        # ---- 主网卡 ----
        if self.nic is None or self.nic.get("name") not in psutil.net_io_counters(pernic=True):
            self.nic = pick_primary_nic()
            self._last_io = None

        nic_name = self.nic.get("name")

        # ---- 网络吞吐（差值法）----
        io_all = psutil.net_io_counters(pernic=True)
        cur = io_all.get(nic_name) if nic_name else None
        if cur is None and io_all:
            cur = max(io_all.values(), key=lambda c: c.bytes_recv)
        if cur is not None:
            if self._last_io is not None and self._last_t:
                dt = max(now - self._last_t, 0.001)
                d_recv = max(cur.bytes_recv - self._last_io.bytes_recv, 0)
                d_sent = max(cur.bytes_sent - self._last_io.bytes_sent, 0)
                data["net"] = {
                    "down_mbps": round(d_recv * 8 / dt / 1e6, 3),
                    "up_mbps": round(d_sent * 8 / dt / 1e6, 3),
                    "down_bytes": d_recv,
                    "up_bytes": d_sent,
                    "down_pps": round(max(cur.packets_recv - self._last_io.packets_recv, 0) / dt, 1),
                    "up_pps": round(max(cur.packets_sent - self._last_io.packets_sent, 0) / dt, 1),
                    "err_in_delta": max(cur.errin - self._last_io.errin, 0),
                    "err_out_delta": max(cur.errout - self._last_io.errout, 0),
                    "drop_in_delta": max(cur.dropin - self._last_io.dropin, 0),
                    "drop_out_delta": max(cur.dropout - self._last_io.dropout, 0),
                    "err_in_total": cur.errin,
                    "err_out_total": cur.errout,
                    "drop_in_total": cur.dropin,
                    "drop_out_total": cur.dropout,
                    "total_recv_gb": round(cur.bytes_recv / 1024 ** 3, 2),
                    "total_sent_gb": round(cur.bytes_sent / 1024 ** 3, 2),
                }
            else:
                data["net"] = {
                    "down_mbps": 0.0, "up_mbps": 0.0, "down_bytes": 0, "up_bytes": 0,
                    "down_pps": 0.0, "up_pps": 0.0,
                    "err_in_delta": 0, "err_out_delta": 0,
                    "drop_in_delta": 0, "drop_out_delta": 0,
                    "err_in_total": cur.errin, "err_out_total": cur.errout,
                    "drop_in_total": cur.dropin, "drop_out_total": cur.dropout,
                    "total_recv_gb": round(cur.bytes_recv / 1024 ** 3, 2),
                    "total_sent_gb": round(cur.bytes_sent / 1024 ** 3, 2),
                }
            self._last_io = cur
            self._last_t = now
        data["nic"] = {"name": nic_name, "speed_mbps": self.nic.get("speed_mbps")}

        # ---- 硬件 ----
        cpu_pct = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        mem = psutil.virtual_memory()
        disk = {"read_mbps": 0.0, "write_mbps": 0.0, "busy_pct": None}
        try:
            dio = psutil.disk_io_counters()
            if dio and self._last_disk and self._last_t:
                dt = max(now - self._last_t, 0.001)
                disk["read_mbps"] = round(max(dio.read_bytes - self._last_disk.read_bytes, 0) / dt / 1e6, 2)
                disk["write_mbps"] = round(max(dio.write_bytes - self._last_disk.write_bytes, 0) / dt / 1e6, 2)
            self._last_disk = dio
        except Exception:
            pass

        freq = {"current_mhz": None, "max_mhz": None}
        try:
            f = psutil.cpu_freq()
            if f:
                freq = {"current_mhz": round(f.current), "max_mhz": round(f.max) if f.max else None}
        except Exception:
            pass

        data["hardware"] = {
            "cpu_pct": round(cpu_pct, 1),
            "cpu_per_core": [round(x, 1) for x in per_core],
            "mem_pct": round(mem.percent, 1),
            "mem_used_gb": round(mem.used / 1024 ** 3, 1),
            "mem_total_gb": round(mem.total / 1024 ** 3, 1),
            "disk": disk,
            "freq": freq,
            "threads": psutil.cpu_count(logical=True),
        }

        # ---- 连接数（net_connections 在 Windows 上偏慢，5 秒一次）----
        if now - self._last_conn_t > 5:
            try:
                cs = psutil.net_connections(kind="inet")
                self.conns = sum(1 for c in cs if c.status == psutil.CONN_ESTABLISHED)
                self._last_conn_t = now
            except Exception:
                self.conns = None
        data["conns"] = self.conns

        # ---- 链路探测 ----
        # 有 pinger 就只读最近一次结果（非阻塞）；没有才走同步探测（仅自测时用）
        if probe:
            if self.pinger is not None:
                data["latency"] = self.pinger.latency()
            else:
                if not self.gw:
                    self.gw = default_gateway()
                data["latency"] = {
                    "gateway": ping_host(self.gw, 4000) if self.gw else None,
                    "public": ping_host(self.public_host, 4000),
                    "dns_ms": dns_latency(self.dns_host),
                    "tcp_ms": tcp_handshake(self.public_host, 53),
                    "target": self.public_host,
                    "timeout_ms": 4000,
                }
        if do_wifi:
            data["wifi"] = wifi_info()
        return data


if __name__ == "__main__":
    s = Sampler()
    prof = hardware_profile()
    print("硬件画像:", prof)
    print("网关:", default_gateway())
    print("电源计划:", power_plan())
    s.sample(probe=False)
    time.sleep(1)
    print("采样:", s.sample(do_wifi=True))
