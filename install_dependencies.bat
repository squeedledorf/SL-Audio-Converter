@echo off
setlocal EnableDelayedExpansion
title SL Audio Converter - Install Dependencies
color 0F

echo ============================================
echo  SL Audio Converter - Install Dependencies
echo ============================================
echo.

:: ---- Check Python ----
echo [1/3] Checking Python...

set "PYTHON_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 (
    python --version >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
        echo       Found Python !PY_VER!
        set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do set "PY_VER=%%v"
        echo       Found Python !PY_VER!
        set "PYTHON_CMD=python3"
    )
)
if not defined PYTHON_CMD (
    echo [ERROR] Python not found. Install from https://www.python.org/downloads/
    echo         Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)
echo.

:: ---- Install pip packages ----
echo [2/3] Installing PyInstaller...
%PYTHON_CMD% -m pip install --upgrade pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)
echo.

:: ---- Check yt-dlp.exe ----
echo [3/3] Checking yt-dlp.exe...
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%yt-dlp.exe" (
    echo       Found yt-dlp.exe
) else (
    echo       Downloading yt-dlp.exe...
    curl -L -o "%SCRIPT_DIR%yt-dlp.exe" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    if !errorlevel! neq 0 (
        echo [WARNING] Failed to download yt-dlp.exe.
        echo           Download manually from https://github.com/yt-dlp/yt-dlp/releases
        echo           and place it in: %SCRIPT_DIR%
    ) else (
        echo       Downloaded yt-dlp.exe
    )
)
echo.

:: ---- Summary ----
echo ============================================
echo  All done! You can now run:
echo    build_exe.bat  - package into an EXE
echo ============================================
echo.
pause
