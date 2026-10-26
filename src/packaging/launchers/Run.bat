@echo off
setlocal
cd /d "%~dp0"
set "APP=%~dp0app"
set "PY=%APP%\.venv\Scripts\python.exe"

rem first run or damaged install: set everything up, then carry on
if exist "%PY%" if exist "%APP%\.setup.json" goto launch
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP%\scripts\setup.ps1"
if errorlevel 2 exit /b 0
if errorlevel 1 (pause & exit /b 1)

:launch
rem one line on purpose: it stays safe if an update replaces this file while the menu is open
"%PY%" -u "%APP%\src\launcher.py" %* || pause & exit /b
