@echo off
setlocal
title SL Audio Converter - Build EXE
color 0F

echo ============================================
echo  Building SL Audio Converter EXE
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not on PATH.
    echo Run setup.bat first.
    pause
    exit /b 1
)

:: Install PyInstaller if needed
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
    echo.
)

:: Build
echo Building EXE (this may take a minute)...
echo.
pyinstaller --onefile --windowed --name "SL Audio Converter" sl_audio_converter.pyw

echo.
if exist "dist\SL Audio Converter.exe" (
    echo ============================================
    echo  Build successful!
    echo  EXE location: dist\SL Audio Converter.exe
    echo ============================================
    echo.
    echo The app downloads yt-dlp itself on first launch.
    echo.
    echo FFmpeg must be installed and on PATH
    echo (setup.bat handles this).
    echo.
    echo For a portable build that bundles ffmpeg + deno,
    echo run build_package.bat instead.
) else (
    echo [ERROR] Build failed. Check the output above.
)

echo.
pause
