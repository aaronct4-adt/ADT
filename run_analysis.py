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

from video_analysis.ui.app import main

if __name__ == "__main__":
    main()
