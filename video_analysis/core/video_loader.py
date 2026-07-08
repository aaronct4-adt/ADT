"""
Video loading and frame access.

Handles AVI and common video formats using OpenCV.
Provides frame-by-frame access and metadata.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Generator
from dataclasses import dataclass


@dataclass
class VideoMetadata:
    """Metadata extracted from a video file."""
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_sec: float
    codec: str


class VideoLoader:
    """Load and access video frames."""
    
    def __init__(self, video_path: str):
        self.path = Path(video_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")
        
        self._metadata = self._extract_metadata()
    
    def _extract_metadata(self) -> VideoMetadata:
        """Extract video metadata."""
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0.0
        
        fourcc = int(self._cap.get(cv2.CAP_PROP_FOURCC))
        codec = ''.join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
        
        return VideoMetadata(
            path=str(self.path),
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration_sec=duration,
            codec=codec,
        )
    
    @property
    def metadata(self) -> VideoMetadata:
        """Get video metadata."""
        return self._metadata
    
    @property
    def fps(self) -> float:
        return self._metadata.fps
    
    @property
    def frame_count(self) -> int:
        return self._metadata.frame_count
    
    @property
    def resolution(self) -> Tuple[int, int]:
        return (self._metadata.width, self._metadata.height)
    
    def get_frame(self, frame_idx: int) -> Optional[np.ndarray]:
        """Get a specific frame by index."""
        if frame_idx < 0 or frame_idx >= self._metadata.frame_count:
            return None
        
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self._cap.read()
        return frame if ret else None
    
    def get_timestamp(self, frame_idx: int) -> float:
        """Get timestamp in seconds for a frame index."""
        return frame_idx / self._metadata.fps
    
    def iter_frames(self, start: int = 0, end: Optional[int] = None, 
                    step: int = 1) -> Generator[Tuple[int, float, np.ndarray], None, None]:
        """
        Iterate over frames.
        
        Yields: (frame_index, timestamp_sec, frame_array)
        """
        if end is None:
            end = self._metadata.frame_count
        
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        
        for idx in range(start, end, step):
            if step == 1:
                ret, frame = self._cap.read()
            else:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = self._cap.read()
            
            if not ret:
                break
            
            timestamp = idx / self._metadata.fps
            yield idx, timestamp, frame
    
    def release(self):
        """Release video capture resources."""
        if self._cap is not None:
            self._cap.release()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.release()
    
    def __del__(self):
        self.release()
