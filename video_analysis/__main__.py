"""
Entry point for running the Video Analysis Tool.

Usage:
    python -m video_analysis
    python -m video_analysis path/to/video.avi
"""

import sys
from .ui.app import VideoAnalysisApp


def main():
    app = VideoAnalysisApp()
    
    # If a video path was provided as argument, load it
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        app.root.after(100, lambda: app._load_video(video_path))
    
    app.run()


if __name__ == "__main__":
    main()
