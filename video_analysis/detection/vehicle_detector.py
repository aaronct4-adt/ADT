"""
Vehicle detection using YOLOv8.

Detects cars, trucks, buses, and motorcycles in video frames.
Works offline once the model weights are downloaded.
"""

import os
import sys
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

# Import ultralytics at module level so PyInstaller can trace it
from ultralytics import YOLO


def _get_model_path(model_name: str) -> str:
    """
    Resolve the model file path, handling both normal and frozen (exe) environments.
    
    When running as a PyInstaller exe, bundled data files are in a temp directory
    referenced by sys._MEIPASS (onedir) or next to the exe.
    """
    searched = []
    
    # Check if running as a frozen exe
    if getattr(sys, 'frozen', False):
        # PyInstaller bundles files into _MEIPASS or next to the exe
        base_paths = [
            Path(sys._MEIPASS),                        # --onefile temp dir
            Path(sys.executable).parent,                # --onedir: next to exe
            Path(sys.executable).parent / '_internal',  # newer PyInstaller versions
        ]
        for base in base_paths:
            candidate = base / model_name
            searched.append(str(candidate))
            if candidate.exists():
                return str(candidate)
    
    # Normal Python execution: check current dir, then script dir
    cwd_candidate = Path(model_name).resolve()
    searched.append(str(cwd_candidate))
    if cwd_candidate.exists():
        return str(cwd_candidate)
    
    script_dir = Path(__file__).parent.parent.parent
    candidate = script_dir / model_name
    searched.append(str(candidate))
    if candidate.exists():
        return str(candidate)
    
    # Raise a clear error instead of silently failing
    raise FileNotFoundError(
        f"Cannot find model file '{model_name}'.\n"
        f"Searched in:\n" + "\n".join(f"  - {p}" for p in searched) + "\n\n"
        f"Please place '{model_name}' next to the executable or in the working directory.\n"
        f"You can download it by running:\n"
        f"  python -c \"from ultralytics import YOLO; YOLO('{model_name}')\""
    )


@dataclass
class Detection:
    """A single vehicle detection in a frame."""
    bbox: Tuple[int, int, int, int]   # (x1, y1, x2, y2)
    confidence: float
    class_id: int                      # COCO class ID
    class_name: str                    # Human-readable name
    
    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]
    
    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]
    
    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    
    @property
    def area(self) -> int:
        return self.width * self.height
    
    @property
    def bottom_center(self) -> Tuple[float, float]:
        """Bottom center point (where vehicle meets ground)."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, float(y2))


# COCO class names for vehicle types
VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


class VehicleDetector:
    """
    YOLOv8-based vehicle detector.
    
    Uses Ultralytics YOLOv8 for detection. The model weights file
    must be available locally for offline operation.
    """
    
    def __init__(self, model_path: str = "yolov8n.pt",
                 confidence_threshold: float = 0.4,
                 iou_threshold: float = 0.5,
                 vehicle_classes: Optional[List[int]] = None):
        """
        Initialize the detector.
        
        Args:
            model_path: Path to YOLOv8 weights file (.pt)
                       Use "yolov8n.pt" (nano), "yolov8s.pt" (small), 
                       "yolov8m.pt" (medium) for speed/accuracy tradeoff
            confidence_threshold: Minimum detection confidence
            iou_threshold: NMS IoU threshold
            vehicle_classes: COCO class IDs to detect (default: car, motorcycle, bus, truck)
        """
        self._model_path = _get_model_path(model_path)
        self._conf_thresh = confidence_threshold
        self._iou_thresh = iou_threshold
        self._vehicle_classes = vehicle_classes or [2, 3, 5, 7]
        
        # Load model
        self._model = YOLO(self._model_path)
        
        # Get class names from model
        self._class_names = self._model.names
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Detect vehicles in a single frame.
        
        Args:
            frame: BGR image (numpy array, HxWx3)
            
        Returns:
            List of Detection objects for vehicles found
        """
        # Run inference
        results = self._model(
            frame,
            conf=self._conf_thresh,
            iou=self._iou_thresh,
            classes=self._vehicle_classes,
            verbose=False,
        )
        
        detections = []
        
        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes
                for i in range(len(boxes)):
                    # Get bbox coordinates
                    x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                    conf = float(boxes.conf[i].cpu().numpy())
                    cls_id = int(boxes.cls[i].cpu().numpy())
                    
                    # Get class name
                    cls_name = VEHICLE_CLASSES.get(cls_id, self._class_names.get(cls_id, "unknown"))
                    
                    detections.append(Detection(
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        confidence=conf,
                        class_id=cls_id,
                        class_name=cls_name,
                    ))
        
        return detections
    
    def detect_batch(self, frames: List[np.ndarray], 
                     batch_size: int = 8) -> List[List[Detection]]:
        """
        Detect vehicles in multiple frames (batch processing).
        
        Args:
            frames: List of BGR images
            batch_size: Inference batch size
            
        Returns:
            List of detection lists, one per frame
        """
        all_detections = []
        
        for i in range(0, len(frames), batch_size):
            batch = frames[i:i + batch_size]
            results = self._model(
                batch,
                conf=self._conf_thresh,
                iou=self._iou_thresh,
                classes=self._vehicle_classes,
                verbose=False,
            )
            
            for result in results:
                frame_detections = []
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes
                    for j in range(len(boxes)):
                        x1, y1, x2, y2 = boxes.xyxy[j].cpu().numpy().astype(int)
                        conf = float(boxes.conf[j].cpu().numpy())
                        cls_id = int(boxes.cls[j].cpu().numpy())
                        cls_name = VEHICLE_CLASSES.get(cls_id, self._class_names.get(cls_id, "unknown"))
                        
                        frame_detections.append(Detection(
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            confidence=conf,
                            class_id=cls_id,
                            class_name=cls_name,
                        ))
                all_detections.append(frame_detections)
        
        return all_detections
