#!/usr/bin/env python3
"""
Axis F1194 Distance Overlay Tool

Captures a snapshot from an Axis encoder channel, detects green tape lines
on the road, generates a transparent overlay image with distance markers,
and uploads it to the encoder via VAPIX API.

Usage: Run the executable or script - a GUI will appear.
"""

import sys
import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk
import requests
from requests.auth import HTTPDigestAuth


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_CONFIG = {
    "encoder_ips": ["195.0.100.1", "195.0.100.2"],
    "username": "root",
    "password": "root",
    "distances_meters": [0, 5, 10],
    "tape_color_hsv_lower": [35, 80, 80],
    "tape_color_hsv_upper": [85, 255, 255],
    "overlay_line_color": [255, 255, 255, 200],
    "overlay_text_color": [255, 255, 255, 255],
    "overlay_line_thickness": 3,
    "overlay_font_size": 24,
    "min_tape_width_ratio": 0.15,
    "snapshot_timeout": 10
}



def load_config():
    """Load configuration from config.json or use defaults."""
    config_path = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))) 
    config_file = config_path / "config.json"
    
    # Also check next to the executable
    exe_dir = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
    config_file_exe = exe_dir / "config.json"
    
    config = DEFAULT_CONFIG.copy()
    
    for cf in [config_file_exe, config_file]:
        if cf.exists():
            try:
                with open(cf, 'r') as f:
                    user_config = json.load(f)
                config.update(user_config)
                break
            except (json.JSONDecodeError, IOError):
                pass
    
    return config


# =============================================================================
# AXIS VAPIX API FUNCTIONS
# =============================================================================

class AxisEncoder:
    """Interface to Axis encoder via VAPIX API."""
    
    def __init__(self, ip, username, password, timeout=10):
        self.ip = ip
        self.base_url = f"http://{ip}"
        self.auth = HTTPDigestAuth(username, password)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = self.auth


    def test_connection(self):
        """Test if we can reach the encoder."""
        try:
            resp = self.session.get(
                f"{self.base_url}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi",
                json={"apiVersion": "1.0", "method": "getSupportedVersions"},
                timeout=self.timeout
            )
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def capture_snapshot(self, camera=1):
        """Capture a JPEG snapshot from the specified camera channel."""
        url = f"{self.base_url}/axis-cgi/jpg/image.cgi?camera={camera}"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        img_array = np.frombuffer(resp.content, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img

    def get_resolution(self, camera=1):
        """Get the resolution of the specified camera channel."""
        img = self.capture_snapshot(camera)
        if img is not None:
            h, w = img.shape[:2]
            return w, h
        return None, None


    def upload_overlay_image(self, image_path, scale_to_resolution=True):
        """Upload a PNG overlay image to the encoder."""
        url = f"{self.base_url}/axis-cgi/uploadoverlayimage.cgi"
        
        json_params = json.dumps({
            "apiVersion": "1.0",
            "method": "uploadOverlayImage",
            "params": {
                "scaleToResolution": scale_to_resolution
            }
        })
        
        with open(image_path, 'rb') as img_file:
            files = {
                'json': ('request.json', json_params, 'application/json'),
                'image': (os.path.basename(image_path), img_file, 'image/png')
            }
            resp = self.session.post(url, files=files, timeout=self.timeout)
        
        resp.raise_for_status()
        result = resp.json()
        
        if 'error' in result:
            raise RuntimeError(f"Upload failed: {result['error']['message']}")
        
        return result['data']['path']

    def add_image_overlay(self, camera, overlay_path, position=None):
        """Add an image overlay to a camera channel."""
        url = f"{self.base_url}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi"
        
        params = {
            "camera": camera,
            "overlayPath": overlay_path
        }
        if position:
            params["position"] = position
        
        payload = {
            "apiVersion": "1.0",
            "method": "addImage",
            "params": params
        }
        
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        result = resp.json()
        
        if 'error' in result:
            raise RuntimeError(f"Add overlay failed: {result['error']['message']}")
        
        return result['data']['identity']


    def list_overlays(self):
        """List all current overlays on the encoder."""
        url = f"{self.base_url}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi"
        payload = {
            "apiVersion": "1.0",
            "method": "list",
            "params": {}
        }
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def remove_overlay(self, identity):
        """Remove an overlay by identity."""
        url = f"{self.base_url}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi"
        payload = {
            "apiVersion": "1.0",
            "method": "remove",
            "params": {"identity": identity}
        }
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        result = resp.json()
        if 'error' in result:
            raise RuntimeError(f"Remove failed: {result['error']['message']}")

    def remove_all_image_overlays(self):
        """Remove all existing image overlays."""
        result = self.list_overlays()
        if 'data' in result and 'imageOverlays' in result['data']:
            for overlay in result['data']['imageOverlays']:
                try:
                    self.remove_overlay(overlay['identity'])
                except RuntimeError:
                    pass


# =============================================================================
# GREEN TAPE DETECTION
# =============================================================================


class TapeDetector:
    """Detects horizontal green tape lines in an image."""
    
    def __init__(self, config):
        self.hsv_lower = np.array(config["tape_color_hsv_lower"])
        self.hsv_upper = np.array(config["tape_color_hsv_upper"])
        self.min_width_ratio = config["min_tape_width_ratio"]
    
    def detect_lines(self, image):
        """
        Detect horizontal green tape lines in the image.
        
        Returns a list of y-coordinates (center of each detected tape line),
        sorted from top to bottom.
        """
        h, w = image.shape[:2]
        
        # Convert to HSV for color detection
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Create mask for green color
        mask = cv2.inRange(hsv, self.hsv_lower, self.hsv_upper)
        
        # Morphological operations to clean up noise
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 10, 3))
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        
        # Close small gaps
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_clean)
        # Emphasize horizontal structures
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_h)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, 
                                        cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter contours by width (must span significant portion of image)
        min_width = w * self.min_width_ratio
        line_centers = []
        
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if cw >= min_width and ch < h * 0.15:  # Wide but not too tall
                center_y = y + ch // 2
                line_centers.append(center_y)
        
        # Sort from top to bottom
        line_centers.sort()
        
        # Merge lines that are very close together (within 2% of image height)
        merged = []
        merge_threshold = h * 0.02
        for y_pos in line_centers:
            if merged and abs(y_pos - merged[-1]) < merge_threshold:
                merged[-1] = (merged[-1] + y_pos) // 2  # Average
            else:
                merged.append(y_pos)
        
        return merged, mask



# =============================================================================
# OVERLAY IMAGE GENERATION
# =============================================================================

class OverlayGenerator:
    """Generates transparent PNG overlay images with distance markers."""
    
    def __init__(self, config):
        self.line_color = tuple(config["overlay_line_color"])
        self.text_color = tuple(config["overlay_text_color"])
        self.line_thickness = config["overlay_line_thickness"]
        self.font_size = config["overlay_font_size"]
    
    def generate_overlay(self, width, height, line_positions, distances):
        """
        Generate a transparent PNG overlay image.
        
        Args:
            width: Image width in pixels
            height: Image height in pixels
            line_positions: List of y-coordinates for the lines
            distances: List of distance labels (matching line_positions)
        
        Returns:
            PIL Image object (RGBA)
        """
        # Create transparent image
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Try to load a reasonable font
        font = self._get_font()
        
        for y_pos, distance in zip(line_positions, distances):
            # Draw horizontal line spanning full width
            for t in range(self.line_thickness):
                y = y_pos + t - self.line_thickness // 2
                if 0 <= y < height:
                    draw.line([(0, y), (width - 1, y)], fill=self.line_color)
            
            # Draw distance label
            label = f"{distance}m"
            # Position text to the right side with some padding
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
            
            text_x = width - text_w - 20  # 20px padding from right
            text_y = y_pos - text_h - 5   # Just above the line
            
            # Draw text background for readability
            bg_padding = 4
            draw.rectangle(
                [text_x - bg_padding, text_y - bg_padding,
                 text_x + text_w + bg_padding, text_y + text_h + bg_padding],
                fill=(0, 0, 0, 150)
            )
            
            # Draw text
            draw.text((text_x, text_y), label, fill=self.text_color, font=font)
        
        return overlay


    def _get_font(self):
        """Get a suitable font for the overlay text."""
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/consola.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]
        
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, self.font_size)
                except (IOError, OSError):
                    continue
        
        # Fallback to default font
        try:
            return ImageFont.truetype("arial.ttf", self.font_size)
        except (IOError, OSError):
            return ImageFont.load_default()

    def save_overlay(self, overlay_image, filepath):
        """Save the overlay as a PNG file."""
        overlay_image.save(filepath, 'PNG')
        return filepath


# =============================================================================
# GUI APPLICATION
# =============================================================================

class DistanceOverlayApp:
    """Main GUI application for the distance overlay tool."""
    
    def __init__(self):
        self.config = load_config()
        self.encoder = None
        self.detector = TapeDetector(self.config)
        self.generator = OverlayGenerator(self.config)
        self.current_snapshot = None
        self.detected_lines = []
        self.manual_lines = []
        
        self._build_gui()


    def _build_gui(self):
        """Build the main application window."""
        self.root = tk.Tk()
        self.root.title("Axis Distance Overlay Tool")
        self.root.geometry("1000x750")
        self.root.resizable(True, True)
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Connection Frame ---
        conn_frame = ttk.LabelFrame(main_frame, text="Encoder Connection", padding=10)
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        # IP Selection
        ttk.Label(conn_frame, text="Encoder IP:").grid(row=0, column=0, sticky=tk.W)
        self.ip_var = tk.StringVar()
        ip_options = self.config["encoder_ips"] + ["Custom..."]
        self.ip_combo = ttk.Combobox(conn_frame, textvariable=self.ip_var, 
                                      values=ip_options, width=20)
        self.ip_combo.grid(row=0, column=1, padx=5)
        self.ip_combo.set(self.config["encoder_ips"][0])
        self.ip_combo.bind("<<ComboboxSelected>>", self._on_ip_selected)
        
        # Custom IP entry
        self.custom_ip_var = tk.StringVar()
        self.custom_ip_entry = ttk.Entry(conn_frame, textvariable=self.custom_ip_var, 
                                          width=20)
        self.custom_ip_entry.grid(row=0, column=2, padx=5)
        self.custom_ip_entry.grid_remove()  # Hidden by default
        
        # Camera channel
        ttk.Label(conn_frame, text="Camera:").grid(row=0, column=3, padx=(20, 0))
        self.camera_var = tk.IntVar(value=1)
        camera_spin = ttk.Spinbox(conn_frame, from_=1, to=4, width=5,
                                   textvariable=self.camera_var)
        camera_spin.grid(row=0, column=4, padx=5)
        
        # Connect button
        self.connect_btn = ttk.Button(conn_frame, text="Connect & Capture",
                                       command=self._connect_and_capture)
        self.connect_btn.grid(row=0, column=5, padx=20)


        # --- Image Display Frame ---
        img_frame = ttk.LabelFrame(main_frame, text="Snapshot & Detection", padding=5)
        img_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Canvas for image display
        self.canvas = tk.Canvas(img_frame, bg='gray20', cursor='crosshair')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        
        # --- Controls Frame ---
        ctrl_frame = ttk.LabelFrame(main_frame, text="Controls", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Detection controls
        ttk.Button(ctrl_frame, text="Auto-Detect Lines",
                   command=self._auto_detect).grid(row=0, column=0, padx=5)
        ttk.Button(ctrl_frame, text="Clear Lines",
                   command=self._clear_lines).grid(row=0, column=1, padx=5)
        
        ttk.Separator(ctrl_frame, orient=tk.VERTICAL).grid(
            row=0, column=2, sticky='ns', padx=15)
        
        # Manual mode hint
        ttk.Label(ctrl_frame, text="Manual: Click image to add lines",
                  foreground='gray').grid(row=0, column=3, padx=5)
        
        ttk.Separator(ctrl_frame, orient=tk.VERTICAL).grid(
            row=0, column=4, sticky='ns', padx=15)
        
        # Apply overlay
        self.apply_btn = ttk.Button(ctrl_frame, text="Generate & Apply Overlay",
                                     command=self._apply_overlay)
        self.apply_btn.grid(row=0, column=5, padx=5)
        
        # Remove existing overlays
        ttk.Button(ctrl_frame, text="Remove All Overlays",
                   command=self._remove_overlays).grid(row=0, column=6, padx=5)


        # --- Distance Assignment Frame ---
        dist_frame = ttk.LabelFrame(main_frame, text="Distance Assignment", padding=10)
        dist_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(dist_frame, 
                  text="Assign distances to detected lines (top to bottom):").pack(
                      anchor=tk.W)
        
        self.dist_list_frame = ttk.Frame(dist_frame)
        self.dist_list_frame.pack(fill=tk.X, pady=5)
        
        self.distance_entries = []
        
        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Ready. Select encoder IP and click Connect.")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, 
                               relief=tk.SUNKEN, padding=5)
        status_bar.pack(fill=tk.X)
        
        # Image display state
        self.display_image = None
        self.display_scale = 1.0
        self.photo_image = None

    def _on_ip_selected(self, event=None):
        """Handle IP combobox selection."""
        if self.ip_var.get() == "Custom...":
            self.custom_ip_entry.grid()
        else:
            self.custom_ip_entry.grid_remove()

    def _get_selected_ip(self):
        """Get the currently selected IP address."""
        if self.ip_var.get() == "Custom...":
            ip = self.custom_ip_var.get().strip()
            if not ip:
                messagebox.showerror("Error", "Please enter a custom IP address.")
                return None
            return ip
        return self.ip_var.get()


    def _connect_and_capture(self):
        """Connect to encoder and capture a snapshot."""
        ip = self._get_selected_ip()
        if not ip:
            return
        
        camera = self.camera_var.get()
        self.status_var.set(f"Connecting to {ip}, camera {camera}...")
        self.root.update()
        
        try:
            self.encoder = AxisEncoder(
                ip, 
                self.config["username"], 
                self.config["password"],
                timeout=self.config["snapshot_timeout"]
            )
            
            # Test connection
            if not self.encoder.test_connection():
                messagebox.showerror("Connection Failed",
                    f"Cannot connect to encoder at {ip}.\n"
                    "Check IP address, network connection, and credentials.")
                self.status_var.set("Connection failed.")
                return
            
            # Capture snapshot
            self.current_snapshot = self.encoder.capture_snapshot(camera)
            if self.current_snapshot is None:
                messagebox.showerror("Error", "Failed to capture snapshot.")
                self.status_var.set("Snapshot capture failed.")
                return
            
            h, w = self.current_snapshot.shape[:2]
            self.status_var.set(
                f"Connected to {ip} | Camera {camera} | "
                f"Resolution: {w}x{h} | Click Auto-Detect or click image manually")
            
            self._display_snapshot()
            self._clear_lines()
            
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Connection Error", f"Network error: {str(e)}")
            self.status_var.set("Connection error.")


    def _display_snapshot(self, lines=None):
        """Display the current snapshot on the canvas with optional line overlays."""
        if self.current_snapshot is None:
            return
        
        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(self.current_snapshot, cv2.COLOR_BGR2RGB)
        
        # Draw detected lines on the display
        if lines:
            for y_pos in lines:
                cv2.line(img_rgb, (0, y_pos), (img_rgb.shape[1] - 1, y_pos),
                         (255, 50, 50), 2)
                # Draw small label
                cv2.putText(img_rgb, f"y={y_pos}", (10, y_pos - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 50, 50), 1)
        
        # Scale to fit canvas
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        if canvas_w < 10 or canvas_h < 10:
            canvas_w = 900
            canvas_h = 500
        
        img_h, img_w = img_rgb.shape[:2]
        scale_w = canvas_w / img_w
        scale_h = canvas_h / img_h
        self.display_scale = min(scale_w, scale_h)
        
        new_w = int(img_w * self.display_scale)
        new_h = int(img_h * self.display_scale)
        
        img_resized = cv2.resize(img_rgb, (new_w, new_h))
        
        # Convert to PhotoImage
        pil_img = Image.fromarray(img_resized)
        self.photo_image = ImageTk.PhotoImage(pil_img)
        
        # Display on canvas
        self.canvas.delete("all")
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, 
                                  image=self.photo_image, anchor=tk.CENTER)
        
        # Store offset for click coordinate mapping
        self.img_offset_x = (canvas_w - new_w) // 2
        self.img_offset_y = (canvas_h - new_h) // 2


    def _on_canvas_click(self, event):
        """Handle manual line placement by clicking on the image."""
        if self.current_snapshot is None:
            return
        
        # Convert canvas click to image coordinates
        img_x = event.x - self.img_offset_x
        img_y = event.y - self.img_offset_y
        
        # Convert from display scale to actual image coordinates
        actual_y = int(img_y / self.display_scale)
        
        h = self.current_snapshot.shape[0]
        if actual_y < 0 or actual_y >= h:
            return
        
        self.manual_lines.append(actual_y)
        self.manual_lines.sort()
        
        # Update display
        all_lines = sorted(set(self.detected_lines + self.manual_lines))
        self._display_snapshot(lines=all_lines)
        self._update_distance_entries(all_lines)
        self.status_var.set(
            f"Manual line added at y={actual_y} | "
            f"Total lines: {len(all_lines)}")

    def _auto_detect(self):
        """Run automatic green tape detection."""
        if self.current_snapshot is None:
            messagebox.showwarning("No Image", 
                                    "Capture a snapshot first.")
            return
        
        self.status_var.set("Detecting green tape lines...")
        self.root.update()
        
        lines, mask = self.detector.detect_lines(self.current_snapshot)
        
        if not lines:
            messagebox.showinfo("No Lines Detected",
                "No green tape lines were detected.\n\n"
                "Try:\n"
                "- Ensuring tape is visible and well-lit\n"
                "- Adjusting HSV color range in config.json\n"
                "- Using manual mode (click on image)")
            self.status_var.set("Auto-detection found no lines. Use manual mode.")
            return
        
        self.detected_lines = lines
        all_lines = sorted(set(self.detected_lines + self.manual_lines))
        
        self._display_snapshot(lines=all_lines)
        self._update_distance_entries(all_lines)
        self.status_var.set(
            f"Auto-detected {len(lines)} line(s). "
            f"Assign distances below, then click 'Generate & Apply'.")


    def _clear_lines(self):
        """Clear all detected and manual lines."""
        self.detected_lines = []
        self.manual_lines = []
        self._display_snapshot()
        self._update_distance_entries([])
        self.status_var.set("Lines cleared.")

    def _update_distance_entries(self, lines):
        """Update the distance entry widgets to match detected lines."""
        # Clear existing entries
        for widget in self.dist_list_frame.winfo_children():
            widget.destroy()
        self.distance_entries = []
        
        if not lines:
            ttk.Label(self.dist_list_frame, 
                      text="No lines detected yet.").pack(anchor=tk.W)
            return
        
        # Default distances from config
        default_distances = self.config["distances_meters"]
        
        for i, y_pos in enumerate(lines):
            frame = ttk.Frame(self.dist_list_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=f"Line {i+1} (y={y_pos}):").pack(
                side=tk.LEFT, padx=(0, 10))
            
            dist_var = tk.StringVar()
            if i < len(default_distances):
                dist_var.set(str(default_distances[i]))
            else:
                dist_var.set(str(i * 5))
            
            entry = ttk.Entry(frame, textvariable=dist_var, width=8)
            entry.pack(side=tk.LEFT)
            ttk.Label(frame, text="meters").pack(side=tk.LEFT, padx=5)
            
            # Delete button for this line
            del_btn = ttk.Button(frame, text="X", width=3,
                                  command=lambda idx=i: self._remove_line(idx))
            del_btn.pack(side=tk.LEFT, padx=10)
            
            self.distance_entries.append((y_pos, dist_var))


    def _remove_line(self, index):
        """Remove a specific line by index."""
        all_lines = sorted(set(self.detected_lines + self.manual_lines))
        if index < len(all_lines):
            y_to_remove = all_lines[index]
            if y_to_remove in self.detected_lines:
                self.detected_lines.remove(y_to_remove)
            if y_to_remove in self.manual_lines:
                self.manual_lines.remove(y_to_remove)
        
        all_lines = sorted(set(self.detected_lines + self.manual_lines))
        self._display_snapshot(lines=all_lines)
        self._update_distance_entries(all_lines)

    def _apply_overlay(self):
        """Generate overlay image and upload to encoder."""
        if self.encoder is None:
            messagebox.showerror("Error", "Not connected to encoder.")
            return
        
        if not self.distance_entries:
            messagebox.showerror("Error", "No lines defined. Detect or add lines first.")
            return
        
        # Gather line positions and distances
        line_positions = []
        distances = []
        
        for y_pos, dist_var in self.distance_entries:
            try:
                dist_val = float(dist_var.get())
            except ValueError:
                messagebox.showerror("Error", 
                    f"Invalid distance value: '{dist_var.get()}'")
                return
            line_positions.append(y_pos)
            distances.append(dist_val)
        
        camera = self.camera_var.get()
        h, w = self.current_snapshot.shape[:2]
        
        self.status_var.set("Generating overlay image...")
        self.root.update()
        
        try:
            # Generate overlay
            overlay_img = self.generator.generate_overlay(
                w, h, line_positions, distances)
            
            # Save to temp file
            temp_dir = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
            overlay_path = temp_dir / f"overlay_camera{camera}.png"
            self.generator.save_overlay(overlay_img, str(overlay_path))
            
            self.status_var.set("Uploading overlay to encoder...")
            self.root.update()
            
            # Upload to encoder
            ovl_path = self.encoder.upload_overlay_image(
                str(overlay_path), scale_to_resolution=False)
            
            # Apply overlay to camera channel
            identity = self.encoder.add_image_overlay(camera, ovl_path)
            
            self.status_var.set(
                f"Overlay applied successfully! Camera {camera}, "
                f"ID: {identity}, Path: {ovl_path}")
            
            messagebox.showinfo("Success",
                f"Distance overlay applied to camera {camera}!\n\n"
                f"Overlay ID: {identity}\n"
                f"Lines: {len(line_positions)}\n"
                f"Distances: {[f'{d}m' for d in distances]}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply overlay:\n{str(e)}")
            self.status_var.set(f"Error: {str(e)}")


    def _remove_overlays(self):
        """Remove all image overlays from the encoder."""
        if self.encoder is None:
            messagebox.showerror("Error", "Not connected to encoder.")
            return
        
        if not messagebox.askyesno("Confirm", 
                "Remove ALL image overlays from this encoder?"):
            return
        
        try:
            self.encoder.remove_all_image_overlays()
            self.status_var.set("All image overlays removed.")
            messagebox.showinfo("Done", "All image overlays have been removed.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove overlays:\n{str(e)}")

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """Main entry point."""
    app = DistanceOverlayApp()
    app.run()


if __name__ == "__main__":
    main()
