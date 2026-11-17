#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sysmon.py —— 系统监控扩展：显卡 / 温度 / 硬盘 / 进程排行

设计原则（这条比功能重要）：
  拿不到的数据一律如实返回 None + 原因，绝不编造。
  温度在 Windows 上没有系统级通用接口，各机器差异极大，
  这里做多来源降级，并把"为什么没有"一并告诉用户。

Windows 温度可得性现实：
  - psutil.sensors_temperatures() 在 Windows 版根本不存在（非本机问题，是上游不支持）
  - WMI MSAcpi_ThermalZoneTemperature 需要管理员权限，且部分主板不暴露热区
  - 磁盘温度需 Get-StorageReliabilityCounter + 管理员权限
  - NVIDIA 显卡温度走 nvidia-smi，不需要管理员，最可靠
"""
import csv
import io
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from collections import defaultdict

import psutil

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd, timeout=8.0, prefer="utf-8"):
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=timeout,
                            creationflags=_CREATE_NO_WINDOW)
        raw = cp.stdout
        for enc in (prefer, "utf-8", "gbk", "cp936"):
            try:
                return raw.decode(enc), cp.stderr.decode(enc, "ignore")
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "ignore"), ""
    except Exception:
        return "", ""


def _num(v):
    """nvidia-smi 读不到时返回 '[N/A]' 或 '[Not Supported]'，统一成 None"""
    if v is None:
        return None
    s = str(v).strip()
    if not s or "N/A" in s or "Not Supported" in s:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def is_admin():
    """Windows 下判断是否管理员：温度、磁盘 SMART 都依赖它"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ================================================================ 显卡

_GPU_FIELDS = (
    "name,utilization.gpu,utilization.memory,memory.used,memory.total,"
    "temperature.gpu,power.draw,power.limit,fan.speed,clocks.current.graphics"
)


class GpuMonitor:
    """
    显卡数据按可靠性降级，三个来源依次尝试：

      1. nvidia-smi —— NVIDIA 官方接口，不需提权，字段最全
      2. LibreHardwareMonitor 的 /data.json —— AMD 走 ADL、Intel 走 IGCL，
         能补上温度/占用/显存/功耗/频率
      3. 都没有 —— 如实返回原因，不编数字

    为什么必须加第二条腿：nvidia-smi 只对 NVIDIA 有效。AMD 和 Intel 在
    Windows 上没有同等的公开命令行接口，而 LHM 内部已经封装了 ADL/IGCL，
    直接把它的传感器读出来是成本最低的正确做法。
    """

    def __init__(self, lhm=None):
        self.available = False
        self.reason = ""
        self.vendor = None
        self._lhm = lhm          # 与 ThermalReader 共用同一个 LhmSource 实例
        self._exe = shutil.which("nvidia-smi")
        if self._exe:
            out, _ = _run([self._exe, "--query-gpu=name", "--format=csv,noheader"], timeout=10)
            if out.strip():
                self.available = True
                self.vendor = "nvidia"
                return
        # 没有 nvidia-smi：查一下是 AMD/Intel/NVIDIA(驱动坏)，好给出准确提示
        self._detect_vendor()

    def _detect_vendor(self):
        out, _ = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                       "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                       "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                      timeout=15)
        names = [l.strip() for l in out.splitlines() if l.strip()]
        joined = " ".join(names).lower()
        if "nvidia" in joined:
            self.vendor = "nvidia"
            self.reason = "检测到 NVIDIA 显卡，但找不到 nvidia-smi（请重装显卡驱动）"
        elif "amd" in joined or "radeon" in joined:
            self.vendor = "amd"
            self.reason = "AMD 显卡没有公开的实时利用率接口，需借助 LibreHardwareMonitor"
        elif "intel" in joined:
            self.vendor = "intel"
            self.reason = "Intel 显卡没有公开的实时利用率接口，需借助 LibreHardwareMonitor"
        else:
            self.reason = "未检测到独立显卡"
        # nvidia-smi 在但查询失败（驱动异常）：仍按 NVIDIA 处理，文案才准确
        if self._exe and not self.vendor:
            self.vendor = "nvidia"
        self._names = names

    def sample(self):
        if self._exe:
            r = self._sample_smi()
            if r.get("available"):
                return r
        r = self._sample_lhm()
        if r.get("available"):
            return r
        return {"available": False, "vendor": self.vendor,
                "reason": self._why_unavailable(r.get("reason") or "")}

    def _sample_smi(self):
        out, _ = _run([self._exe,
                       f"--query-gpu={_GPU_FIELDS}",
                       "--format=csv,noheader,nounits"], timeout=8)
        if not out.strip():
            return {"available": False, "reason": "nvidia-smi 返回空（驱动异常或显卡被独占）",
                    "vendor": "nvidia"}
        gpus = []
        try:
            for row in csv.reader(io.StringIO(out.strip())):
                if len(row) < 10:
                    continue
                gpus.append({
                    "name": row[0].strip(),
                    "util_pct": _num(row[1]),
                    "mem_util_pct": _num(row[2]),
                    "mem_used_mb": _num(row[3]),
                    "mem_total_mb": _num(row[4]),
                    "temp_c": _num(row[5]),
                    "power_w": _num(row[6]),
                    "power_limit_w": _num(row[7]),
                    "fan_pct": _num(row[8]),
                    "clock_mhz": _num(row[9]),
                })
        except Exception as e:
            return {"available": False, "reason": f"解析失败: {e}", "vendor": "nvidia"}
        if not gpus:
            return {"available": False, "reason": "无可用 GPU 数据", "vendor": "nvidia"}
        return {"available": True, "vendor": "nvidia", "source": "nvidia-smi", "gpus": gpus}

    def _sample_lhm(self):
        """AMD / Intel（以及驱动坏掉的 NVIDIA）走 LibreHardwareMonitor"""
        if self._lhm is None:
            return {"available": False, "reason": "未接入 LibreHardwareMonitor"}
        data = self._lhm.read()
        gpus = data.get("gpus") or []
        if not gpus:
            return {"available": False,
                    "reason": data.get("reason") or "LibreHardwareMonitor 未上报显卡传感器"}
        return {"available": True, "vendor": self.vendor or "unknown",
                "source": "LibreHardwareMonitor", "gpus": gpus}

    def _why_unavailable(self, sub):
        """把"为什么没有显卡数据"说成人话——要让用户知道下一步该干嘛"""
        if self.vendor == "amd":
            base = ("AMD 显卡的实时数据需要 LibreHardwareMonitor 提供："
                    "安装本程序时勾选温度组件，或单独下载 LHM 并让它常驻运行")
        elif self.vendor == "intel":
            base = ("Intel 核显多数没有独立温度传感器（与 CPU 同一块晶片）；"
                    "Arc 独显需要 LibreHardwareMonitor 提供数据")
        elif self.vendor == "nvidia":
            base = "找不到可用的 nvidia-smi（请重装显卡驱动），LibreHardwareMonitor 也没有在运行"
        else:
            base = "未检测到可用的显卡接口"
        return base + (f"（{sub}）" if sub else "")


# ================================================================ 温度

class LhmSource:
    """
    LibreHardwareMonitor 本地 HTTP 服务（默认 127.0.0.1:8085）。

    为什么走它：Windows 没有通用温度接口，AMD 平台更不暴露 ACPI 热区，
    真正的 CPU 温度只能靠内核驱动读 SMN/MSR。LHM 干的就是这件事，
    它把传感器通过 HTTP 暴露出来，我们只做消费方——不碰驱动、不碰硬件。

    前提：LHM 常驻运行且已勾选「Run web server」。未运行时本类静默降级。
    """

    BASE = "http://127.0.0.1:8085"
    CPU_HINT = ("ryzen", "core i", "cpu", "threadripper", "xeon", "athlon")
    BOARD_HINT = ("mainboard", "motherboard", "board")
    DISK_HINT = ("ssd", "nvme", "hdd", "storage", "drive", "wd ", "samsung",
                 "crucial", "kingston", "seagate", "toshiba", "fanxiang", "aigo")
    # 显卡：ImageURL 是 images_icon/nvidia.png、ati.png(AMD)、intel.png
    GPU_IMG = ("nvidia", "ati", "amd", "intel", "gpu")
    GPU_HINT = ("geforce", "radeon", "graphics", "arc a", "gpu")
    # 数值优先按这些名字取，取不到再退回最大值
    CPU_PREFER = ("core (tctl/tdie)", "cpu package", "core average", "core max", "tctl", "tdie")
    # 这些名字是告警/临界阈值，不是当前读数——混进来会显示成假高温
    NOT_A_READING = re.compile(r"(warning|critical|max\b|min\b|limit)", re.I)

    def __init__(self):
        self.available = None      # None 未探测 / True / False
        self.reason = "尚未探测"
        self._probe_ts = 0.0
        # data.json 是几百 KB 的 JSON，同一轮采样里温度与显卡都会来读，
        # 缓存 0.8 秒可省掉一次重复的 HTTP + 解析
        self._root = None
        self._root_ts = 0.0

    def _probe(self):
        now = time.time()
        if self._root is not None and now - self._root_ts < 0.8:
            return self._root
        try:
            with urllib.request.urlopen(self.BASE + "/data.json", timeout=1.5) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
                self._root, self._root_ts = data, now
                return data
        except Exception as e:
            self.available = False
            self.reason = ("LibreHardwareMonitor 未运行，或未开启 Web Server"
                           f"（{type(e).__name__}）")
            return None

    def _collect(self, node, hw_name, out):
        """递归收集形如 '45.0 °C' 的传感器值（叶子节点的 Children 是空数组，不是 None）"""
        for ch in node.get("Children") or []:
            kids = ch.get("Children") or []
            if kids:
                self._collect(ch, hw_name, out)
                continue
            m = re.search(r"(-?\d+(?:\.\d+)?)\s*°C", ch.get("Value") or "")
            if m:
                out.append((hw_name, ch.get("Text") or "", float(m.group(1))))

    EMPTY = {"cpu": None, "board": None, "disks": {}, "gpus": [], "reason": ""}

    def read(self):
        """返回 {'cpu': {..}|None, 'board': {..}|None, 'disks': {名: 温度}, 'gpus': [..]}"""
        now = time.time()
        # 不可用时 20 秒内不重试，避免每次采样都白等超时
        if self.available is False and now - self._probe_ts < 20:
            return dict(self.EMPTY, reason=self.reason)
        self._probe_ts = now

        root = self._probe()
        if not root:
            return dict(self.EMPTY, reason=self.reason)

        self.available = True
        self.reason = ""
        return self.parse(root)

    def _kind(self, hw):
        """
        判定硬件类型。优先用 ImageURL——LHM 会给出 images_icon/cpu.png、
        mainboard.png、hdd.png 这类图标名，比按型号名猜可靠得多
        （"Gigabyte B550M AORUS" 这种名字里根本没有 board 字样）。
        """
        img = (hw.get("ImageURL") or "").lower()
        name = (hw.get("Text") or "").lower()
        if "cpu" in img or any(k in name for k in self.CPU_HINT):
            return "cpu"
        if "mainboard" in img or "motherboard" in img or any(k in name for k in self.BOARD_HINT):
            return "board"
        if any(k in img for k in ("hdd", "ssd", "storage", "drive")) \
                or any(k in name for k in self.DISK_HINT):
            return "disk"
        # 显卡放最后：前面几条先吃掉 CPU/主板/硬盘，避免 "Intel" 这种词
        # 把 Intel 的 CPU 误判成 GPU
        if any(k in img for k in self.GPU_IMG) \
                or any(k in name for k in self.GPU_HINT):
            return "gpu"
        return ""

    def parse(self, root):
        """
        从 LHM 的 data.json 提取温度。独立成方法，便于脱离 HTTP 单测。

        真实结构（本机实测）：Sensor → 机器名 → 硬件 → 分组 → 传感器，
        比文档里说的多一层机器名，所以按 ImageURL 递归找硬件节点，
        不假设固定层级。

        两个必须过滤的坑：
          - "Warning Temperature 89°C" / "Critical Temperature" 是告警阈值，不是当前温度
          - 有些 USB 桥接盘没有型号名，报 0°C
        """
        found = []
        self._find_hardware(root, found)

        cpu_cands, board_cands, disks, gpus = [], [], {}, []
        for kind, name, sensors, node in found:
            if not name:
                continue                     # 无型号名的设备不显示
            if kind == "board":
                board_cands.extend(sensors)
            elif kind == "disk":
                disks[name] = self._disk_temp(sensors)
            elif kind == "cpu":
                cpu_cands.extend(sensors)
            elif kind == "gpu":
                g = self._gpu_metrics(name, node)
                if g:
                    gpus.append(g)

        cpu = None
        if cpu_cands:
            pick = None
            for _, text, v in cpu_cands:
                if any(p in text.lower() for p in self.CPU_PREFER):
                    pick = (text, v)
                    break
            if pick is None:
                pick = max(((t, v) for _, t, v in cpu_cands), key=lambda x: x[1])
            cpu = {"value": round(pick[1], 1), "unit": "°C",
                   "source": f"LibreHardwareMonitor · {pick[0]}"}

        board = None
        if board_cands:
            _, text, v = max(board_cands, key=lambda x: x[2])
            board = {"value": round(v, 1), "unit": "°C",
                     "source": f"LibreHardwareMonitor · {text}"}

        # 去掉取不到有效温度的盘
        disks = {k: v for k, v in disks.items() if v is not None}
        return {"cpu": cpu, "board": board, "disks": disks, "gpus": gpus, "reason": ""}

    def _find_hardware(self, node, out):
        """递归找出所有硬件节点；命中的节点不再向下分类（子芯片归它所属的板卡）"""
        for ch in node.get("Children") or []:
            kind = self._kind(ch)
            if kind:
                sensors = []
                self._collect(ch, ch.get("Text") or "", sensors)
                out.append((kind, (ch.get("Text") or "").strip(), sensors, ch))
            else:
                self._find_hardware(ch, out)

    # ------------------------------------------------------------ 显卡
    # 三家显卡在 LHM 里的传感器命名各有一套：
    #   NVIDIA  Temperatures/GPU Core、Load/GPU Core、Powers/GPU Package
    #   AMD     Temperatures/GPU Core、Load/GPU Core、Powers/GPU Core（部分型号给 Package）
    #   Intel   Temperatures/GPU Core、Load/D3D 3D、Powers/GPU Power
    # 所以按"分组 + 名称偏好"两级匹配，而不是写死某个名字。

    @staticmethod
    def _num_unit(v):
        """'38.0 °C' -> 38.0；'1302 RPM' -> 1302.0；取不到返回 None"""
        m = re.search(r"(-?\d+(?:\.\d+)?)", v or "")
        return float(m.group(1)) if m else None

    def _leaves_of(self, node, prefix=""):
        """把一个硬件节点下的所有叶子传感器拍平成 [(路径, 原始值字符串)]"""
        out = []
        for ch in node.get("Children") or []:
            label = ch.get("Text") or ""
            kids = ch.get("Children") or []
            if kids:
                out.extend(self._leaves_of(ch, prefix + label + "/"))
            else:
                out.append((prefix + label, ch.get("Value") or ""))
        return out

    def _gpu_metrics(self, name, node):
        leaves = self._leaves_of(node)

        def pick(group, prefer, unit=None, exclude=(), fallback=True):
            """
            fallback=False 表示"名字对不上就宁可空着"。
            显存总量必须这样：Intel 只报 D3D 专用显存用量，没有总量项，
            若允许兜底就会把"已用"当成"总量"，显存条直接显示 100%。
            """
            pool = []
            for path, val in leaves:
                p = path.lower()
                if group and group not in p:
                    continue
                if unit and unit not in val.lower():
                    continue
                if exclude and any(k in p for k in exclude):
                    continue
                if self.NOT_A_READING.search(p):
                    continue
                v = self._num_unit(val)
                if v is None:
                    continue
                pool.append((p, v))
            for key in prefer:
                for p, v in pool:
                    if key in p:
                        return v
            return pool[0][1] if (pool and fallback) else None

        temp = pick("temperature", ("gpu core", "gpu", "core"))
        util = pick("load", ("gpu core", "d3d 3d", "core", "gpu"), unit="%")
        # "GPU Memory Controller" 是显存控制器占用，不是显存占用，要排除
        mem_util = pick("load", ("gpu memory", "memory"), unit="%",
                        exclude=("controller", "bus", "power"))
        mem_used = pick("data", ("gpu memory used", "memory used", "dedicated memory used"),
                        unit="mb", exclude=("free",))
        mem_total = pick("data", ("gpu memory total", "memory total"), unit="mb",
                         fallback=False)
        power = pick("power", ("gpu package", "gpu power", "gpu core"), unit="w")
        clock = pick("clock", ("gpu core", "core"), unit="mhz")
        fan = pick("control", ("gpu fan", "fan"), unit="%")

        # 温度、占用、显存全都没有，说明这个节点不是真显卡（可能是虚拟适配器）
        if temp is None and util is None and mem_used is None:
            return None
        return {
            "name": name,
            "util_pct": util,
            "mem_util_pct": mem_util,
            "mem_used_mb": mem_used,
            "mem_total_mb": mem_total,
            "temp_c": temp,
            "power_w": power,
            "power_limit_w": None,      # LHM 不给 TDP 上限，留空让前端隐藏该项
            "fan_pct": fan,
            "clock_mhz": clock,
            "source": "LibreHardwareMonitor",
        }

    def _disk_temp(self, sensors):
        """一块盘的温度：优先 Composite Temperature，否则取有效读数最大值"""
        usable = [(t, v) for _, t, v in sensors
                  if not self.NOT_A_READING.search(t) and 0 < v < 120]
        if not usable:
            return None
        for name, v in usable:
            if "composite" in name.lower():
                return round(v, 1)
        return round(max(v for _, v in usable), 1)


class ThermalReader:
    """
    多来源降级读取温度。
    返回值结构固定：每一项都是 {value, unit, source} 或 {value: None, reason}
    """

    def __init__(self):
        self.admin = is_admin()
        self.lhm = LhmSource()
        self._cache = None
        self._ts = 0

    def _cpu_temp(self):
        """ACPI 热区。非管理员通常直接失败；部分主板根本不暴露。"""
        ps = (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
            "$z=Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature "
            "-ErrorAction SilentlyContinue;"
            "if($z){$z|ForEach-Object{[math]::Round(($_.CurrentTemperature/10)-273.15,1)}}"
        )
        out, _ = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=12)
        vals = []
        for line in out.splitlines():
            v = _num(line)
            if v is not None and -20 < v < 150:   # 过滤明显异常值
                vals.append(v)
        if not vals:
            reason = ("需要管理员权限运行" if not self.admin
                      else "主板未暴露 ACPI 热区（常见于部分消费级/AMD 平台）")
            return {"value": None, "reason": reason}
        return {"value": round(max(vals), 1), "unit": "°C", "source": "ACPI 热区"}

    def _disk_temps(self):
        """Get-StorageReliabilityCounter 需要管理员；返回 {盘型号: 温度}"""
        ps = (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
            "$d=Get-PhysicalDisk;"
            "$r=$d|Get-StorageReliabilityCounter -ErrorAction SilentlyContinue;"
            "if($r){$r|ForEach-Object{"
            "if($_.Temperature -ne $null -and $_.Temperature -gt 0){"
            "\"$($_.DeviceId)`t$($_.Temperature)`t$($_.Wear)`t$($_.PowerOnHours)\"}}}"
        )
        out, _ = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=15)
        result = {}
        for line in out.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                t = _num(parts[1])
                if t is not None and 0 < t < 120:
                    result[parts[0]] = t
        return result

    def _disk_health(self):
        """健康状态与容量：不需要管理员，始终可读"""
        ps = (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
            "Get-PhysicalDisk|ForEach-Object{"
            "\"$($_.FriendlyName)`t$($_.MediaType)`t$($_.HealthStatus)`t$($_.Size)\"}"
        )
        out, _ = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=15)
        disks = []
        for line in out.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 4:
                size = _num(parts[3])
                disks.append({
                    "name": parts[0],
                    "media": parts[1] or "未知",
                    "health": parts[2] or "未知",
                    "size_gb": round(size / 1024 ** 3) if size else None,
                })
        return disks

    def disk_health(self):
        return self._disk_health()

    def sample(self, force=False):
        """
        整体 15 秒一次即可——温度是慢变量，采太勤没有意义还费资源。
        force=True 用于首帧，不想等缓存过期。
        """
        now = time.time()
        if not force and self._cache and now - self._ts < 15:
            return self._cache

        # 优先 LHM：一次 HTTP 拿到 CPU 封装温度 + 主板 + 每块硬盘，
        # 比逐个跑 PowerShell（每次 1-2 秒）便宜得多
        lhm = self.lhm.read()

        if lhm["cpu"]:
            cpu = lhm["cpu"]
        else:
            cpu = dict(self._cpu_temp())
            if cpu.get("value") is None:
                cpu["reason"] = (cpu.get("reason") or "") + \
                    "；装 LibreHardwareMonitor 并让它常驻运行可解决"

        if lhm["disks"]:
            disks = {k: {"value": v, "unit": "°C"} for k, v in lhm["disks"].items()}
        elif self.admin:
            temps = self._disk_temps()
            disks = ({k: {"value": v, "unit": "°C"} for k, v in temps.items()}
                     if temps else {"_": {"value": None,
                                          "reason": "已提权，但这几块盘未上报温度"}})
        else:
            disks = {"_": {"value": None,
                           "reason": "需要管理员权限，或让 LibreHardwareMonitor 常驻运行"}}

        self._cache = {
            "cpu": cpu,
            "board": lhm["board"],
            "disks": disks,
            "source": "lhm" if lhm["cpu"] else "acpi",
            "reason": lhm.get("reason") or "",
            "admin": self.admin,
            "ts": now,
        }
        self._ts = now
        return self._cache


# ================================================================ 硬盘（容量/IO/健康）

class DiskMonitor:
    def __init__(self):
        self._last_io = None
        self._last_t = None
        self.meta = []          # 物理盘型号/健康，低频刷新
        self._meta_ts = 0
        self.partitions = []    # 分区容量，10 秒刷新
        self._part_ts = 0

    def sample(self, thermal_reader=None):
        now = time.time()
        out = {"read_mbps": 0.0, "write_mbps": 0.0, "partitions": self.partitions,
               "physical": self.meta}

        # IO 速率（每秒）
        try:
            dio = psutil.disk_io_counters(perdisk=False)
            if dio and self._last_io and self._last_t:
                dt = max(now - self._last_t, 0.001)
                out["read_mbps"] = round(max(dio.read_bytes - self._last_io.read_bytes, 0) / dt / 1e6, 2)
                out["write_mbps"] = round(max(dio.write_bytes - self._last_io.write_bytes, 0) / dt / 1e6, 2)
            self._last_io = dio
            self._last_t = now
        except Exception:
            pass

        # 分区容量 10 秒刷一次（磁盘容量变化很慢，没必要每秒查）
        if now - self._part_ts > 10:
            parts = []
            for p in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    parts.append({
                        "device": p.device.rstrip("\\"),
                        "total_gb": round(u.total / 1024 ** 3, 1),
                        "used_gb": round(u.used / 1024 ** 3, 1),
                        "free_gb": round(u.free / 1024 ** 3, 1),
                        "pct": round(u.percent, 1),
                    })
                except Exception:
                    continue
            self.partitions = parts
            self._part_ts = now
            out["partitions"] = parts

        # 物理盘型号/健康 60 秒刷一次
        if now - self._meta_ts > 60 and thermal_reader is not None:
            self.meta = thermal_reader.disk_health()
            self._meta_ts = now
            out["physical"] = self.meta

        return out


# ================================================================ 进程排行

class ProcRanker:
    """
    CPU 占用必须用"两次采样的 CPU 时间差"算，不能直接用 cpu_percent()：
    psutil 的 cpu_percent 把上次调用时间存在 Process 实例上，而 process_iter
    每次返回新实例，导致每次都返回 0.0 —— 这是个非常常见的坑。
    """

    def __init__(self, ncores=None):
        self.ncores = ncores or psutil.cpu_count(logical=True) or 1
        self._prev_cpu = {}     # pid -> 累计 CPU 秒数
        self._last_t = None
        self._cache = {"cpu": [], "mem": [], "ts": 0}

    # 系统伪进程：不是应用，混进排行会把真实应用挤掉
    _SKIP_PIDS = {0, 4}   # 0 = System Idle Process, 4 = System（内核）
    _SKIP_NAMES = {"system idle process", "idle", "系统空闲进程", "system"}

    def sample(self):
        now = time.time()
        dt = (now - self._last_t) if self._last_t else 0.0

        # 按进程名聚合：Chrome/Edge 这类多进程应用必须合并，
        # 否则前 10 名会被同一个浏览器的渲染进程占满，用户看不出是谁在吃资源。
        agg = defaultdict(lambda: {"cpu": 0.0, "mem": 0, "count": 0, "pid": None, "cpu_raw": 0.0})

        total_mem = psutil.virtual_memory().total
        seen = set()
        for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_times"]):
            try:
                pid = p.info["pid"]
                name = p.info["name"] or f"pid-{pid}"
                # System Idle Process 统计的是"空闲时间"，显示成 90% 会把
                # 真正吃 CPU 的应用全部压下去，必须排除
                if pid in self._SKIP_PIDS or name.lower() in self._SKIP_NAMES:
                    continue
                mi = p.info["memory_info"]
                ct = p.info["cpu_times"]
                if mi is None or ct is None:
                    continue
                seen.add(pid)
                total_cpu = ct.user + ct.system

                pct = 0.0
                if dt > 0 and pid in self._prev_cpu:
                    # 归一化到全机百分比（与任务管理器口径一致）
                    pct = max(total_cpu - self._prev_cpu[pid], 0.0) / dt * 100 / self.ncores
                self._prev_cpu[pid] = total_cpu

                key = name.lower()
                a = agg[key]
                a["cpu"] += pct
                a["cpu_raw"] += total_cpu
                a["mem"] += mi.rss
                a["count"] += 1
                if a["pid"] is None:
                    a["pid"] = pid
                a["name"] = name
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, KeyError):
                continue

        # 清理已退出进程的历史，防止字典无限增长
        for pid in list(self._prev_cpu.keys()):
            if pid not in seen:
                self._prev_cpu.pop(pid, None)

        rows = []
        for a in agg.values():
            rows.append({
                "name": a.get("name", "?"),
                "pid": a["pid"],
                "count": a["count"],
                "cpu_pct": round(min(a["cpu"], 100.0 * self.ncores), 1),
                "mem_mb": round(a["mem"] / 1024 ** 2, 1),
                "mem_pct": round(a["mem"] / total_mem * 100, 2) if total_mem else 0,
            })

        self._last_t = now
        self._cache = {
            "cpu": sorted(rows, key=lambda r: r["cpu_pct"], reverse=True)[:10],
            "mem": sorted(rows, key=lambda r: r["mem_mb"], reverse=True)[:10],
            "ts": now,
            "ready": dt > 0,
        }
        return self._cache

    def cached(self):
        return self._cache


# ================================================================ 慢速采样线程

class SlowSampler:
    """
    GPU / 温度 / 进程排行都是"慢指标"或"贵调用"（nvidia-smi ~100ms、
    PowerShell ~800ms、遍历进程 ~30ms），绝不能放进 1 秒主循环，
    否则会把主循环节奏拖垮。这里独立线程 + 各自周期 + 共享缓存。
    """

    def __init__(self):
        self.thermal = ThermalReader()
        # 共用同一个 LhmSource：一次 HTTP 同时供温度和显卡用，省一次往返
        self.gpu = GpuMonitor(lhm=self.thermal.lhm)
        self.disk = DiskMonitor()
        self.procs = ProcRanker()
        self.state = {
            "gpu": None,
            "thermal": None,
            "disk": None,
            "procs": None,
        }
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def snapshot(self):
        with self._lock:
            return dict(self.state)

    def run(self):
        """
        周期是按实测开销定的，不是拍脑袋：
          进程遍历 344ms/次（339 进程 × 约 1ms 的 OpenProcess，Windows 固有开销）
            → 5 秒一次，排行不需要秒级刷新
          磁盘     约 1ms → 2 秒
          nvidia-smi 约 73ms → 2 秒（GPU 利用率变化快，值得这个频率）
          温度     PowerShell 约 800ms → 15 秒（温度是慢变量，内部还有缓存）
        """
        PROC_INTERVAL = 5.0
        last_gpu = last_proc = last_disk = 0.0
        proc_bootstrapped = False
        while not self._stop.is_set():
            now = time.time()
            try:
                if now - last_gpu >= 2.0:
                    g = self.gpu.sample()
                    with self._lock:
                        self.state["gpu"] = g
                    last_gpu = now

                if now - last_proc >= PROC_INTERVAL:
                    p = self.procs.sample()
                    with self._lock:
                        self.state["procs"] = p
                    last_proc = now
                    # 首次只建立 CPU 时间基线，数据全为 0。1 秒后补采一次，
                    # 让用户不用干等 5 秒才看到第一份排行。
                    if not proc_bootstrapped:
                        proc_bootstrapped = True
                        last_proc = now - (PROC_INTERVAL - 1.0)

                if now - last_disk >= 2.0:
                    d = self.disk.sample(self.thermal)
                    with self._lock:
                        self.state["disk"] = d
                    last_disk = now

                # 温度最慢，15 秒一次（内部还有缓存）
                t = self.thermal.sample()
                with self._lock:
                    self.state["thermal"] = t
            except Exception:
                pass
            self._stop.wait(1.0)

    def stop(self):
        self._stop.set()


if __name__ == "__main__":
    s = SlowSampler()
    print("管理员:", is_admin())
    print("GPU 可用:", s.gpu.available, "|", s.gpu.reason or "")
    print("\n--- GPU ---")
    print(json.dumps(s.gpu.sample(), ensure_ascii=False, indent=2))
    print("\n--- 温度 ---")
    print(json.dumps(s.thermal.sample(force=True), ensure_ascii=False, indent=2))
    print("\n--- 磁盘 ---")
    d = s.disk.sample(s.thermal)
    print(json.dumps({"io": [d["read_mbps"], d["write_mbps"]], "parts": d["partitions"]},
                     ensure_ascii=False))
    print("\n--- 进程（首次无 CPU 数据，正常）---")
    s.procs.sample()
    time.sleep(2)
    p = s.procs.sample()
    for r in p["cpu"][:5]:
        print(f"  CPU {r['cpu_pct']:5.1f}%  {r['mem_mb']:8.1f}MB  {r['name']} x{r['count']}")
    print("  --- 内存 ---")
    for r in p["mem"][:5]:
        print(f"  MEM {r['mem_mb']:8.1f}MB  {r['cpu_pct']:5.1f}%  {r['name']} x{r['count']}")
