"""
Build script for creating a standalone Windows .exe using PyInstaller.

Usage (on a Windows machine with Python installed):

    1. Install build dependencies:
       pip install pyinstaller

    2. Install project dependencies (CPU-only torch for smaller exe):
       pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
       pip install ultralytics opencv-python numpy Pillow scipy

    3. Download the YOLOv8 model:
       python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

    4. Run this build script:
       python build_exe.py

    The output .exe will be in: dist/VehicleDistanceAnalysis/VehicleDistanceAnalysis.exe

Notes:
    - CPU-only PyTorch reduces the exe from ~2GB to ~500MB
    - The build takes 5-10 minutes
    - The output is a folder (not a single file) for faster startup
    - To create a single .exe (slower startup): change --onedir to --onefile
"""

import subprocess
import sys
import os
from pathlib import Path


def build():
    """Run PyInstaller to create the exe."""

    # Ensure yolov8n.pt exists
    model_path = Path("yolov8n.pt")
    if not model_path.exists():
        print("Downloading YOLOv8 model...")
        from ultralytics import YOLO
        YOLO("yolov8n.pt")

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "VehicleDistanceAnalysis",
        "--onedir",
        "--windowed",
        "--noconfirm",

        # Bundle the YOLOv8 model weights
        "--add-data", f"yolov8n.pt{os.pathsep}.",

        # Collect ENTIRE packages (not just hidden imports)
        # This is critical — ultralytics has many submodules and data files
        "--collect-all", "ultralytics",
        "--collect-all", "torch",
        "--collect-all", "torchvision",

        # Hidden imports for standard library / other packages
        "--hidden-import", "scipy",
        "--hidden-import", "scipy.optimize",
        "--hidden-import", "scipy.optimize.linear_sum_assignment",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",

        # Exclude unnecessary modules to reduce size
        "--exclude-module", "matplotlib",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "tensorboard",

        # Entry point
        "run_analysis.py",
    ]

    print("Running PyInstaller...")
    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print()
        print("=" * 60)
        print("BUILD SUCCESSFUL!")
        print("=" * 60)
        print()
        print("Output location:")
        print(f"  dist/VehicleDistanceAnalysis/VehicleDistanceAnalysis.exe")
        print()
        print("To distribute:")
        print("  1. Copy the entire 'dist/VehicleDistanceAnalysis/' folder")
        print("     to the target machine")
        print("  2. Run VehicleDistanceAnalysis.exe")
        print()
        print("No Python installation required on the target machine!")
    else:
        print()
        print("BUILD FAILED. Check the output above for errors.")
        sys.exit(1)


if __name__ == "__main__":
    build()
