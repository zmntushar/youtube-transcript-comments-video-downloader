@echo off
title YouTube Toolkit
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo.
    echo  The app is not set up yet.
    echo  Run install.bat first, then start this file again.
    echo.
    pause
    exit /b 1
)

start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
exit /b 0
