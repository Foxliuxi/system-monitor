#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pack.py —— 一键构建：依赖环境 -> 单文件 exe -> 安装包。

为什么用 Python 编排而不是纯批处理：
  产品名是中文（系统实时监测），而 cmd 按 OEM 代码页解析 .bat，
  中文写进批处理里会被字节错位截断（本项目踩过：`if not errorlevel` 被切成
  `rorlevel`）。所以 .bat 只留一行 ASCII 启动器，中文全部活在 Python 里。

用法：双击 build_all.bat，或 `python build/build_pack.py`
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
VENV = os.path.join(BUILD, "venv")
PY = os.path.join(VENV, "Scripts", "python.exe")
APP_NAME = "系统实时监测"
APP_VER = "1.6"
DIST = os.path.join(ROOT, "dist-onefile")
DELIV = os.path.join(ROOT, "deliverables")
MIRROR = ["-i", "https://mirrors.aliyun.com/pypi/simple/",
          "--trusted-host", "mirrors.aliyun.com"]


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd[:6]), "..." if len(cmd) > 6 else "")
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        sys.exit("  [FAIL] 退出码 %d" % r.returncode)
    return r


def ensure_venv():
    if os.path.isfile(PY):
        print("  venv 已存在，跳过安装")
        return
    print("  创建 venv…")
    run([sys.executable, "-m", "venv", VENV])
    print("  安装 psutil + pyinstaller（首次约 20MB，走阿里云镜像）…")
    run([PY, "-m", "pip", "install", "-q", "--default-timeout=60", *MIRROR,
         "psutil", "pyinstaller"])


def build_exe():
    run([PY, os.path.join(BUILD, "make_icon.py")], cwd=ROOT)

    cmd = [os.path.join(VENV, "Scripts", "pyinstaller.exe"),
           "--noconfirm", "--onefile", "--console",
           "--name", APP_NAME,
           "--icon", os.path.join(BUILD, "icon.ico"),
           "--add-data", os.path.join(ROOT, "web") + ";web",
           "--version-file", os.path.join(BUILD, "version.txt"),
           "--distpath", DIST,
           "--workpath", os.path.join(BUILD, "pyi-onefile"),
           "--specpath", BUILD,
           "server.py"]
    log = os.path.join(BUILD, "build_onefile.log")
    with open(log, "wb") as f:
        r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        sys.exit("  [FAIL] PyInstaller 失败，见 %s" % log)
    exe = os.path.join(DIST, APP_NAME + ".exe")
    if not os.path.isfile(exe):
        sys.exit("  [FAIL] 没有产出 exe")
    print("  exe: %s (%.1f MB)" % (exe, os.path.getsize(exe) / 1024 / 1024))


def build_installer():
    staging = os.path.join(ROOT, "installer", "staging")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    shutil.copy2(os.path.join(DIST, APP_NAME + ".exe"), staging)
    # 温度组件必须在 make_payload 之前生成：后者要检查 staging 的完整性
    run([sys.executable, os.path.join(BUILD, "make_lhm_pack.py")], cwd=ROOT)
    run([sys.executable, os.path.join(ROOT, "installer", "make_payload.py")], cwd=ROOT)
    run([sys.executable, os.path.join(ROOT, "installer", "make_iexpress.py")], cwd=ROOT)


def build_portable():
    """
    便携版 zip：一个文件夹，解压即用，不写注册表。

    温度组件这里不展开成散文件，而是把 staging 里那个 zip 的条目
    直接搬进便携版的 LibreHardwareMonitor 子目录——同一份载荷两处复用，
    免得安装包和便携版带了不同版本的 LHM。
    """
    out = os.path.join(DELIV, "%s_v%s_便携版.zip" % (APP_NAME, APP_VER))
    exe = os.path.join(DIST, APP_NAME + ".exe")
    readme = os.path.join(ROOT, "installer", "使用说明.txt")
    lhm_zip = os.path.join(ROOT, "installer", "staging", "LibreHardwareMonitor.zip")
    if not os.path.isfile(exe):
        sys.exit("  [FAIL] 没有 portable 用的 exe")
    if not os.path.isfile(readme):
        sys.exit("  [FAIL] 缺 installer/使用说明.txt")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(exe, APP_NAME + "/" + APP_NAME + ".exe")
        z.write(readme, APP_NAME + "/使用说明.txt")
        if os.path.isfile(lhm_zip):
            with zipfile.ZipFile(lhm_zip) as src:
                for info in src.infolist():
                    z.writestr(APP_NAME + "/LibreHardwareMonitor/" + info.filename,
                               src.read(info))
        else:
            print("  [警告] 没有 LibreHardwareMonitor.zip，便携版不含温度组件")
    print("  便携版: %s (%.1f MB)" % (out, os.path.getsize(out) / 1024 / 1024))


def main():
    print("\n[1/5] 构建环境")
    ensure_venv()
    print("\n[2/5] 生成图标")
    print("\n[3/5] 打包单文件 exe（1-3 分钟）")
    build_exe()
    print("\n[4/5] 生成安装包（含可选温度组件）")
    build_installer()
    print("\n[5/5] 生成便携版 zip")
    build_portable()
    print("\n完成。产物：")
    print("  便携版 exe : %s" % os.path.join(DIST, APP_NAME + ".exe"))
    print("  便携版 zip : %s" % os.path.join(DELIV, "%s_v%s_便携版.zip" % (APP_NAME, APP_VER)))
    print("  安装包     : %s" % os.path.join(ROOT, "installer",
                                             "%s_安装包_v%s.exe" % (APP_NAME, APP_VER)))


if __name__ == "__main__":
    main()
