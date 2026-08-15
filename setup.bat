@echo off
setlocal EnableDelayedExpansion
title SL Audio Converter - Setup
color 0F

echo ============================================
echo   SL Audio Converter - Setup
echo ============================================
echo.
echo This will install everything needed to run
echo the SL Audio Converter on your system:
echo.
echo   - Python 3 (with tkinter)
echo   - FFmpeg (audio processing)
echo   - yt-dlp (YouTube downloads)
echo.
echo ============================================
echo.
pause

:: ---- Check for admin rights ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Some installs may need admin rights.
    echo     Right-click this script and "Run as administrator"
    echo     if anything fails.
    echo.
)

:: ---- Check for winget ----
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] winget is not available on this system.
    echo.
    echo winget comes built-in with Windows 10 ^(1709+^) and Windows 11.
    echo If you don't have it, install "App Installer" from the Microsoft Store:
    echo   https://aka.ms/getwinget
    echo.
    echo After installing winget, run this script again.
    pause
    exit /b 1
)
echo [OK] winget found.
echo.

:: ============================================
:: PYTHON
:: ============================================
echo --------------------------------------------
echo  Checking Python...
echo --------------------------------------------

set "PYTHON_CMD="

:: Check common names
where python >nul 2>&1
if %errorlevel% equ 0 (
    :: Make sure it's real Python, not the Windows Store stub
    python --version >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
        echo   Found: Python !PY_VER!
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do set "PY_VER=%%v"
        echo   Found: Python !PY_VER!
        set "PYTHON_CMD=python3"
    )
)

if not defined PYTHON_CMD (
    echo   Python not found. Installing via winget...
    echo.
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Python install failed.
        echo   Try installing manually: https://www.python.org/downloads/
        echo   IMPORTANT: Check "Add Python to PATH" during install.
        pause
        exit /b 1
    )
    echo.
    echo   [!] Python was just installed. You may need to restart
    echo       this script for it to be found on PATH.
    echo.
    set "PYTHON_CMD=python"
)

echo [OK] Python is ready.
echo.

:: ---- Verify tkinter ----
echo   Checking tkinter...
%PYTHON_CMD% -c "import tkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] tkinter is not available in your Python install.
    echo   tkinter is included by default with the python.org installer.
    echo   If you installed Python another way, reinstall from:
    echo     https://www.python.org/downloads/
    echo   Make sure "tcl/tk and IDLE" is checked during install.
    echo.
) else (
    echo   [OK] tkinter is available.
)
echo.

:: ============================================
:: FFMPEG
:: ============================================
echo --------------------------------------------
echo  Checking FFmpeg...
echo --------------------------------------------

where ffmpeg >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=3" %%v in ('ffmpeg -version 2^>^&1 ^| findstr /b "ffmpeg version"') do (
        echo   Found: FFmpeg %%v
    )
    echo [OK] FFmpeg is ready.
) else (
    echo   FFmpeg not found. Installing via winget...
    echo.
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] FFmpeg install failed.
        echo   Try installing manually: https://www.gyan.dev/ffmpeg/builds/
        echo   Add the bin folder to your system PATH.
        pause
        exit /b 1
    )
    echo.
    echo [OK] FFmpeg installed.
    echo   [!] You may need to restart this script for ffmpeg
    echo       to be found on PATH.
)
echo.

:: ============================================
:: YT-DLP
:: ============================================
echo --------------------------------------------
echo  Checking yt-dlp...
echo --------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "YTDLP_PATH=%SCRIPT_DIR%yt-dlp.exe"

if exist "%YTDLP_PATH%" (
    echo   Found: yt-dlp.exe in converter folder.
    echo   Updating to latest version...
    echo.
    curl -L -o "%YTDLP_PATH%" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    if !errorlevel! neq 0 (
        echo   [WARNING] Update failed, but existing yt-dlp.exe should still work.
    ) else (
        echo   [OK] yt-dlp.exe updated.
    )
) else (
    echo   Downloading yt-dlp.exe...
    echo.
    curl -L -o "%YTDLP_PATH%" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Failed to download yt-dlp.
        echo   Download manually from: https://github.com/yt-dlp/yt-dlp/releases
        echo   Place yt-dlp.exe in: %SCRIPT_DIR%
        pause
        exit /b 1
    )
    echo   [OK] yt-dlp.exe downloaded.
)
echo.

:: ============================================
:: FINAL VERIFICATION
:: ============================================
echo ============================================
echo  Verification
echo ============================================
echo.

set "ALL_GOOD=1"

:: Python
where python >nul 2>&1 || where python3 >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Python
) else (
    echo   [!!] Python - not found on PATH. Restart terminal and try again.
    set "ALL_GOOD=0"
)

:: FFmpeg
where ffmpeg >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] FFmpeg
) else (
    echo   [!!] FFmpeg - not found on PATH. Restart terminal and try again.
    set "ALL_GOOD=0"
)

:: yt-dlp
if exist "%YTDLP_PATH%" (
    echo   [OK] yt-dlp.exe
) else (
    echo   [!!] yt-dlp.exe - missing from converter folder.
    set "ALL_GOOD=0"
)

:: tkinter
%PYTHON_CMD% -c "import tkinter" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] tkinter
) else (
    echo   [!!] tkinter - not available. Reinstall Python from python.org.
    set "ALL_GOOD=0"
)

echo.
echo ============================================

if "!ALL_GOOD!"=="1" (
    echo  All set! You can now run sl_audio_converter.pyw
    echo.
    echo  Just double-click the .pyw file, or run:
    echo    python sl_audio_converter.pyw
) else (
    echo  Some items need attention (see above).
    echo  If you just installed something, close this
    echo  window and run setup.bat again.
)

echo ============================================
echo.
pause
