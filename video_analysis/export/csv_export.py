"""
CSV data export module.

Exports time-series distance data for selected vehicles and lane measurements.
"""

import csv
import os
from typing import List, Optional, Set
from pathlib import Path

from ..detection.distance_estimator import FrameDistances


class CSVExporter:
    """
    Export frame-by-frame distance data to CSV files.
    
    Outputs:
    - Vehicle distances: time, vehicle_id, class, distance_m, lateral_offset_m
    - Lane distances: time, left_offset_m, right_offset_m, lane_width_m
    """
    
    def __init__(self, output_dir: str = "./output"):
        """
        Args:
            output_dir: Directory to write CSV files
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_vehicle_distances(self, frame_data: List[FrameDistances],
                                  selected_vehicle_ids: Optional[Set[int]] = None,
                                  filename: str = "vehicle_distances.csv") -> str:
        """
        Export vehicle distance time-series to CSV.
        
        Args:
            frame_data: List of per-frame distance results
            selected_vehicle_ids: If set, only export these vehicle IDs.
                                  If None, export all vehicles.
            filename: Output filename
            
        Returns:
            Path to the output CSV file
        """
        output_path = self._output_dir / filename
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "frame", "time_sec", "vehicle_id", "class", 
                "distance_m", "lateral_offset_m",
                "lane_offset_left_m", "lane_offset_right_m",
                "confidence",
                "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"
            ])
            
            for fd in frame_data:
                for vd in fd.vehicles:
                    # Filter by selected vehicles if specified
                    if selected_vehicle_ids and vd.track_id not in selected_vehicle_ids:
                        continue
                    
                    writer.writerow([
                        fd.frame_idx,
                        f"{fd.timestamp_sec:.3f}",
                        vd.track_id,
                        vd.class_name,
                        f"{vd.distance_m:.2f}",
                        f"{vd.lateral_offset_m:.2f}",
                        f"{vd.lane_offset_left_m:.2f}" if vd.lane_offset_left_m is not None else "",
                        f"{vd.lane_offset_right_m:.2f}" if vd.lane_offset_right_m is not None else "",
                        f"{vd.confidence:.2f}",
                        vd.bbox[0], vd.bbox[1], vd.bbox[2], vd.bbox[3],
                    ])
        
        print(f"Vehicle distances exported to: {output_path}")
        return str(output_path)
    
    def export_lane_distances(self, frame_data: List[FrameDistances],
                               filename: str = "lane_distances.csv") -> str:
        """
        Export lane distance time-series to CSV.
        
        Args:
            frame_data: List of per-frame distance results
            filename: Output filename
            
        Returns:
            Path to the output CSV file
        """
        output_path = self._output_dir / filename
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "frame", "time_sec", 
                "left_lane_offset_m", "right_lane_offset_m", "lane_width_m"
            ])
            
            for fd in frame_data:
                if fd.lane is not None:
                    writer.writerow([
                        fd.frame_idx,
                        f"{fd.timestamp_sec:.3f}",
                        f"{fd.lane.left_lane_offset_m:.2f}" if fd.lane.left_lane_offset_m is not None else "",
                        f"{fd.lane.right_lane_offset_m:.2f}" if fd.lane.right_lane_offset_m is not None else "",
                        f"{fd.lane.lane_width_m:.2f}" if fd.lane.lane_width_m is not None else "",
                    ])
        
        print(f"Lane distances exported to: {output_path}")
        return str(output_path)
    
    def export_summary(self, frame_data: List[FrameDistances],
                       selected_vehicle_ids: Optional[Set[int]] = None,
                       filename: str = "analysis_summary.csv") -> str:
        """
        Export a summary with per-vehicle statistics.
        
        Args:
            frame_data: List of per-frame distance results
            selected_vehicle_ids: Vehicle IDs to include
            filename: Output filename
            
        Returns:
            Path to the output CSV file
        """
        output_path = self._output_dir / filename
        
        # Collect stats per vehicle
        vehicle_stats = {}
        
        for fd in frame_data:
            for vd in fd.vehicles:
                if selected_vehicle_ids and vd.track_id not in selected_vehicle_ids:
                    continue
                
                if vd.track_id not in vehicle_stats:
                    vehicle_stats[vd.track_id] = {
                        "class": vd.class_name,
                        "distances": [],
                        "first_seen": fd.timestamp_sec,
                        "last_seen": fd.timestamp_sec,
                        "frame_count": 0,
                    }
                
                stats = vehicle_stats[vd.track_id]
                stats["distances"].append(vd.distance_m)
                stats["last_seen"] = fd.timestamp_sec
                stats["frame_count"] += 1
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "vehicle_id", "class", "frames_tracked",
                "first_seen_sec", "last_seen_sec", "duration_sec",
                "min_distance_m", "max_distance_m", "avg_distance_m",
            ])
            
            for vid, stats in sorted(vehicle_stats.items()):
                distances = stats["distances"]
                duration = stats["last_seen"] - stats["first_seen"]
                
                writer.writerow([
                    vid,
                    stats["class"],
                    stats["frame_count"],
                    f"{stats['first_seen']:.3f}",
                    f"{stats['last_seen']:.3f}",
                    f"{duration:.3f}",
                    f"{min(distances):.2f}",
                    f"{max(distances):.2f}",
                    f"{sum(distances)/len(distances):.2f}",
                ])
        
        print(f"Summary exported to: {output_path}")
        return str(output_path)
