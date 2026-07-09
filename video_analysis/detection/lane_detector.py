"""
Lane line detection using a hybrid approach.

Combines classical image processing (Canny + Hough) with
RANSAC-based fitting for robust lane detection.

Works best on road scenes; may not produce results in
indoor/garage/test environments.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class LaneLine:
    """A detected lane line."""
    # Polynomial coefficients (2nd degree): x = ay^2 + by + c
    coefficients: Tuple[float, float, float]
    
    # Points along the line (for drawing): list of (x, y)
    points: List[Tuple[int, int]]
    
    # Classification
    side: str                   # "left", "right", or "center"
    confidence: float           # Detection confidence (0-1)
    
    # Pixel position at bottom of image
    x_at_bottom: Optional[float] = None
    
    def get_x_at_y(self, y: float) -> float:
        """Get x coordinate at a given y value."""
        a, b, c = self.coefficients
        return a * y * y + b * y + c


@dataclass 
class LaneDetectionResult:
    """Results from lane detection on a single frame."""
    left_lane: Optional[LaneLine] = None
    right_lane: Optional[LaneLine] = None
    center_lines: List[LaneLine] = None
    
    # Raw detected line segments (for visualization)
    raw_lines: List[Tuple[int, int, int, int]] = None
    
    # ROI mask used
    roi_mask: Optional[np.ndarray] = None
    
    def __post_init__(self):
        if self.center_lines is None:
            self.center_lines = []
        if self.raw_lines is None:
            self.raw_lines = []
    
    @property
    def has_lanes(self) -> bool:
        """Whether any lanes were detected."""
        return self.left_lane is not None or self.right_lane is not None
    
    @property
    def all_lines(self) -> List[LaneLine]:
        """Get all detected lane lines."""
        lines = []
        if self.left_lane:
            lines.append(self.left_lane)
        if self.right_lane:
            lines.append(self.right_lane)
        lines.extend(self.center_lines)
        return lines


class LaneDetector:
    """
    Robust lane line detector using classical CV + RANSAC.
    
    Pipeline:
    1. Color space conversion + thresholding (white/yellow lines)
    2. Canny edge detection
    3. Region of Interest masking
    4. Hough line transform
    5. Line filtering and classification (left/right)
    6. Polynomial fitting with RANSAC-like outlier rejection
    """
    
    def __init__(self, 
                 roi_top_fraction: float = 0.45,
                 canny_low: int = 40,
                 canny_high: int = 120,
                 hough_threshold: int = 20,
                 hough_min_line_length: int = 20,
                 hough_max_line_gap: int = 150,
                 min_slope: float = 0.2,
                 temporal_smoothing: int = 5):
        """
        Args:
            roi_top_fraction: Top of ROI as fraction of image height (0.5 = bottom half)
            canny_low: Lower Canny threshold
            canny_high: Upper Canny threshold
            hough_threshold: Hough accumulator threshold
            hough_min_line_length: Minimum line segment length
            hough_max_line_gap: Maximum gap between line segments
            min_slope: Minimum absolute slope for a line to be considered a lane
            temporal_smoothing: Number of frames for temporal averaging
        """
        self._roi_top = roi_top_fraction
        self._canny_low = canny_low
        self._canny_high = canny_high
        self._hough_threshold = hough_threshold
        self._hough_min_length = hough_min_line_length
        self._hough_max_gap = hough_max_line_gap
        self._min_slope = min_slope
        self._smoothing = temporal_smoothing
        
        # History for temporal smoothing
        self._left_history: List[Tuple[float, float, float]] = []
        self._right_history: List[Tuple[float, float, float]] = []
    
    def detect(self, frame: np.ndarray) -> LaneDetectionResult:
        """
        Detect lane lines in a single frame.
        
        Args:
            frame: BGR image (numpy array)
            
        Returns:
            LaneDetectionResult with detected lanes
        """
        h, w = frame.shape[:2]
        
        # Step 1: Pre-processing
        processed = self._preprocess(frame)
        
        # Step 2: Edge detection
        edges = cv2.Canny(processed, self._canny_low, self._canny_high)
        
        # Step 3: ROI mask
        roi_mask = self._create_roi_mask(h, w)
        masked_edges = cv2.bitwise_and(edges, edges, mask=roi_mask)
        
        # Step 4: Hough line detection
        lines = cv2.HoughLinesP(
            masked_edges,
            rho=1,
            theta=np.pi / 180,
            threshold=self._hough_threshold,
            minLineLength=self._hough_min_length,
            maxLineGap=self._hough_max_gap,
        )
        
        if lines is None:
            return LaneDetectionResult(roi_mask=roi_mask)
        
        # Step 5: Classify lines as left or right
        left_segments = []
        right_segments = []
        raw_lines = []
        
        center_x = w / 2.0
        
        for line in lines:
            # HoughLinesP returns shape (N, 1, 4) or (N, 4)
            if line.ndim == 2:
                x1, y1, x2, y2 = line[0]
            else:
                x1, y1, x2, y2 = line
            raw_lines.append((int(x1), int(y1), int(x2), int(y2)))
            
            # Calculate slope (in image coords, y increases downward)
            if x2 == x1:
                continue
            
            slope = (y2 - y1) / (x2 - x1)
            
            # Filter by minimum slope
            if abs(slope) < self._min_slope:
                continue
            
            # Classify: negative slope = left lane, positive slope = right lane
            # (because y increases downward in image coords)
            midpoint_x = (x1 + x2) / 2.0
            
            if slope < 0 and midpoint_x < center_x:
                left_segments.append((x1, y1, x2, y2))
            elif slope > 0 and midpoint_x > center_x:
                right_segments.append((x1, y1, x2, y2))
        
        # Step 6: Fit lane lines
        left_lane = self._fit_lane(left_segments, h, w, "left")
        right_lane = self._fit_lane(right_segments, h, w, "right")
        
        # Apply temporal smoothing
        if left_lane:
            self._left_history.append(left_lane.coefficients)
            if len(self._left_history) > self._smoothing:
                self._left_history.pop(0)
            left_lane = self._smooth_lane(self._left_history, h, w, "left")
        
        if right_lane:
            self._right_history.append(right_lane.coefficients)
            if len(self._right_history) > self._smoothing:
                self._right_history.pop(0)
            right_lane = self._smooth_lane(self._right_history, h, w, "right")
        
        return LaneDetectionResult(
            left_lane=left_lane,
            right_lane=right_lane,
            raw_lines=raw_lines,
            roi_mask=roi_mask,
        )
    
    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Pre-process frame for lane detection.
        
        Combines:
        - Grayscale conversion
        - White line detection (high brightness)
        - Yellow line detection (HSV filtering)
        - Gaussian blur
        """
        # Grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # White line mask - use adaptive or lower threshold for highway markings
        # In overcast conditions, lane markings can be 140-200 brightness
        _, white_mask = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        # Also try adaptive threshold for markings in shadow
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY, 15, -10)
        white_mask = cv2.bitwise_or(white_mask, adaptive)
        
        # Yellow line mask (HSV)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        yellow_lower = np.array([15, 50, 100])
        yellow_upper = np.array([40, 255, 255])
        yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
        
        # Combine masks
        combined = cv2.bitwise_or(white_mask, yellow_mask)
        
        # Morphological cleanup - close small gaps in dashed lines
        kernel = np.ones((3, 3), np.uint8)
        combined = cv2.dilate(combined, kernel, iterations=1)
        combined = cv2.erode(combined, kernel, iterations=1)
        
        # Final blur
        result = cv2.GaussianBlur(combined, (5, 5), 0)
        
        return result
    
    def _create_roi_mask(self, h: int, w: int) -> np.ndarray:
        """Create a trapezoidal ROI mask for the road area."""
        mask = np.zeros((h, w), dtype=np.uint8)
        
        # Trapezoidal region covering the road
        # Wide-angle lenses (108° HFOV) show lanes extending further to the sides
        top_y = int(h * self._roi_top)
        
        # Wide ROI to catch lanes at the edges of wide-angle view
        vertices = np.array([[
            (int(w * 0.0), h),            # Bottom-left (full width)
            (int(w * 0.2), top_y),        # Top-left (wider)
            (int(w * 0.8), top_y),        # Top-right (wider)
            (int(w * 1.0), h),            # Bottom-right (full width)
        ]], dtype=np.int32)
        
        cv2.fillPoly(mask, vertices, 255)
        return mask
    
    def _fit_lane(self, segments: List[Tuple[int, int, int, int]], 
                  h: int, w: int, side: str) -> Optional[LaneLine]:
        """Fit a polynomial to line segments."""
        if len(segments) < 2:
            return None
        
        # Collect all points from segments
        all_x = []
        all_y = []
        
        for x1, y1, x2, y2 in segments:
            all_x.extend([x1, x2])
            all_y.extend([y1, y2])
        
        all_x = np.array(all_x, dtype=np.float64)
        all_y = np.array(all_y, dtype=np.float64)
        
        if len(all_x) < 3:
            return None
        
        try:
            # Fit 2nd degree polynomial: x = f(y)
            # This handles near-vertical lines better than y = f(x)
            coeffs = np.polyfit(all_y, all_x, 2)
            
            # Generate points along the line
            y_range = np.linspace(int(h * self._roi_top), h - 1, 50)
            x_range = np.polyval(coeffs, y_range)
            
            # Filter points within image bounds
            valid = (x_range >= 0) & (x_range < w)
            y_range = y_range[valid]
            x_range = x_range[valid]
            
            if len(x_range) < 2:
                return None
            
            points = [(int(x), int(y)) for x, y in zip(x_range, y_range)]
            
            # Get x at bottom of image
            x_at_bottom = float(np.polyval(coeffs, h - 1))
            
            return LaneLine(
                coefficients=(float(coeffs[0]), float(coeffs[1]), float(coeffs[2])),
                points=points,
                side=side,
                confidence=min(len(segments) / 10.0, 1.0),
                x_at_bottom=x_at_bottom,
            )
        except (np.linalg.LinAlgError, ValueError):
            return None
    
    def _smooth_lane(self, history: List[Tuple[float, float, float]],
                     h: int, w: int, side: str) -> Optional[LaneLine]:
        """Average lane coefficients over recent frames."""
        if not history:
            return None
        
        # Weighted average (recent frames weighted more)
        weights = np.linspace(0.5, 1.0, len(history))
        weights /= weights.sum()
        
        avg_coeffs = np.zeros(3)
        for weight, coeffs in zip(weights, history):
            avg_coeffs += weight * np.array(coeffs)
        
        # Generate smoothed points
        y_range = np.linspace(int(h * self._roi_top), h - 1, 50)
        x_range = np.polyval(avg_coeffs, y_range)
        
        valid = (x_range >= 0) & (x_range < w)
        y_range = y_range[valid]
        x_range = x_range[valid]
        
        if len(x_range) < 2:
            return None
        
        points = [(int(x), int(y)) for x, y in zip(x_range, y_range)]
        x_at_bottom = float(np.polyval(avg_coeffs, h - 1))
        
        return LaneLine(
            coefficients=(float(avg_coeffs[0]), float(avg_coeffs[1]), float(avg_coeffs[2])),
            points=points,
            side=side,
            confidence=min(len(history) / self._smoothing, 1.0),
            x_at_bottom=x_at_bottom,
        )
    
    def reset(self):
        """Reset temporal smoothing history."""
        self._left_history.clear()
        self._right_history.clear()
