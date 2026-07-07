#!/usr/bin/env python3
"""
Axis F1194 Distance Overlay Tool v2.0

Captures a snapshot from an Axis encoder channel, detects colored tape lines
on the road, generates a transparent overlay image with distance markers,
and uploads it to the encoder via VAPIX API.

Features:
- Eyedropper color picker for tape detection
- Adjustable detection sensitivity
- Per-line color selection
- Alphabetical line labels (A, B, C...)
- Two-point angled/vertical line support
- Extend lines to edges
- Quad view overlay support (cameras 1-4 + Quad)

Usage: Run the executable or script - a GUI will appear.
"""

import sys
import os
import json
import string
import math
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
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
    "tape_color_hsv_lower": [35, 50, 50],
    "tape_color_hsv_upper": [85, 255, 255],
    "hsv_tolerance": 25,
    "overlay_line_color": [255, 255, 255, 200],
    "overlay_text_color": [255, 255, 255, 255],
    "overlay_line_thickness": 3,
    "overlay_font_size": 24,
    "min_tape_width_ratio": 0.05,
    "min_tape_height_ratio": 0.005,
    "snapshot_timeout": 10
}

# Basic colors available for per-line overlay coloring
LINE_COLORS = {
    "White": (255, 255, 255, 220),
    "Red": (255, 50, 50, 220),
    "Green": (50, 255, 50, 220),
    "Blue": (80, 80, 255, 220),
    "Yellow": (255, 255, 50, 220),
    "Cyan": (50, 255, 255, 220),
    "Magenta": (255, 50, 255, 220),
    "Orange": (255, 165, 0, 220),
}



def load_config():
    """Load configuration from config.json or use defaults."""
    config_path = Path(getattr(sys, '_MEIPASS',
                               os.path.dirname(os.path.abspath(__file__))))
    config_file = config_path / "config.json"

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
# AXIS VAPIX API
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
            resp = self.session.post(
                f"{self.base_url}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi",
                json={"apiVersion": "1.0", "method": "getSupportedVersions"},
                timeout=self.timeout
            )
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def capture_snapshot(self, camera=1):
        """Capture a JPEG snapshot from the specified camera channel.
        camera can be 1-4 for individual channels, or 'quad' for the
        quad stream (camera=5 on F1194 multi-channel encoders).
        """
        if camera == "quad":
            # Quad view is typically camera 5 on multi-channel encoders
            # Try camera=5 first, fall back to quad=yes parameter
            url = f"{self.base_url}/axis-cgi/jpg/image.cgi?camera=5"
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    img_array = np.frombuffer(resp.content, dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        return img
            except requests.exceptions.RequestException:
                pass
            # Fallback: try quad=yes parameter
            url = (f"{self.base_url}/axis-cgi/jpg/image.cgi"
                   f"?camera=1&squarepixel=1&quad=yes")
        else:
            url = f"{self.base_url}/axis-cgi/jpg/image.cgi?camera={camera}"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        img_array = np.frombuffer(resp.content, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img


    def upload_overlay_image(self, image_path, scale_to_resolution=False):
        """Upload a PNG overlay image to the encoder."""
        url = f"{self.base_url}/axis-cgi/uploadoverlayimage.cgi"
        json_params = json.dumps({
            "apiVersion": "1.0",
            "method": "uploadOverlayImage",
            "params": {"scaleToResolution": scale_to_resolution}
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
        params = {"camera": camera, "overlayPath": overlay_path}
        if position:
            params["position"] = position
        payload = {"apiVersion": "1.0", "method": "addImage", "params": params}
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        result = resp.json()
        if 'error' in result:
            raise RuntimeError(
                f"Add overlay failed: {result['error']['message']}")
        return result['data']['identity']


    def list_overlays(self):
        """List all current overlays on the encoder."""
        url = f"{self.base_url}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi"
        payload = {"apiVersion": "1.0", "method": "list", "params": {}}
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def remove_overlay(self, identity):
        """Remove an overlay by identity."""
        url = f"{self.base_url}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi"
        payload = {"apiVersion": "1.0", "method": "remove",
                   "params": {"identity": identity}}
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
# TAPE DETECTION (with eyedropper support)
# =============================================================================

class TapeDetector:
    """Detects colored tape lines in an image using HSV filtering."""

    def __init__(self, config):
        self.hsv_lower = np.array(config["tape_color_hsv_lower"])
        self.hsv_upper = np.array(config["tape_color_hsv_upper"])
        self.min_width_ratio = config.get("min_tape_width_ratio", 0.05)
        self.min_height_ratio = config.get("min_tape_height_ratio", 0.005)

    def set_color_from_bgr(self, bgr_color, tolerance=25):
        """Set detection color from a BGR pixel value (eyedropper)."""
        pixel = np.uint8([[bgr_color]])
        hsv_pixel = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0][0]
        h, s, v = int(hsv_pixel[0]), int(hsv_pixel[1]), int(hsv_pixel[2])
        self.hsv_lower = np.array([
            max(0, h - tolerance),
            max(30, s - 60),
            max(30, v - 60)
        ])
        self.hsv_upper = np.array([
            min(179, h + tolerance),
            min(255, s + 60),
            min(255, v + 60)
        ])
        return self.hsv_lower.tolist(), self.hsv_upper.tolist()

    def detect_lines(self, image):
        """Detect colored tape lines in the image.
        Returns list of y-coordinates (horizontal lines) sorted top to bottom.
        """
        h, w = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.hsv_lower, self.hsv_upper)

        # Clean up with morphological operations
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_clean)

        # Use a smaller horizontal kernel for increased sensitivity
        kernel_w = max(w // 20, 10)
        kernel_h_struct = cv2.getStructuringElement(
            cv2.MORPH_RECT, (kernel_w, 2))
        mask_h = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_h_struct)

        contours, _ = cv2.findContours(
            mask_h, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_width = w * self.min_width_ratio
        line_centers = []

        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if cw >= min_width and ch < h * 0.2:
                center_y = y + ch // 2
                line_centers.append(center_y)

        line_centers.sort()

        # Merge nearby lines
        merged = []
        merge_threshold = h * 0.015
        for y_pos in line_centers:
            if merged and abs(y_pos - merged[-1]) < merge_threshold:
                merged[-1] = (merged[-1] + y_pos) // 2
            else:
                merged.append(y_pos)

        return merged, mask



# =============================================================================
# LINE DATA STRUCTURE
# =============================================================================

class OverlayLine:
    """Represents a single overlay line defined by two points."""

    def __init__(self, pt1, pt2, label="A", color_name="White",
                 extend_left=True, extend_right=True):
        self.pt1 = pt1  # (x, y) tuple
        self.pt2 = pt2  # (x, y) tuple
        self.label = label
        self.color_name = color_name
        self.extend_left = extend_left
        self.extend_right = extend_right

    @property
    def color_rgba(self):
        return LINE_COLORS.get(self.color_name, LINE_COLORS["White"])

    def get_extended_points(self, img_width, img_height, bounds=None):
        """Calculate line endpoints, optionally extended to boundaries.

        When extended, the line is projected to whichever boundary
        it hits first (top, bottom, left, or right).

        Args:
            img_width: Full image width
            img_height: Full image height
            bounds: Optional (x_min, y_min, x_max, y_max) tuple defining
                    the region the line should be constrained to.
                    If None, uses full image (0, 0, img_width-1, img_height-1).
        """
        x1, y1 = self.pt1
        x2, y2 = self.pt2
        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            return self.pt1, self.pt2

        if not self.extend_left and not self.extend_right:
            return self.pt1, self.pt2

        # Determine boundary limits
        if bounds:
            bx_min, by_min, bx_max, by_max = bounds
        else:
            bx_min, by_min, bx_max, by_max = 0, 0, img_width - 1, img_height - 1

        # Vertical line (dx == 0)
        if dx == 0:
            top = (x1, by_min) if self.extend_left else self.pt1
            bot = (x1, by_max) if self.extend_right else self.pt2
            return top, bot

        # Horizontal line (dy == 0)
        if dy == 0:
            left = (bx_min, y1) if self.extend_left else self.pt1
            right = (bx_max, y1) if self.extend_right else self.pt2
            return left, right

        # General case: angled line - find intersection with boundaries
        def clip_to_boundary(px, py, vx, vy):
            """From point (px,py) going in direction (vx,vy), find where
            it hits the boundary. Returns the boundary point."""
            candidates = []
            # Left edge: x=bx_min
            if vx != 0:
                t = (bx_min - px) / vx
                if t > 0:
                    yy = py + t * vy
                    if by_min <= yy <= by_max:
                        candidates.append((t, (bx_min, int(yy))))
            # Right edge: x=bx_max
            if vx != 0:
                t = (bx_max - px) / vx
                if t > 0:
                    yy = py + t * vy
                    if by_min <= yy <= by_max:
                        candidates.append((t, (bx_max, int(yy))))
            # Top edge: y=by_min
            if vy != 0:
                t = (by_min - py) / vy
                if t > 0:
                    xx = px + t * vx
                    if bx_min <= xx <= bx_max:
                        candidates.append((t, (int(xx), by_min)))
            # Bottom edge: y=by_max
            if vy != 0:
                t = (by_max - py) / vy
                if t > 0:
                    xx = px + t * vx
                    if bx_min <= xx <= bx_max:
                        candidates.append((t, (int(xx), by_max)))
            if candidates:
                candidates.sort(key=lambda c: c[0])
                return candidates[0][1]
            return (int(px), int(py))

        # Extend left: go backward from pt1
        if self.extend_left:
            left_pt = clip_to_boundary(x1, y1, -dx, -dy)
        else:
            left_pt = self.pt1

        # Extend right: go forward from pt2
        if self.extend_right:
            right_pt = clip_to_boundary(x2, y2, dx, dy)
        else:
            right_pt = self.pt2

        return left_pt, right_pt

    def is_vertical(self):
        """Check if line is approximately vertical."""
        dx = abs(self.pt2[0] - self.pt1[0])
        dy = abs(self.pt2[1] - self.pt1[1])
        return dy > dx * 3 if dx > 0 else True



# =============================================================================
# OVERLAY IMAGE GENERATION
# =============================================================================

class OverlayGenerator:
    """Generates transparent PNG overlay images with line markers."""

    def __init__(self, config):
        self.line_thickness = config["overlay_line_thickness"]
        self.font_size = config["overlay_font_size"]
        self.text_color = tuple(config["overlay_text_color"])

    def generate_overlay(self, width, height, lines, quad_mode=False):
        """Generate a transparent PNG overlay from OverlayLine objects.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            lines: List of OverlayLine objects
            quad_mode: If True, clamp line extensions to their quadrant

        Returns:
            PIL Image object (RGBA)
        """
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = self._get_font()

        for line in lines:
            color = line.color_rgba

            # Determine bounds for extension
            if quad_mode:
                bounds = self._get_quadrant_bounds(line, width, height)
            else:
                bounds = None

            pt_a, pt_b = line.get_extended_points(width, height, bounds)

            # Draw the line with thickness
            draw.line([pt_a, pt_b], fill=color, width=self.line_thickness)

            # Draw label on the line itself (right side for horizontal,
            # beside for vertical)
            label = line.label
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            if line.is_vertical():
                # Place label beside the line, near the top of the drawn segment
                text_x = pt_a[0] + 8
                text_y = pt_a[1] + 10
            else:
                # Place label at the right end of the drawn line, just above
                text_x = pt_b[0] - text_w - 10
                # Calculate y at that x position along the line
                if pt_b[0] != pt_a[0]:
                    t = (text_x - pt_a[0]) / (pt_b[0] - pt_a[0])
                    line_y_at_label = int(pt_a[1] + t * (pt_b[1] - pt_a[1]))
                else:
                    line_y_at_label = pt_b[1]
                text_y = line_y_at_label - text_h - 4

            # Clamp to image bounds
            text_x = max(2, min(width - text_w - 2, text_x))
            text_y = max(2, min(height - text_h - 2, text_y))

            # Background box for readability
            bg_pad = 3
            draw.rectangle(
                [text_x - bg_pad, text_y - bg_pad,
                 text_x + text_w + bg_pad, text_y + text_h + bg_pad],
                fill=(0, 0, 0, 160)
            )
            draw.text((text_x, text_y), label, fill=self.text_color, font=font)

        return overlay


    def _get_quadrant_bounds(self, line, width, height):
        """Determine which quadrant the line's center belongs to and return
        the boundary box (x_min, y_min, x_max, y_max) for that quadrant.

        Quad layout:
            Top-Left (cam 1)     | Top-Right (cam 2)
            -----------------------------------------
            Bottom-Left (cam 3)  | Bottom-Right (cam 4)
        """
        mid_x = width // 2
        mid_y = height // 2

        # Use the midpoint of the line's two defined points
        center_x = (line.pt1[0] + line.pt2[0]) // 2
        center_y = (line.pt1[1] + line.pt2[1]) // 2

        if center_x < mid_x and center_y < mid_y:
            # Top-left quadrant
            return (0, 0, mid_x - 1, mid_y - 1)
        elif center_x >= mid_x and center_y < mid_y:
            # Top-right quadrant
            return (mid_x, 0, width - 1, mid_y - 1)
        elif center_x < mid_x and center_y >= mid_y:
            # Bottom-left quadrant
            return (0, mid_y, mid_x - 1, height - 1)
        else:
            # Bottom-right quadrant
            return (mid_x, mid_y, width - 1, height - 1)

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

        # Line management
        self.lines = []  # List of OverlayLine objects
        self.next_label_idx = 0

        # Click mode state
        self.click_mode = "line"  # "line", "eyedropper"
        self.pending_point = None  # First point of a two-point line

        # Display state
        self.display_scale = 1.0
        self.photo_image = None
        self.img_offset_x = 0
        self.img_offset_y = 0

        self._build_gui()


    def _build_gui(self):
        """Build the main application window."""
        self.root = tk.Tk()
        self.root.title("Axis Distance Overlay Tool v2.0")
        self.root.geometry("1100x820")
        self.root.resizable(True, True)

        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Connection Frame ---
        conn_frame = ttk.LabelFrame(main_frame, text="Encoder Connection",
                                     padding=10)
        conn_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(conn_frame, text="Encoder IP:").grid(
            row=0, column=0, sticky=tk.W)
        self.ip_var = tk.StringVar()
        ip_options = self.config["encoder_ips"] + ["Custom..."]
        self.ip_combo = ttk.Combobox(conn_frame, textvariable=self.ip_var,
                                      values=ip_options, width=18)
        self.ip_combo.grid(row=0, column=1, padx=5)
        self.ip_combo.set(self.config["encoder_ips"][0])
        self.ip_combo.bind("<<ComboboxSelected>>", self._on_ip_selected)

        self.custom_ip_var = tk.StringVar()
        self.custom_ip_entry = ttk.Entry(conn_frame,
                                          textvariable=self.custom_ip_var,
                                          width=18)
        self.custom_ip_entry.grid(row=0, column=2, padx=5)
        self.custom_ip_entry.grid_remove()

        # Camera channel (1-4 + Quad)
        ttk.Label(conn_frame, text="Camera:").grid(
            row=0, column=3, padx=(15, 0))
        self.camera_var = tk.StringVar(value="1")
        camera_combo = ttk.Combobox(
            conn_frame, textvariable=self.camera_var,
            values=["1", "2", "3", "4", "Quad"], width=6, state="readonly")
        camera_combo.grid(row=0, column=4, padx=5)

        self.connect_btn = ttk.Button(conn_frame, text="Connect & Capture",
                                       command=self._connect_and_capture)
        self.connect_btn.grid(row=0, column=5, padx=15)


        # --- Image Display Frame ---
        img_frame = ttk.LabelFrame(main_frame, text="Snapshot & Lines",
                                    padding=5)
        img_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.canvas = tk.Canvas(img_frame, bg='gray20', cursor='crosshair')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        # --- Tools Frame ---
        tools_frame = ttk.LabelFrame(main_frame, text="Tools", padding=8)
        tools_frame.pack(fill=tk.X, pady=(0, 8))

        # Click mode selector
        ttk.Label(tools_frame, text="Click Mode:").grid(
            row=0, column=0, padx=(0, 5))

        self.mode_var = tk.StringVar(value="line")
        ttk.Radiobutton(tools_frame, text="Add Line (2 clicks)",
                        variable=self.mode_var, value="line").grid(
                            row=0, column=1, padx=5)
        ttk.Radiobutton(tools_frame, text="Eyedropper (pick color)",
                        variable=self.mode_var, value="eyedropper").grid(
                            row=0, column=2, padx=5)

        ttk.Separator(tools_frame, orient=tk.VERTICAL).grid(
            row=0, column=3, sticky='ns', padx=12)

        # Auto-detect
        ttk.Button(tools_frame, text="Auto-Detect Lines",
                   command=self._auto_detect).grid(row=0, column=4, padx=5)

        # Sensitivity slider
        ttk.Label(tools_frame, text="Sensitivity:").grid(
            row=0, column=5, padx=(10, 2))
        self.sensitivity_var = tk.IntVar(value=50)
        sens_scale = ttk.Scale(tools_frame, from_=10, to=100,
                               variable=self.sensitivity_var,
                               orient=tk.HORIZONTAL, length=100)
        sens_scale.grid(row=0, column=6, padx=5)

        ttk.Separator(tools_frame, orient=tk.VERTICAL).grid(
            row=0, column=7, sticky='ns', padx=12)

        ttk.Button(tools_frame, text="Clear All Lines",
                   command=self._clear_lines).grid(row=0, column=8, padx=5)

        ttk.Separator(tools_frame, orient=tk.VERTICAL).grid(
            row=0, column=9, sticky='ns', padx=12)

        ttk.Button(tools_frame, text="Generate & Apply Overlay",
                   command=self._apply_overlay).grid(row=0, column=10, padx=5)
        ttk.Button(tools_frame, text="Remove All Overlays",
                   command=self._remove_overlays).grid(row=0, column=11, padx=5)


        # --- Eyedropper status ---
        self.eyedropper_frame = ttk.Frame(tools_frame)
        self.eyedropper_frame.grid(row=1, column=0, columnspan=12,
                                    sticky=tk.W, pady=(5, 0))
        self.eyedropper_label = ttk.Label(
            self.eyedropper_frame,
            text="Eyedropper: Click on tape in image to set detection color")
        self.eyedropper_label.pack(side=tk.LEFT)

        self.color_sample = tk.Label(self.eyedropper_frame, text="  ",
                                      bg="#00AA00", width=4)
        self.color_sample.pack(side=tk.LEFT, padx=10)

        ttk.Label(self.eyedropper_frame, text="HSV Tolerance:").pack(
            side=tk.LEFT, padx=(10, 2))
        self.tolerance_var = tk.IntVar(
            value=self.config.get("hsv_tolerance", 25))
        ttk.Spinbox(self.eyedropper_frame, from_=5, to=60, width=4,
                    textvariable=self.tolerance_var).pack(side=tk.LEFT)

        # --- Line List Frame ---
        line_frame = ttk.LabelFrame(main_frame, text="Lines (alphabetical)",
                                     padding=8)
        line_frame.pack(fill=tk.X, pady=(0, 8))

        # Scrollable line list
        self.line_list_frame = ttk.Frame(line_frame)
        self.line_list_frame.pack(fill=tk.X)

        # --- Status Bar ---
        self.status_var = tk.StringVar(
            value="Ready. Select encoder IP and click Connect & Capture.")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var,
                               relief=tk.SUNKEN, padding=5)
        status_bar.pack(fill=tk.X)


    # =========================================================================
    # CONNECTION & CAPTURE
    # =========================================================================

    def _on_ip_selected(self, event=None):
        if self.ip_var.get() == "Custom...":
            self.custom_ip_entry.grid()
        else:
            self.custom_ip_entry.grid_remove()

    def _get_selected_ip(self):
        if self.ip_var.get() == "Custom...":
            ip = self.custom_ip_var.get().strip()
            if not ip:
                messagebox.showerror("Error",
                                     "Please enter a custom IP address.")
                return None
            return ip
        return self.ip_var.get()

    def _get_camera_value(self):
        """Get camera value - int for 1-4, 'quad' for Quad."""
        val = self.camera_var.get()
        if val.lower() == "quad":
            return "quad"
        return int(val)

    def _connect_and_capture(self):
        """Connect to encoder and capture a snapshot."""
        ip = self._get_selected_ip()
        if not ip:
            return

        camera = self._get_camera_value()
        camera_display = "Quad" if camera == "quad" else f"{camera}"
        self.status_var.set(
            f"Connecting to {ip}, camera {camera_display}...")
        self.root.update()

        try:
            self.encoder = AxisEncoder(
                ip, self.config["username"], self.config["password"],
                timeout=self.config["snapshot_timeout"])

            if not self.encoder.test_connection():
                messagebox.showerror("Connection Failed",
                    f"Cannot connect to encoder at {ip}.\n"
                    "Check IP address, network, and credentials.")
                self.status_var.set("Connection failed.")
                return

            self.current_snapshot = self.encoder.capture_snapshot(camera)
            if self.current_snapshot is None:
                messagebox.showerror("Error", "Failed to capture snapshot.")
                self.status_var.set("Snapshot capture failed.")
                return

            h, w = self.current_snapshot.shape[:2]
            self.status_var.set(
                f"Connected to {ip} | Camera {camera_display} | "
                f"{w}x{h} | Use tools to add lines")
            self._display_snapshot()
            self._clear_lines()

        except requests.exceptions.RequestException as e:
            messagebox.showerror("Connection Error",
                                 f"Network error: {str(e)}")
            self.status_var.set("Connection error.")


    # =========================================================================
    # DISPLAY
    # =========================================================================

    def _display_snapshot(self):
        """Display the current snapshot with all lines drawn."""
        if self.current_snapshot is None:
            return

        img_rgb = cv2.cvtColor(self.current_snapshot, cv2.COLOR_BGR2RGB)
        h, w = img_rgb.shape[:2]

        # Draw all lines on preview
        is_quad = (self._get_camera_value() == "quad")
        for line in self.lines:
            # In quad mode, clamp to quadrant boundaries
            if is_quad:
                bounds = self.generator._get_quadrant_bounds(line, w, h)
            else:
                bounds = None
            pt_a, pt_b = line.get_extended_points(w, h, bounds)
            # Convert RGBA to RGB for cv2
            color_rgb = line.color_rgba[:3]
            cv2.line(img_rgb, pt_a, pt_b, color_rgb, 2)
            # Place label at the right end of the line (or top for vertical)
            if line.is_vertical():
                label_x = pt_a[0] + 8
                label_y = pt_a[1] + 20
            else:
                label_x = pt_b[0] - 40
                # Calculate y on line at label_x
                if pt_b[0] != pt_a[0]:
                    t = (label_x - pt_a[0]) / (pt_b[0] - pt_a[0])
                    label_y = int(pt_a[1] + t * (pt_b[1] - pt_a[1])) - 8
                else:
                    label_y = pt_b[1] - 8
            label_x = max(5, min(w - 50, label_x))
            label_y = max(15, min(h - 5, label_y))
            cv2.putText(img_rgb, line.label, (label_x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_rgb, 2)

        # Draw pending point (first click of two-point line)
        if self.pending_point:
            px, py = self.pending_point
            cv2.circle(img_rgb, (px, py), 6, (255, 255, 0), 2)
            cv2.putText(img_rgb, "Click 2nd point", (px + 10, py - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        # Scale to fit canvas
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            canvas_w, canvas_h = 950, 450

        scale_w = canvas_w / w
        scale_h = canvas_h / h
        self.display_scale = min(scale_w, scale_h)

        new_w = int(w * self.display_scale)
        new_h = int(h * self.display_scale)
        img_resized = cv2.resize(img_rgb, (new_w, new_h))

        pil_img = Image.fromarray(img_resized)
        self.photo_image = ImageTk.PhotoImage(pil_img)

        self.canvas.delete("all")
        self.canvas.create_image(canvas_w // 2, canvas_h // 2,
                                  image=self.photo_image, anchor=tk.CENTER)
        self.img_offset_x = (canvas_w - new_w) // 2
        self.img_offset_y = (canvas_h - new_h) // 2


    # =========================================================================
    # CANVAS CLICK HANDLING
    # =========================================================================

    def _canvas_to_image_coords(self, event):
        """Convert canvas click coordinates to image pixel coordinates."""
        img_x = event.x - self.img_offset_x
        img_y = event.y - self.img_offset_y
        actual_x = int(img_x / self.display_scale)
        actual_y = int(img_y / self.display_scale)
        return actual_x, actual_y

    def _on_canvas_click(self, event):
        """Handle canvas click based on current mode."""
        if self.current_snapshot is None:
            return

        actual_x, actual_y = self._canvas_to_image_coords(event)
        h, w = self.current_snapshot.shape[:2]

        # Bounds check
        if actual_x < 0 or actual_x >= w or actual_y < 0 or actual_y >= h:
            return

        mode = self.mode_var.get()

        if mode == "eyedropper":
            self._do_eyedropper(actual_x, actual_y)
        elif mode == "line":
            self._do_line_click(actual_x, actual_y)

    def _do_eyedropper(self, x, y):
        """Sample color at (x, y) and set as detection color."""
        bgr = self.current_snapshot[y, x].tolist()
        tolerance = self.tolerance_var.get()
        lower, upper = self.detector.set_color_from_bgr(bgr, tolerance)

        # Update color sample display
        r, g, b = bgr[2], bgr[1], bgr[0]
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        self.color_sample.configure(bg=hex_color)

        self.eyedropper_label.config(
            text=f"Eyedropper: Sampled BGR=({bgr[0]},{bgr[1]},{bgr[2]}) "
                 f"| HSV range: {lower} - {upper}")
        self.status_var.set(
            f"Color sampled at ({x},{y}). Now click Auto-Detect or "
            f"switch to Line mode.")

    def _do_line_click(self, x, y):
        """Handle two-point line placement."""
        if self.pending_point is None:
            # First click
            self.pending_point = (x, y)
            self.status_var.set(
                f"First point at ({x},{y}). Click second point to "
                f"complete line.")
            self._display_snapshot()
        else:
            # Second click - create the line
            pt1 = self.pending_point
            pt2 = (x, y)
            self.pending_point = None

            label = self._get_next_label()
            line = OverlayLine(pt1, pt2, label=label,
                               color_name="White",
                               extend_left=False, extend_right=False)
            self.lines.append(line)

            self._display_snapshot()
            self._update_line_list()
            self.status_var.set(
                f"Line {label} added: ({pt1[0]},{pt1[1]}) -> "
                f"({pt2[0]},{pt2[1]})")


    # =========================================================================
    # LINE MANAGEMENT
    # =========================================================================

    def _get_next_label(self):
        """Get next alphabetical label (A, B, C... Z, AA, AB...)."""
        idx = self.next_label_idx
        self.next_label_idx += 1
        if idx < 26:
            return string.ascii_uppercase[idx]
        else:
            first = string.ascii_uppercase[(idx // 26) - 1]
            second = string.ascii_uppercase[idx % 26]
            return first + second

    def _clear_lines(self):
        """Clear all lines."""
        self.lines = []
        self.next_label_idx = 0
        self.pending_point = None
        self._display_snapshot()
        self._update_line_list()
        self.status_var.set("All lines cleared.")

    def _auto_detect(self):
        """Run automatic tape detection."""
        if self.current_snapshot is None:
            messagebox.showwarning("No Image", "Capture a snapshot first.")
            return

        # Adjust sensitivity: lower ratio = more sensitive
        sensitivity = self.sensitivity_var.get()
        self.detector.min_width_ratio = max(0.02, (100 - sensitivity) / 1000.0)

        self.status_var.set("Detecting tape lines...")
        self.root.update()

        lines_y, mask = self.detector.detect_lines(self.current_snapshot)

        if not lines_y:
            messagebox.showinfo("No Lines Detected",
                "No tape lines were detected.\n\n"
                "Try:\n"
                "- Use Eyedropper to sample the tape color\n"
                "- Increase sensitivity slider\n"
                "- Increase HSV tolerance\n"
                "- Use manual two-point line mode")
            self.status_var.set("No lines detected. Try eyedropper or manual.")
            return

        # Convert detected y-positions to full-width horizontal lines
        h, w = self.current_snapshot.shape[:2]
        for y_pos in lines_y:
            label = self._get_next_label()
            line = OverlayLine((0, y_pos), (w - 1, y_pos),
                               label=label, color_name="White",
                               extend_left=False, extend_right=False)
            self.lines.append(line)

        self._display_snapshot()
        self._update_line_list()
        self.status_var.set(
            f"Auto-detected {len(lines_y)} line(s). "
            f"Adjust colors/labels below.")


    def _update_line_list(self):
        """Rebuild the line list UI with per-line controls."""
        for widget in self.line_list_frame.winfo_children():
            widget.destroy()

        if not self.lines:
            ttk.Label(self.line_list_frame,
                      text="No lines yet. Use Auto-Detect or click "
                           "two points on the image.").pack(anchor=tk.W)
            return

        # Header row
        hdr = ttk.Frame(self.line_list_frame)
        hdr.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(hdr, text="Label", width=6, font=('', 8, 'bold')).pack(
            side=tk.LEFT)
        ttk.Label(hdr, text="Points", width=28, font=('', 8, 'bold')).pack(
            side=tk.LEFT)
        ttk.Label(hdr, text="Color", width=10, font=('', 8, 'bold')).pack(
            side=tk.LEFT)
        ttk.Label(hdr, text="Extend", width=12, font=('', 8, 'bold')).pack(
            side=tk.LEFT)

        for i, line in enumerate(self.lines):
            row = ttk.Frame(self.line_list_frame)
            row.pack(fill=tk.X, pady=1)

            # Label (editable)
            label_var = tk.StringVar(value=line.label)
            label_entry = ttk.Entry(row, textvariable=label_var, width=5)
            label_entry.pack(side=tk.LEFT, padx=(0, 5))
            label_entry.bind("<FocusOut>",
                             lambda e, idx=i, v=label_var:
                                 self._update_line_label(idx, v.get()))

            # Points display
            pts_text = (f"({line.pt1[0]},{line.pt1[1]}) -> "
                        f"({line.pt2[0]},{line.pt2[1]})")
            ttk.Label(row, text=pts_text, width=28).pack(side=tk.LEFT)

            # Color dropdown
            color_var = tk.StringVar(value=line.color_name)
            color_combo = ttk.Combobox(
                row, textvariable=color_var,
                values=list(LINE_COLORS.keys()), width=8, state="readonly")
            color_combo.pack(side=tk.LEFT, padx=5)
            color_combo.bind("<<ComboboxSelected>>",
                             lambda e, idx=i, v=color_var:
                                 self._update_line_color(idx, v.get()))

            # Extend checkboxes
            ext_frame = ttk.Frame(row)
            ext_frame.pack(side=tk.LEFT, padx=5)

            ext_l_var = tk.BooleanVar(value=line.extend_left)
            ttk.Checkbutton(ext_frame, text="L", variable=ext_l_var,
                            command=lambda idx=i, v=ext_l_var:
                                self._update_extend(idx, 'left', v.get())
                            ).pack(side=tk.LEFT)

            ext_r_var = tk.BooleanVar(value=line.extend_right)
            ttk.Checkbutton(ext_frame, text="R", variable=ext_r_var,
                            command=lambda idx=i, v=ext_r_var:
                                self._update_extend(idx, 'right', v.get())
                            ).pack(side=tk.LEFT)

            # Delete button
            ttk.Button(row, text="X", width=3,
                       command=lambda idx=i: self._remove_line(idx)).pack(
                           side=tk.LEFT, padx=10)


    def _update_line_label(self, idx, new_label):
        """Update label for a line."""
        if idx < len(self.lines) and new_label.strip():
            self.lines[idx].label = new_label.strip()
            self._display_snapshot()

    def _update_line_color(self, idx, color_name):
        """Update color for a line."""
        if idx < len(self.lines):
            self.lines[idx].color_name = color_name
            self._display_snapshot()

    def _update_extend(self, idx, side, value):
        """Update extend setting for a line."""
        if idx < len(self.lines):
            if side == 'left':
                self.lines[idx].extend_left = value
            else:
                self.lines[idx].extend_right = value
            self._display_snapshot()

    def _remove_line(self, idx):
        """Remove a specific line."""
        if idx < len(self.lines):
            self.lines.pop(idx)
            self._display_snapshot()
            self._update_line_list()


    # =========================================================================
    # OVERLAY GENERATION & UPLOAD
    # =========================================================================

    def _apply_overlay(self):
        """Generate overlay image and upload to encoder."""
        if self.encoder is None:
            messagebox.showerror("Error", "Not connected to encoder.")
            return

        if not self.lines:
            messagebox.showerror("Error",
                                 "No lines defined. Add lines first.")
            return

        camera = self._get_camera_value()
        h, w = self.current_snapshot.shape[:2]

        self.status_var.set("Generating overlay image...")
        self.root.update()

        try:
            is_quad = (camera == "quad")
            overlay_img = self.generator.generate_overlay(
                w, h, self.lines, quad_mode=is_quad)

            temp_dir = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
            cam_label = "quad" if camera == "quad" else str(camera)
            overlay_path = temp_dir / f"overlay_camera{cam_label}.png"
            self.generator.save_overlay(overlay_img, str(overlay_path))

            self.status_var.set("Uploading overlay to encoder...")
            self.root.update()

            ovl_path = self.encoder.upload_overlay_image(
                str(overlay_path), scale_to_resolution=False)

            # For quad, apply to camera 5 (quad view channel)
            if camera == "quad":
                identity = self.encoder.add_image_overlay(5, ovl_path)
                self.status_var.set(
                    f"Overlay applied to Quad view! ID: {identity}")
                messagebox.showinfo("Success",
                    f"Distance overlay applied to Quad view (camera 5)!\n\n"
                    f"Overlay ID: {identity}\n"
                    f"Lines: {len(self.lines)}")
            else:
                identity = self.encoder.add_image_overlay(camera, ovl_path)
                self.status_var.set(
                    f"Overlay applied! Camera {camera}, ID: {identity}")
                messagebox.showinfo("Success",
                    f"Overlay applied to camera {camera}!\n\n"
                    f"Overlay ID: {identity}\n"
                    f"Lines: {len(self.lines)}")

        except Exception as e:
            messagebox.showerror("Error",
                                 f"Failed to apply overlay:\n{str(e)}")
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
            messagebox.showinfo("Done",
                                "All image overlays have been removed.")
        except Exception as e:
            messagebox.showerror("Error",
                                 f"Failed to remove overlays:\n{str(e)}")

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
