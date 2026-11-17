#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_iexpress.py —— 用 Windows 自带的 IExpress 生成"双击即安装"的自解压安装包。

为什么不用 7-Zip SFX：
  7z.sfx / 7zCon.sfx 默认解压到**当前目录**，双击后会在安装包旁边散落 20MB 文件，
  重装还会弹"是否覆盖 install.cmd"。而 IExpress 是系统组件，天然解压到
  %TEMP%\\IXPxxx.TMP 并执行指定命令，用完自己清理，正是安装器该有的行为。

编码：Sed 文件必须是 ANSI，中文 Windows 下即 GBK。存成 UTF-8 会把中文路径变成乱码，
IExpress 直接拒绝或打出坏包。
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.join(HERE, "staging")
TARGET = os.path.join(HERE, "系统实时监测_安装包_v1.6.exe")
SED = os.path.join(HERE, "build.sed")


def collect():
    """收集待打包文件，返回相对路径列表（相对 staging）"""
    out = []
    for root, _, files in os.walk(STAGING):
        for f in files:
            full = os.path.join(root, f)
            out.append(os.path.relpath(full, STAGING))
    return sorted(out)


def build():
    if not os.path.isdir(STAGING):
        sys.exit("staging 目录不存在，先跑打包流程")

    rels = collect()
    if not os.path.isfile(os.path.join(STAGING, "install.cmd")):
        sys.exit("staging 里缺少 install.cmd")

    strings = "\n".join('FILE%d="%s"' % (i, r.replace("/", "\\"))
                        for i, r in enumerate(rels))
    entries = "\n".join("%%FILE%d%%=" % i for i in range(len(rels)))

    sed = """[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName={target}
FriendlyName=系统实时监测 安装程序
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[Strings]
{strings}
[SourceFiles]
SourceFiles0={src}\\
[SourceFiles0]
{entries}
""".format(target=TARGET, strings=strings, src=STAGING, entries=entries)

    io.open(SED, "w", encoding="cp936", newline="\r\n").write(sed)
    print("Sed 已生成，文件数 %d" % len(rels))

    r = subprocess.run([r"C:\Windows\System32\iexpress.exe", "/N", "/Q", SED],
                       capture_output=True, timeout=600)
    print("IExpress 退出码:", r.returncode)
    if r.stdout.strip():
        print(r.stdout.decode("gbk", "ignore")[-800:])

    if not os.path.isfile(TARGET):
        sys.exit("打包失败：没有产出 %s" % TARGET)
    print("产出: %s (%.1f MB)" % (TARGET, os.path.getsize(TARGET) / 1024 / 1024))


if __name__ == "__main__":
    build()
