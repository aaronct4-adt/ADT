"""
Annotated video export module.

Generates a new video file with overlaid bounding boxes, vehicle IDs,
distance labels, and lane lines drawn on each frame.
"""

import cv2
import numpy as np
from typing import List, Optional, Set, Tuple
from pathlib import Path

from ..detection.tracker import TrackedObject
from ..detection.lane_detector import LaneDetectionResult
from ..detection.distance_estimator import FrameDistances, VehicleDistance


# Color palette for vehicle tracks (BGR)
TRACK_COLORS = [
    (0, 255, 0),     # Green
    (255, 128, 0),   # Blue-ish
    (0, 255, 255),   # Yellow
    (255, 0, 255),   # Magenta
    (0, 128, 255),   # Orange
    (255, 255, 0),   # Cyan
    (128, 0, 255),   # Purple
    (0, 255, 128),   # Spring green
    (255, 0, 128),   # Rose
    (128, 255, 0),   # Lime
]

# Lane line colors
LANE_COLOR_LEFT = (255, 100, 100)    # Blue-ish
LANE_COLOR_RIGHT = (100, 100, 255)   # Red-ish
LANE_COLOR_CENTER = (100, 255, 100)  # Green-ish


def get_track_color(track_id: int) -> Tuple[int, int, int]:
    """Get a consistent color for a track ID."""
    return TRACK_COLORS[track_id % len(TRACK_COLORS)]


class FrameAnnotator:
    """
    Draws annotations on video frames.
    
    Used for both the interactive GUI display and the export video.
    """
    
    def __init__(self, selected_ids: Optional[Set[int]] = None,
                 show_all_boxes: bool = True,
                 show_distance: bool = True,
                 show_lanes: bool = True,
                 show_lane_distance: bool = True):
        """
        Args:
            selected_ids: Vehicle IDs to highlight (thicker box, distance label)
            show_all_boxes: Draw boxes for all detected vehicles
            show_distance: Show distance labels
            show_lanes: Draw detected lane lines
            show_lane_distance: Show lane offset distances
        """
        self.selected_ids = selected_ids or set()
        self.show_all_boxes = show_all_boxes
        self.show_distance = show_distance
        self.show_lanes = show_lanes
        self.show_lane_distance = show_lane_distance
    
    def annotate_frame(self, frame: np.ndarray,
                       frame_distances: Optional[FrameDistances] = None,
                       lane_result: Optional[LaneDetectionResult] = None,
                       tracks: Optional[List[TrackedObject]] = None) -> np.ndarray:
        """
        Draw all annotations on a frame.
        
        Args:
            frame: BGR image to annotate (will be copied)
            frame_distances: Distance measurements for this frame
            lane_result: Lane detection results
            tracks: Tracked objects (used if frame_distances not available)
            
        Returns:
            Annotated frame (new array, original not modified)
        """
        annotated = frame.copy()
        
        # Draw lane lines first (under vehicle boxes)
        if self.show_lanes and lane_result and lane_result.has_lanes:
            self._draw_lanes(annotated, lane_result)
        
        # Draw vehicle boxes and distance labels
        if frame_distances:
            self._draw_vehicles_with_distance(annotated, frame_distances)
        elif tracks:
            self._draw_vehicles_no_distance(annotated, tracks)
        
        # Draw lane distance info
        if self.show_lane_distance and frame_distances and frame_distances.lane:
            self._draw_lane_distance_info(annotated, frame_distances)
        
        # Draw timestamp
        if frame_distances:
            self._draw_timestamp(annotated, frame_distances.timestamp_sec)
        
        return annotated
    
    def _draw_vehicles_with_distance(self, frame: np.ndarray, 
                                      fd: FrameDistances):
        """Draw vehicle boxes with distance labels."""
        for vd in fd.vehicles:
            is_selected = vd.track_id in self.selected_ids
            
            if not self.show_all_boxes and not is_selected:
                continue
            
            color = get_track_color(vd.track_id)
            thickness = 3 if is_selected else 1
            x1, y1, x2, y2 = vd.bbox
            
            # Draw bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            
            # Label with ID and class
            label = f"ID:{vd.track_id} {vd.class_name}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            
            # Background for label
            cv2.rectangle(frame, (x1, y1 - label_size[1] - 6), 
                         (x1 + label_size[0] + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            
            # Distance label (only for selected or all if show_distance)
            if self.show_distance and (is_selected or not self.selected_ids):
                dist_label = f"{vd.distance_m:.1f}m"
                if is_selected:
                    dist_label += f" | lat:{vd.lateral_offset_m:.1f}m"
                
                dist_size = cv2.getTextSize(dist_label, cv2.FONT_HERSHEY_SIMPLEX, 
                                            0.6, 2)[0]
                
                # Position below the box
                text_x = x1
                text_y = y2 + dist_size[1] + 8
                
                # Background
                cv2.rectangle(frame, (text_x - 2, y2 + 2),
                             (text_x + dist_size[0] + 4, text_y + 4),
                             (0, 0, 0), -1)
                cv2.putText(frame, dist_label, (text_x, text_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    def _draw_vehicles_no_distance(self, frame: np.ndarray,
                                    tracks: List[TrackedObject]):
        """Draw vehicle boxes without distance info (detection-only mode)."""
        for track in tracks:
            is_selected = track.track_id in self.selected_ids
            
            if not self.show_all_boxes and not is_selected:
                continue
            
            color = get_track_color(track.track_id)
            thickness = 3 if is_selected else 1
            x1, y1, x2, y2 = track.bbox
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            
            label = f"ID:{track.track_id} {track.class_name}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            cv2.rectangle(frame, (x1, y1 - label_size[1] - 6),
                         (x1 + label_size[0] + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    
    def _draw_lanes(self, frame: np.ndarray, lane_result: LaneDetectionResult):
        """Draw detected lane lines."""
        if lane_result.left_lane:
            pts = np.array(lane_result.left_lane.points, dtype=np.int32)
            if len(pts) > 1:
                cv2.polylines(frame, [pts], False, LANE_COLOR_LEFT, 3)
        
        if lane_result.right_lane:
            pts = np.array(lane_result.right_lane.points, dtype=np.int32)
            if len(pts) > 1:
                cv2.polylines(frame, [pts], False, LANE_COLOR_RIGHT, 3)
        
        for center_line in lane_result.center_lines:
            pts = np.array(center_line.points, dtype=np.int32)
            if len(pts) > 1:
                cv2.polylines(frame, [pts], False, LANE_COLOR_CENTER, 2)
    
    def _draw_lane_distance_info(self, frame: np.ndarray, fd: FrameDistances):
        """Draw lane offset information in the corner."""
        h, w = frame.shape[:2]
        y_pos = h - 20
        
        if fd.lane.left_lane_offset_m is not None:
            text = f"Left lane: {fd.lane.left_lane_offset_m:.1f}m"
            cv2.putText(frame, text, (10, y_pos - 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, LANE_COLOR_LEFT, 1)
        
        if fd.lane.right_lane_offset_m is not None:
            text = f"Right lane: {fd.lane.right_lane_offset_m:.1f}m"
            cv2.putText(frame, text, (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, LANE_COLOR_RIGHT, 1)
    
    def _draw_timestamp(self, frame: np.ndarray, timestamp: float):
        """Draw timestamp in top-right corner."""
        h, w = frame.shape[:2]
        text = f"t={timestamp:.2f}s"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
        x = w - text_size[0] - 10
        cv2.putText(frame, text, (x, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)


class VideoExporter:
    """
    Export annotated video with bounding boxes, distance labels, and lane lines.
    """
    
    def __init__(self, output_dir: str = "./output", fps: Optional[float] = None):
        """
        Args:
            output_dir: Directory to write output video
            fps: Output video FPS (None = match input)
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._fps = fps
    
    def export(self, frames: List[np.ndarray],
               frame_distances: List[FrameDistances],
               lane_results: Optional[List[Optional[LaneDetectionResult]]] = None,
               selected_ids: Optional[Set[int]] = None,
               input_fps: float = 30.0,
               filename: str = "annotated_output.mp4") -> str:
        """
        Export annotated video.
        
        Args:
            frames: List of original BGR frames
            frame_distances: Per-frame distance data
            lane_results: Per-frame lane detection results (optional)
            selected_ids: Vehicle IDs to highlight
            input_fps: Input video FPS (used if self._fps is None)
            filename: Output filename
            
        Returns:
            Path to the output video file
        """
        output_path = self._output_dir / filename
        fps = self._fps or input_fps
        
        if not frames:
            print("No frames to export!")
            return ""
        
        h, w = frames[0].shape[:2]
        
        # Use mp4v codec for compatibility
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))
        
        if not writer.isOpened():
            raise RuntimeError(f"Cannot open video writer: {output_path}")
        
        annotator = FrameAnnotator(
            selected_ids=selected_ids,
            show_all_boxes=True,
            show_distance=True,
            show_lanes=True,
            show_lane_distance=True,
        )
        
        total = len(frames)
        
        for i, frame in enumerate(frames):
            # Get distance data for this frame
            fd = frame_distances[i] if i < len(frame_distances) else None
            
            # Get lane data for this frame
            lr = None
            if lane_results and i < len(lane_results):
                lr = lane_results[i]
            
            # Annotate
            annotated = annotator.annotate_frame(frame, fd, lr)
            
            # Write
            writer.write(annotated)
            
            # Progress
            if (i + 1) % 100 == 0 or i == total - 1:
                print(f"  Exporting frame {i+1}/{total}...")
        
        writer.release()
        print(f"Annotated video exported to: {output_path}")
        return str(output_path)
