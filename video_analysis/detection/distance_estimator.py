"""
Distance estimation module.

Combines camera model with detection/tracking data to produce
distance measurements:
- Distance to tracked vehicles
- Lateral offset to lane edges
- Temporal smoothing for stable readings
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque

from ..core.camera_model import CameraModel
from ..core.config import DistanceConfig
from .tracker import TrackedObject
from .lane_detector import LaneDetectionResult


@dataclass
class VehicleDistance:
    """Distance measurement for a single vehicle at a point in time."""
    track_id: int
    class_name: str
    distance_m: float               # Longitudinal distance to front of vehicle (ground plane)
    lateral_offset_m: float         # Lateral offset from ego center (positive = right)
    lane_offset_left_m: Optional[float] = None   # Distance from left lane line to vehicle (meters)
    lane_offset_right_m: Optional[float] = None  # Distance from right lane line to vehicle (meters)
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    method: str = "combined"        # "width", "ground", or "combined"


@dataclass
class LaneDistance:
    """Distance measurement to lane edges."""
    left_lane_offset_m: Optional[float] = None    # Distance to left lane (positive = left is to left)
    right_lane_offset_m: Optional[float] = None   # Distance to right lane (positive = right is to right)
    lane_width_m: Optional[float] = None          # Detected lane width


@dataclass
class FrameDistances:
    """All distance measurements for a single frame."""
    frame_idx: int
    timestamp_sec: float
    vehicles: List[VehicleDistance] = field(default_factory=list)
    lane: Optional[LaneDistance] = None


class DistanceEstimator:
    """
    Estimates distances to vehicles and lane edges using camera geometry.
    
    Uses the CameraModel for pixel-to-world transformations and applies
    temporal smoothing for stable distance readouts.
    """
    
    def __init__(self, camera_model: CameraModel, config: DistanceConfig):
        """
        Args:
            camera_model: Configured camera model with intrinsics
            config: Distance estimation configuration
        """
        self._camera = camera_model
        self._config = config
        
        # Temporal smoothing buffers per track_id
        self._distance_history: Dict[int, deque] = {}
        self._smoothing_window = config.temporal_smoothing_frames
    
    def estimate_frame(self, frame_idx: int, timestamp: float,
                       tracks: List[TrackedObject],
                       lane_result: Optional[LaneDetectionResult] = None,
                       image_width: Optional[int] = None) -> FrameDistances:
        """
        Estimate all distances for a single frame.
        
        Args:
            frame_idx: Frame index
            timestamp: Frame timestamp in seconds
            tracks: Currently tracked vehicles
            lane_result: Lane detection results (if available)
            image_width: Image width (for lane offset calculation)
            
        Returns:
            FrameDistances with all measurements
        """
        result = FrameDistances(
            frame_idx=frame_idx,
            timestamp_sec=timestamp,
        )
        
        # Estimate distance to each tracked vehicle
        for track in tracks:
            vd = self._estimate_vehicle_distance(track, lane_result, image_width)
            if vd is not None:
                result.vehicles.append(vd)
        
        # Estimate lane distances (ego vehicle to lane edges)
        if lane_result and lane_result.has_lanes and image_width:
            result.lane = self._estimate_lane_distances(lane_result, image_width)
        
        return result
    
    def _estimate_vehicle_distance(self, track: TrackedObject,
                                     lane_result: Optional[LaneDetectionResult] = None,
                                     image_width: Optional[int] = None) -> Optional[VehicleDistance]:
        """Estimate distance to a single tracked vehicle, including lane offsets."""
        bbox = track.bbox
        x1, y1, x2, y2 = bbox
        
        # Get assumed width based on vehicle class
        real_width = self._get_vehicle_width(track.class_name)
        
        # Estimate distance using camera model (combined method)
        distance = self._camera.estimate_vehicle_distance(
            bbox, real_width_m=real_width, method="combined"
        )
        
        # Clamp to credible range
        if distance < self._config.min_distance_m:
            distance = self._config.min_distance_m
        elif distance > self._config.max_distance_m:
            distance = self._config.max_distance_m
        
        # Apply temporal smoothing
        distance = self._smooth_distance(track.track_id, distance)
        
        # --- FOOTPRINT ESTIMATION ---
        # The YOLO bounding box is an image-space rectangle that includes
        # the full visible vehicle (roof to road, with perspective distortion).
        # For plan-view measurements, we need the vehicle's ROAD-LEVEL footprint.
        #
        # Approach: shrink the YOLO bbox width by 10% on each side.
        # YOLO boxes are typically wider than the actual vehicle body
        # (they include mirrors, shadows, and some background).
        # This gives a better approximation of the vehicle body edges.
        
        bbox_width = x2 - x1
        inset = int(bbox_width * 0.10)
        footprint_left_x = float(x1 + inset)
        footprint_right_x = float(x2 - inset)
        
        # Use the bbox bottom (y2) as the vehicle's road contact point
        footprint_bottom_y = float(y2)
        
        # Calculate lateral offset from ego center (using footprint center)
        center_offset_px = bbox_center_x - self._camera.principal_point[0]
        lateral_offset = self._camera.lateral_offset_px_to_m(
            center_offset_px, distance
        )
        
        # Calculate distance from lane lines to vehicle FOOTPRINT edges
        lane_offset_left = None
        lane_offset_right = None
        
        if lane_result and lane_result.has_lanes:
            # Left lane: distance from lane line to vehicle's LEFT footprint edge
            if lane_result.left_lane:
                lane_x = lane_result.left_lane.get_x_at_y(footprint_bottom_y)
                # Pixel gap: vehicle footprint left edge minus lane line x
                px_diff = footprint_left_x - lane_x
                if px_diff > 0 and distance > 0:
                    lane_offset_left = self._camera.lateral_offset_px_to_m(px_diff, distance)
                    lane_offset_left = round(abs(lane_offset_left), 2)
            
            # Right lane: distance from vehicle's RIGHT footprint edge to lane line
            if lane_result.right_lane:
                lane_x = lane_result.right_lane.get_x_at_y(footprint_bottom_y)
                # Pixel gap: lane line x minus vehicle footprint right edge
                px_diff = lane_x - footprint_right_x
                if px_diff > 0 and distance > 0:
                    lane_offset_right = self._camera.lateral_offset_px_to_m(px_diff, distance)
                    lane_offset_right = round(abs(lane_offset_right), 2)
        
        return VehicleDistance(
            track_id=track.track_id,
            class_name=track.class_name,
            distance_m=round(distance, 2),
            lateral_offset_m=round(lateral_offset, 2),
            lane_offset_left_m=lane_offset_left,
            lane_offset_right_m=lane_offset_right,
            bbox=bbox,
            confidence=track.confidence,
            method="combined",
        )
    
    def _estimate_lane_distances(self, lane_result: LaneDetectionResult,
                                  image_width: int) -> LaneDistance:
        """Estimate lateral distances to detected lane lines."""
        ego_center_x = image_width / 2.0
        
        # Reference distance at bottom of image (close range for lane measurement)
        # Use a point ~5m ahead for lane offset calculation
        ref_distance = 5.0
        
        left_offset = None
        right_offset = None
        lane_width = None
        
        if lane_result.left_lane and lane_result.left_lane.x_at_bottom is not None:
            left_x = lane_result.left_lane.x_at_bottom
            left_offset_px = ego_center_x - left_x  # Positive = lane is to the left
            left_offset = self._camera.lateral_offset_px_to_m(
                left_offset_px, ref_distance
            )
            left_offset = round(abs(left_offset), 2)
        
        if lane_result.right_lane and lane_result.right_lane.x_at_bottom is not None:
            right_x = lane_result.right_lane.x_at_bottom
            right_offset_px = right_x - ego_center_x  # Positive = lane is to the right
            right_offset = self._camera.lateral_offset_px_to_m(
                right_offset_px, ref_distance
            )
            right_offset = round(abs(right_offset), 2)
        
        if left_offset is not None and right_offset is not None:
            lane_width = round(left_offset + right_offset, 2)
        
        return LaneDistance(
            left_lane_offset_m=left_offset,
            right_lane_offset_m=right_offset,
            lane_width_m=lane_width,
        )
    
    def _get_vehicle_width(self, class_name: str) -> float:
        """Get assumed real-world width for a vehicle class."""
        widths = {
            "car": self._config.avg_car_width_m,
            "truck": self._config.avg_truck_width_m,
            "bus": self._config.avg_bus_width_m,
            "motorcycle": self._config.avg_motorcycle_width_m,
        }
        return widths.get(class_name, self._config.avg_car_width_m)
    
    def _smooth_distance(self, track_id: int, raw_distance: float) -> float:
        """Apply temporal smoothing to a distance measurement."""
        if track_id not in self._distance_history:
            self._distance_history[track_id] = deque(maxlen=self._smoothing_window)
        
        history = self._distance_history[track_id]
        history.append(raw_distance)
        
        if len(history) < 2:
            return raw_distance
        
        # Weighted moving average (more recent = higher weight)
        weights = np.linspace(0.5, 1.0, len(history))
        weights /= weights.sum()
        
        smoothed = sum(w * d for w, d in zip(weights, history))
        return smoothed
    
    def clear_history(self, track_id: Optional[int] = None):
        """Clear smoothing history for a track or all tracks."""
        if track_id is not None:
            self._distance_history.pop(track_id, None)
        else:
            self._distance_history.clear()
    
    def reset(self):
        """Reset all state."""
        self._distance_history.clear()
