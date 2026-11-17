@echo off
chcp 936 >nul 2>&1
setlocal
title 系统实时监测 安装程序

rem ===================================================================
rem  安装脚本：由 IExpress 自解压包在 %TEMP%\IXPxxx.TMP 里调起
rem
rem  为什么打包成"单文件 exe + 平级脚本 + 一个 zip"，而不用带子目录的结构：
rem  IExpress 是 Win9x 时代的工具，CAB 里的子目录条目会被静默丢弃——
rem  实测只解出脚本，程序目录整个不见。所以主程序是单文件 exe，
rem  温度组件（几十个文件 + 语言子目录）压成一个 zip，安装时再展开。
rem
rem  其余设计要点：
rem   1) 装到 %LOCALAPPDATA%\Programs，不需要管理员权限，不弹 UAC
rem   2) 温度组件是可选的：它要装内核驱动、要管理员，由使用者自己决定
rem   3) 快捷方式用 WScript.Shell 创建；中文路径只走环境变量，不进命令行
rem   4) 代码行保持纯 ASCII，中文只在 echo 提示里
rem   5) 每步写日志到 %TEMP%\SysMon_install.log
rem ===================================================================

set "APPNAME=系统实时监测"
set "VERSION=1.6.0"
set "LOG=%TEMP%\SysMon_install.log"
set "SRC=%~dp0系统实时监测.exe"
set "DEST=%LOCALAPPDATA%\Programs\系统实时监测"
set "EXE=%DEST%\系统实时监测.exe"
set "LHM_ZIP=%~dp0LibreHardwareMonitor.zip"
set "LHM_DIR=%DEST%\LibreHardwareMonitor"
set "LHM_EXE=%LHM_DIR%\LibreHardwareMonitor.exe"
set "LNK_DESK=%USERPROFILE%\Desktop\系统实时监测.lnk"
set "LNK_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\系统实时监测.lnk"
set "LNK_UNINST=%APPDATA%\Microsoft\Windows\Start Menu\Programs\卸载 系统实时监测.lnk"
set "LNK_LHM=%APPDATA%\Microsoft\Windows\Start Menu\Programs\温度组件 LibreHardwareMonitor.lnk"
set "UNINST_KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\SysMon"

echo [%DATE% %TIME%] ===== 安装开始 ===== >"%LOG%"
echo 解包目录: %~dp0 >>"%LOG%"
echo 目标目录: %DEST% >>"%LOG%"

echo.
echo   ==========================================================
echo      系统实时监测  v%VERSION%   安装程序
echo   ==========================================================
echo.
echo      安装位置：%DEST%
echo      权限要求：无需管理员（温度组件除外，见下一步）
echo      网络行为：仅本机 127.0.0.1，不对外、不上传
echo.

if not exist "%SRC%" (
    echo [失败] 找不到 %SRC% >>"%LOG%"
    echo   [错误] 安装包不完整：找不到主程序。
    echo          请重新下载完整的安装包。
    echo.
    pause
    exit /b 1
)
for %%A in ("%SRC%") do echo [1] 主程序存在，大小 %%~zA 字节 >>"%LOG%"

rem 旧实例在跑的话文件会被占用，复制会失败
taskkill /f /im "系统实时监测.exe" >>"%LOG%" 2>&1
if exist "%DEST%" (
    echo   [0/4] 检测到已安装的旧版本，先移除...
    call :stop_lhm
    rd /s /q "%DEST%" >>"%LOG%" 2>&1
)

echo   [1/4] 复制程序...
mkdir "%DEST%" >>"%LOG%" 2>&1
copy /y "%SRC%" "%EXE%" >>"%LOG%" 2>&1
if not exist "%EXE%" (
    echo [失败] 复制后仍无 %EXE% >>"%LOG%"
    echo.
    echo   [错误] 文件复制失败。
    echo          最常见原因：安全软件拦截了写入。
    echo          请把本安装包加入白名单后重试。
    echo          日志：%LOG%
    echo.
    pause
    exit /b 1
)
echo [2] 复制完成 >>"%LOG%"

rem ---------------------------------------------------------------- 可选组件
set "INSTALL_LHM=0"
if not exist "%LHM_ZIP%" goto :skip_prompt

echo.
echo   ------------------------------------------------------------
echo     可选组件：硬件温度读取（LibreHardwareMonitor）
echo   ------------------------------------------------------------
echo     主程序不装它也能用，只是下面这些看不到：
echo       · CPU 温度、主板温度、每块硬盘的温度
echo       · AMD / Intel 显卡的实时温度、占用、显存
echo.
echo     代价：需要一次管理员授权（装内核驱动才能读温度），
echo           常驻内存约 30-60 MB，托盘里多一个图标。
echo     它是第三方开源软件（MPL 2.0），装不装由你决定。
echo.
choice /c YN /n /m "   一并安装温度组件吗？[Y=安装(推荐) / N=跳过] "
if not errorlevel 2 set "INSTALL_LHM=1"

:skip_prompt
if "%INSTALL_LHM%"=="1" (
    call :install_lhm
) else (
    echo   [2/4] 跳过温度组件
)

echo   [3/4] 创建快捷方式...
copy /y "%~dp0uninstall.cmd" "%DEST%\uninstall.cmd" >>"%LOG%" 2>&1
call :mkshort "%LNK_DESK%" "%EXE%"
call :mkshort "%LNK_MENU%" "%EXE%"
call :mkshort "%LNK_UNINST%" "%DEST%\uninstall.cmd"
if exist "%LNK_DESK%" (echo [3] 桌面快捷方式 OK >>"%LOG%") else (echo [3] 桌面快捷方式创建失败 >>"%LOG%")

echo   [4/4] 注册卸载信息（设置 → 应用 里可卸载）...
rem 用 PowerShell 写注册表而不是 reg.exe：少 8 次进程启动，
rem 也不受某些环境对 reg.exe 的程序黑名单影响（被拦时是静默失败，很难发现）。
rem EstimatedSize 按主程序 + 温度组件估算，只影响"应用"列表里的占用显示。
set "REG_NAME=%APPNAME%"
set "REG_VER=%VERSION%"
set "REG_EXE=%EXE%"
set "REG_DEST=%DEST%"
set "REG_UNINST=%DEST%\uninstall.cmd"
set "REG_SIZE=22000"
if "%INSTALL_LHM%"=="0" set "REG_SIZE=11000"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SysMon'; if(-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }; $kv=@{DisplayName=$env:REG_NAME; DisplayVersion=$env:REG_VER; Publisher='SysMon'; DisplayIcon=$env:REG_EXE; InstallLocation=$env:REG_DEST; UninstallString=('\"'+$env:REG_UNINST+'\"'); EstimatedSize=[int]$env:REG_SIZE}; foreach($k in $kv.Keys){ New-ItemProperty -Path $p -Name $k -Value $kv[$k] -Force | Out-Null }; New-ItemProperty -Path $p -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null; New-ItemProperty -Path $p -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null" >>"%LOG%" 2>&1

echo.
echo   ==========================================================
echo      安装完成
echo   ==========================================================
echo.
echo      桌面和开始菜单都有快捷方式，双击即可。
echo      启动后浏览器会自动打开看板。
echo.
echo      窗口关掉 = 监控停止，这是设计如此：程序就活在那个窗口里。
echo      想让它一直跑，最小化窗口即可。
echo.
if "%INSTALL_LHM%"=="1" (
    echo      温度组件已安装。它需要常驻才能读到温度，
    echo      若托盘里没有它的图标，从开始菜单启动一次即可。
) else (
    echo      未安装温度组件：CPU / 主板 / 硬盘温度为"不可用"。
    echo      想补上可以重跑本安装包选 Y，或自行下载 LibreHardwareMonitor。
)
echo.
echo      安装日志：%LOG%
echo.
echo   正在启动...
start "" "%EXE%"
echo [4] 已启动 %EXE% >>"%LOG%"
echo [%DATE% %TIME%] ===== 安装完成 ===== >>"%LOG%"

rem 静默等待 8 秒后自动关窗；timeout 在无输入句柄时会立刻返回，不影响流程
timeout /t 8 >nul 2>&1
exit /b 0

rem -------------------------------------------------------- 安装温度组件
:install_lhm
echo   [2/4] 安装温度组件...
if not exist "%LHM_DIR%" mkdir "%LHM_DIR%" >>"%LOG%" 2>&1

rem Expand-Archive 是逐个文件解，慢；ZipFile.ExtractToDirectory 一次解完
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; [IO.Compression.ZipFile]::ExtractToDirectory($env:LHM_ZIP, $env:LHM_DIR)" >>"%LOG%" 2>&1

if not exist "%LHM_EXE%" (
    echo         [提示] 解压失败，主程序不受影响。日志：%LOG%
    exit /b 0
)
echo         已解压到 %LHM_DIR%
call :mkshort "%LNK_LHM%" "%LHM_EXE%"

rem 已经有 LHM 在跑（用户自己装过）就别再起一个，会抢驱动和端口
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $c=New-Object Net.Sockets.TcpClient('127.0.0.1',8085); $c.Close(); exit 0 } catch { exit 1 }"
if not errorlevel 1 (
    echo         检测到温度服务已在 8085 运行，跳过启动
    exit /b 0
)

echo         正在启动温度组件，会弹一次管理员授权，请点「是」
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:LHM_EXE -WorkingDirectory $env:LHM_DIR -Verb RunAs" >>"%LOG%" 2>&1

rem 等它把 Web Server 拉起来（最多 10 秒）；用户可能在 UAC 上多停一会儿
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 12;$i++){ try { $c=New-Object Net.Sockets.TcpClient('127.0.0.1',8085); $c.Close(); $ok=$true; break } catch { Start-Sleep -Milliseconds 800 } }; if($ok){ exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo         温度服务暂未就绪：可能在 UAC 上点了「否」，或 LHM 还在启动。
    echo         稍后可点开始菜单「温度组件 LibreHardwareMonitor」再试。
) else (
    echo         温度服务已在 127.0.0.1:8085 就绪
)
exit /b 0

rem -------------------------------------------------------- 只停自己装的 LHM
:stop_lhm
rem 按路径匹配，不误杀用户自己另外安装的 LibreHardwareMonitor
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ps=Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue; foreach($x in $ps){ try { if($x.Path -and $x.Path.StartsWith($env:DEST,[StringComparison]::OrdinalIgnoreCase)){ Stop-Process -Id $x.Id -Force -ErrorAction SilentlyContinue } } catch {} }" >>"%LOG%" 2>&1
exit /b 0

rem ---------------------------------------------------------------- 建快捷方式
:mkshort
if "%~1"=="" exit /b 0
set "SC_LNK=%~1"
set "SC_EXE=%~2"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($env:SC_LNK); $s.TargetPath=$env:SC_EXE; $s.WorkingDirectory=Split-Path $env:SC_EXE; $s.IconLocation=$env:SC_EXE; $s.Description='系统实时监测 - 网络与硬件看板'; $s.Save()" >>"%LOG%" 2>&1
exit /b 0
