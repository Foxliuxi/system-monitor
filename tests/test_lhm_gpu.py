#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_lhm_gpu.py —— 校验从 LibreHardwareMonitor 的 data.json 解析显卡数据。

为什么要有这个测试：本机只有 NVIDIA，AMD 和 Intel 的传感器命名只能靠
构造样本验证。三家厂商在 LHM 里的分组/名称并不一致，写死某个名字就会
在另一种卡上静默返回空——这正是最难被用户说清楚、也最难远程排查的一类 bug。

跑法：build/venv/Scripts/python.exe tests/test_lhm_gpu.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sysmon import LhmSource  # noqa: E402


def node(text, value="", children=None, img=""):
    return {"Text": text, "Value": value, "ImageURL": img, "Children": children or []}


def wrap(hw):
    """模拟 data.json 的真实层级：Sensor -> 机器名 -> 硬件节点"""
    return {"Text": "Sensor", "Children": [
        {"Text": "DESKTOP-TEST", "Children": [hw]}]}


def amd_gpu():
    return node("AMD Radeon RX 7800 XT", img="images_icon/ati.png", children=[
        node("Temperatures", children=[
            node("GPU Core", "58.0 °C"),
            node("GPU Hot Spot", "71.0 °C"),
            node("GPU Memory", "62.0 °C"),
        ]),
        node("Load", children=[
            node("GPU Core", "43.5 %"),
            node("GPU Memory Controller", "12.0 %"),
            node("GPU Memory", "27.0 %"),
            node("D3D 3D", "41.0 %"),
        ]),
        node("Powers", children=[node("GPU Package", "168.4 W")]),
        node("Clocks", children=[
            node("GPU Core", "2100.0 MHz"),
            node("GPU Memory", "2425.0 MHz"),
        ]),
        node("Data", children=[
            node("GPU Memory Free", "11900.0 MB"),
            node("GPU Memory Used", "4400.0 MB"),
            node("GPU Memory Total", "16384.0 MB"),
        ]),
        node("Controls", children=[node("GPU Fan", "38.0 %")]),
    ])


def intel_gpu():
    return node("Intel(R) Arc(TM) A770 Graphics", img="images_icon/intel.png", children=[
        node("Temperatures", children=[
            node("GPU Core", "49.0 °C"),
        ]),
        node("Load", children=[
            node("D3D 3D", "17.0 %"),
            node("GPU Core", "15.0 %"),
        ]),
        node("Powers", children=[node("GPU Power", "42.0 W")]),
        node("Clocks", children=[node("GPU Core", "2400.0 MHz")]),
        node("Data", children=[
            node("D3D Dedicated Memory Used", "2048.0 MB"),
        ]),
    ])


def cpu_node():
    """混入一个 CPU 节点，确认 GPU 判定不会把它一起算进来"""
    return node("AMD Ryzen 7 7800X3D", img="images_icon/cpu.png", children=[
        node("Temperatures", children=[node("Core (Tctl/Tdie)", "61.0 °C")]),
    ])


def warning_only_gpu():
    """只有告警阈值、没有真实读数的虚拟适配器——不该被当成显卡"""
    return node("Microsoft Basic Display Adapter", img="images_icon/gpu.png", children=[
        node("Temperatures", children=[
            node("GPU Core Warning Temperature", "95.0 °C"),
            node("GPU Core Critical Temperature", "110.0 °C"),
        ]),
    ])


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_amd():
    src = LhmSource()
    out = src.parse(wrap(amd_gpu()))
    assert len(out["gpus"]) == 1, out
    g = out["gpus"][0]
    assert g["name"] == "AMD Radeon RX 7800 XT", g["name"]
    assert g["temp_c"] == 58.0, g["temp_c"]              # 不能取 Hot Spot
    assert g["util_pct"] == 43.5, g["util_pct"]
    assert g["mem_util_pct"] == 27.0, g["mem_util_pct"]  # 不能取 Controller
    assert g["mem_used_mb"] == 4400.0, g["mem_used_mb"]  # 不能取 Free
    assert g["mem_total_mb"] == 16384.0, g["mem_total_mb"]
    assert g["power_w"] == 168.4, g["power_w"]
    assert g["clock_mhz"] == 2100.0, g["clock_mhz"]      # 不能取显存频率
    assert g["fan_pct"] == 38.0, g["fan_pct"]
    assert g["source"] == "LibreHardwareMonitor"


@case
def test_intel():
    src = LhmSource()
    out = src.parse(wrap(intel_gpu()))
    assert len(out["gpus"]) == 1, out
    g = out["gpus"][0]
    assert g["temp_c"] == 49.0, g["temp_c"]
    assert g["util_pct"] == 15.0, g["util_pct"]          # 优先 GPU Core 而非 D3D 3D
    assert g["power_w"] == 42.0, g["power_w"]
    assert g["mem_used_mb"] == 2048.0, g["mem_used_mb"]  # 退回 D3D 专用显存
    assert g["mem_total_mb"] is None, g["mem_total_mb"]


@case
def test_cpu_not_misjudged_as_gpu():
    src = LhmSource()
    root = {"Text": "Sensor", "Children": [{"Text": "PC", "Children": [cpu_node()]}]}
    out = src.parse(root)
    assert out["gpus"] == [], out["gpus"]
    assert out["cpu"] and out["cpu"]["value"] == 61.0, out["cpu"]


@case
def test_warning_only_not_a_gpu():
    src = LhmSource()
    out = src.parse(wrap(warning_only_gpu()))
    assert out["gpus"] == [], out["gpus"]


def main():
    bad = 0
    for fn in CASES:
        try:
            fn()
            print("  [OK]   %s" % fn.__name__)
        except AssertionError as e:
            bad += 1
            print("  [FAIL] %s -> %s" % (fn.__name__, e))
    print("\n%d/%d 通过" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
