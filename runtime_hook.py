"""
PyInstaller runtime hook for ultralytics.

Ensures ultralytics can find its config/data files when running
from a frozen (packaged) exe.
"""

import os
import sys

# When frozen, set the ultralytics settings dir to a writable location
# next to the exe so it doesn't try to write to a temp folder
if getattr(sys, 'frozen', False):
    exe_dir = os.path.dirname(sys.executable)
    
    # Tell ultralytics where to find/store its settings
    os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(exe_dir, '.ultralytics'))
    
    # Ensure the config dir exists
    config_dir = os.path.join(exe_dir, '.ultralytics')
    os.makedirs(config_dir, exist_ok=True)
