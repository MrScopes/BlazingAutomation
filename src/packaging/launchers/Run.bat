@echo off
setlocal
cd /d "%~dp0"
set "APP=%~dp0app"
set "PY=%APP%\.venv\Scripts\python.exe"

rem first run, moved folder or damaged install: set everything up (or repair it), then carry on
if exist "%APP%\.setup.json" if exist "%PY%" "%PY%" -c "import sys" >nul 2>&1 && goto launch
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP%\scripts\setup.ps1"
if errorlevel 2 exit /b 0
if errorlevel 1 (pause & exit /b 1)

:launch
rem one line on purpose: it stays safe if an update replaces this file while the menu is open
"%PY%" -u "%APP%\src\launcher.py" %* || pause & exit /b
