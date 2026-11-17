@echo off
rem ASCII-only launcher. All Chinese names live in build_pack.py,
rem because cmd parses .bat with the OEM codepage and would mangle them.
cd /d "%~dp0"
if exist "build\venv\Scripts\python.exe" (
    build\venv\Scripts\python.exe build\build_pack.py
) else (
    python build\build_pack.py
)
if errorlevel 1 pause
