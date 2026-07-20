#!/usr/bin/env python3
"""
Quad-Box Video Merger - GUI Version
====================================
Features:
- Up to 4 source videos with browse + preview thumbnails
- FULL source quadrant option (entire frame scaled to slot)
- Per-video time offsets
- Global frame range (start/end time)
- Output preview (single composite frame before full export)
- Save / Load presets (JSON)
- Codec selection
- Progress bar with live status
"""

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np

QUADRANT_NAMES = ["TL", "TR", "BL", "BR"]
SOURCE_QUADRANTS = ["TL", "TR", "BL", "BR", "FULL"]
VIDEO_SOURCES = ["1", "2", "3", "4"]
SYNC_MODES = ["Lock Time", "Lock Frame Rate"]
QUADRANT_LABELS = {"TL": "Top-Left", "TR": "Top-Right",
                   "BL": "Bottom-Left", "BR": "Bottom-Right"}


def time_to_seconds(time_str):
    if not time_str or not time_str.strip():
        return 0.0
    parts = time_str.strip().split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def extract_quadrant(frame, quadrant_name):
    if quadrant_name == "FULL":
        return frame.copy()
    h, w = frame.shape[:2]
    mid_y, mid_x = h // 2, w // 2
    if quadrant_name == "TL":
        return frame[0:mid_y, 0:mid_x]
    elif quadrant_name == "TR":
        return frame[0:mid_y, mid_x:w]
    elif quadrant_name == "BL":
        return frame[mid_y:h, 0:mid_x]
    elif quadrant_name == "BR":
        return frame[mid_y:h, mid_x:w]
    raise ValueError(f"Unknown quadrant: {quadrant_name}")


def frame_to_tk_image(frame, max_size=(200, 150)):
    h, w = frame.shape[:2]
    scale = min(max_size[0] / w, max_size[1] / h)
    frame_resized = cv2.resize(frame, (int(w * scale), int(h * scale)))
    img = Image.fromarray(frame_resized)
    return ImageTk.PhotoImage(img)



def build_output_frame(frames, mapping, output_size):
    out_w, out_h = output_size
    mid_x, mid_y = out_w // 2, out_h // 2
    quad_size = (mid_x, mid_y)
    output = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    for out_quad, (vid_idx, src_quad) in mapping.items():
        q = extract_quadrant(frames[vid_idx], src_quad)
        q = cv2.resize(q, quad_size)
        if out_quad == "TL":
            output[0:mid_y, 0:mid_x] = q
        elif out_quad == "TR":
            output[0:mid_y, mid_x:out_w] = q
        elif out_quad == "BL":
            output[mid_y:out_h, 0:mid_x] = q
        elif out_quad == "BR":
            output[mid_y:out_h, mid_x:out_w] = q
    return output


class QuadMergerApp:
    NUM_VIDEOS = 4

    def __init__(self, root):
        self.root = root
        self.root.title("Quad-Box Video Merger")
        self.root.resizable(True, True)

        # Video paths and metadata
        self.video_paths = [tk.StringVar() for _ in range(self.NUM_VIDEOS)]
        self.video_offsets = [tk.StringVar(value="") for _ in range(self.NUM_VIDEOS)]
        self.video_frames_rgb = [None] * self.NUM_VIDEOS
        self.video_infos = [{} for _ in range(self.NUM_VIDEOS)]

        # Output
        self.output_path = tk.StringVar()
        self.codec_var = tk.StringVar(value="MJPG")
        self.start_time_var = tk.StringVar(value="")
        self.end_time_var = tk.StringVar(value="")
        self.sync_mode_var = tk.StringVar(value="Lock Time")

        # Mapping
        self.mapping_vars = {}
        for i, q in enumerate(QUADRANT_NAMES):
            self.mapping_vars[q] = {
                "video": tk.StringVar(value=str(i // 2 + 1)),
                "quadrant": tk.StringVar(value=q),
            }

        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI BUILD                                                            #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._build_video_section(main)
        self._build_preview_section(main)
        self._build_mapping_section(main)
        self._build_output_section(main)
        self._build_action_section(main)


    def _build_video_section(self, parent):
        frame = ttk.LabelFrame(parent, text="1. Select Videos (Video 3 & 4 optional)", padding=8)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        colors = ["#1a53ff", "#138000", "#8B008B", "#B8600C"]
        labels = ["Video 1:", "Video 2:", "Video 3 (opt):", "Video 4 (opt):"]
        commands = [lambda i=i: self._browse_video(i) for i in range(self.NUM_VIDEOS)]

        self.video_info_labels = []
        for i in range(self.NUM_VIDEOS):
            r = i * 2
            color = colors[i]
            lbl = ttk.Label(frame, text=labels[i], foreground=color)
            lbl.grid(row=r, column=0, sticky="w", padx=(0, 5), pady=(4 if i > 0 else 0, 0))

            ttk.Entry(frame, textvariable=self.video_paths[i], width=40).grid(
                row=r, column=1, sticky="ew", pady=(4 if i > 0 else 0, 0))

            ttk.Button(frame, text="Browse...", command=commands[i]).grid(
                row=r, column=2, padx=(4, 0), pady=(4 if i > 0 else 0, 0))

            ttk.Label(frame, text="Offset:").grid(row=r, column=3, padx=(10, 2), pady=(4 if i > 0 else 0, 0))
            ttk.Entry(frame, textvariable=self.video_offsets[i], width=10).grid(
                row=r, column=4, pady=(4 if i > 0 else 0, 0))

            info = ttk.Label(frame, text="", foreground="gray", font=("", 8))
            info.grid(row=r + 1, column=0, columnspan=5, sticky="w")
            self.video_info_labels.append(info)

        # Offset hint
        ttk.Label(frame, text="Offset format: HH:MM:SS or MM:SS or seconds",
                  foreground="gray", font=("", 8)).grid(
            row=self.NUM_VIDEOS * 2, column=0, columnspan=5, sticky="w", pady=(4, 0))

    def _build_preview_section(self, parent):
        frame = ttk.LabelFrame(parent, text="2. Preview (First Frame)", padding=8)
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        colors = ["blue", "green", "purple", "darkorange"]
        self.preview_labels = []
        self.preview_img_refs = [None] * self.NUM_VIDEOS

        for i in range(self.NUM_VIDEOS):
            lbl = ttk.Label(frame, text=f"[Video {i+1}]", anchor="center",
                            width=22, relief="sunken")
            lbl.grid(row=0, column=i, padx=4)
            self.preview_labels.append(lbl)
            ttk.Label(frame, text=f"Video {i+1}", foreground=colors[i]).grid(row=1, column=i)


    def _build_mapping_section(self, parent):
        frame = ttk.LabelFrame(parent, text="3. Map Quadrants", padding=8)
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Output Slot", font=("", 9, "bold")).grid(row=0, column=0, padx=(0, 12))
        ttk.Label(frame, text="Source Video", font=("", 9, "bold")).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(frame, text="Source Quadrant", font=("", 9, "bold")).grid(row=0, column=2)

        diagram = "  TL | TR\n  ---|---\n  BL | BR\n\nFULL = whole frame"
        ttk.Label(frame, text=diagram, font=("Courier", 8), foreground="gray").grid(
            row=0, column=3, rowspan=5, padx=(24, 0), sticky="n")

        for i, q in enumerate(QUADRANT_NAMES):
            r = i + 1
            ttk.Label(frame, text=f"{QUADRANT_LABELS[q]} ({q})").grid(
                row=r, column=0, sticky="w", padx=(0, 12), pady=2)
            ttk.Combobox(frame, textvariable=self.mapping_vars[q]["video"],
                         values=VIDEO_SOURCES, width=6, state="readonly").grid(
                row=r, column=1, padx=(0, 12), pady=2)
            ttk.Combobox(frame, textvariable=self.mapping_vars[q]["quadrant"],
                         values=SOURCE_QUADRANTS, width=8, state="readonly").grid(
                row=r, column=2, pady=2)

    def _build_output_section(self, parent):
        frame = ttk.LabelFrame(parent, text="4. Output Settings", padding=8)
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        # Output file
        ttk.Label(frame, text="Output File:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Entry(frame, textvariable=self.output_path, width=44).grid(row=0, column=1, sticky="ew")
        ttk.Button(frame, text="Save As...", command=self._browse_output).grid(
            row=0, column=2, padx=(4, 0))

        # Codec
        ttk.Label(frame, text="Codec:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(6, 0))
        ttk.Combobox(frame, textvariable=self.codec_var,
                     values=["MJPG", "XVID", "DIVX", "mp4v"],
                     width=8, state="readonly").grid(row=1, column=1, sticky="w", pady=(6, 0))

        # Sync mode
        sync_frame = ttk.Frame(frame)
        sync_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(sync_frame, text="Sync Mode:").grid(row=0, column=0, padx=(0, 4))
        ttk.Combobox(sync_frame, textvariable=self.sync_mode_var,
                     values=SYNC_MODES, width=16, state="readonly").grid(row=0, column=1, padx=(0, 10))
        ttk.Label(sync_frame,
                  text="Lock Time = real-time sync (skips frames). "
                       "Lock Frame Rate = native playback (slow-mo preserved).",
                  foreground="gray", font=("", 8)).grid(row=0, column=2)

        # Frame range
        range_frame = ttk.Frame(frame)
        range_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(range_frame, text="Start Time:").grid(row=0, column=0, padx=(0, 4))
        ttk.Entry(range_frame, textvariable=self.start_time_var, width=10).grid(row=0, column=1, padx=(0, 16))
        ttk.Label(range_frame, text="End Time:").grid(row=0, column=2, padx=(0, 4))
        ttk.Entry(range_frame, textvariable=self.end_time_var, width=10).grid(row=0, column=3)
        ttk.Label(range_frame, text="(HH:MM:SS — leave blank for full video)",
                  foreground="gray", font=("", 8)).grid(row=0, column=4, padx=(10, 0))

        # Preset buttons
        preset_frame = ttk.Frame(frame)
        preset_frame.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(preset_frame, text="Preset:").grid(row=0, column=0, padx=(0, 6))
        ttk.Button(preset_frame, text="Save Preset", command=self._save_preset).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(preset_frame, text="Load Preset", command=self._load_preset).grid(row=0, column=2)


    def _build_action_section(self, parent):
        frame = ttk.Frame(parent, padding=(0, 4))
        frame.grid(row=4, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=0, column=0, pady=(0, 6))
        self.preview_btn = ttk.Button(btn_row, text="Preview Frame", command=self._start_preview)
        self.preview_btn.grid(row=0, column=0, padx=(0, 12))
        self.merge_btn = ttk.Button(btn_row, text="Merge Videos", command=self._start_merge)
        self.merge_btn.grid(row=0, column=1)

        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(frame, variable=self.progress_var, maximum=100).grid(
            row=1, column=0, sticky="ew")
        self.status_label = ttk.Label(frame, text="Ready", foreground="gray")
        self.status_label.grid(row=2, column=0, sticky="w", pady=(4, 0))

    # ------------------------------------------------------------------ #
    #  FILE BROWSING                                                       #
    # ------------------------------------------------------------------ #
    def _browse_video(self, index):
        path = filedialog.askopenfilename(
            title=f"Select Video {index + 1}",
            filetypes=[("Video files", "*.avi *.mp4 *.mkv *.mov"), ("All files", "*.*")])
        if path:
            self.video_paths[index].set(path)
            self._load_video_info(index, path)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save Merged Video As",
            defaultextension=".avi",
            filetypes=[("AVI files", "*.avi"), ("All files", "*.*")])
        if path:
            self.output_path.set(path)

    def _load_video_info(self, index, path):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            messagebox.showerror("Error", f"Cannot open: {path}")
            return
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ret, frame = cap.read()
        cap.release()

        if not ret:
            messagebox.showerror("Error", f"Cannot read frame from: {path}")
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.video_frames_rgb[index] = frame_rgb
        self.video_infos[index] = {"w": w, "h": h, "fps": fps, "total": total}

        duration = total / fps if fps > 0 else 0
        h_d, m_d, s_d = int(duration//3600), int((duration%3600)//60), duration%60
        self.video_info_labels[index].config(
            text=f"  {os.path.basename(path)} — {w}x{h}, {fps:.1f} FPS, "
                 f"{total} frames ({h_d:02d}:{m_d:02d}:{s_d:05.2f})")

        tk_img = frame_to_tk_image(frame_rgb, max_size=(200, 150))
        self.preview_labels[index].config(image=tk_img, text="")
        self.preview_img_refs[index] = tk_img


    # ------------------------------------------------------------------ #
    #  PRESETS                                                             #
    # ------------------------------------------------------------------ #
    def _save_preset(self):
        path = filedialog.asksaveasfilename(
            title="Save Preset As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        preset = {
            "video1": self.video_paths[0].get(),
            "video2": self.video_paths[1].get(),
            "video3": self.video_paths[2].get(),
            "video4": self.video_paths[3].get(),
            "offset1": self.video_offsets[0].get(),
            "offset2": self.video_offsets[1].get(),
            "offset3": self.video_offsets[2].get(),
            "offset4": self.video_offsets[3].get(),
            "map": [
                f"{q}={self.mapping_vars[q]['video'].get()}:{self.mapping_vars[q]['quadrant'].get()}"
                for q in QUADRANT_NAMES
            ],
            "codec": self.codec_var.get(),
            "start_time": self.start_time_var.get(),
            "end_time": self.end_time_var.get(),
            "sync_mode": self.sync_mode_var.get(),
        }
        with open(path, "w") as f:
            json.dump(preset, f, indent=2)
        messagebox.showinfo("Preset Saved", f"Preset saved to:\n{path}")

    def _load_preset(self):
        path = filedialog.askopenfilename(
            title="Load Preset",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path or not os.path.isfile(path):
            return
        with open(path, "r") as f:
            preset = json.load(f)

        for i in range(self.NUM_VIDEOS):
            vp = preset.get(f"video{i+1}", "")
            self.video_paths[i].set(vp or "")
            self.video_offsets[i].set(preset.get(f"offset{i+1}", "") or "")
            if vp and os.path.isfile(vp):
                self._load_video_info(i, vp)

        map_entries = preset.get("map", [])
        for entry in map_entries:
            try:
                out_q, src = entry.split("=")
                vid_n, src_q = src.split(":")
                out_q = out_q.strip().upper()
                if out_q in self.mapping_vars:
                    self.mapping_vars[out_q]["video"].set(vid_n.strip())
                    self.mapping_vars[out_q]["quadrant"].set(src_q.strip().upper())
            except Exception:
                pass

        self.codec_var.set(preset.get("codec", "MJPG"))
        self.start_time_var.set(preset.get("start_time", "") or "")
        self.end_time_var.set(preset.get("end_time", "") or "")
        self.sync_mode_var.set(preset.get("sync_mode", "Lock Time") or "Lock Time")

        messagebox.showinfo("Preset Loaded", f"Preset loaded from:\n{path}")


    # ------------------------------------------------------------------ #
    #  HELPERS                                                             #
    # ------------------------------------------------------------------ #
    def _get_mapping(self):
        mapping = {}
        for q in QUADRANT_NAMES:
            vid_num = int(self.mapping_vars[q]["video"].get())
            src_quad = self.mapping_vars[q]["quadrant"].get()
            mapping[q] = (vid_num - 1, src_quad)
        return mapping

    def _get_active_video_paths(self):
        """Return list of (index, path) for videos that are loaded."""
        result = []
        for i in range(self.NUM_VIDEOS):
            p = self.video_paths[i].get()
            if p:
                result.append((i, p))
        return result

    def _get_used_video_indices(self):
        """Return set of 0-based video indices referenced in the mapping."""
        mapping = self._get_mapping()
        return {vid_idx for vid_idx, _ in mapping.values()}

    def _validate(self):
        if not self.video_paths[0].get():
            messagebox.showwarning("Missing Input", "Please select Video 1.")
            return False
        if not self.video_paths[1].get():
            messagebox.showwarning("Missing Input", "Please select Video 2.")
            return False
        if not self.output_path.get():
            messagebox.showwarning("Missing Input", "Please select an output file.")
            return False
        for i in range(2):
            if not os.path.isfile(self.video_paths[i].get()):
                messagebox.showerror("Error", f"Video {i+1} not found: {self.video_paths[i].get()}")
                return False
        used = self._get_used_video_indices()
        for idx in used:
            if idx >= 2:
                vp = self.video_paths[idx].get()
                if not vp:
                    messagebox.showwarning("Missing Input",
                        f"Mapping references Video {idx+1} but it isn't loaded.")
                    return False
                if not os.path.isfile(vp):
                    messagebox.showerror("Error", f"Video {idx+1} not found: {vp}")
                    return False
        return True

    def _build_run_params(self):
        """Collect all parameters needed for the merge."""
        used_indices = sorted(self._get_used_video_indices())
        max_idx = max(used_indices) if used_indices else 1

        video_paths = []
        offsets = []
        for i in range(max_idx + 1):
            video_paths.append(self.video_paths[i].get())
            offsets.append(time_to_seconds(self.video_offsets[i].get()))

        mapping = self._get_mapping()
        start_t = time_to_seconds(self.start_time_var.get())
        end_str = self.end_time_var.get().strip()
        end_t = time_to_seconds(end_str) if end_str else None

        # Convert GUI label to internal mode string
        sync_mode = "time" if self.sync_mode_var.get() == "Lock Time" else "framerate"

        return video_paths, offsets, mapping, start_t, end_t, sync_mode

    def _disable_buttons(self):
        self.merge_btn.config(state="disabled")
        self.preview_btn.config(state="disabled")

    def _enable_buttons(self):
        self.root.after(0, lambda: self.merge_btn.config(state="normal"))
        self.root.after(0, lambda: self.preview_btn.config(state="normal"))

    def _set_status(self, text, color="black"):
        self.root.after(0, lambda: self.status_label.config(text=text, foreground=color))

    def _set_progress(self, value):
        self.root.after(0, lambda: self.progress_var.set(value))


    # ------------------------------------------------------------------ #
    #  PREVIEW                                                             #
    # ------------------------------------------------------------------ #
    def _start_preview(self):
        if not self._validate():
            return
        self._disable_buttons()
        self._set_status("Generating preview...", "black")
        threading.Thread(target=self._do_preview, daemon=True).start()

    def _do_preview(self):
        try:
            video_paths, offsets, mapping, start_t, _, _sync = self._build_run_params()

            caps = []
            frames = []
            video_info = []
            for i, path in enumerate(video_paths):
                cap = cv2.VideoCapture(path)
                fps_v = cap.get(cv2.CAP_PROP_FPS) or 25.0
                video_info.append({"fps": fps_v,
                                   "w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                   "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})
                if offsets[i] > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(offsets[i] * fps_v))
                if start_t > 0:
                    cur = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, cur + int(start_t * fps_v))
                caps.append(cap)

            out_w = max(v["w"] for v in video_info)
            out_h = max(v["h"] for v in video_info)
            out_w = out_w + (out_w % 2)
            out_h = out_h + (out_h % 2)

            all_ok = True
            for cap in caps:
                ret, frame = cap.read()
                if not ret:
                    all_ok = False
                    break
                if frame.shape[1] != out_w or frame.shape[0] != out_h:
                    frame = cv2.resize(frame, (out_w, out_h))
                frames.append(frame)

            for cap in caps:
                cap.release()

            if not all_ok or not frames:
                self._set_status("Preview failed: could not read frames.", "red")
                self._enable_buttons()
                return

            composite = build_output_frame(frames, mapping, (out_w, out_h))
            composite_rgb = cv2.cvtColor(composite, cv2.COLOR_BGR2RGB)

            # Save to disk next to output
            out = self.output_path.get()
            preview_path = (out.rsplit(".", 1)[0] if "." in out else out) + "_preview.jpg"
            cv2.imwrite(preview_path, composite)

            # Show in popup window
            self.root.after(0, lambda: self._show_preview_window(composite_rgb, preview_path))
            self._set_status(f"Preview saved: {os.path.basename(preview_path)}", "green")

        except Exception as e:
            self._set_status(f"Preview error: {e}", "red")
        finally:
            self._enable_buttons()

    def _show_preview_window(self, frame_rgb, preview_path):
        win = tk.Toplevel(self.root)
        win.title("Output Preview")
        h, w = frame_rgb.shape[:2]
        scale = min(800 / w, 600 / h, 1.0)
        display = cv2.resize(frame_rgb, (int(w * scale), int(h * scale)))
        img = ImageTk.PhotoImage(Image.fromarray(display))
        lbl = ttk.Label(win, image=img)
        lbl.image = img
        lbl.pack(padx=10, pady=10)
        ttk.Label(win, text=f"Saved to: {preview_path}", foreground="gray").pack(pady=(0, 6))
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))


    # ------------------------------------------------------------------ #
    #  MERGE                                                               #
    # ------------------------------------------------------------------ #
    def _start_merge(self):
        if not self._validate():
            return
        self._disable_buttons()
        self._set_status("Merging...", "black")
        self._set_progress(0)
        threading.Thread(target=self._do_merge, daemon=True).start()

    def _do_merge(self):
        try:
            video_paths, offsets, mapping, start_t, end_t, sync_mode = self._build_run_params()
            output_path = self.output_path.get()
            codec = self.codec_var.get()

            caps = []
            video_info = []
            for i, path in enumerate(video_paths):
                cap = cv2.VideoCapture(path)
                if not cap.isOpened():
                    self._set_status(f"Error: Cannot open Video {i+1}.", "red")
                    for c in caps: c.release()
                    self._enable_buttons()
                    return
                fps_v = cap.get(cv2.CAP_PROP_FPS) or 25.0
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                video_info.append({"w": w, "h": h, "fps": fps_v, "total": total})

                if offsets[i] > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(offsets[i] * fps_v))
                if start_t > 0:
                    cur = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, cur + int(start_t * fps_v))
                caps.append(cap)

            out_w = max(v["w"] for v in video_info)
            out_h = max(v["h"] for v in video_info)
            out_w = out_w + (out_w % 2)
            out_h = out_h + (out_h % 2)

            out_fps = video_info[0]["fps"]

            max_frames = None
            if end_t is not None and end_t > 0:
                duration = end_t - start_t
                if duration <= 0:
                    self._set_status("Error: end time must be after start time.", "red")
                    for c in caps: c.release()
                    self._enable_buttons()
                    return
                max_frames = int(duration * out_fps)

            # Estimate total for progress bar
            if max_frames:
                total_frames_est = max_frames
            elif sync_mode == "time":
                # In time-sync mode, output frames = shortest duration × output FPS
                durations = []
                for i, v in enumerate(video_info):
                    remaining_frames = v["total"] - int(caps[i].get(cv2.CAP_PROP_POS_FRAMES))
                    duration_secs = remaining_frames / v["fps"] if v["fps"] > 0 else 0
                    durations.append(duration_secs)
                shortest_duration = min(durations) if durations else 0
                total_frames_est = int(shortest_duration * out_fps)
            else:
                # In framerate mode, output frames = min frame count across sources
                total_frames_est = min(v["total"] for v in video_info)

            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(output_path, fourcc, out_fps, (out_w, out_h))
            if not writer.isOpened():
                self._set_status(f"Error: Cannot create output with codec '{codec}'.", "red")
                for c in caps: c.release()
                self._enable_buttons()
                return

            frame_count = 0
            last_frames = [None] * len(caps)
            start_positions = [int(cap.get(cv2.CAP_PROP_POS_FRAMES)) for cap in caps]

            while True:
                if max_frames is not None and frame_count >= max_frames:
                    break

                frames = []
                all_ok = True

                if sync_mode == "time":
                    output_time = frame_count / out_fps
                    for i, cap in enumerate(caps):
                        src_fps = video_info[i]["fps"]
                        src_total = video_info[i]["total"]
                        target_frame = start_positions[i] + int(output_time * src_fps)

                        # If target exceeds total frames, this video is exhausted
                        if target_frame >= src_total:
                            all_ok = False
                            break

                        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

                        if target_frame > current_frame:
                            if target_frame - current_frame > 10:
                                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                            else:
                                for _ in range(target_frame - current_frame - 1):
                                    if not cap.grab():
                                        break
                            ret, frame = cap.read()
                            if ret:
                                last_frames[i] = frame
                            elif last_frames[i] is not None:
                                frame = last_frames[i]
                            else:
                                all_ok = False
                                break
                        elif target_frame == current_frame:
                            ret, frame = cap.read()
                            if ret:
                                last_frames[i] = frame
                            elif last_frames[i] is not None:
                                frame = last_frames[i]
                            else:
                                all_ok = False
                                break
                        else:
                            if last_frames[i] is not None:
                                frame = last_frames[i]
                            else:
                                ret, frame = cap.read()
                                if not ret:
                                    all_ok = False
                                    break
                                last_frames[i] = frame

                        if frame.shape[1] != out_w or frame.shape[0] != out_h:
                            frame = cv2.resize(frame, (out_w, out_h))
                        frames.append(frame)
                else:
                    for i, cap in enumerate(caps):
                        ret, frame = cap.read()
                        if not ret:
                            all_ok = False
                            break
                        last_frames[i] = frame
                        if frame.shape[1] != out_w or frame.shape[0] != out_h:
                            frame = cv2.resize(frame, (out_w, out_h))
                        frames.append(frame)

                if not all_ok:
                    break

                writer.write(build_output_frame(frames, mapping, (out_w, out_h)))
                frame_count += 1

                if total_frames_est > 0:
                    self._set_progress((frame_count / total_frames_est) * 100)
                if frame_count % 50 == 0:
                    self._set_status(
                        f"Processing: {frame_count}/{total_frames_est if total_frames_est else '?'} frames...",
                        "black")

            for c in caps: c.release()
            writer.release()

            self._set_progress(100)
            self._set_status(
                f"Done! {frame_count} frames -> {os.path.basename(output_path)}", "green")
            self.root.after(0, lambda: messagebox.showinfo(
                "Merge Complete",
                f"Merged {frame_count} frames!\n\nSaved to:\n{output_path}"))

        except Exception as e:
            self._set_status(f"Error: {e}", "red")
        finally:
            self._enable_buttons()


def main():
    root = tk.Tk()
    root.geometry("860x820")
    app = QuadMergerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
