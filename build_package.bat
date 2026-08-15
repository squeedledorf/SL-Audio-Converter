@echo off
setlocal
title SL Audio Converter - Build Portable Package
color 0F

echo ============================================
echo  Building portable package
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not on PATH.
    echo Run setup.bat first.
    pause
    exit /b 1
)

python "%~dp0build_package.py"

echo.
pause
