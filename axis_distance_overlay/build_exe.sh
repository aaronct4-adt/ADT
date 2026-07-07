#!/bin/bash
# ============================================================
# Axis Distance Overlay Tool - Build Script (Linux/Mac)
#
# This script builds a standalone executable using PyInstaller.
# Run this on a machine WITH Python and internet access.
# ============================================================

echo "============================================"
echo " Axis Distance Overlay - Build Tool"
echo "============================================"
echo ""

# Check Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Please install Python 3.8+"
    exit 1
fi

echo "[1/3] Installing dependencies..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies."
    exit 1
fi

echo ""
echo "[2/3] Building standalone executable..."
pyinstaller --onefile \
    --windowed \
    --name "AxisDistanceOverlay" \
    --add-data "config.json:." \
    --hidden-import=numpy \
    --hidden-import=cv2 \
    --hidden-import=PIL \
    --hidden-import=requests \
    distance_overlay.py

if [ $? -ne 0 ]; then
    echo "ERROR: PyInstaller build failed."
    exit 1
fi

echo ""
echo "[3/3] Build complete!"
echo ""
echo "============================================"
echo " OUTPUT: dist/AxisDistanceOverlay"
echo "============================================"
echo ""
echo "Transfer these files to the target computer:"
echo "  1. dist/AxisDistanceOverlay"
echo "  2. config.json (place next to the executable)"
echo ""
echo "The config.json is optional - defaults are built in."
echo "============================================"
