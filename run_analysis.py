#!/usr/bin/env python3
"""
Vehicle Distance Analysis Tool - Launcher Script

Run this script to launch the interactive GUI:
    python run_analysis.py
    python run_analysis.py path/to/video.avi

Requirements: pip install -r requirements.txt
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Explicit imports so PyInstaller can trace these dependencies
# (they are used dynamically in submodules and PyInstaller may miss them)
import ultralytics  # noqa: F401
import torch  # noqa: F401
import torchvision  # noqa: F401
import cv2  # noqa: F401
import numpy  # noqa: F401
import PIL  # noqa: F401
import scipy  # noqa: F401

from video_analysis.ui.app import main

if __name__ == "__main__":
    main()
