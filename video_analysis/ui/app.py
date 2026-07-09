"""
Interactive GUI for video analysis.

Tkinter-based desktop application for:
- Loading video files (quad-view or full-screen)
- Selecting view/quadrant to analyze
- Frame-by-frame scrubbing with bounding boxes
- Vehicle selection (click to select/deselect)
- Running analysis and exporting results
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import cv2
import numpy as np
from PIL import Image, ImageTk
from pathlib import Path
from typing import Optional, Set, List, Dict, Tuple
import threading
import json



class VideoAnalysisApp:
    """Main application window."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Vehicle Distance Analysis Tool")
        self.root.geometry("1400x900")
        
        # State
        self._video_path: Optional[str] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_count = 0
        self._fps = 30.0
        self._current_frame_idx = 0
        self._current_frame: Optional[np.ndarray] = None
        self._display_frame: Optional[np.ndarray] = None
        
        # Quad view state
        self._is_quad_view = False
        self._selected_quadrant: Optional[str] = None  # or "full"
        self._quad_rects: Dict[str, Tuple[int,int,int,int]] = {}
        
        # Detection state
        self._detector = None
        self._tracker = None
        self._lane_detector = None
        self._distance_estimator = None
        self._camera_model = None
        
        # Analysis results (per-frame)
        self._all_tracks: Dict[int, List] = {}  # frame_idx -> tracks
        self._all_distances: List = []
        self._all_lanes: List = []
        
        # Selection state
        self._selected_vehicle_ids: Set[int] = set()
        self._analysis_complete = False
        
        # Camera config
        self._camera_config = None
        
        self._build_ui()
    

    def _build_ui(self):
        """Build the application UI."""
        # Menu bar
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Video...", command=self._open_video)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)
        
        # Main layout: left panel (controls) + center (video) + right (info)
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel - Controls
        left_panel = ttk.LabelFrame(main_frame, text="Controls", width=250)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)
        
        # Open button
        ttk.Button(left_panel, text="Open Video", 
                   command=self._open_video).pack(pady=5, padx=5, fill=tk.X)
        
        # View selection frame
        self._view_frame = ttk.LabelFrame(left_panel, text="View Selection")
        self._view_frame.pack(pady=5, padx=5, fill=tk.X)
        
        self._view_var = tk.StringVar(value="full")
        ttk.Radiobutton(self._view_frame, text="Full Frame", 
                        variable=self._view_var, value="full",
                        command=self._on_view_change).pack(anchor=tk.W)
        ttk.Radiobutton(self._view_frame, text="Top-Left", 
                        variable=self._view_var, value="top_left",
                        command=self._on_view_change).pack(anchor=tk.W)
        ttk.Radiobutton(self._view_frame, text="Top-Right", 
                        variable=self._view_var, value="top_right",
                        command=self._on_view_change).pack(anchor=tk.W)
        ttk.Radiobutton(self._view_frame, text="Bottom-Left", 
                        variable=self._view_var, value="bottom_left",
                        command=self._on_view_change).pack(anchor=tk.W)
        ttk.Radiobutton(self._view_frame, text="Bottom-Right", 
                        variable=self._view_var, value="bottom_right",
                        command=self._on_view_change).pack(anchor=tk.W)
        

        # Camera settings frame
        self._cam_frame = ttk.LabelFrame(left_panel, text="Camera Settings")
        self._cam_frame.pack(pady=5, padx=5, fill=tk.X)
        
        # Preset dropdown
        ttk.Label(self._cam_frame, text="Preset:").pack(anchor=tk.W)
        self._preset_var = tk.StringVar(value="Axis F2015-RE")
        preset_combo = ttk.Combobox(self._cam_frame, 
                                     textvariable=self._preset_var,
                                     values=["Axis F2015-RE", "Auto-Estimate", "Custom"],
                                     state="readonly")
        preset_combo.pack(fill=tk.X, pady=2)
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)
        
        # Custom camera parameters (hidden until Custom selected)
        self._custom_cam_frame = ttk.Frame(self._cam_frame)
        
        ttk.Label(self._custom_cam_frame, text="HFOV (degrees):").pack(anchor=tk.W)
        self._hfov_var = tk.StringVar(value="108.0")
        ttk.Entry(self._custom_cam_frame, textvariable=self._hfov_var, 
                  width=10).pack(fill=tk.X, pady=1)
        
        ttk.Label(self._custom_cam_frame, text="VFOV (degrees):").pack(anchor=tk.W)
        self._vfov_var = tk.StringVar(value="58.0")
        ttk.Entry(self._custom_cam_frame, textvariable=self._vfov_var, 
                  width=10).pack(fill=tk.X, pady=1)
        
        ttk.Label(self._custom_cam_frame, text="Mount Height (m):").pack(anchor=tk.W)
        self._mount_h_var = tk.StringVar(value="1.4")
        ttk.Entry(self._custom_cam_frame, textvariable=self._mount_h_var, 
                  width=10).pack(fill=tk.X, pady=1)
        
        ttk.Label(self._custom_cam_frame, text="Tilt Down (degrees):").pack(anchor=tk.W)
        self._tilt_var = tk.StringVar(value="0.0")
        ttk.Entry(self._custom_cam_frame, textvariable=self._tilt_var, 
                  width=10).pack(fill=tk.X, pady=1)
        
        # Analysis buttons
        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        ttk.Button(left_panel, text="Run Detection",
                   command=self._run_detection).pack(pady=3, padx=5, fill=tk.X)
        ttk.Button(left_panel, text="Select All Vehicles",
                   command=self._select_all_vehicles).pack(pady=3, padx=5, fill=tk.X)
        ttk.Button(left_panel, text="Clear Selection",
                   command=self._clear_selection).pack(pady=3, padx=5, fill=tk.X)
        
        # Export buttons
        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Label(left_panel, text="Export:", 
                  font=("", 9, "bold")).pack(anchor=tk.W, padx=5)
        
        ttk.Button(left_panel, text="Export CSV",
                   command=self._export_csv).pack(pady=3, padx=5, fill=tk.X)
        ttk.Button(left_panel, text="Export Annotated Video",
                   command=self._export_video).pack(pady=3, padx=5, fill=tk.X)
        

        # Center panel - Video display
        center_frame = ttk.Frame(main_frame)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Canvas for video
        self._canvas = tk.Canvas(center_frame, bg="black")
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Button-1>", self._on_canvas_click)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        
        # Frame slider
        slider_frame = ttk.Frame(center_frame)
        slider_frame.pack(fill=tk.X, pady=(5, 0))
        
        self._frame_label = ttk.Label(slider_frame, text="Frame: 0 / 0")
        self._frame_label.pack(side=tk.LEFT, padx=5)
        
        self._slider = ttk.Scale(slider_frame, from_=0, to=100,
                                  orient=tk.HORIZONTAL,
                                  command=self._on_slider_change)
        self._slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self._time_label = ttk.Label(slider_frame, text="0.00s")
        self._time_label.pack(side=tk.RIGHT, padx=5)
        
        # Playback controls
        play_frame = ttk.Frame(center_frame)
        play_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(play_frame, text="⏮", width=3,
                   command=self._goto_start).pack(side=tk.LEFT, padx=2)
        ttk.Button(play_frame, text="◀", width=3,
                   command=self._prev_frame).pack(side=tk.LEFT, padx=2)
        self._play_btn = ttk.Button(play_frame, text="▶ Play", width=8,
                                     command=self._toggle_play)
        self._play_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(play_frame, text="▶", width=3,
                   command=self._next_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(play_frame, text="⏭", width=3,
                   command=self._goto_end).pack(side=tk.LEFT, padx=2)
        
        self._playing = False
        

        # Right panel - Vehicle info
        right_panel = ttk.LabelFrame(main_frame, text="Detected Vehicles", width=250)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_panel.pack_propagate(False)
        
        # Vehicle list
        self._vehicle_listbox = tk.Listbox(right_panel, selectmode=tk.MULTIPLE,
                                            height=20)
        self._vehicle_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self._vehicle_listbox.bind("<<ListboxSelect>>", self._on_vehicle_select)
        
        # Distance info
        self._info_text = tk.Text(right_panel, height=8, state=tk.DISABLED,
                                   wrap=tk.WORD, font=("Courier", 9))
        self._info_text.pack(fill=tk.X, padx=5, pady=5)
        
        # Status bar
        self._status_var = tk.StringVar(value="Ready. Open a video to begin.")
        status_bar = ttk.Label(self.root, textvariable=self._status_var,
                               relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Progress bar
        self._progress = ttk.Progressbar(self.root, mode='determinate')
        self._progress.pack(side=tk.BOTTOM, fill=tk.X, padx=5)
    

    # --- Video Loading ---
    
    def _open_video(self):
        """Open a video file dialog."""
        filetypes = [
            ("Video files", "*.avi *.mp4 *.mkv *.mov *.wmv"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(
            title="Open Video File",
            filetypes=filetypes,
        )
        if path:
            self._load_video(path)
    
    def _load_video(self, path: str):
        """Load a video file."""
        if self._cap is not None:
            self._cap.release()
        
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            messagebox.showerror("Error", f"Cannot open video:\n{path}")
            return
        
        self._video_path = path
        self._fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Update slider range
        self._slider.configure(to=max(self._frame_count - 1, 1))
        self._current_frame_idx = 0
        
        # Reset analysis state
        self._all_tracks = {}
        self._all_distances = []
        self._all_lanes = []
        self._selected_vehicle_ids = set()
        self._analysis_complete = False
        self._vehicle_listbox.delete(0, tk.END)
        
        # Auto-detect if quad view (aspect ratio check)
        # Quad views typically have 2:1-ish sub-views
        self._detect_quad_view(width, height)
        
        # Update camera config for detected resolution
        self._update_camera_for_resolution(width, height)
        
        # Show first frame
        self._goto_frame(0)
        
        duration = self._frame_count / self._fps
        self._status_var.set(
            f"Loaded: {Path(path).name} | {width}x{height} | "
            f"{self._fps:.1f} fps | {self._frame_count} frames | "
            f"{duration:.1f}s"
        )
    
    def _detect_quad_view(self, width: int, height: int):
        """Try to detect if the video is a quad-view composite."""
        # Read first frame and check for dividing lines
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = self._cap.read()
        if not ret:
            return
        
        # Check for dark horizontal/vertical lines near center
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        
        # Check vertical line
        v_band = frame[:, cx-2:cx+2, :].mean()
        # Check horizontal line
        h_band = frame[cy-2:cy+2, :, :].mean()
        
        # Check if sub-views have different content
        tl = frame[0:cy, 0:cx]
        tr = frame[0:cy, cx:w]
        bl = frame[cy:h, 0:cx]
        br = frame[cy:h, cx:w]
        
        # Count active quadrants (not black)
        active_count = sum(1 for q in [tl, tr, bl, br] 
                          if q.mean() > 5 and q.std() > 10)
        
        if active_count >= 2 and (v_band < 30 or h_band < 30):
            self._is_quad_view = True
            self._status_var.set("Quad-view detected. Select a view to analyze.")
        else:
            self._is_quad_view = False
            self._view_var.set("full")
    

    def _update_camera_for_resolution(self, width: int, height: int):
        """Update camera model based on detected video resolution."""
        from ..core.config import CameraConfig, AppConfig, DistanceConfig
        from ..core.camera_model import CameraModel
        
        preset = self._preset_var.get()
        
        # Determine effective resolution (sub-view or full)
        if self._view_var.get() != "full":
            eff_w = width // 2
            eff_h = height // 2
        else:
            eff_w = width
            eff_h = height
        
        if preset == "Axis F2015-RE":
            config = CameraConfig(
                focal_length_mm=3.1,
                hfov_degrees=108.0,
                vfov_degrees=58.0,
                image_width=eff_w,
                image_height=eff_h,
                mount_height_m=float(self._mount_h_var.get() or "1.4"),
                tilt_degrees=float(self._tilt_var.get() or "0.0"),
            )
        elif preset == "Auto-Estimate":
            # Estimate FOV from resolution and common sensor sizes
            # Assume a typical 1/3" sensor (4.8mm x 3.6mm) as fallback
            config = self._auto_estimate_camera(eff_w, eff_h)
        else:  # Custom
            config = CameraConfig(
                focal_length_mm=3.1,  # Not used directly - FOV overrides
                hfov_degrees=float(self._hfov_var.get() or "90.0"),
                vfov_degrees=float(self._vfov_var.get() or "60.0"),
                image_width=eff_w,
                image_height=eff_h,
                mount_height_m=float(self._mount_h_var.get() or "1.4"),
                tilt_degrees=float(self._tilt_var.get() or "0.0"),
            )
        
        self._camera_config = config
        self._camera_model = CameraModel(config)
    
    def _auto_estimate_camera(self, width: int, height: int):
        """
        Auto-estimate camera parameters from resolution.
        
        Uses heuristics based on common IP camera configurations:
        - Standard HD (1280x720, 1920x1080): typically 90-110 deg HFOV
        - For wide-angle (>100 deg), focal is short (2-4mm)
        - For normal view (60-90 deg), focal is medium (4-12mm)
        
        Without lens info, assumes a moderate wide-angle (~90 deg HFOV)
        which is common for vehicle-mounted cameras.
        """
        from ..core.config import CameraConfig
        
        # Default: assume 90 degree HFOV (common for dashcams/vehicle cams)
        # and calculate VFOV from aspect ratio
        hfov = 90.0
        aspect = width / height
        vfov = 2.0 * np.degrees(np.arctan(np.tan(np.radians(hfov/2.0)) / aspect))
        
        return CameraConfig(
            focal_length_mm=3.5,  # Approximate, not used directly
            hfov_degrees=hfov,
            vfov_degrees=vfov,
            image_width=width,
            image_height=height,
            mount_height_m=float(self._mount_h_var.get() or "1.4"),
            tilt_degrees=float(self._tilt_var.get() or "0.0"),
        )
    

    # --- Frame Navigation ---
    
    def _goto_frame(self, idx: int):
        """Navigate to a specific frame and display it."""
        if self._cap is None:
            return
        
        idx = max(0, min(idx, self._frame_count - 1))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self._cap.read()
        
        if not ret:
            return
        
        self._current_frame_idx = idx
        self._current_frame = frame
        
        # Extract the selected view
        display = self._extract_view(frame)
        
        # Overlay annotations if analysis is done
        if self._analysis_complete and idx in self._all_tracks:
            display = self._annotate_display(display, idx)
        
        self._display_frame = display
        self._update_canvas(display)
        self._update_frame_info(idx)
    
    def _extract_view(self, frame: np.ndarray) -> np.ndarray:
        """Extract the selected view from the frame."""
        view = self._view_var.get()
        
        if view == "full":
            return frame.copy()
        
        # Always split at center when a quadrant is selected,
        # regardless of auto-detection result
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        
        if view == "top_left":
            return frame[0:cy, 0:cx].copy()
        elif view == "top_right":
            return frame[0:cy, cx:w].copy()
        elif view == "bottom_left":
            return frame[cy:h, 0:cx].copy()
        elif view == "bottom_right":
            return frame[cy:h, cx:w].copy()
        
        return frame.copy()
    
    def _annotate_display(self, frame: np.ndarray, idx: int) -> np.ndarray:
        """Add detection/distance annotations to the display frame."""
        from ..export.video_export import FrameAnnotator
        
        annotator = FrameAnnotator(
            selected_ids=self._selected_vehicle_ids,
            show_all_boxes=True,
            show_distance=self._analysis_complete,
            show_lanes=True,
            show_lane_distance=True,
        )
        
        fd = None
        if idx < len(self._all_distances):
            fd = self._all_distances[idx]
        
        lr = None
        if idx < len(self._all_lanes):
            lr = self._all_lanes[idx]
        
        tracks = self._all_tracks.get(idx, [])
        
        return annotator.annotate_frame(frame, fd, lr, tracks)
    
    def _update_canvas(self, frame: np.ndarray):
        """Display a frame on the canvas, scaled to fit."""
        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()
        
        if canvas_w < 10 or canvas_h < 10:
            return
        
        h, w = frame.shape[:2]
        
        # Scale to fit canvas while maintaining aspect ratio
        scale = min(canvas_w / w, canvas_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        resized = cv2.resize(frame, (new_w, new_h))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        
        self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        
        # Center on canvas
        x_offset = (canvas_w - new_w) // 2
        y_offset = (canvas_h - new_h) // 2
        
        self._canvas.delete("all")
        self._canvas.create_image(x_offset, y_offset, 
                                   anchor=tk.NW, image=self._photo)
        
        # Store scaling info for click mapping
        self._display_scale = scale
        self._display_offset = (x_offset, y_offset)
        self._display_size = (new_w, new_h)
    
    def _update_frame_info(self, idx: int):
        """Update frame label and slider."""
        self._frame_label.configure(
            text=f"Frame: {idx} / {self._frame_count - 1}")
        
        time_sec = idx / self._fps
        self._time_label.configure(text=f"{time_sec:.2f}s")
        
        # Update slider without triggering callback
        self._slider.set(idx)
        
        # Update distance info for selected vehicles
        self._update_info_panel(idx)
    

    def _on_slider_change(self, value):
        """Handle slider movement."""
        idx = int(float(value))
        if idx != self._current_frame_idx:
            self._goto_frame(idx)
    
    def _prev_frame(self):
        self._goto_frame(self._current_frame_idx - 1)
    
    def _next_frame(self):
        self._goto_frame(self._current_frame_idx + 1)
    
    def _goto_start(self):
        self._goto_frame(0)
    
    def _goto_end(self):
        self._goto_frame(self._frame_count - 1)
    
    def _toggle_play(self):
        """Toggle playback."""
        self._playing = not self._playing
        if self._playing:
            self._play_btn.configure(text="⏸ Pause")
            self._play_loop()
        else:
            self._play_btn.configure(text="▶ Play")
    
    def _play_loop(self):
        """Playback loop."""
        if not self._playing:
            return
        
        if self._current_frame_idx >= self._frame_count - 1:
            self._playing = False
            self._play_btn.configure(text="▶ Play")
            return
        
        self._goto_frame(self._current_frame_idx + 1)
        
        # Schedule next frame (approximate real-time)
        delay_ms = max(1, int(1000 / self._fps))
        self.root.after(delay_ms, self._play_loop)
    
    def _on_canvas_resize(self, event):
        """Re-draw frame when canvas resizes."""
        if self._display_frame is not None:
            self._update_canvas(self._display_frame)
    

    # --- Vehicle Selection ---
    
    def _on_canvas_click(self, event):
        """Handle click on canvas to select/deselect vehicles."""
        if not self._analysis_complete:
            return
        
        # Map canvas click to frame coordinates
        if not hasattr(self, '_display_scale'):
            return
        
        # Convert canvas coords to frame coords
        frame_x = (event.x - self._display_offset[0]) / self._display_scale
        frame_y = (event.y - self._display_offset[1]) / self._display_scale
        
        # Check if click is inside any bounding box
        idx = self._current_frame_idx
        if idx not in self._all_tracks:
            return
        
        for track in self._all_tracks[idx]:
            x1, y1, x2, y2 = track.bbox
            if x1 <= frame_x <= x2 and y1 <= frame_y <= y2:
                # Toggle selection
                if track.track_id in self._selected_vehicle_ids:
                    self._selected_vehicle_ids.discard(track.track_id)
                else:
                    self._selected_vehicle_ids.add(track.track_id)
                
                # Refresh display
                display = self._extract_view(self._current_frame)
                display = self._annotate_display(display, idx)
                self._display_frame = display
                self._update_canvas(display)
                self._update_vehicle_list()
                self._update_info_panel(idx)
                break
    
    def _on_vehicle_select(self, event):
        """Handle vehicle list selection."""
        selection = self._vehicle_listbox.curselection()
        self._selected_vehicle_ids.clear()
        
        for i in selection:
            text = self._vehicle_listbox.get(i)
            # Extract ID from "ID:X - class"
            try:
                vid = int(text.split("ID:")[1].split(" ")[0])
                self._selected_vehicle_ids.add(vid)
            except (IndexError, ValueError):
                pass
        
        # Refresh display
        if self._current_frame is not None:
            display = self._extract_view(self._current_frame)
            if self._analysis_complete:
                display = self._annotate_display(display, self._current_frame_idx)
            self._display_frame = display
            self._update_canvas(display)
    
    def _select_all_vehicles(self):
        """Select all detected vehicles."""
        for i in range(self._vehicle_listbox.size()):
            self._vehicle_listbox.selection_set(i)
        self._on_vehicle_select(None)
    
    def _clear_selection(self):
        """Clear vehicle selection."""
        self._selected_vehicle_ids.clear()
        self._vehicle_listbox.selection_clear(0, tk.END)
        
        if self._current_frame is not None:
            display = self._extract_view(self._current_frame)
            if self._analysis_complete:
                display = self._annotate_display(display, self._current_frame_idx)
            self._display_frame = display
            self._update_canvas(display)
    
    def _update_vehicle_list(self):
        """Update the vehicle listbox with all detected track IDs."""
        self._vehicle_listbox.delete(0, tk.END)
        
        # Collect all unique vehicle IDs across frames
        all_ids = set()
        id_info = {}
        
        for tracks in self._all_tracks.values():
            for track in tracks:
                if track.track_id not in all_ids:
                    all_ids.add(track.track_id)
                    id_info[track.track_id] = track.class_name
        
        for vid in sorted(all_ids):
            cls = id_info.get(vid, "unknown")
            self._vehicle_listbox.insert(tk.END, f"ID:{vid} - {cls}")
            
            # Re-select if was selected
            if vid in self._selected_vehicle_ids:
                self._vehicle_listbox.selection_set(tk.END)
    
    def _update_info_panel(self, frame_idx: int):
        """Update the info text panel with current frame distances."""
        self._info_text.configure(state=tk.NORMAL)
        self._info_text.delete("1.0", tk.END)
        
        if frame_idx < len(self._all_distances):
            fd = self._all_distances[frame_idx]
            
            for vd in fd.vehicles:
                if not self._selected_vehicle_ids or vd.track_id in self._selected_vehicle_ids:
                    self._info_text.insert(tk.END,
                        f"ID:{vd.track_id} {vd.class_name}\n"
                        f"  Dist fwd: {vd.distance_m:.1f}m\n"
                        f"  Ego lat:  {vd.lateral_offset_m:.1f}m\n"
                    )
                    if vd.lane_offset_left_m is not None:
                        self._info_text.insert(tk.END,
                            f"  L.lane:   {vd.lane_offset_left_m:.1f}m\n")
                    if vd.lane_offset_right_m is not None:
                        self._info_text.insert(tk.END,
                            f"  R.lane:   {vd.lane_offset_right_m:.1f}m\n")
                    self._info_text.insert(tk.END, "\n")
            
            if fd.lane:
                self._info_text.insert(tk.END, "--- Lane ---\n")
                if fd.lane.left_lane_offset_m is not None:
                    self._info_text.insert(tk.END, 
                        f"  Left:  {fd.lane.left_lane_offset_m:.1f}m\n")
                if fd.lane.right_lane_offset_m is not None:
                    self._info_text.insert(tk.END, 
                        f"  Right: {fd.lane.right_lane_offset_m:.1f}m\n")
        
        self._info_text.configure(state=tk.DISABLED)
    

    # --- View/Preset Callbacks ---
    
    def _on_view_change(self):
        """Handle view selection change."""
        if self._cap is not None:
            # Recalculate camera for new effective resolution
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._update_camera_for_resolution(w, h)
            
            # Clear analysis if view changed
            self._all_tracks = {}
            self._all_distances = []
            self._all_lanes = []
            self._analysis_complete = False
            self._vehicle_listbox.delete(0, tk.END)
            self._selected_vehicle_ids.clear()
            
            # Redisplay current frame
            self._goto_frame(self._current_frame_idx)
    
    def _on_preset_change(self, event=None):
        """Handle camera preset change."""
        preset = self._preset_var.get()
        
        if preset == "Custom":
            self._custom_cam_frame.pack(fill=tk.X, pady=5)
        else:
            self._custom_cam_frame.pack_forget()
        
        if preset == "Axis F2015-RE":
            self._hfov_var.set("108.0")
            self._vfov_var.set("58.0")
        elif preset == "Auto-Estimate":
            # Will be computed when resolution is known
            pass
        
        # Update camera model if video is loaded
        if self._cap is not None:
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._update_camera_for_resolution(w, h)
    

    # --- Analysis ---
    
    def _run_detection(self):
        """Run vehicle detection and tracking on all frames."""
        if self._cap is None:
            messagebox.showwarning("No Video", "Please open a video first.")
            return
        
        # Confirm before running (can take time)
        result = messagebox.askyesno(
            "Run Detection",
            f"This will process {self._frame_count} frames.\n"
            f"Estimated time: {self._frame_count / 30:.0f} - {self._frame_count / 10:.0f} seconds.\n\n"
            f"Continue?"
        )
        if not result:
            return
        
        self._status_var.set("Running detection... please wait.")
        self._progress['value'] = 0
        self.root.update()
        
        # Run in thread to keep UI responsive
        thread = threading.Thread(target=self._detection_worker, daemon=True)
        thread.start()
    
    def _detection_worker(self):
        """Background worker for detection/tracking."""
        from ..detection.vehicle_detector import VehicleDetector
        from ..detection.tracker import VehicleTracker
        from ..detection.lane_detector import LaneDetector
        from ..detection.distance_estimator import DistanceEstimator
        from ..core.config import DistanceConfig
        
        try:
            # Initialize models
            detector = VehicleDetector(
                model_path="yolov8n.pt",
                confidence_threshold=0.5,
            )
            tracker = VehicleTracker(max_age=30, min_hits=3, iou_threshold=0.4)
            lane_det = LaneDetector()
            
            dist_config = DistanceConfig()
            dist_est = DistanceEstimator(self._camera_model, dist_config)
            
            # Get effective image dimensions
            if self._view_var.get() != "full":
                w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) // 2
            else:
                w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            
            self._all_tracks = {}
            self._all_distances = []
            self._all_lanes = []
            
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            
            for idx in range(self._frame_count):
                ret, frame = self._cap.read()
                if not ret:
                    break
                
                # Extract selected view
                view_frame = self._extract_view(frame)
                
                # Detect vehicles
                detections = detector.detect(view_frame)
                tracks = tracker.update(detections)
                
                # Detect lanes
                lane_result = lane_det.detect(view_frame)
                
                # Estimate distances
                timestamp = idx / self._fps
                frame_dist = dist_est.estimate_frame(
                    idx, timestamp, tracks, lane_result, w
                )
                
                # Store results
                self._all_tracks[idx] = list(tracks)
                self._all_distances.append(frame_dist)
                self._all_lanes.append(lane_result)
                
                # Update progress (on main thread)
                if idx % 10 == 0:
                    progress = (idx + 1) / self._frame_count * 100
                    self.root.after(0, self._update_progress, progress, idx)
            
            self._analysis_complete = True
            self.root.after(0, self._detection_complete)
            
        except Exception as e:
            import traceback
            error_detail = f"{str(e)}\n\nFull traceback:\n{traceback.format_exc()}"
            print(error_detail, file=sys.stderr)  # Print to console if visible
            self.root.after(0, self._detection_error, error_detail)
    
    def _update_progress(self, value: float, frame_idx: int):
        """Update progress bar (called on main thread)."""
        self._progress['value'] = value
        self._status_var.set(f"Processing frame {frame_idx}/{self._frame_count}...")
    
    def _detection_complete(self):
        """Called when detection finishes."""
        self._progress['value'] = 100
        self._status_var.set(
            f"Detection complete! "
            f"Found vehicles in {sum(1 for t in self._all_tracks.values() if t)} frames. "
            f"Click on vehicles to select them."
        )
        self._update_vehicle_list()
        # Refresh current frame with annotations
        self._goto_frame(self._current_frame_idx)
    
    def _detection_error(self, error_msg: str):
        """Called when detection fails."""
        self._progress['value'] = 0
        self._status_var.set(f"Detection failed: {error_msg}")
        messagebox.showerror("Detection Error", f"Detection failed:\n{error_msg}")
    

    # --- Export ---
    
    def _export_csv(self):
        """Export CSV data for selected vehicles."""
        if not self._analysis_complete:
            messagebox.showwarning("No Data", 
                                   "Run detection first before exporting.")
            return
        
        if not self._selected_vehicle_ids:
            result = messagebox.askyesno(
                "No Selection",
                "No vehicles selected. Export data for ALL vehicles?"
            )
            if not result:
                return
            selected = None
        else:
            selected = self._selected_vehicle_ids
        
        # Ask for output directory
        output_dir = filedialog.askdirectory(title="Select Output Directory")
        if not output_dir:
            return
        
        from ..export.csv_export import CSVExporter
        
        exporter = CSVExporter(output_dir=output_dir)
        
        # Export vehicle distances
        csv_path = exporter.export_vehicle_distances(
            self._all_distances, selected
        )
        
        # Export lane distances
        lane_path = exporter.export_lane_distances(self._all_distances)
        
        # Export summary
        summary_path = exporter.export_summary(
            self._all_distances, selected
        )
        
        messagebox.showinfo("Export Complete",
            f"CSV files exported to:\n{output_dir}\n\n"
            f"Files:\n- vehicle_distances.csv\n- lane_distances.csv\n- analysis_summary.csv"
        )
        self._status_var.set(f"CSV exported to {output_dir}")
    
    def _export_video(self):
        """Export annotated video replay."""
        if not self._analysis_complete:
            messagebox.showwarning("No Data",
                                   "Run detection first before exporting.")
            return
        
        # Ask for output path
        output_path = filedialog.asksaveasfilename(
            title="Save Annotated Video",
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("AVI Video", "*.avi")],
        )
        if not output_path:
            return
        
        self._status_var.set("Exporting annotated video...")
        self._progress['value'] = 0
        self.root.update()
        
        # Run export in background
        thread = threading.Thread(
            target=self._video_export_worker, 
            args=(output_path,),
            daemon=True,
        )
        thread.start()
    
    def _video_export_worker(self, output_path: str):
        """Background worker for video export."""
        from ..export.video_export import FrameAnnotator
        
        try:
            annotator = FrameAnnotator(
                selected_ids=self._selected_vehicle_ids if self._selected_vehicle_ids else None,
                show_all_boxes=True,
                show_distance=True,
                show_lanes=True,
                show_lane_distance=True,
            )
            
            # Determine output resolution
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, first_frame = self._cap.read()
            if not ret:
                return
            
            view_frame = self._extract_view(first_frame)
            h, w = view_frame.shape[:2]
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, self._fps, (w, h))
            
            if not writer.isOpened():
                self.root.after(0, messagebox.showerror, "Error", 
                               "Cannot create output video file.")
                return
            
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            
            for idx in range(self._frame_count):
                ret, frame = self._cap.read()
                if not ret:
                    break
                
                view_frame = self._extract_view(frame)
                
                # Get annotations
                fd = self._all_distances[idx] if idx < len(self._all_distances) else None
                lr = self._all_lanes[idx] if idx < len(self._all_lanes) else None
                tracks = self._all_tracks.get(idx, [])
                
                annotated = annotator.annotate_frame(view_frame, fd, lr, tracks)
                writer.write(annotated)
                
                if idx % 30 == 0:
                    progress = (idx + 1) / self._frame_count * 100
                    self.root.after(0, self._update_progress, progress, idx)
            
            writer.release()
            self.root.after(0, self._video_export_complete, output_path)
            
        except Exception as e:
            self.root.after(0, self._detection_error, str(e))
    
    def _video_export_complete(self, output_path: str):
        """Called when video export finishes."""
        self._progress['value'] = 100
        self._status_var.set(f"Video exported: {output_path}")
        messagebox.showinfo("Export Complete",
                           f"Annotated video saved to:\n{output_path}")
    

    # --- Main ---
    
    def run(self):
        """Start the application main loop."""
        self.root.mainloop()
        
        # Cleanup
        if self._cap is not None:
            self._cap.release()


def main():
    """Entry point for the application."""
    app = VideoAnalysisApp()
    app.run()


if __name__ == "__main__":
    main()
