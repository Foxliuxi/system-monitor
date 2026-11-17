#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py —— 系统实时监测服务
设计取舍：
  - 只用标准库 http.server + SSE，不引 FastAPI/uvicorn。理由：单人运维，双击即跑，
    少一个依赖就少一个半夜出问题的地方。
  - SSE 而不是 WebSocket：数据是单向推送（服务端→浏览器），SSE 原生支持断线重连，
    代码量只有 WS 的三分之一。
  - 只监听 127.0.0.1：这台机器的网络指标不该暴露给局域网任何人。

用法：python server.py [--port 8770] [--no-browser]
"""
import argparse
import json
import logging
import mimetypes
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 打包成 exe 后 __file__ 指向临时解包目录，静态资源要用 PyInstaller 给的 _MEIPASS。
# 源码运行时仍走脚本所在目录，两种模式的路径解析必须分开写，否则打出来的 exe 找不到 web/。
def _base_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
WEB_DIR = os.path.join(BASE_DIR, "web")

import collector
import analyzer
import sysmon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sysmon")


# ================================================================ 监测核心

class Monitor:
    """采集 + 分析的状态机，被采集线程驱动，被 HTTP 线程读取"""

    def __init__(self, public_host="223.5.5.5", dns_host="www.baidu.com",
                 ping_timeout_ms=4000, lang="zh"):
        self.lang = "en" if lang == "en" else "zh"
        self.profile = collector.hardware_profile()
        self.profile["power_plan"] = collector.power_plan()
        self.profile["gateway"] = collector.default_gateway()
        self.started_at = time.time()
        # 探测独立线程：单次 ping 最坏吃满超时窗口，绝不能塞进 1 秒采样循环，
        # 否则采样节奏被拖慢、丢包率的分母也跟着失真。
        self.pinger = collector.Pinger(gateway=self.profile["gateway"],
                                       host=public_host,
                                       timeout_ms=ping_timeout_ms)
        self.sampler = collector.Sampler(public_host=public_host, dns_host=dns_host,
                                         pinger=self.pinger)
        # 慢指标（显卡/温度/进程排行/磁盘容量）单独线程：
        # nvidia-smi ~100ms、PowerShell ~800ms、遍历进程 ~30ms，
        # 塞进 1 秒主循环会把它拖垮。
        self.slow = sysmon.SlowSampler()
        self.analyzer = analyzer.Analyzer(self.profile, lang="zh")
        # 英文分析结论同帧一起算：一套规则、两份文案，纯计算开销可以忽略
        # （不这么做的话，某个客户端切到英文就得等一整轮采样才有新结论）
        self.analyzer_en = analyzer.Analyzer(self.profile, lang="en")
        self.wifi = None
        self.latest = None
        self.history = deque(maxlen=1800)   # 30 分钟 @1s
        self.version = 0
        self.lock = threading.Lock()
        self._stop = threading.Event()

    # ---------------------------------------------------------- 采集循环
    def run(self):
        last_wifi = 0.0
        first = True
        while not self._stop.is_set():
            t0 = time.time()
            try:
                need_wifi = (t0 - last_wifi) >= 5.0
                sample = self.sampler.sample(probe=True, do_wifi=need_wifi)
                if need_wifi:
                    self.wifi = sample.get("wifi")
                    last_wifi = t0
                else:
                    sample["wifi"] = self.wifi

                stats = self.pinger.stats()
                result = self.analyzer.analyze(sample, self.wifi, probe_stats=stats)
                result_en = self.analyzer_en.analyze(sample, self.wifi, probe_stats=stats)

                net = sample.get("net") or {}
                hw = sample.get("hardware") or {}
                lat = sample.get("latency") or {}
                slow = self.slow.snapshot()

                snap = {
                    "ts": sample.get("ts"),
                    "uptime": round(time.time() - self.started_at),
                    "net": net,
                    "hardware": hw,
                    "latency": lat,
                    "wifi": sample.get("wifi"),
                    "conns": sample.get("conns"),
                    "nic": sample.get("nic"),
                    "analysis": result,
                    "analysis_en": result_en,
                    "gpu": slow.get("gpu"),
                    "thermal": slow.get("thermal"),
                    "disk": slow.get("disk"),
                    "procs": slow.get("procs"),
                }
                compact = {
                    "t": sample.get("ts"),
                    "d": round(net.get("down_mbps") or 0, 3),
                    "u": round(net.get("up_mbps") or 0, 3),
                    "g": lat.get("gateway"),
                    "p": lat.get("public"),
                    # 明确记录"这次确实超时"，供图表打红点；
                    # 不能用空值判断，空值也可能是探测未完成或发包失败
                    "gk": 1 if lat.get("gw_status") == "timeout" else 0,
                    "pk": 1 if lat.get("pub_status") == "timeout" else 0,
                    "c": hw.get("cpu_pct"),
                    "m": hw.get("mem_pct"),
                }
                with self.lock:
                    self.latest = snap
                    self.history.append(compact)
                    self.version += 1
                if first:
                    log.info(say("first_sample", self.lang),
                             (snap.get("nic") or {}).get("name"), self.profile.get("gateway"))
                    first = False
            except Exception:
                log.error("sample error:\n%s" if self.lang == "en" else "采样异常:\n%s",
                          traceback.format_exc())

            # 用实际耗时补偿，保持 ~1s 稳定节奏；探测慢时也不堆积
            elapsed = time.time() - t0
            self._stop.wait(max(0.05, 1.0 - elapsed))

    def stop(self):
        self._stop.set()

    def snapshot(self, lang="zh"):
        """
        按语言取快照。分析文案由服务端生成，所以两种语言的结论都要预先算好，
        这里只做「挑一份塞回 analysis 字段」——前端拿到的结构完全不变。
        """
        with self.lock:
            latest = self.latest
            if latest is not None:
                # 拷一份再改，绝不能动共享的 latest：另一个客户端可能是另一种语言
                latest = dict(latest)
                if lang == "en" and latest.get("analysis_en"):
                    latest["analysis"] = latest["analysis_en"]
                latest.pop("analysis_en", None)
            return {
                "profile": self.profile,
                "latest": latest,
                "history": list(self.history),
                "server_time": time.time(),
            }


# ================================================================ HTTP 层

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    monitor = None
    quiet = False

    def log_message(self, fmt, *args):
        if not self.quiet:
            log.debug("%s %s", self.address_string(), fmt % args)

    # ---------------------------------------------------------- 工具
    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _write_chunk(self, data: bytes):
        self.wfile.write(b"%X\r\n" % len(data) + data + b"\r\n")
        self.wfile.flush()

    # ---------------------------------------------------------- 路由
    def _lang(self):
        """界面语言由前端决定（localStorage 优先），这里只认它传过来的 ?lang="""
        q = parse_qs(urlparse(self.path).query)
        return "en" if (q.get("lang") or ["zh"])[0] == "en" else "zh"

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                return self._serve_file("index.html")
            if path == "/api/snapshot":
                return self._send_json(self.monitor.snapshot(self._lang()))
            if path == "/api/stream":
                return self._serve_stream(self._lang())
            if path.startswith("/api/"):
                return self._send_json({"error": "not found"}, 404)
            return self._serve_file(path.lstrip("/"))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception:
            log.error("请求异常 %s:\n%s", path, traceback.format_exc())
            try:
                self._send_json({"error": "internal"}, 500)
            except Exception:
                pass

    # ---------------------------------------------------------- 静态文件
    def _serve_file(self, rel):
        # 路径穿越防护：只允许 web 目录内的文件
        target = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not target.startswith(WEB_DIR) or not os.path.isfile(target):
            return self._send(404, "404 Not Found".encode(), "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(target, "rb") as f:
            body = f.read()
        self._send(200, body, ctype)

    # ---------------------------------------------------------- SSE
    def _serve_stream(self, lang="zh"):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_version = -1
        idle_since = time.time()

        # 首帧：历史数据，避免打开页面后要等一分钟才有曲线
        init = self.monitor.snapshot(lang)
        self._write_chunk(
            ("event: init\ndata: " + json.dumps(init, ensure_ascii=False) + "\n\n").encode("utf-8")
        )
        with self.monitor.lock:
            last_version = self.monitor.version

        while True:
            try:
                with self.monitor.lock:
                    ver = self.monitor.version
                if ver != last_version:
                    snap = self.monitor.snapshot(lang)["latest"]
                else:
                    snap = None
                if snap is not None:
                    self._write_chunk(
                        ("event: tick\ndata: " + json.dumps(snap, ensure_ascii=False) + "\n\n")
                        .encode("utf-8")
                    )
                    last_version = ver
                    idle_since = time.time()
                elif time.time() - idle_since > 15:
                    # 心跳：防止代理/系统休眠静默掐断连接
                    self._write_chunk(b": ping\n\n")
                    idle_since = time.time()
                time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return


# ================================================================ 启动

class QuietServer(ThreadingHTTPServer):
    """
    socketserver 默认在客户端断开时打印完整 traceback。
    浏览器刷新、关闭标签页都会触发 ConnectionReset/BrokenPipe —— 这是正常行为，
    不是故障。若不拦截，日志会被刷屏，真正的问题就淹没了。
    """
    daemon_threads = True

    # Windows 下 SO_REUSEADDR 允许两个进程绑同一端口，结果是新实例"启动成功"
    # 但请求全被老实例接走——改代码不生效却查不出原因（本机真踩过）。
    # 关掉复用：端口被占就绑定失败，由 pick_port 顺延到下一个，行为可预期。
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                            BrokenPipeError, TimeoutError)):
            return
        log.error("请求处理异常 (来自 %s): %s", client_address, exc, exc_info=True)


def pick_port(start=8770, tries=20):
    """
    探测可用端口。注意：探测手段必须与真正绑定同口径。
    以前这里给探测 socket 开了 SO_REUSEADDR，Windows 下即使端口被占用也能 bind 成功，
    于是探测说"8770 可用"，真正的服务再绑就静默共存了——老实例继续接请求，
    改完代码却看不到变化。现在加 SO_EXCLUSIVEADDRUSE，与 QuietServer 保持一致。
    """
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("找不到可用端口")


def detect_lang():
    """按系统界面语言选默认输出语言：中文 Windows 说中文，其他说英文"""
    try:
        import ctypes
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "zh" if (langid & 0x3FF) == 0x04 else "en"
    except Exception:
        return "zh"


# 控制台提示。web 界面和分析结论有自己的语言包（web/i18n.js、i18n_rules.py），
# 这里是「黑窗口」那一层——发给英文用户时不该满屏中文。
MSG = {
    "banner": {
        "zh": ["系统实时监测  ·  System Monitor",
               "· 浏览器会自动打开看板，关闭本窗口即停止",
               "· 数据只在本机处理，不上传任何服务器"],
        "en": ["System Monitor",
               "· The dashboard opens in your browser; closing this window stops it",
               "· Everything is processed locally — nothing is uploaded"],
    },
    "probing": {"zh": "正在采集硬件画像…（首次约需 2 秒）",
                "en": "Profiling hardware… (about 2s on first run)"},
    "cpu": {"zh": "CPU: %s | %s核%s线程 | 内存 %.1fGB",
            "en": "CPU: %s | %s cores / %s threads | %.1f GB RAM"},
    "gw": {"zh": "网关: %s | 电源计划: %s", "en": "Gateway: %s | Power plan: %s"},
    "first_sample": {"zh": "首次采样完成，网卡=%s 网关=%s",
                     "en": "First sample done — NIC=%s gateway=%s"},
    "gpu_ok": {"zh": "显卡: %s（nvidia-smi 可用，已采集利用率/显存/温度/功耗）",
               "en": "GPU: %s (nvidia-smi available — utilization/VRAM/temp/power)"},
    "gpu_na": {"zh": "显卡: 不可用 —— %s", "en": "GPU: unavailable — %s"},
    "gpu_lhm_ok": {"zh": "显卡: %s（经 LibreHardwareMonitor 采集）",
                   "en": "GPU: %s (via LibreHardwareMonitor)"},
    "no_admin": {"zh": "温度: CPU/硬盘温度需要管理员权限，当前为普通权限，将以 -- 显示",
                 "en": "Temps: CPU/drive temperatures need admin rights; running unprivileged, "
                       "they will show as --"},
    "no_admin_hint": {"zh": "      需要的话：右键 run.bat → 以管理员身份运行",
                      "en": "      To fix: right-click run.bat → Run as administrator"},
    "started": {"zh": "监测服务已启动 → %s", "en": "Monitor is live at %s"},
    "stop_hint": {"zh": "按 Ctrl+C 停止", "en": "Press Ctrl+C to stop"},
    "stopping": {"zh": "正在停止…", "en": "Stopping…"},
    "stopped": {"zh": "已停止", "en": "Stopped"},
    "no_port": {"zh": "找不到可用端口", "en": "No free port available"},
}


def say(key, lang, *args):
    s = MSG[key]["en" if lang == "en" else "zh"]
    return s % args if args else s


def main():
    ap = argparse.ArgumentParser(
        description="实时网络监测 / Real-time system & network monitor")
    ap.add_argument("--port", type=int, default=8770, help="监听端口 / listen port")
    ap.add_argument("--no-browser", action="store_true", help="不自动开浏览器 / no auto-open")
    ap.add_argument("--quiet", action="store_true", help="只输出警告 / warnings only")
    ap.add_argument("--lang", choices=["zh", "en"], default=None,
                    help="控制台语言（默认跟随系统）/ console language (auto by default)")
    ap.add_argument("--ping-target", default="223.5.5.5",
                    help="公网延迟探测目标 / public latency target"
                         "（默认阿里DNS，海外可换 1.1.1.1）")
    ap.add_argument("--ping-timeout", type=int, default=4000,
                    help="ICMP 超时窗口毫秒 / ICMP timeout in ms（默认 4000）")
    ap.add_argument("--dns-host", default="www.baidu.com",
                    help="DNS 解析耗时测试域名 / hostname used for DNS timing")
    args = ap.parse_args()

    lang = args.lang or detect_lang()

    if args.quiet:
        log.setLevel(logging.WARNING)

    # 提示放在 Python 里输出：.bat 必须保持纯 ASCII（cmd 按系统代码页解析，
    # 中文会被字节错位、截断命令），所以界面文案由这里负责。
    print()
    print("  " + "=" * 54)
    for line in MSG["banner"][lang]:
        print("     " + line)
    print("  " + "=" * 54)
    print()
    sys.stdout.flush()   # 输出被重定向时 stdout 是块缓冲，不刷新会看不到横幅

    log.info(say("probing", lang))
    mon = Monitor(public_host=args.ping_target, dns_host=args.dns_host,
                  ping_timeout_ms=args.ping_timeout, lang=lang)
    log.info(say("cpu", lang),
             mon.profile.get("cpu_model"), mon.profile.get("cpu_cores"),
             mon.profile.get("cpu_threads"), mon.profile.get("mem_total_gb") or 0)
    log.info(say("gw", lang),
             mon.profile.get("gateway"), mon.profile.get("power_plan"))

    t = threading.Thread(target=mon.run, name="collector", daemon=True)
    t.start()
    mon.pinger.start()          # 探测独立线程，晚于采样线程启动也没关系（先读到空结果）
    ts = threading.Thread(target=mon.slow.run, name="slow", daemon=True)
    ts.start()

    # 显卡/温度能力在启动时说清楚，避免用户盯着"--"猜
    g = mon.slow.gpu
    if g.available:
        name = (g.sample().get("gpus") or [{}])[0].get("name") or (
            "unknown" if lang == "en" else "未知")
        log.info(say("gpu_ok" if g.vendor == "nvidia" else "gpu_lhm_ok", lang), name)
    else:
        log.info(say("gpu_na", lang), g.reason)
    if not mon.slow.thermal.admin:
        log.warning(say("no_admin", lang))
        log.warning(say("no_admin_hint", lang))

    port = pick_port(args.port)
    Handler.monitor = mon
    Handler.quiet = args.quiet
    httpd = QuietServer(("127.0.0.1", port), Handler)

    url = f"http://127.0.0.1:{port}/"
    log.info(say("started", lang), url)
    log.info(say("stop_hint", lang))

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info(say("stopping", lang))
    finally:
        mon.stop()
        mon.pinger.stop()
        mon.slow.stop()
        httpd.shutdown()
        httpd.server_close()
        log.info(say("stopped", lang))





if __name__ == "__main__":
    main()
