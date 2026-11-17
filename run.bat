@echo off
REM ===========================================================
REM  NetMon launcher
REM  IMPORTANT: keep this file pure ASCII.
REM  cmd.exe parses .bat with the system code page (GBK on zh-CN).
REM  Non-ASCII text here gets byte-shifted and can split lines,
REM  which breaks commands like "if not errorlevel 1".
REM  All Chinese UI text is printed by Python instead.
REM ===========================================================
setlocal
cd /d "%~dp0"
title System Monitor - Real-time
echo.

REM --- find a Python interpreter that already has psutil ---
set "PY="

py -3 -c "import psutil" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto RUN

python -c "import psutil" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto RUN

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -c "import psutil" >nul 2>nul
  if not errorlevel 1 set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
)
if defined PY goto RUN

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -c "import psutil" >nul 2>nul
  if not errorlevel 1 set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if defined PY goto RUN

REM --- python exists but psutil missing: try to install it ---
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto INSTALL

python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto INSTALL

echo   [ERROR] Python not found on this machine.
echo.
echo   Install Python 3.9+ from https://www.python.org/downloads/
echo   and tick "Add Python to PATH" during setup.
echo.
pause
exit /b 1

:INSTALL
echo   [SETUP] Python found, but psutil is missing.
echo   Installing psutil now (requires internet)...
echo.
%PY% -m pip install psutil
if errorlevel 1 (
  echo.
  echo   Install failed. Run this manually:
  echo     %PY% -m pip install psutil
  echo.
  pause
  exit /b 1
)
echo.

:RUN
%PY% server.py %*
if errorlevel 1 (
  echo.
  echo   [EXIT] The program stopped with an error. See message above.
  echo.
  pause
)
endlocal
