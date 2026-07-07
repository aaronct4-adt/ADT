@echo off
REM ============================================================
REM Axis Distance Overlay Tool - Build Script
REM 
REM This script builds a standalone .exe using PyInstaller.
REM Run this on a machine WITH Python and internet access.
REM The resulting .exe can be transferred to the target computer.
REM ============================================================

echo ============================================
echo  Axis Distance Overlay - Build Tool
echo ============================================
echo.

REM Check Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [2/3] Building standalone executable...
pyinstaller --onefile ^
    --windowed ^
    --name "AxisDistanceOverlay" ^
    --add-data "config.json;." ^
    --hidden-import=numpy ^
    --hidden-import=cv2 ^
    --hidden-import=PIL ^
    --hidden-import=requests ^
    distance_overlay.py

if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Build complete!
echo.
echo ============================================
echo  OUTPUT: dist\AxisDistanceOverlay.exe
echo ============================================
echo.
echo Transfer these files to the target computer:
echo   1. dist\AxisDistanceOverlay.exe
echo   2. config.json (place next to the .exe)
echo.
echo The config.json is optional - defaults are built in.
echo Edit it to change IP addresses, colors, etc.
echo ============================================
pause
