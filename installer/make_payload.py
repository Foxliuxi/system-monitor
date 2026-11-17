#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_payload.py —— 把安装脚本转成 cmd 能正确解析的编码，并放进 staging。

为什么必须转编码：
  cmd.exe 按当前代码页逐行读取 .bat/.cmd。脚本里写了 chcp 936，所以文件本身
  必须是 GBK；存成 UTF-8 会被按 GBK 解读，中文乱码之外还可能吃掉引号，
  导致"命令语法不正确"这类莫名其妙的报错（本项目踩过一次）。

为什么源文件保持 UTF-8：
  便于用编辑器/版本管理查看和改动，编码只在打包这一步统一处理。
"""
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.join(HERE, "staging")
SCRIPTS = ("install.cmd", "uninstall.cmd")


def main():
    if not os.path.isdir(STAGING):
        sys.exit("staging 不存在，先构建 exe 并复制进来")

    for name in SCRIPTS:
        src = os.path.join(HERE, name)
        if not os.path.isfile(src):
            sys.exit("缺少源脚本: %s" % name)
        text = io.open(src, encoding="utf-8").read()
        dst = os.path.join(STAGING, name)
        io.open(dst, "w", encoding="cp936", newline="\r\n").write(text)
        print("  %-14s -> GBK, %d 字节" % (name, os.path.getsize(dst)))

    exe = os.path.join(HERE, "..", "dist-onefile", "系统实时监测.exe")
    if not os.path.isfile(os.path.join(STAGING, "系统实时监测.exe")):
        if os.path.isfile(exe):
            shutil.copy2(exe, STAGING)
            print("  已从 dist-onefile 补入主程序")
        else:
            sys.exit("staging 里没有主程序，也没有 dist-onefile 可复制")

    print("  staging 就绪，文件数 %d" % len(os.listdir(STAGING)))


if __name__ == "__main__":
    main()
