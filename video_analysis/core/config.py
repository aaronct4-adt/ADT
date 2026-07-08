"""
Configuration and camera presets for the Video Analysis Tool.

Supports Axis F2015-RE and custom camera configurations.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple
import math


@dataclass
class CameraConfig:
    """Camera intrinsic and mounting parameters."""
    
    # Lens parameters
    focal_length_mm: float = 3.1          # Focal length in mm
    hfov_degrees: float = 108.0           # Horizontal field of view
    vfov_degrees: float = 58.0            # Vertical field of view
    
    # Image parameters
    image_width: int = 1280
    image_height: int = 720
    
    # Mounting parameters (estimated defaults)
    mount_height_m: float = 1.4           # Height above road surface (meters)
    tilt_degrees: float = 0.0             # Downward tilt from horizontal (positive = looking down)
    
    # View type: front, rear, left_side, right_side, rear_left, rear_right
    view_type: str = "front"
    
    @property
    def focal_length_px(self) -> float:
        """Focal length in pixels (derived from HFOV and image width)."""
        return self.image_width / (2.0 * math.tan(math.radians(self.hfov_degrees / 2.0)))
    
    @property
    def focal_length_py(self) -> float:
        """Focal length in pixels vertical (derived from VFOV and image height)."""
        return self.image_height / (2.0 * math.tan(math.radians(self.vfov_degrees / 2.0)))
    
    @property
    def principal_point(self) -> Tuple[float, float]:
        """Principal point (image center)."""
        return (self.image_width / 2.0, self.image_height / 2.0)


@dataclass
class DetectionConfig:
    """Configuration for detection models."""
    
    # YOLOv8 model size: nano, small, medium, large, xlarge
    yolo_model: str = "yolov8n.pt"       # nano for speed, upgrade if needed
    confidence_threshold: float = 0.4
    iou_threshold: float = 0.5
    
    # Vehicle classes from COCO: car, motorcycle, bus, truck
    vehicle_classes: list = field(default_factory=lambda: [2, 3, 5, 7])
    
    # Tracking
    tracker_max_age: int = 30             # Frames to keep lost track
    tracker_min_hits: int = 3             # Min detections before confirmed
    tracker_iou_threshold: float = 0.3


@dataclass
class LaneConfig:
    """Configuration for lane detection."""
    
    # Pre-processing
    blur_kernel: int = 5
    canny_low: int = 50
    canny_high: int = 150
    
    # Hough transform parameters
    hough_threshold: int = 50
    hough_min_line_length: int = 100
    hough_max_line_gap: int = 50
    
    # ROI (fraction of image) - bottom portion for lane detection
    roi_top_fraction: float = 0.5         # Start from middle of image
    
    # Lane width assumption (US standard lane = 3.7m, metric = 3.5m)
    assumed_lane_width_m: float = 3.7


@dataclass  
class DistanceConfig:
    """Configuration for distance estimation."""
    
    # Known object widths for distance estimation (meters)
    avg_car_width_m: float = 1.8
    avg_truck_width_m: float = 2.5
    avg_bus_width_m: float = 2.6
    avg_motorcycle_width_m: float = 0.8
    
    # Maximum credible distance (beyond this, measurements are unreliable)
    max_distance_m: float = 150.0
    min_distance_m: float = 2.0
    
    # Smoothing
    temporal_smoothing_frames: int = 5    # Moving average window


@dataclass
class AppConfig:
    """Top-level application configuration."""
    
    camera: CameraConfig = field(default_factory=CameraConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    lane: LaneConfig = field(default_factory=LaneConfig)
    distance: DistanceConfig = field(default_factory=DistanceConfig)
    
    # Output settings
    output_dir: str = "./output"
    export_fps: Optional[float] = None    # None = match input video FPS


# --- Camera Presets ---

AXIS_F2015_RE = CameraConfig(
    focal_length_mm=3.1,
    hfov_degrees=108.0,
    vfov_degrees=58.0,
    image_width=1280,
    image_height=720,
    mount_height_m=1.4,
    tilt_degrees=0.0,
    view_type="front",
)


def get_default_config(view_type: str = "front", mount_height_m: float = 1.4) -> AppConfig:
    """Get default config for Axis F2015-RE with specified view and mount height."""
    camera = CameraConfig(
        focal_length_mm=3.1,
        hfov_degrees=108.0,
        vfov_degrees=58.0,
        image_width=1280,
        image_height=720,
        mount_height_m=mount_height_m,
        tilt_degrees=0.0,
        view_type=view_type,
    )
    return AppConfig(camera=camera)
