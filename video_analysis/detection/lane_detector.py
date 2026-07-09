"""
Lane line detection using bird's-eye view perspective transform.

Uses a perspective warp to create a top-down view of the road,
where lane lines appear as vertical features that are much easier
to detect reliably. Then projects the detected lines back to the
original camera view.

Much more robust than direct Hough detection on the perspective view.
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
    Lane detector using bird's-eye view (BEV) perspective transform.
    
    Pipeline:
    1. Define source/destination points for perspective transform
    2. Warp frame to bird's-eye view
    3. Apply color thresholding (white + yellow lines)
    4. Use sliding window or histogram peaks to find lane pixels
    5. Fit polynomial to lane pixels in BEV space
    6. Project fitted lane back to original camera view
    
    This is much more robust than direct Hough line detection because:
    - Lane lines appear vertical in BEV (easy to find)
    - Dashed lines are naturally connected in the vertical direction
    - Curvature is easier to fit in BEV
    """
    
    def __init__(self, temporal_smoothing: int = 5):
        """
        Args:
            temporal_smoothing: Number of frames for temporal averaging
        """
        self._smoothing = temporal_smoothing
        
        # History for temporal smoothing
        self._left_history: List[np.ndarray] = []
        self._right_history: List[np.ndarray] = []
        
        # Perspective transform matrices (computed once per resolution)
        self._M = None
        self._M_inv = None
        self._warp_size = None
        self._src_pts = None
        self._dst_pts = None
        self._last_resolution = None
        
        # User-drawn lane guide points (set via set_lane_guides)
        self._user_left_points: Optional[List[Tuple[int, int]]] = None
        self._user_right_points: Optional[List[Tuple[int, int]]] = None
        self._guides_set = False
    
    def set_lane_guides(self, left_points: List[Tuple[int, int]], 
                        right_points: List[Tuple[int, int]],
                        image_height: int, image_width: int):
        """
        Set user-drawn lane guide points to seed the perspective transform.
        
        The user clicks points along the left and right lane lines.
        These define the source trapezoid for the BEV warp, ensuring
        the perspective transform captures the actual lane region.
        
        Args:
            left_points: List of (x, y) points along the left lane line
                         (at least 2 points, ordered top to bottom)
            right_points: List of (x, y) points along the right lane line
                          (at least 2 points, ordered top to bottom)
            image_height: Frame height
            image_width: Frame width
        """
        self._user_left_points = sorted(left_points, key=lambda p: p[1])
        self._user_right_points = sorted(right_points, key=lambda p: p[1])
        self._guides_set = True
        
        # Recompute perspective transform from user guides
        self._compute_transform_from_guides(image_height, image_width)
    
    def _compute_transform_from_guides(self, h: int, w: int):
        """Compute perspective transform using user-drawn lane guides."""
        left_pts = self._user_left_points
        right_pts = self._user_right_points
        
        if not left_pts or not right_pts:
            return
        
        # Use the topmost and bottommost points from each lane
        # to define the source trapezoid
        left_top = left_pts[0]      # Highest left point (farthest)
        left_bottom = left_pts[-1]  # Lowest left point (nearest)
        right_top = right_pts[0]    # Highest right point (farthest)
        right_bottom = right_pts[-1]  # Lowest right point (nearest)
        
        # Source trapezoid: defined by user's lane points
        src = np.float32([
            [left_bottom[0], left_bottom[1]],    # Bottom-left
            [left_top[0], left_top[1]],          # Top-left
            [right_top[0], right_top[1]],        # Top-right
            [right_bottom[0], right_bottom[1]],  # Bottom-right
        ])
        
        # Destination: parallel lanes in BEV (straight vertical lines)
        margin = w * 0.25
        dst = np.float32([
            [margin, h],         # Bottom-left
            [margin, 0],         # Top-left
            [w - margin, 0],     # Top-right
            [w - margin, h],     # Bottom-right
        ])
        
        self._src_pts = src
        self._dst_pts = dst
        self._M = cv2.getPerspectiveTransform(src, dst)
        self._M_inv = cv2.getPerspectiveTransform(dst, src)
        self._warp_size = (w, h)
        self._last_resolution = (h, w)
    
    @property
    def has_guides(self) -> bool:
        """Whether user lane guides have been set."""
        return self._guides_set
    
    def _setup_perspective(self, h: int, w: int):
        """Compute perspective transform matrices for this resolution."""
        # If user guides are set, don't recompute (they take priority)
        if self._guides_set and self._M is not None:
            return
        
        if self._last_resolution == (h, w):
            return
        
        self._last_resolution = (h, w)
        
        # Default source points (used when no user guides provided)
        # Trapezoidal region on the road for a wide-angle forward camera
        src = np.float32([
            [w * 0.15, h * 0.95],   # Bottom-left
            [w * 0.40, h * 0.55],   # Top-left
            [w * 0.60, h * 0.55],   # Top-right
            [w * 0.85, h * 0.95],   # Bottom-right
        ])
        
        # Destination points: rectangle (bird's eye view)
        dst = np.float32([
            [w * 0.2, h],       # Bottom-left
            [w * 0.2, 0],       # Top-left
            [w * 0.8, 0],       # Top-right
            [w * 0.8, h],       # Bottom-right
        ])
        
        self._src_pts = src
        self._dst_pts = dst
        self._M = cv2.getPerspectiveTransform(src, dst)
        self._M_inv = cv2.getPerspectiveTransform(dst, src)
        self._warp_size = (w, h)
    
    def detect(self, frame: np.ndarray) -> LaneDetectionResult:
        """
        Detect lane lines in a single frame.
        
        Args:
            frame: BGR image (numpy array)
            
        Returns:
            LaneDetectionResult with detected lanes
        """
        h, w = frame.shape[:2]
        self._setup_perspective(h, w)
        
        # Step 1: Create binary mask of lane-like pixels
        binary = self._threshold_frame(frame)
        
        # Step 2: Warp to bird's-eye view
        bev = cv2.warpPerspective(binary, self._M, self._warp_size)
        
        # Step 3: Find lane pixels using histogram + sliding windows
        left_pixels, right_pixels = self._find_lane_pixels(bev)
        
        # Step 4: Fit polynomials to lane pixels (in BEV space)
        left_fit = self._fit_polynomial(left_pixels, h)
        right_fit = self._fit_polynomial(right_pixels, h)
        
        # Step 5: Apply temporal smoothing
        left_fit = self._smooth_fit(left_fit, self._left_history)
        right_fit = self._smooth_fit(right_fit, self._right_history)
        
        # Step 6: Generate lane line points and project back to camera view
        left_lane = self._create_lane_line(left_fit, h, w, "left")
        right_lane = self._create_lane_line(right_fit, h, w, "right")
        
        return LaneDetectionResult(
            left_lane=left_lane,
            right_lane=right_lane,
        )
    
    def _threshold_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Create a binary mask highlighting lane line pixels.
        Uses multiple color spaces for robustness.
        """
        # Convert to different color spaces
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hls = cv2.cvtColor(frame, cv2.COLOR_BGR2HLS)
        
        # White line detection: high lightness in HLS
        l_channel = hls[:, :, 1]
        _, white_mask = cv2.threshold(l_channel, 160, 255, cv2.THRESH_BINARY)
        
        # Also use Sobel gradient on lightness (catches edges of lines)
        sobel_x = cv2.Sobel(l_channel, cv2.CV_64F, 1, 0, ksize=3)
        abs_sobel = np.absolute(sobel_x)
        if abs_sobel.max() > 0:
            scaled_sobel = np.uint8(255 * abs_sobel / abs_sobel.max())
        else:
            scaled_sobel = np.zeros_like(l_channel)
        _, sobel_mask = cv2.threshold(scaled_sobel, 30, 255, cv2.THRESH_BINARY)
        
        # Yellow line detection: saturation channel
        s_channel = hls[:, :, 2]
        _, yellow_mask = cv2.threshold(s_channel, 80, 255, cv2.THRESH_BINARY)
        
        # Combine all masks
        combined = cv2.bitwise_or(white_mask, sobel_mask)
        combined = cv2.bitwise_or(combined, yellow_mask)
        
        return combined
    
    def _find_lane_pixels(self, bev: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Find lane line pixels in the bird's-eye view using
        histogram peak + sliding window approach.
        
        Returns:
            (left_pixels, right_pixels) each as Nx2 arrays of (x, y) coords
        """
        h, w = bev.shape[:2]
        
        # Histogram of bottom half to find lane starting positions
        bottom_half = bev[h // 2:, :]
        histogram = np.sum(bottom_half, axis=0)
        
        midpoint = w // 2
        left_base = np.argmax(histogram[:midpoint])
        right_base = np.argmax(histogram[midpoint:]) + midpoint
        
        # Sliding window parameters
        n_windows = 9
        window_height = h // n_windows
        margin = 50  # Width of window
        min_pixels = 30  # Minimum pixels to recenter window
        
        # Get all nonzero pixel positions
        nonzero = bev.nonzero()
        nonzero_y = nonzero[0]
        nonzero_x = nonzero[1]
        
        # Track window positions
        left_current = left_base
        right_current = right_base
        
        left_lane_inds = []
        right_lane_inds = []
        
        for window in range(n_windows):
            # Window boundaries
            win_y_low = h - (window + 1) * window_height
            win_y_high = h - window * window_height
            
            win_x_left_low = left_current - margin
            win_x_left_high = left_current + margin
            win_x_right_low = right_current - margin
            win_x_right_high = right_current + margin
            
            # Find pixels in window
            good_left = (
                (nonzero_y >= win_y_low) & (nonzero_y < win_y_high) &
                (nonzero_x >= win_x_left_low) & (nonzero_x < win_x_left_high)
            ).nonzero()[0]
            
            good_right = (
                (nonzero_y >= win_y_low) & (nonzero_y < win_y_high) &
                (nonzero_x >= win_x_right_low) & (nonzero_x < win_x_right_high)
            ).nonzero()[0]
            
            left_lane_inds.append(good_left)
            right_lane_inds.append(good_right)
            
            # Recenter window if enough pixels found
            if len(good_left) > min_pixels:
                left_current = int(np.mean(nonzero_x[good_left]))
            if len(good_right) > min_pixels:
                right_current = int(np.mean(nonzero_x[good_right]))
        
        # Concatenate indices
        left_lane_inds = np.concatenate(left_lane_inds) if left_lane_inds else np.array([])
        right_lane_inds = np.concatenate(right_lane_inds) if right_lane_inds else np.array([])
        
        # Extract pixel positions
        if len(left_lane_inds) > 0:
            left_pixels = np.column_stack((nonzero_x[left_lane_inds], 
                                           nonzero_y[left_lane_inds]))
        else:
            left_pixels = np.array([]).reshape(0, 2)
        
        if len(right_lane_inds) > 0:
            right_pixels = np.column_stack((nonzero_x[right_lane_inds], 
                                            nonzero_y[right_lane_inds]))
        else:
            right_pixels = np.array([]).reshape(0, 2)
        
        return left_pixels, right_pixels
    
    def _fit_polynomial(self, pixels: np.ndarray, h: int) -> Optional[np.ndarray]:
        """
        Fit a 2nd-degree polynomial to lane pixels.
        
        Args:
            pixels: Nx2 array of (x, y) pixel positions in BEV
            h: Image height
            
        Returns:
            Polynomial coefficients [a, b, c] for x = a*y^2 + b*y + c
            or None if not enough pixels
        """
        if len(pixels) < 50:
            return None
        
        x = pixels[:, 0]
        y = pixels[:, 1]
        
        try:
            # Fit x = f(y) which handles vertical/near-vertical lines well
            coeffs = np.polyfit(y, x, 2)
            return coeffs
        except (np.linalg.LinAlgError, ValueError):
            return None
    
    def _smooth_fit(self, current_fit: Optional[np.ndarray],
                    history: List[np.ndarray]) -> Optional[np.ndarray]:
        """Apply temporal smoothing to polynomial fit."""
        if current_fit is not None:
            history.append(current_fit)
            if len(history) > self._smoothing:
                history.pop(0)
        
        if not history:
            return None
        
        # Weighted average of recent fits
        weights = np.linspace(0.5, 1.0, len(history))
        weights /= weights.sum()
        
        avg_fit = np.zeros(3)
        for w, fit in zip(weights, history):
            avg_fit += w * fit
        
        return avg_fit
    
    def _create_lane_line(self, fit: Optional[np.ndarray], 
                          h: int, w: int, side: str) -> Optional[LaneLine]:
        """
        Create a LaneLine from BEV polynomial fit, projected back to camera view.
        Offsets the line to the inside edge of the lane marking.
        """
        if fit is None:
            return None
        
        # Generate points in BEV space
        y_bev = np.linspace(0, h - 1, 40)
        x_bev = fit[0] * y_bev**2 + fit[1] * y_bev + fit[2]
        
        # Offset to inside edge of lane marking
        # Lane markings are typically 10-15cm (4-6 inches) wide.
        # We want to measure from the INSIDE edge (toward driving lane).
        # In BEV space, use a generous offset to get fully past the paint.
        inside_offset_px = 18
        if side == "left":
            x_bev = x_bev + inside_offset_px   # Shift right (toward driving lane)
        elif side == "right":
            x_bev = x_bev - inside_offset_px   # Shift left (toward driving lane)
        
        # Filter points within image bounds
        valid = (x_bev >= 0) & (x_bev < w)
        x_bev = x_bev[valid]
        y_bev = y_bev[valid]
        
        if len(x_bev) < 2:
            return None
        
        # Project BEV points back to camera view
        bev_points = np.float32(np.column_stack((x_bev, y_bev)).reshape(-1, 1, 2))
        camera_points = cv2.perspectiveTransform(bev_points, self._M_inv)
        camera_points = camera_points.reshape(-1, 2)
        
        # Filter camera points within image bounds
        valid_cam = (
            (camera_points[:, 0] >= 0) & (camera_points[:, 0] < w) &
            (camera_points[:, 1] >= 0) & (camera_points[:, 1] < h)
        )
        camera_points = camera_points[valid_cam]
        
        if len(camera_points) < 2:
            return None
        
        points = [(int(p[0]), int(p[1])) for p in camera_points]
        
        # Fit a polynomial in camera space for get_x_at_y functionality
        cam_x = camera_points[:, 0]
        cam_y = camera_points[:, 1]
        
        try:
            cam_coeffs = np.polyfit(cam_y, cam_x, 2)
        except (np.linalg.LinAlgError, ValueError):
            cam_coeffs = np.polyfit(cam_y, cam_x, 1)
            cam_coeffs = np.array([0.0, cam_coeffs[0], cam_coeffs[1]])
        
        x_at_bottom = float(cam_coeffs[0] * (h-1)**2 + cam_coeffs[1] * (h-1) + cam_coeffs[2])
        
        return LaneLine(
            coefficients=(float(cam_coeffs[0]), float(cam_coeffs[1]), float(cam_coeffs[2])),
            points=points,
            side=side,
            confidence=min(len(camera_points) / 20.0, 1.0),
            x_at_bottom=x_at_bottom,
        )
    
    def reset(self):
        """Reset temporal smoothing history."""
        self._left_history.clear()
        self._right_history.clear()
