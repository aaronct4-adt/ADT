"""
Camera model for distance estimation.

Supports the Axis F2015-RE (3.1mm, 108° HFOV, 58° VFOV) and custom cameras.
Handles pixel-to-world coordinate transformations for distance computation.
"""

import math
import numpy as np
from typing import Tuple, Optional
from .config import CameraConfig


class CameraModel:
    """
    Pinhole camera model with wide-angle correction.
    
    Converts pixel coordinates to real-world distance estimates using:
    - Known object width method (lateral distance from apparent size)
    - Ground plane intersection (longitudinal distance from bbox bottom)
    - Lane offset computation
    """
    
    def __init__(self, config: CameraConfig):
        self.config = config
        self._fx = config.focal_length_px
        self._fy = config.focal_length_py
        self._cx, self._cy = config.principal_point
        self._h = config.mount_height_m
        self._tilt_rad = math.radians(config.tilt_degrees)
        
        # Pre-compute intrinsic matrix
        self._K = np.array([
            [self._fx, 0, self._cx],
            [0, self._fy, self._cy],
            [0, 0, 1]
        ], dtype=np.float64)
    
    @property
    def intrinsic_matrix(self) -> np.ndarray:
        """3x3 camera intrinsic matrix."""
        return self._K.copy()
    
    @property
    def focal_px(self) -> Tuple[float, float]:
        """Focal length in pixels (fx, fy)."""
        return (self._fx, self._fy)
    
    @property
    def principal_point(self) -> Tuple[float, float]:
        """Principal point (cx, cy)."""
        return (self._cx, self._cy)
    
    def distance_from_width(self, bbox_width_px: float, 
                            real_width_m: float) -> float:
        """
        Estimate distance to an object using known width.
        
        Uses: distance = (real_width * focal_length) / apparent_width_pixels
        
        For wide-angle lenses, applies correction for objects away from center.
        
        Args:
            bbox_width_px: Width of the bounding box in pixels
            real_width_m: Known real-world width of the object in meters
            
        Returns:
            Estimated distance in meters
        """
        if bbox_width_px <= 0:
            return float('inf')
        
        # Basic pinhole distance
        distance = (real_width_m * self._fx) / bbox_width_px
        
        return distance
    
    def distance_from_ground_plane(self, bbox_bottom_y: float) -> float:
        """
        Estimate distance using ground plane intersection.
        
        Assumes flat road. Uses the bottom of the bounding box (where
        the vehicle touches the ground) to estimate longitudinal distance.
        
        Args:
            bbox_bottom_y: Y pixel coordinate of the bottom of the bbox
            
        Returns:
            Estimated distance in meters (along ground plane)
        """
        # Angle from optical axis to bottom of bbox
        # Positive angle = below horizon
        pixel_offset = bbox_bottom_y - self._cy
        angle_from_center = math.atan2(pixel_offset, self._fy)
        
        # Total angle below horizontal (including camera tilt)
        angle_below_horizontal = angle_from_center + self._tilt_rad
        
        if angle_below_horizontal <= 0:
            # Object is at or above horizon - can't estimate distance
            return float('inf')
        
        # Distance on ground plane
        distance = self._h / math.tan(angle_below_horizontal)
        
        return max(distance, 0.0)
    
    def lateral_offset_px_to_m(self, pixel_offset_from_center: float,
                                distance_m: float) -> float:
        """
        Convert a horizontal pixel offset to meters at a given distance.
        
        Args:
            pixel_offset_from_center: Pixels from image center (positive = right)
            distance_m: Distance to the point in meters
            
        Returns:
            Lateral offset in meters
        """
        if distance_m <= 0:
            return 0.0
        return (pixel_offset_from_center * distance_m) / self._fx
    
    def bbox_center_offset(self, bbox: Tuple[int, int, int, int]) -> float:
        """
        Get horizontal pixel offset of bbox center from image center.
        
        Args:
            bbox: (x1, y1, x2, y2) bounding box
            
        Returns:
            Pixel offset (positive = right of center)
        """
        x1, y1, x2, y2 = bbox
        center_x = (x1 + x2) / 2.0
        return center_x - self._cx
    
    def estimate_vehicle_distance(self, bbox: Tuple[int, int, int, int],
                                   real_width_m: float = 1.8,
                                   method: str = "combined") -> float:
        """
        Estimate distance to a vehicle using the best available method.
        
        Args:
            bbox: (x1, y1, x2, y2) bounding box
            real_width_m: Assumed real width of the vehicle
            method: "width", "ground", or "combined" (average of both)
            
        Returns:
            Distance in meters
        """
        x1, y1, x2, y2 = bbox
        bbox_width = x2 - x1
        bbox_bottom = y2
        
        if method == "width":
            return self.distance_from_width(bbox_width, real_width_m)
        elif method == "ground":
            return self.distance_from_ground_plane(bbox_bottom)
        else:  # combined
            d_width = self.distance_from_width(bbox_width, real_width_m)
            d_ground = self.distance_from_ground_plane(bbox_bottom)
            
            # If one method gives infinity, use the other
            if d_width == float('inf'):
                return d_ground
            if d_ground == float('inf'):
                return d_width
            
            # Weighted average - ground plane is more reliable at close range,
            # width-based is better at longer range
            if d_ground < 30:
                # Close range: trust ground plane more
                return 0.7 * d_ground + 0.3 * d_width
            else:
                # Far range: trust width more
                return 0.4 * d_ground + 0.6 * d_width
    
    def lane_edge_distance(self, lane_x_at_bottom: float, 
                           vehicle_center_x: float,
                           distance_at_bottom_m: float,
                           lane_width_m: float = 3.7) -> float:
        """
        Estimate lateral distance from vehicle to a detected lane line.
        
        Args:
            lane_x_at_bottom: X pixel of lane line at bottom of image
            vehicle_center_x: X pixel of ego vehicle center (typically image center)
            distance_at_bottom_m: Distance at the bottom of the image
            lane_width_m: Assumed lane width in meters
            
        Returns:
            Lateral distance to lane edge in meters
        """
        pixel_offset = lane_x_at_bottom - vehicle_center_x
        return self.lateral_offset_px_to_m(pixel_offset, distance_at_bottom_m)
    
    def pixel_to_ground_point(self, px: float, py: float) -> Optional[Tuple[float, float]]:
        """
        Project a pixel to a point on the ground plane (z=0).
        
        Args:
            px, py: Pixel coordinates
            
        Returns:
            (x_ground, z_ground) in meters where x=lateral, z=forward distance
            or None if the ray doesn't intersect the ground
        """
        # Ray direction in camera frame
        dx = (px - self._cx) / self._fx
        dy = (py - self._cy) / self._fy
        dz = 1.0
        
        # Apply tilt rotation (around X axis)
        cos_t = math.cos(self._tilt_rad)
        sin_t = math.sin(self._tilt_rad)
        
        # Rotated ray direction
        ray_y = dy * cos_t - dz * sin_t
        ray_z = dy * sin_t + dz * cos_t
        ray_x = dx
        
        # Ground plane intersection: camera is at height h
        # Ray: P = [0, h, 0] + t * [ray_x, -ray_y, ray_z]
        # Ground: y = 0 → t = h / ray_y (if ray_y > 0, pointing down)
        if ray_y <= 0:
            return None  # Ray points up, no ground intersection
        
        t = self._h / ray_y
        x_ground = ray_x * t
        z_ground = ray_z * t
        
        return (x_ground, z_ground)
