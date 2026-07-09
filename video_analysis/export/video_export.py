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
            # Draw lane-to-vehicle distance lines on the ground
            if self.show_lane_distance and lane_result and lane_result.has_lanes:
                self._draw_lane_distance_lines(annotated, frame_distances, lane_result)
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
            
            # Draw 3D cuboid instead of flat rectangle
            self._draw_3d_box(frame, vd.bbox, vd.distance_m, color, thickness)
            
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
                # Primary: longitudinal distance (to rear face of vehicle ahead)
                dist_label = f"{vd.distance_m:.1f}m"
                
                # Add lane-relative lateral distances if available
                lane_parts = []
                if vd.lane_offset_left_m is not None:
                    lane_parts.append(f"L.lane:{vd.lane_offset_left_m:.1f}m")
                if vd.lane_offset_right_m is not None:
                    lane_parts.append(f"R.lane:{vd.lane_offset_right_m:.1f}m")
                
                if lane_parts:
                    dist_label += " | " + " ".join(lane_parts)
                elif is_selected:
                    # Fallback: show offset from ego center
                    dist_label += f" | ego lat:{vd.lateral_offset_m:.1f}m"
                
                dist_size = cv2.getTextSize(dist_label, cv2.FONT_HERSHEY_SIMPLEX, 
                                            0.5, 1)[0]
                
                # Position below the box
                text_x = x1
                text_y = y2 + dist_size[1] + 8
                
                # Background
                cv2.rectangle(frame, (text_x - 2, y2 + 2),
                             (text_x + dist_size[0] + 4, text_y + 4),
                             (0, 0, 0), -1)
                cv2.putText(frame, dist_label, (text_x, text_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    def _draw_3d_box(self, frame: np.ndarray, 
                     bbox: tuple, distance_m: float,
                     color: tuple, thickness: int):
        """
        Draw the vehicle footprint as a flat plan-view trapezoid on the road.
        
        Uses the YOLO bbox shrunk inward by 10% on each side (YOLO boxes
        are typically wider than the actual vehicle body). The polygon
        covers only the bottom 30% of the bbox height, representing the
        vehicle's road-level footprint.
        """
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        
        bbox_width = x2 - x1
        bbox_height = y2 - y1
        center_x = (x1 + x2) / 2.0
        
        # Shrink width inward by 10% on each side to match actual vehicle body
        # (YOLO boxes tend to be wider than the physical vehicle)
        inset = int(bbox_width * 0.10)
        body_left = x1 + inset
        body_right = x2 - inset
        body_width = body_right - body_left
        
        # Tire contact point (rear of vehicle on road) - 85% down
        tire_y = int(y1 + bbox_height * 0.85)
        
        # Front edge of footprint: 25% of bbox height above tire level
        footprint_depth = int(bbox_height * 0.25)
        front_y = tire_y - footprint_depth
        
        # Rear edge at tire level, full body width
        rear_left = (body_left, tire_y)
        rear_right = (body_right, tire_y)
        
        # Front edge: slightly narrower + shifted toward VP
        taper_px = int(body_width * 0.06)
        vp_x = w / 2.0
        lateral_shift = int((vp_x - center_x) * 0.04)
        
        front_left = (body_left + taper_px + lateral_shift, front_y)
        front_right = (body_right - taper_px + lateral_shift, front_y)
        
        # Draw the flat footprint quadrilateral
        pts = np.array([rear_left, rear_right, front_right, front_left], dtype=np.int32)
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=thickness)
        
        # Thicker rear edge (this is where distance is measured from)
        cv2.line(frame, rear_left, rear_right, color, thickness + 1)
    
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
                cv2.polylines(frame, [pts], False, LANE_COLOR_LEFT, 2)
        
        if lane_result.right_lane:
            pts = np.array(lane_result.right_lane.points, dtype=np.int32)
            if len(pts) > 1:
                cv2.polylines(frame, [pts], False, LANE_COLOR_RIGHT, 2)
        
        for center_line in lane_result.center_lines:
            pts = np.array(center_line.points, dtype=np.int32)
            if len(pts) > 1:
                cv2.polylines(frame, [pts], False, LANE_COLOR_CENTER, 1)
    
    def _draw_lane_distance_lines(self, frame: np.ndarray, 
                                   fd: FrameDistances,
                                   lane_result: LaneDetectionResult):
        """
        Draw horizontal lines on the road from vehicle to nearest lane line,
        showing the lateral distance measurement.
        """
        if not lane_result or not lane_result.has_lanes:
            return
        
        for vd in fd.vehicles:
            is_selected = vd.track_id in self.selected_ids
            if not is_selected and self.selected_ids:
                continue
            
            x1, y1, x2, y2 = vd.bbox
            bbox_width = x2 - x1
            bbox_height = y2 - y1
            
            # Match the footprint drawing: 10% inset, 85% tire level
            inset = int(bbox_width * 0.10)
            vehicle_left_x = x1 + inset
            vehicle_right_x = x2 - inset
            tire_y = int(y1 + bbox_height * 0.85)
            
            color = get_track_color(vd.track_id)
            
            # Draw line from left lane to vehicle LEFT EDGE at tire level
            if vd.lane_offset_left_m is not None and lane_result.left_lane:
                lane_x = int(lane_result.left_lane.get_x_at_y(float(tire_y)))
                self._draw_dashed_line(frame, (lane_x, tire_y), 
                                       (vehicle_left_x, tire_y), 
                                       LANE_COLOR_LEFT, 2)
                # Label
                mid_x = (lane_x + vehicle_left_x) // 2
                cv2.putText(frame, f"{vd.lane_offset_left_m:.1f}m",
                           (mid_x - 15, tire_y - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, LANE_COLOR_LEFT, 1)
            
            # Draw line from vehicle RIGHT EDGE to right lane at tire level
            if vd.lane_offset_right_m is not None and lane_result.right_lane:
                lane_x = int(lane_result.right_lane.get_x_at_y(float(tire_y)))
                self._draw_dashed_line(frame, (vehicle_right_x, tire_y),
                                       (lane_x, tire_y),
                                       LANE_COLOR_RIGHT, 2)
                # Label
                mid_x = (vehicle_right_x + lane_x) // 2
                cv2.putText(frame, f"{vd.lane_offset_right_m:.1f}m",
                           (mid_x - 15, tire_y - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, LANE_COLOR_RIGHT, 1)
    
    def _draw_dashed_line(self, frame: np.ndarray, 
                          pt1: tuple, pt2: tuple, 
                          color: tuple, thickness: int, 
                          dash_length: int = 8):
        """Draw a dashed line between two points."""
        x1, y1 = pt1
        x2, y2 = pt2
        dx = x2 - x1
        dy = y2 - y1
        dist = max(1, int((dx*dx + dy*dy) ** 0.5))
        
        num_dashes = dist // (dash_length * 2)
        if num_dashes < 1:
            cv2.line(frame, pt1, pt2, color, thickness)
            return
        
        for i in range(num_dashes + 1):
            start_frac = (i * 2 * dash_length) / dist
            end_frac = min(((i * 2 + 1) * dash_length) / dist, 1.0)
            
            if start_frac > 1.0:
                break
            
            sx = int(x1 + dx * start_frac)
            sy = int(y1 + dy * start_frac)
            ex = int(x1 + dx * end_frac)
            ey = int(y1 + dy * end_frac)
            
            cv2.line(frame, (sx, sy), (ex, ey), color, thickness)
    
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
