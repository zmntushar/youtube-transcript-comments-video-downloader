@echo off
setlocal EnableDelayedExpansion
title YouTube Toolkit - Installer
cd /d "%~dp0"

echo.
echo  ===========================================================
echo    YouTube Toolkit - Installer
echo  ===========================================================
echo.
echo  This installs everything the app needs:
echo    * a private Python environment in .venv
echo    * customtkinter, yt-dlp, youtube-transcript-api, pyperclip
echo    * FFmpeg and Deno (via winget)
echo.

REM ----------------------------------------------------------------
REM  1. Locate Python
REM ----------------------------------------------------------------
set "PY_CMD="
py -3 --version >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD (
    python --version >nul 2>&1 && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo  [X] Python was not found on this PC.
    echo.
    echo      Install it from https://www.python.org/downloads/
    echo      and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo  [1/4] Using Python:
%PY_CMD% --version
echo.

REM ----------------------------------------------------------------
REM  2. Create the virtual environment
REM ----------------------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo  [2/4] Reusing the existing .venv environment.
) else (
    echo  [2/4] Creating the .venv environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo.
        echo  [X] Could not create the virtual environment.
        pause
        exit /b 1
    )
)
echo.

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

REM ----------------------------------------------------------------
REM  3. Install the Python packages
REM ----------------------------------------------------------------
echo  [3/4] Installing Python packages...
echo.
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo.
    echo  [X] pip could not be upgraded. Check your internet connection.
    pause
    exit /b 1
)

"%VENV_PY%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [X] Package installation failed. Check your internet connection.
    pause
    exit /b 1
)
echo.

REM ----------------------------------------------------------------
REM  4. Install the Windows programs
REM ----------------------------------------------------------------
echo  [4/4] Checking the Windows programs FFmpeg and Deno...
echo.

where winget >nul 2>&1
if errorlevel 1 (
    echo  [!] winget is not available on this PC.
    echo      Install these two manually, then rerun this file:
    echo        FFmpeg  https://www.gyan.dev/ffmpeg/builds/
    echo        Deno    https://deno.com/
    echo.
    goto :done
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo  - Installing FFmpeg...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --disable-interactivity
) else (
    echo  - FFmpeg is already installed.
)
echo.

where deno >nul 2>&1
if errorlevel 1 (
    echo  - Installing Deno...
    winget install --id DenoLand.Deno -e --accept-source-agreements --accept-package-agreements --disable-interactivity
) else (
    echo  - Deno is already installed.
)
echo.

:done
echo  ===========================================================
echo    Setup finished.
echo.
echo    Start the app by double-clicking:  run.bat
echo.
echo    If a download reports a missing program, sign out and back
echo    in once so Windows picks up the new PATH entries.
echo  ===========================================================
echo.
pause
