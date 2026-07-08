"""
Quad-view splitter for multi-camera composite frames.

Splits a 2x2 composite frame (e.g., 1280x720) into 4 individual sub-views.
Handles the standard Axis encoder quad layout.
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional, Dict
from enum import Enum


class QuadPosition(Enum):
    """Position in the 2x2 grid."""
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


# Common view assignments for quad arrangements
VIEW_LABELS = {
    QuadPosition.TOP_LEFT: "View 1 (Top-Left)",
    QuadPosition.TOP_RIGHT: "View 2 (Top-Right)",
    QuadPosition.BOTTOM_LEFT: "View 3 (Bottom-Left)",
    QuadPosition.BOTTOM_RIGHT: "View 4 (Bottom-Right)",
}


class QuadSplitter:
    """
    Split a composite quad-view frame into individual camera views.
    
    Assumes a 2x2 grid layout. Detects the split point automatically
    or uses the frame center.
    """
    
    def __init__(self, frame_width: int = 1280, frame_height: int = 720,
                 auto_detect_borders: bool = True):
        """
        Args:
            frame_width: Full composite frame width
            frame_height: Full composite frame height
            auto_detect_borders: If True, try to detect dividing lines
        """
        self._width = frame_width
        self._height = frame_height
        self._auto_detect = auto_detect_borders
        
        # Default split at center
        self._split_x = frame_width // 2
        self._split_y = frame_height // 2
        
        # Sub-view dimensions
        self._sub_width = self._split_x
        self._sub_height = self._split_y
    
    @property
    def sub_view_size(self) -> Tuple[int, int]:
        """Size of each sub-view (width, height)."""
        return (self._sub_width, self._sub_height)
    
    def detect_borders(self, frame: np.ndarray) -> Tuple[int, int]:
        """
        Try to detect the border/dividing lines in the composite frame.
        
        Looks for vertical and horizontal black lines or transitions.
        Falls back to center split if detection fails.
        
        Returns:
            (split_x, split_y) pixel coordinates
        """
        h, w = frame.shape[:2]
        
        # Check for a vertical dividing line near center
        # Look at a narrow band around the center
        center_x = w // 2
        search_range = 20
        
        min_col_mean = float('inf')
        best_x = center_x
        
        for x in range(center_x - search_range, center_x + search_range):
            col_mean = frame[:, x, :].mean()
            if col_mean < min_col_mean:
                min_col_mean = col_mean
                best_x = x
        
        # Check for horizontal dividing line near center
        center_y = h // 2
        min_row_mean = float('inf')
        best_y = center_y
        
        for y in range(center_y - search_range, center_y + search_range):
            row_mean = frame[y, :, :].mean()
            if row_mean < min_row_mean:
                min_row_mean = row_mean
                best_y = y
        
        self._split_x = best_x
        self._split_y = best_y
        self._sub_width = best_x
        self._sub_height = best_y
        
        return (best_x, best_y)
    
    def split(self, frame: np.ndarray) -> Dict[QuadPosition, np.ndarray]:
        """
        Split a composite frame into 4 sub-views.
        
        Args:
            frame: The full composite frame (HxWx3 BGR)
            
        Returns:
            Dict mapping QuadPosition to the sub-view image array
        """
        sx = self._split_x
        sy = self._split_y
        
        return {
            QuadPosition.TOP_LEFT: frame[0:sy, 0:sx].copy(),
            QuadPosition.TOP_RIGHT: frame[0:sy, sx:self._width].copy(),
            QuadPosition.BOTTOM_LEFT: frame[sy:self._height, 0:sx].copy(),
            QuadPosition.BOTTOM_RIGHT: frame[sy:self._height, sx:self._width].copy(),
        }
    
    def get_quadrant(self, frame: np.ndarray, 
                     position: QuadPosition) -> np.ndarray:
        """
        Extract a single quadrant from the composite frame.
        
        Args:
            frame: Full composite frame
            position: Which quadrant to extract
            
        Returns:
            Sub-view image array
        """
        sx = self._split_x
        sy = self._split_y
        
        if position == QuadPosition.TOP_LEFT:
            return frame[0:sy, 0:sx].copy()
        elif position == QuadPosition.TOP_RIGHT:
            return frame[0:sy, sx:self._width].copy()
        elif position == QuadPosition.BOTTOM_LEFT:
            return frame[sy:self._height, 0:sx].copy()
        elif position == QuadPosition.BOTTOM_RIGHT:
            return frame[sy:self._height, sx:self._width].copy()
        else:
            raise ValueError(f"Unknown position: {position}")
    
    def is_view_active(self, sub_frame: np.ndarray, 
                       min_brightness: float = 5.0,
                       min_std: float = 10.0) -> bool:
        """
        Check if a sub-view appears to have an active camera signal.
        
        Identifies black/blank views that should be skipped.
        
        Args:
            sub_frame: The sub-view image
            min_brightness: Minimum mean pixel value to consider active
            min_std: Minimum std dev to consider active (not solid color)
            
        Returns:
            True if the view appears active/valid
        """
        mean_val = sub_frame.mean()
        std_val = sub_frame.std()
        return mean_val > min_brightness and std_val > min_std
    
    def get_active_views(self, frame: np.ndarray) -> Dict[QuadPosition, np.ndarray]:
        """
        Split frame and return only active (non-blank) views.
        
        Args:
            frame: Full composite frame
            
        Returns:
            Dict of only active views
        """
        all_views = self.split(frame)
        return {
            pos: view for pos, view in all_views.items()
            if self.is_view_active(view)
        }
    
    def analyze_views(self, frame: np.ndarray) -> Dict[QuadPosition, dict]:
        """
        Analyze all quadrants and return info about each.
        
        Returns:
            Dict mapping position to info dict with keys:
            - active: bool
            - mean_brightness: float
            - std: float
            - size: (w, h)
        """
        views = self.split(frame)
        info = {}
        
        for pos, view in views.items():
            info[pos] = {
                "active": self.is_view_active(view),
                "mean_brightness": float(view.mean()),
                "std": float(view.std()),
                "size": (view.shape[1], view.shape[0]),
                "label": VIEW_LABELS[pos],
            }
        
        return info
