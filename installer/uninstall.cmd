@echo off
chcp 936 >nul 2>&1
setlocal
title 卸载 系统实时监测

set "DEST=%LOCALAPPDATA%\Programs\系统实时监测"
set "LNK_DESK=%USERPROFILE%\Desktop\系统实时监测.lnk"
set "LNK_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\系统实时监测.lnk"
set "LNK_UNINST=%APPDATA%\Microsoft\Windows\Start Menu\Programs\卸载 系统实时监测.lnk"
set "LNK_LHM=%APPDATA%\Microsoft\Windows\Start Menu\Programs\温度组件 LibreHardwareMonitor.lnk"
set "LOG=%TEMP%\SysMon_uninstall.log"

rem 自己在被删除的目录里跑，Windows 不允许删正在使用的文件。
rem 所以先把自己复制到 %TEMP% 再执行，--worker 表示已经在临时目录里。
if /i "%~1"=="--worker" goto :do_remove

echo.
echo   即将卸载「系统实时监测」。
echo   监控数据只存在内存里，没有历史文件，卸载不会丢任何数据。
echo.
choice /c YN /n /m "   确定卸载吗？[Y=是 / N=取消] "
if errorlevel 2 exit /b 0

copy /y "%~f0" "%TEMP%\sysmon_uninstall_worker.cmd" >nul 2>&1
if not exist "%TEMP%\sysmon_uninstall_worker.cmd" (
    echo   [错误] 无法写入临时目录，卸载中止。
    pause
    exit /b 1
)
start "" /min "%TEMP%\sysmon_uninstall_worker.cmd" --worker
exit /b 0

:do_remove
echo [%DATE% %TIME%] ===== 卸载开始 ===== >"%LOG%"

echo.
echo   [1/4] 关闭正在运行的程序...
taskkill /f /im "系统实时监测.exe" >>"%LOG%" 2>&1

rem 温度组件若在跑，它的文件被占用会导致下面 rd 删不干净。
rem 按路径过滤，只杀本程序装的那份，不碰用户自己另外装的 LHM。
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ps=Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue; foreach($x in $ps){ try { if($x.Path -and $x.Path.StartsWith($env:DEST,[StringComparison]::OrdinalIgnoreCase)){ Stop-Process -Id $x.Id -Force -ErrorAction SilentlyContinue } } catch {} }" >>"%LOG%" 2>&1
timeout /t 2 >nul 2>&1

echo   [2/4] 删除快捷方式...
del /f /q "%LNK_DESK%" >>"%LOG%" 2>&1
del /f /q "%LNK_MENU%" >>"%LOG%" 2>&1
del /f /q "%LNK_UNINST%" >>"%LOG%" 2>&1
del /f /q "%LNK_LHM%" >>"%LOG%" 2>&1

echo   [3/4] 移除卸载注册项...
rem 与安装脚本保持一致：用 PowerShell 而不是 reg.exe。
rem reg.exe 在部分环境会被程序黑名单拦截，且失败时不留痕迹。
rem 注册表在 HKCU，普通权限即可删除。
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SysMon'; if (Test-Path $p) { Remove-Item $p -Recurse -Force }" >>"%LOG%" 2>&1

echo   [4/4] 删除程序文件...
rd /s /q "%DEST%" >>"%LOG%" 2>&1
timeout /t 2 >nul 2>&1

if exist "%DEST%" (
    echo.
    echo   [提示] 目录未能完全删除，可能仍被进程占用。
    echo          重启后手动删除即可：%DEST%
    echo.
    pause
) else (
    echo.
    echo   已卸载完成。
    echo.
    echo   说明：温度组件（LibreHardwareMonitor）已随目录一起删除；
    echo         它的内核驱动不会因为删目录而卸载，留在系统里无害，
    echo         也不占用资源，下次任何需要读写传感器的软件还能复用。
    echo.
    timeout /t 6 >nul 2>&1
)

echo [%DATE% %TIME%] ===== 卸载结束 ===== >>"%LOG%"
rem 自删：直接 del 会报"找不到批处理文件"，因为 cmd 还在读这个脚本。
rem `(goto)` 让 cmd 先关闭脚本句柄，再执行删除，是无副作用的写法。
(goto) 2>nul & del /f /q "%~f0"
exit /b 0
