#!/usr/bin/env python3
"""
Quad-Box Video Merger - GUI Version
====================================
A tkinter-based GUI that lets you:
1. Load two quad-box (or full-screen) AVI videos
2. Visually select which quadrant from which video maps to each output slot
   - Use "FULL" to scale the entire source video into one output quadrant
3. Choose codec and output path
4. Export the merged video with a progress bar

No command-line knowledge required!
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2
import numpy as np
from PIL import Image, ImageTk


QUADRANT_NAMES = ["TL", "TR", "BL", "BR"]
SOURCE_QUADRANTS = ["TL", "TR", "BL", "BR", "FULL"]
QUADRANT_LABELS = {
    "TL": "Top-Left",
    "TR": "Top-Right",
    "BL": "Bottom-Left",
    "BR": "Bottom-Right",
}


def extract_quadrant(frame, quadrant_name):
    """Extract a quadrant from a frame, or return the full frame."""
    if quadrant_name == "FULL":
        return frame.copy()

    h, w = frame.shape[:2]
    mid_y = h // 2
    mid_x = w // 2

    if quadrant_name == "TL":
        return frame[0:mid_y, 0:mid_x]
    elif quadrant_name == "TR":
        return frame[0:mid_y, mid_x:w]
    elif quadrant_name == "BL":
        return frame[mid_y:h, 0:mid_x]
    elif quadrant_name == "BR":
        return frame[mid_y:h, mid_x:w]
    else:
        raise ValueError(f"Unknown quadrant: {quadrant_name}")


def get_first_frame(video_path):
    """Get the first frame of a video for preview."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    ret, frame = cap.read()
    cap.release()
    if ret:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return None


def frame_to_tk_image(frame, max_size=(320, 240)):
    """Convert a numpy frame to a tkinter-compatible image, resized to fit."""
    h, w = frame.shape[:2]
    scale = min(max_size[0] / w, max_size[1] / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h))
    img = Image.fromarray(resized)
    return ImageTk.PhotoImage(img)


class QuadMergerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quad-Box Video Merger")
        self.root.resizable(True, True)

        # State
        self.video1_path = tk.StringVar()
        self.video2_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.codec_var = tk.StringVar(value="XVID")
        self.video1_frame = None  # numpy RGB frame
        self.video2_frame = None
        self.video1_info = {}
        self.video2_info = {}

        # Mapping: output quadrant -> (video_number_str, source_quadrant)
        self.mapping_vars = {}
        for q in QUADRANT_NAMES:
            self.mapping_vars[q] = {
                "video": tk.StringVar(value="1"),
                "quadrant": tk.StringVar(value=q),
            }

        self._build_ui()

    def _build_ui(self):
        """Build the full GUI layout."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # --- Section 1: File Selection ---
        file_frame = ttk.LabelFrame(main_frame, text="1. Select Videos", padding=10)
        file_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="Video 1:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Entry(file_frame, textvariable=self.video1_path, width=50).grid(row=0, column=1, sticky="ew")
        ttk.Button(file_frame, text="Browse...", command=self._browse_video1).grid(row=0, column=2, padx=(5, 0))

        ttk.Label(file_frame, text="Video 2:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(5, 0))
        ttk.Entry(file_frame, textvariable=self.video2_path, width=50).grid(row=1, column=1, sticky="ew", pady=(5, 0))
        ttk.Button(file_frame, text="Browse...", command=self._browse_video2).grid(row=1, column=2, padx=(5, 0), pady=(5, 0))

        # Video info labels
        self.video1_info_label = ttk.Label(file_frame, text="", foreground="gray")
        self.video1_info_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.video2_info_label = ttk.Label(file_frame, text="", foreground="gray")
        self.video2_info_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # --- Section 2: Preview ---
        preview_frame = ttk.LabelFrame(main_frame, text="2. Preview (First Frame)", padding=10)
        preview_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.preview1_label = ttk.Label(preview_frame, text="[Load Video 1]", anchor="center")
        self.preview1_label.grid(row=0, column=0, padx=(0, 10))
        self.preview2_label = ttk.Label(preview_frame, text="[Load Video 2]", anchor="center")
        self.preview2_label.grid(row=0, column=1, padx=(10, 0))

        ttk.Label(preview_frame, text="Video 1", foreground="blue").grid(row=1, column=0)
        ttk.Label(preview_frame, text="Video 2", foreground="green").grid(row=1, column=1)

        # --- Section 3: Quadrant Mapping ---
        map_frame = ttk.LabelFrame(main_frame, text="3. Map Quadrants", padding=10)
        map_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Header
        ttk.Label(map_frame, text="Output Quadrant", font=("", 9, "bold")).grid(row=0, column=0, padx=(0, 15))
        ttk.Label(map_frame, text="Source Video", font=("", 9, "bold")).grid(row=0, column=1, padx=(0, 15))
        ttk.Label(map_frame, text="Source Quadrant", font=("", 9, "bold")).grid(row=0, column=2)

        # Diagram reference
        diagram_text = "  TL | TR\n  ---|---\n  BL | BR\n\n  FULL = entire frame"
        ttk.Label(map_frame, text=diagram_text, font=("Courier", 9), foreground="gray").grid(
            row=0, column=3, rowspan=3, padx=(30, 0), sticky="n"
        )

        for i, q in enumerate(QUADRANT_NAMES):
            row = i + 1
            ttk.Label(map_frame, text=f"{QUADRANT_LABELS[q]} ({q})").grid(row=row, column=0, sticky="w", padx=(0, 15), pady=2)

            vid_combo = ttk.Combobox(
                map_frame,
                textvariable=self.mapping_vars[q]["video"],
                values=["1", "2"],
                width=8,
                state="readonly",
            )
            vid_combo.grid(row=row, column=1, padx=(0, 15), pady=2)

            quad_combo = ttk.Combobox(
                map_frame,
                textvariable=self.mapping_vars[q]["quadrant"],
                values=SOURCE_QUADRANTS,
                width=8,
                state="readonly",
            )
            quad_combo.grid(row=row, column=2, pady=2)

        # --- Section 4: Output Settings ---
        out_frame = ttk.LabelFrame(main_frame, text="4. Output Settings", padding=10)
        out_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        out_frame.columnconfigure(1, weight=1)

        ttk.Label(out_frame, text="Output File:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Entry(out_frame, textvariable=self.output_path, width=50).grid(row=0, column=1, sticky="ew")
        ttk.Button(out_frame, text="Save As...", command=self._browse_output).grid(row=0, column=2, padx=(5, 0))

        ttk.Label(out_frame, text="Codec:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(5, 0))
        codec_combo = ttk.Combobox(
            out_frame,
            textvariable=self.codec_var,
            values=["XVID", "MJPG", "DIVX", "mp4v"],
            width=10,
            state="readonly",
        )
        codec_combo.grid(row=1, column=1, sticky="w", pady=(5, 0))

        # --- Section 5: Merge Button & Progress ---
        action_frame = ttk.Frame(main_frame, padding=(0, 5))
        action_frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        action_frame.columnconfigure(0, weight=1)

        self.merge_btn = ttk.Button(action_frame, text="Merge Videos", command=self._start_merge)
        self.merge_btn.grid(row=0, column=0, pady=(0, 5))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(action_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, sticky="ew")

        self.status_label = ttk.Label(action_frame, text="Ready", foreground="gray")
        self.status_label.grid(row=2, column=0, sticky="w", pady=(5, 0))

    def _browse_video1(self):
        path = filedialog.askopenfilename(
            title="Select Video 1",
            filetypes=[("AVI files", "*.avi"), ("All video files", "*.avi *.mp4 *.mkv *.mov"), ("All files", "*.*")],
        )
        if path:
            self.video1_path.set(path)
            self._load_video_preview(1, path)

    def _browse_video2(self):
        path = filedialog.askopenfilename(
            title="Select Video 2",
            filetypes=[("AVI files", "*.avi"), ("All video files", "*.avi *.mp4 *.mkv *.mov"), ("All files", "*.*")],
        )
        if path:
            self.video2_path.set(path)
            self._load_video_preview(2, path)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save Merged Video As",
            defaultextension=".avi",
            filetypes=[("AVI files", "*.avi"), ("All files", "*.*")],
        )
        if path:
            self.output_path.set(path)

    def _load_video_preview(self, video_num, path):
        """Load a video, show preview and info."""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            messagebox.showerror("Error", f"Cannot open video: {path}")
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

        info_text = f"{os.path.basename(path)} — {w}x{h}, {fps:.1f} FPS, {total} frames"

        if video_num == 1:
            self.video1_frame = frame_rgb
            self.video1_info = {"w": w, "h": h, "fps": fps, "total": total}
            self.video1_info_label.config(text=f"  Video 1: {info_text}")
            tk_img = frame_to_tk_image(frame_rgb, max_size=(300, 225))
            self.preview1_label.config(image=tk_img, text="")
            self.preview1_label._img = tk_img  # keep reference
        else:
            self.video2_frame = frame_rgb
            self.video2_info = {"w": w, "h": h, "fps": fps, "total": total}
            self.video2_info_label.config(text=f"  Video 2: {info_text}")
            tk_img = frame_to_tk_image(frame_rgb, max_size=(300, 225))
            self.preview2_label.config(image=tk_img, text="")
            self.preview2_label._img = tk_img

    def _get_mapping(self):
        """Get mapping dict from GUI controls."""
        mapping = {}
        for q in QUADRANT_NAMES:
            vid_num = int(self.mapping_vars[q]["video"].get())
            src_quad = self.mapping_vars[q]["quadrant"].get()
            mapping[q] = (vid_num - 1, src_quad)  # 0-based index
        return mapping

    def _validate(self):
        """Validate all inputs before merging."""
        if not self.video1_path.get():
            messagebox.showwarning("Missing Input", "Please select Video 1.")
            return False
        if not self.video2_path.get():
            messagebox.showwarning("Missing Input", "Please select Video 2.")
            return False
        if not self.output_path.get():
            messagebox.showwarning("Missing Input", "Please select an output file path.")
            return False
        if not os.path.isfile(self.video1_path.get()):
            messagebox.showerror("Error", f"Video 1 not found: {self.video1_path.get()}")
            return False
        if not os.path.isfile(self.video2_path.get()):
            messagebox.showerror("Error", f"Video 2 not found: {self.video2_path.get()}")
            return False
        return True

    def _start_merge(self):
        """Start the merge in a background thread."""
        if not self._validate():
            return

        self.merge_btn.config(state="disabled")
        self.status_label.config(text="Merging...", foreground="black")
        self.progress_var.set(0)

        thread = threading.Thread(target=self._do_merge, daemon=True)
        thread.start()

    def _do_merge(self):
        """Perform the actual merge (runs in background thread)."""
        try:
            mapping = self._get_mapping()
            video1_path = self.video1_path.get()
            video2_path = self.video2_path.get()
            output_path = self.output_path.get()
            codec = self.codec_var.get()

            cap1 = cv2.VideoCapture(video1_path)
            cap2 = cv2.VideoCapture(video2_path)

            if not cap1.isOpened() or not cap2.isOpened():
                self._update_status("Error: Cannot open one or both videos.", "red")
                self._enable_button()
                return

            w1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
            h1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps1 = cap1.get(cv2.CAP_PROP_FPS)
            total1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))

            w2 = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
            h2 = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total2 = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT))

            out_w = max(w1, w2)
            out_h = max(h1, h2)
            out_w = out_w + (out_w % 2)
            out_h = out_h + (out_h % 2)

            total_frames = min(total1, total2)

            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(output_path, fourcc, fps1, (out_w, out_h))

            if not writer.isOpened():
                self._update_status(f"Error: Cannot create output file with codec '{codec}'.", "red")
                cap1.release()
                cap2.release()
                self._enable_button()
                return

            frame_count = 0

            while True:
                ret1, frame1 = cap1.read()
                ret2, frame2 = cap2.read()

                if not ret1 or not ret2:
                    break

                if frame1.shape[1] != out_w or frame1.shape[0] != out_h:
                    frame1 = cv2.resize(frame1, (out_w, out_h))
                if frame2.shape[1] != out_w or frame2.shape[0] != out_h:
                    frame2 = cv2.resize(frame2, (out_w, out_h))

                output_frame = self._build_output_frame([frame1, frame2], mapping, (out_w, out_h))
                writer.write(output_frame)

                frame_count += 1
                if total_frames > 0:
                    pct = (frame_count / total_frames) * 100
                    self._update_progress(pct)

                if frame_count % 50 == 0:
                    self._update_status(f"Processing: {frame_count}/{total_frames} frames...", "black")

            cap1.release()
            cap2.release()
            writer.release()

            self._update_progress(100)
            self._update_status(f"Done! Wrote {frame_count} frames to: {os.path.basename(output_path)}", "green")
            self._enable_button()

            # Show completion dialog
            self.root.after(0, lambda: messagebox.showinfo(
                "Merge Complete",
                f"Successfully merged {frame_count} frames!\n\nSaved to:\n{output_path}"
            ))

        except Exception as e:
            self._update_status(f"Error: {str(e)}", "red")
            self._enable_button()

    def _build_output_frame(self, frames, mapping, output_size):
        """Build the output frame by assembling quadrants."""
        out_w, out_h = output_size
        mid_x = out_w // 2
        mid_y = out_h // 2
        quad_size = (mid_x, mid_y)

        output = np.zeros((out_h, out_w, 3), dtype=np.uint8)

        for out_quad, (vid_idx, src_quad) in mapping.items():
            src_frame = frames[vid_idx]
            quadrant_img = extract_quadrant(src_frame, src_quad)
            quadrant_img = cv2.resize(quadrant_img, quad_size)

            if out_quad == "TL":
                output[0:mid_y, 0:mid_x] = quadrant_img
            elif out_quad == "TR":
                output[0:mid_y, mid_x:out_w] = quadrant_img
            elif out_quad == "BL":
                output[mid_y:out_h, 0:mid_x] = quadrant_img
            elif out_quad == "BR":
                output[mid_y:out_h, mid_x:out_w] = quadrant_img

        return output

    def _update_progress(self, value):
        """Thread-safe progress update."""
        self.root.after(0, lambda: self.progress_var.set(value))

    def _update_status(self, text, color="black"):
        """Thread-safe status label update."""
        self.root.after(0, lambda: self.status_label.config(text=text, foreground=color))

    def _enable_button(self):
        """Thread-safe button re-enable."""
        self.root.after(0, lambda: self.merge_btn.config(state="normal"))


def main():
    root = tk.Tk()
    root.geometry("700x650")
    app = QuadMergerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
