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
echo    * the PO token provider, required for quality above 360p
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

echo  [1/5] Using Python:
%PY_CMD% --version
echo.

REM ----------------------------------------------------------------
REM  2. Create the virtual environment
REM ----------------------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo  [2/5] Reusing the existing .venv environment.
) else (
    echo  [2/5] Creating the .venv environment...
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
echo  [3/5] Installing Python packages...
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
echo  [4/5] Checking the Windows programs FFmpeg and Deno...
echo.

where winget >nul 2>&1
if errorlevel 1 (
    echo  [!] winget is not available on this PC.
    echo      Install these two manually, then rerun this file:
    echo        FFmpeg  https://www.gyan.dev/ffmpeg/builds/
    echo        Deno    https://deno.com/
    echo.
    goto :potprovider
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

REM ----------------------------------------------------------------
REM  5. PO token provider
REM     YouTube refuses adaptive streams (anything above 360p) without a
REM     GVS PO token. yt-dlp cannot mint one, so we install the bgutil
REM     provider. Its server version must match the pip plugin version.
REM ----------------------------------------------------------------
:potprovider
echo  [5/5] Setting up the PO token provider...
echo.

REM Nested quotes inside for /f are unreliable in cmd, so round-trip the
REM version through a temp file instead.
set "POT_VER="
set "POT_VER_FILE=%TEMP%\yt_toolkit_potver.txt"
del "%POT_VER_FILE%" >nul 2>&1
"%VENV_PY%" -c "import importlib.metadata as m, pathlib, sys; pathlib.Path(sys.argv[1]).write_text(m.version('bgutil-ytdlp-pot-provider'))" "%POT_VER_FILE%" >nul 2>&1
if exist "%POT_VER_FILE%" set /p POT_VER=<"%POT_VER_FILE%"
del "%POT_VER_FILE%" >nul 2>&1

if not defined POT_VER (
    echo  [!] The bgutil plugin is not installed. Skipping.
    echo      Downloads will be limited to 360p.
    goto :done
)

echo  - Plugin version %POT_VER%

if exist "potprovider\node_modules" (
    echo  - Provider already set up.
    goto :done
)

where node >nul 2>&1
if errorlevel 1 (
    echo  [!] Node.js was not found, so the provider cannot be set up.
    echo      Downloads will be limited to 360p.
    echo      Install it with:  winget install OpenJS.NodeJS
    echo      then rerun this file.
    goto :done
)

echo  - Downloading provider %POT_VER%...
REM A zip plus Expand-Archive avoids depending on tar, which may resolve to a
REM GNU build from Git/WSL that cannot handle Windows paths.
REM No pipes or redirects below: cmd would eat them inside the ^ continuation.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "try {" ^
  "  $u='https://codeload.github.com/Brainicism/bgutil-ytdlp-pot-provider/zip/refs/tags/%POT_VER%';" ^
  "  $z=Join-Path $env:TEMP 'bgutil.zip';" ^
  "  $x=Join-Path $env:TEMP 'bgutil_unzip';" ^
  "  Invoke-WebRequest -Uri $u -OutFile $z;" ^
  "  if (Test-Path $x) { Remove-Item -Recurse -Force $x };" ^
  "  Expand-Archive -Path $z -DestinationPath $x -Force;" ^
  "  $src=Join-Path $x 'bgutil-ytdlp-pot-provider-%POT_VER%\server';" ^
  "  if (-not (Test-Path $src)) { throw 'server folder missing in archive' };" ^
  "  if (Test-Path 'potprovider') { Remove-Item -Recurse -Force 'potprovider' };" ^
  "  Move-Item $src 'potprovider';" ^
  "  Remove-Item $z -Force; Remove-Item -Recurse -Force $x;" ^
  "  exit 0" ^
  "} catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo  [!] Could not download the provider. Downloads will be limited to 360p.
    goto :done
)

if not exist "potprovider\package.json" (
    echo  [!] The provider download looks incomplete. Downloads limited to 360p.
    goto :done
)

echo  - Installing provider dependencies...
pushd potprovider
call npm install --omit=dev --no-audit --no-fund
popd

if exist "potprovider\node_modules" (
    echo  - Provider ready.
) else (
    echo  [!] npm install failed. Downloads will be limited to 360p.
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
