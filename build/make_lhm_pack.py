#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_lhm_pack.py —— 把 LibreHardwareMonitor 打成一个可随安装包分发的 zip。

为什么是 zip 而不是散文件：
  IExpress（Windows 自带的安装包工具）会把 CAB 里的子目录静默丢弃，
  只认平级文件。LHM 是几十个文件 + 语言子目录，直接塞进去必然残缺。
  所以打成单个 zip，安装时用 .NET 的 ZipFile 解压——IExpress 只需处理
  一个平级文件，子目录问题就不存在了。

为什么替换掉它的 config：
  LHM 默认**不开** Web Server，而本程序正是通过 127.0.0.1:8085 读它。
  不预置配置的话，用户装完还要自己去菜单里勾选项，等于没装。
  这里生成一份只含必要开关的精简配置，其余交给 LHM 用默认值初始化。
  同时不要分发我们自己的 config——那里面是开发者本机的传感器偏好。
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "installer", "lhm_meta")
STAGING = os.path.join(ROOT, "installer", "staging")
OUT_NAME = "LibreHardwareMonitor.zip"

# 能用环境变量覆盖，方便别人在自己机器上重建这个包
SRC = os.environ.get("LHM_SRC", r"C:\Tools\LibreHardwareMonitor")

# .pdb 是调试符号、.xml 是文档注释、.bak 是旧配置，生产包都不需要
SKIP_SUFFIX = (".pdb", ".xml", ".bak")
# 本机的用户配置与下载来的原始压缩包，绝不能进分发内容
SKIP_NAME = ("lhm.zip", "LibreHardwareMonitor.config")

# LHM 是 WinForms + .NET Framework 4.7.2；这几项在 appSettings 里控制
# "退出时收进托盘""关闭窗口不退出""启动即开 Web Server"。
# 少任何一项，用户都得手工点一次菜单——等于这个可选组件白装。
CONFIG = """\ufeff<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <appSettings>
    <add key="runWebServerMenuItem" value="true" />
    <add key="minCloseMenuItem" value="true" />
    <add key="minTrayMenuItem" value="true" />
  </appSettings>
</configuration>
"""

NOTICE = """LibreHardwareMonitor —— 本目录下的程序并非本软件的一部分
================================================================

来源   : https://github.com/LibreHardwareMonitor/LibreHardwareMonitor
版本   : v0.9.6
许可证 : Mozilla Public License 2.0（全文见同目录 LICENSE）

它的作用是读取硬件传感器（CPU/主板/硬盘/显卡温度），通过本机
http://127.0.0.1:8085/data.json 提供给「系统实时监测」。
「系统实时监测」只做 HTTP 消费，不修改它的任何文件。

为什么要管理员权限：
  LHM 需要加载内核驱动（PawnIO）才能读温度，每次启动都会请求提权。
  这属于改变系统底层的行为，所以做成安装时可选，由使用者自己决定。

不想要它：卸载「系统实时监测」时会连同本目录一起删除；
          也可以在任务管理器结束 LibreHardwareMonitor.exe 后直接删掉本目录。

隐私   : Web Server 只监听 127.0.0.1，不对局域网或外网开放。
"""


def collect(src):
    """收集要打包的文件，返回 [(绝对路径, zip 内相对路径)]"""
    items = []
    for name in sorted(os.listdir(src)):
        full = os.path.join(src, name)
        if name in SKIP_NAME or name.lower().endswith(SKIP_SUFFIX):
            continue
        if os.path.isfile(full):
            items.append((full, name))
        elif os.path.isdir(full):
            # 语言资源目录（zh-CN / de / es …），每个只有十几 KB
            for sub in sorted(os.listdir(full)):
                p = os.path.join(full, sub)
                if os.path.isfile(p):
                    items.append((p, name + "/" + sub))
    return items


def main():
    if not os.path.isfile(os.path.join(SRC, "LibreHardwareMonitor.exe")):
        sys.exit("找不到 %s\\LibreHardwareMonitor.exe\n"
                 "用 LHM_SRC 环境变量指向你的 LibreHardwareMonitor 目录" % SRC)
    if not os.path.isdir(STAGING):
        sys.exit("staging 不存在，先跑 build/build_pack.py 建好 staging")

    items = collect(SRC)
    out = os.path.join(STAGING, OUT_NAME)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for full, rel in items:
            z.write(full, rel)
        z.writestr("LibreHardwareMonitor.config", CONFIG)
        lic = os.path.join(META, "LICENSE")
        if os.path.isfile(lic):
            z.write(lic, "LICENSE")
        else:
            print("  [警告] 缺 %s，分发时许可证不全" % lic)
        z.writestr("来源与许可说明.txt", NOTICE)

    raw = sum(os.path.getsize(f) for f, _ in items)
    size = os.path.getsize(out)
    print("  LHM: %d 个文件，原始 %.1f MB -> 压缩 %.1f MB"
          % (len(items), raw / 1024 / 1024, size / 1024 / 1024))
    print("  载荷: %s" % out)


if __name__ == "__main__":
    main()
