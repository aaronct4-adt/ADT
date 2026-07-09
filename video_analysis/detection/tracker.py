"""
Multi-object tracker using IoU-based assignment.

Assigns persistent IDs to detected vehicles across frames.
Lightweight implementation (no deep features) suitable for offline use.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field
from .vehicle_detector import Detection


@dataclass
class TrackedObject:
    """A tracked vehicle with persistent ID."""
    track_id: int
    bbox: Tuple[int, int, int, int]       # Current (x1, y1, x2, y2)
    confidence: float
    class_id: int
    class_name: str
    age: int = 0                           # Frames since first seen
    hits: int = 1                          # Total detection count
    frames_since_seen: int = 0            # Frames since last detection
    velocity: Tuple[float, float] = (0.0, 0.0)  # Estimated (dx, dy) per frame
    mask: Optional[np.ndarray] = None     # Segmentation mask (if available)
    
    # History for smoothing
    bbox_history: List[Tuple[int, int, int, int]] = field(default_factory=list)
    
    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    
    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]
    
    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]
    
    @property
    def is_confirmed(self) -> bool:
        """Track is confirmed after min_hits detections."""
        return self.hits >= 3
    
    @property
    def bottom_center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, float(y2))


def _iou(box_a: Tuple[int, int, int, int], 
          box_b: Tuple[int, int, int, int]) -> float:
    """Compute IoU between two bounding boxes."""
    xa = max(box_a[0], box_b[0])
    ya = max(box_a[1], box_b[1])
    xb = min(box_a[2], box_b[2])
    yb = min(box_a[3], box_b[3])
    
    inter_area = max(0, xb - xa) * max(0, yb - ya)
    if inter_area == 0:
        return 0.0
    
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    
    union_area = area_a + area_b - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def _compute_iou_matrix(tracks: List[TrackedObject], 
                         detections: List[Detection]) -> np.ndarray:
    """Compute IoU matrix between existing tracks and new detections."""
    n_tracks = len(tracks)
    n_dets = len(detections)
    
    iou_matrix = np.zeros((n_tracks, n_dets), dtype=np.float32)
    
    for i, track in enumerate(tracks):
        # Use predicted position (simple linear motion)
        predicted_bbox = _predict_bbox(track)
        for j, det in enumerate(detections):
            iou_matrix[i, j] = _iou(predicted_bbox, det.bbox)
    
    return iou_matrix


def _predict_bbox(track: TrackedObject) -> Tuple[int, int, int, int]:
    """Predict next bbox position using simple velocity model."""
    x1, y1, x2, y2 = track.bbox
    dx, dy = track.velocity
    
    return (
        int(x1 + dx),
        int(y1 + dy),
        int(x2 + dx),
        int(y2 + dy),
    )


class VehicleTracker:
    """
    IoU-based multi-object tracker.
    
    Uses Hungarian algorithm for optimal assignment of detections to tracks.
    Maintains persistent IDs across frames.
    """
    
    def __init__(self, max_age: int = 30, min_hits: int = 3,
                 iou_threshold: float = 0.3,
                 history_length: int = 30):
        """
        Args:
            max_age: Maximum frames to keep a lost track before removing
            min_hits: Minimum detections before a track is confirmed
            iou_threshold: Minimum IoU for matching detection to track
            history_length: How many past bboxes to keep per track
        """
        self._max_age = max_age
        self._min_hits = min_hits
        self._iou_threshold = iou_threshold
        self._history_length = history_length
        
        self._tracks: List[TrackedObject] = []
        self._next_id = 1
        self._frame_count = 0
    
    @property
    def tracks(self) -> List[TrackedObject]:
        """Get all current tracks (including unconfirmed)."""
        return self._tracks
    
    @property
    def confirmed_tracks(self) -> List[TrackedObject]:
        """Get only confirmed tracks."""
        return [t for t in self._tracks if t.is_confirmed]
    
    def update(self, detections: List[Detection]) -> List[TrackedObject]:
        """
        Update tracker with new frame detections.
        
        Args:
            detections: List of detections from current frame
            
        Returns:
            List of confirmed tracked objects in current frame
        """
        self._frame_count += 1
        
        if len(self._tracks) == 0:
            # No existing tracks - create new ones from all detections
            for det in detections:
                self._create_track(det)
            return self.confirmed_tracks
        
        if len(detections) == 0:
            # No detections - age all tracks
            self._age_tracks()
            self._remove_dead_tracks()
            return self.confirmed_tracks
        
        # Compute IoU matrix
        iou_matrix = _compute_iou_matrix(self._tracks, detections)
        
        # Hungarian assignment
        matched_tracks, matched_dets, unmatched_tracks, unmatched_dets = \
            self._assign(iou_matrix)
        
        # Update matched tracks
        for track_idx, det_idx in zip(matched_tracks, matched_dets):
            self._update_track(self._tracks[track_idx], detections[det_idx])
        
        # Age unmatched tracks
        for track_idx in unmatched_tracks:
            self._tracks[track_idx].frames_since_seen += 1
            self._tracks[track_idx].age += 1
        
        # Create new tracks for unmatched detections
        for det_idx in unmatched_dets:
            self._create_track(detections[det_idx])
        
        # Remove dead tracks
        self._remove_dead_tracks()
        
        return self.confirmed_tracks
    
    def _assign(self, iou_matrix: np.ndarray):
        """Greedy assignment based on IoU (simple and fast)."""
        n_tracks, n_dets = iou_matrix.shape
        
        matched_tracks = []
        matched_dets = []
        used_tracks = set()
        used_dets = set()
        
        # Sort all IoU values in descending order and greedily assign
        if n_tracks > 0 and n_dets > 0:
            # Try scipy Hungarian first, fall back to greedy
            try:
                from scipy.optimize import linear_sum_assignment
                cost_matrix = 1.0 - iou_matrix
                row_indices, col_indices = linear_sum_assignment(cost_matrix)
                
                for r, c in zip(row_indices, col_indices):
                    if iou_matrix[r, c] >= self._iou_threshold:
                        matched_tracks.append(r)
                        matched_dets.append(c)
                        used_tracks.add(r)
                        used_dets.add(c)
            except ImportError:
                # Greedy fallback
                flat_indices = np.argsort(-iou_matrix.ravel())
                for flat_idx in flat_indices:
                    r = flat_idx // n_dets
                    c = flat_idx % n_dets
                    
                    if iou_matrix[r, c] < self._iou_threshold:
                        break
                    
                    if r not in used_tracks and c not in used_dets:
                        matched_tracks.append(r)
                        matched_dets.append(c)
                        used_tracks.add(r)
                        used_dets.add(c)
        
        unmatched_tracks = [i for i in range(n_tracks) if i not in used_tracks]
        unmatched_dets = [i for i in range(n_dets) if i not in used_dets]
        
        return matched_tracks, matched_dets, unmatched_tracks, unmatched_dets
    
    def _create_track(self, detection: Detection):
        """Create a new track from a detection."""
        track = TrackedObject(
            track_id=self._next_id,
            bbox=detection.bbox,
            confidence=detection.confidence,
            class_id=detection.class_id,
            class_name=detection.class_name,
            age=0,
            hits=1,
            frames_since_seen=0,
            velocity=(0.0, 0.0),
            mask=detection.mask,
            bbox_history=[detection.bbox],
        )
        self._tracks.append(track)
        self._next_id += 1
    
    def _update_track(self, track: TrackedObject, detection: Detection):
        """Update an existing track with a new detection."""
        old_center = track.center
        new_center = detection.center
        
        # Update velocity (exponential moving average)
        alpha = 0.3
        dx = new_center[0] - old_center[0]
        dy = new_center[1] - old_center[1]
        track.velocity = (
            alpha * dx + (1 - alpha) * track.velocity[0],
            alpha * dy + (1 - alpha) * track.velocity[1],
        )
        
        # Update bbox and metadata
        track.bbox = detection.bbox
        track.confidence = detection.confidence
        track.class_id = detection.class_id
        track.class_name = detection.class_name
        track.mask = detection.mask
        track.hits += 1
        track.age += 1
        track.frames_since_seen = 0
        
        # Update history
        track.bbox_history.append(detection.bbox)
        if len(track.bbox_history) > self._history_length:
            track.bbox_history.pop(0)
    
    def _age_tracks(self):
        """Increment age for all tracks."""
        for track in self._tracks:
            track.frames_since_seen += 1
            track.age += 1
    
    def _remove_dead_tracks(self):
        """Remove tracks that haven't been seen recently."""
        self._tracks = [
            t for t in self._tracks
            if t.frames_since_seen <= self._max_age
        ]
    
    def reset(self):
        """Reset tracker state."""
        self._tracks = []
        self._next_id = 1
        self._frame_count = 0
    
    def get_track_by_id(self, track_id: int) -> Optional[TrackedObject]:
        """Find a track by its ID."""
        for track in self._tracks:
            if track.track_id == track_id:
                return track
        return None
