#!/usr/bin/env python3
"""
Quad-Box Video Merger
=====================
Takes up to four AVI videos (quad-box or full-screen), lets you pick which
quadrant from which source video maps to each quadrant of the output, then
exports the merged result.

Features:
- Up to 4 source videos
- FULL source option (scale entire frame into one quadrant)
- Time offset per video (start each at a different point)
- Frame range export (only export a specific range)
- Sync mode: lock time (real-time sync) or lock framerate (native playback)
- Batch mode (process multiple videos with same mapping)
- Save/load preset configurations (JSON)
- Output preview (show a single frame preview before full export)

Quadrant layout:
    +----+----+
    | TL | TR |
    +----+----+
    | BL | BR |
    +----+----+

Usage:
    python quad_merge.py --video1 a.avi --video2 b.avi --output merged.avi \
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR

    python quad_merge.py --preset my_config.json --output merged.avi

    python quad_merge.py --video1 a.avi --video2 b.avi --output merged.avi \
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:FULL \
        --offset1 00:00:05 --offset2 00:00:10 \
        --start-time 00:01:00 --end-time 00:05:00

    python quad_merge.py --batch batch_config.json
"""

import argparse
import json
import os
import sys
import glob as glob_module

import cv2
import numpy as np



QUADRANT_NAMES = ["TL", "TR", "BL", "BR"]
SOURCE_QUADRANTS = ["TL", "TR", "BL", "BR", "FULL"]
MAX_VIDEOS = 4
SYNC_MODES = ["time", "framerate"]


def time_to_seconds(time_str):
    """Convert HH:MM:SS or MM:SS or SS string to seconds."""
    if time_str is None:
        return 0.0
    parts = time_str.strip().split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    else:
        raise ValueError(f"Invalid time format: {time_str}")


def seconds_to_time(seconds):
    """Convert seconds to HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"



def parse_mapping(map_args, num_videos):
    """
    Parse mapping arguments like 'TL=1:TR' into a dict.
    Returns: {output_quad: (video_index, source_quad)}
        video_index is 0-based internally
        source_quad can be TL, TR, BL, BR, or FULL
    """
    valid_vid_nums = list(range(1, num_videos + 1))
    mapping = {}
    for entry in map_args:
        try:
            out_quad, source = entry.split("=")
            out_quad = out_quad.strip().upper()
            vid_num, src_quad = source.strip().split(":")
            vid_num = int(vid_num)
            src_quad = src_quad.strip().upper()

            if out_quad not in QUADRANT_NAMES:
                print(f"Error: Invalid output quadrant '{out_quad}'. Must be one of {QUADRANT_NAMES}")
                sys.exit(1)
            if src_quad not in SOURCE_QUADRANTS:
                print(f"Error: Invalid source quadrant '{src_quad}'. Must be one of {SOURCE_QUADRANTS}")
                sys.exit(1)
            if vid_num not in valid_vid_nums:
                print(f"Error: Video number must be one of {valid_vid_nums}, got '{vid_num}'")
                sys.exit(1)

            mapping[out_quad] = (vid_num - 1, src_quad)
        except ValueError:
            print(f"Error: Invalid mapping format '{entry}'. Expected: TL=1:TR or TL=1:FULL")
            sys.exit(1)

    for q in QUADRANT_NAMES:
        if q not in mapping:
            print(f"Error: Output quadrant '{q}' is not mapped. All 4 must be specified.")
            sys.exit(1)

    return mapping



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


def build_output_frame(frames, mapping, output_size):
    """Build the output frame by assembling quadrants from source frames."""
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



def seek_video(cap, seconds, fps):
    """Seek a VideoCapture to a given time offset in seconds."""
    if seconds > 0:
        frame_num = int(seconds * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)


def save_preset(args, path):
    """Save current CLI arguments to a JSON preset file."""
    preset = {
        "video1": args.video1,
        "video2": args.video2,
        "video3": args.video3,
        "video4": args.video4,
        "map": args.map,
        "codec": args.codec,
        "fps": args.fps,
        "offset1": args.offset1,
        "offset2": args.offset2,
        "offset3": args.offset3,
        "offset4": args.offset4,
        "start_time": args.start_time,
        "end_time": args.end_time,
        "sync_mode": args.sync_mode,
        "hold_last_frame": args.hold_last_frame,
    }
    with open(path, "w") as f:
        json.dump(preset, f, indent=2)
    print(f"Preset saved to: {path}")


def load_preset(path):
    """Load a preset JSON file and return as a namespace-like dict."""
    if not os.path.isfile(path):
        print(f"Error: Preset file not found: {path}")
        sys.exit(1)
    with open(path, "r") as f:
        preset = json.load(f)
    print(f"Preset loaded from: {path}")
    return preset



def run_merge(video_paths, offsets, mapping, output_path, codec, fps_override,
              start_time, end_time, preview_only=False, sync_mode="time",
              hold_last_frame=False, verbose=True):
    """
    Core merge function. Used by both single and batch modes.

    Args:
        video_paths: list of video file paths (1-4 items)
        offsets: list of time offsets in seconds (same length as video_paths)
        mapping: dict {out_quad: (vid_idx, src_quad)}
        output_path: output file path
        codec: FourCC string
        fps_override: override FPS or None
        start_time: global start time in seconds (applied after per-video offsets)
        end_time: global end time in seconds or None
        preview_only: if True, export only the first merged frame as a JPEG
        sync_mode: "time" (lock real-time, skip/duplicate frames) or
                   "framerate" (one source frame per output frame, no compensation)
        hold_last_frame: if True, when a video ends its last frame is frozen
                         until ALL videos are exhausted. If False, merge stops
                         as soon as any video ends.
        verbose: print progress
    Returns:
        frame_count written, or None on error
    """
    # Open captures
    caps = []
    for i, path in enumerate(video_paths):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print(f"Error: Cannot open video {i+1}: {path}")
            for c in caps:
                c.release()
            return None
        caps.append(cap)

    # Get properties
    video_info = []
    for cap in caps:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_info.append({"w": w, "h": h, "fps": fps, "total": total})

    if verbose:
        for i, info in enumerate(video_info):
            off = offsets[i] if i < len(offsets) else 0.0
            print(f"  Video {i+1}: {info['w']}x{info['h']} @ {info['fps']:.2f} FPS, "
                  f"{info['total']} frames, offset={seconds_to_time(off)}")
        print(f"  Sync mode: {sync_mode}")

    # Seek each video to its offset
    for i, cap in enumerate(caps):
        off = offsets[i] if i < len(offsets) else 0.0
        seek_video(cap, off, video_info[i]["fps"])

    # Additional global start seek (applied on top of per-video offsets)
    if start_time and start_time > 0:
        for i, cap in enumerate(caps):
            fps_i = video_info[i]["fps"]
            cur_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            extra_frames = int(start_time * fps_i)
            cap.set(cv2.CAP_PROP_POS_FRAMES, cur_frame + extra_frames)

    # Output size
    out_w = max(info["w"] for info in video_info)
    out_h = max(info["h"] for info in video_info)
    out_w = out_w + (out_w % 2)
    out_h = out_h + (out_h % 2)

    out_fps = fps_override if fps_override else video_info[0]["fps"]

    # Compute max frames based on end_time
    max_frames = None
    if end_time is not None and end_time > 0:
        range_start = start_time if start_time else 0.0
        duration = end_time - range_start
        if duration <= 0:
            print("Error: end-time must be greater than start-time.")
            for c in caps:
                c.release()
            return None
        max_frames = int(duration * out_fps)

    if preview_only:
        # Just read one frame and save as JPEG
        frames = []
        all_ok = True
        for cap in caps:
            ret, frame = cap.read()
            if not ret:
                all_ok = False
                break
            frames.append(frame)
        for c in caps:
            c.release()

        if not all_ok:
            print("Error: Could not read preview frames.")
            return None

        for i in range(len(frames)):
            if frames[i].shape[1] != out_w or frames[i].shape[0] != out_h:
                frames[i] = cv2.resize(frames[i], (out_w, out_h))

        preview_frame = build_output_frame(frames, mapping, (out_w, out_h))
        preview_path = output_path.rsplit(".", 1)[0] + "_preview.jpg"
        cv2.imwrite(preview_path, preview_frame)
        print(f"Preview saved to: {preview_path}")
        return 1

    # Setup writer
    fourcc = cv2.VideoWriter_fourcc(*codec)
    writer = cv2.VideoWriter(output_path, fourcc, out_fps, (out_w, out_h))
    if not writer.isOpened():
        print(f"Error: Cannot create output file: {output_path} (codec={codec})")
        for c in caps:
            c.release()
        return None

    frame_count = 0
    # Track the last successfully read frame for each video (for time sync)
    last_frames = [None] * len(caps)
    # Track start positions (frame index after all seeks) for time sync
    start_positions = [int(cap.get(cv2.CAP_PROP_POS_FRAMES)) for cap in caps]

    # Estimate total output frames for progress display
    if max_frames:
        est_total = max_frames
    elif sync_mode == "time":
        # Duration-based estimate: shortest or longest depending on hold mode
        durations = []
        for i, cap in enumerate(caps):
            remaining = video_info[i]["total"] - start_positions[i]
            dur = remaining / video_info[i]["fps"] if video_info[i]["fps"] > 0 else 0
            durations.append(dur)
        if hold_last_frame:
            est_total = int(max(durations) * out_fps) if durations else 0
        else:
            est_total = int(min(durations) * out_fps) if durations else 0
    else:
        if hold_last_frame:
            est_total = max(info["total"] for info in video_info)
        else:
            est_total = min(info["total"] for info in video_info)

    while True:
        if max_frames is not None and frame_count >= max_frames:
            break

        frames = []
        all_ok = True

        if sync_mode == "time":
            # Time-lock mode: calculate which frame each video should be at
            # based on elapsed output time
            output_time = frame_count / out_fps  # seconds elapsed in output
            all_exhausted = True  # track if ALL videos are done

            for i, cap in enumerate(caps):
                src_fps = video_info[i]["fps"]
                src_total = video_info[i]["total"]
                # The frame number this video should be at for this output time
                target_frame = start_positions[i] + int(output_time * src_fps)

                # If target exceeds total frames, this video is exhausted
                if target_frame >= src_total:
                    if hold_last_frame and last_frames[i] is not None:
                        # Hold: use the last frame we have
                        frame = last_frames[i]
                    else:
                        # Stop: this video is done and we don't hold
                        all_ok = False
                        break
                else:
                    all_exhausted = False
                    current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

                    if target_frame > current_frame:
                        # Need to skip ahead — seek or read forward
                        if target_frame - current_frame > 10:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                        else:
                            # Read and discard frames to advance
                            for _ in range(target_frame - current_frame - 1):
                                ret = cap.grab()
                                if not ret:
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
                        # Read next frame normally
                        ret, frame = cap.read()
                        if ret:
                            last_frames[i] = frame
                        elif last_frames[i] is not None:
                            frame = last_frames[i]
                        else:
                            all_ok = False
                            break
                    else:
                        # Target is behind current — use last frame (duplicate)
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

            # If holding last frame and ALL videos are exhausted, we're done
            if hold_last_frame and all_exhausted:
                all_ok = False

        else:
            # Framerate-lock mode: read one frame per video per output frame
            all_exhausted = True
            for i, cap in enumerate(caps):
                ret, frame = cap.read()
                if not ret:
                    if hold_last_frame and last_frames[i] is not None:
                        frame = last_frames[i]
                    else:
                        all_ok = False
                        break
                else:
                    all_exhausted = False
                    last_frames[i] = frame
                if frame.shape[1] != out_w or frame.shape[0] != out_h:
                    frame = cv2.resize(frame, (out_w, out_h))
                frames.append(frame)

            # If holding and ALL videos exhausted, stop
            if hold_last_frame and all_exhausted:
                all_ok = False

        if not all_ok:
            break

        output_frame = build_output_frame(frames, mapping, (out_w, out_h))
        writer.write(output_frame)
        frame_count += 1

        if verbose and frame_count % 100 == 0:
            print(f"  {frame_count}/{est_total} frames...")

    for c in caps:
        c.release()
    writer.release()

    if verbose:
        print(f"  Done: {frame_count} frames -> {output_path}")

    return frame_count



def run_batch(batch_config_path):
    """
    Run batch mode from a JSON config file.

    Batch config format:
    {
      "jobs": [
        {
          "video1": "a.avi",
          "video2": "b.avi",
          "video3": "c.avi",   (optional)
          "video4": "d.avi",   (optional)
          "output": "merged_1.avi",
          "map": ["TL=1:TL", "TR=2:TR", "BL=1:BL", "BR=2:BR"],
          "codec": "MJPG",     (optional)
          "fps": null,         (optional)
          "offset1": "00:00:05",  (optional)
          "offset2": "00:00:10",  (optional)
          "offset3": null,     (optional)
          "offset4": null,     (optional)
          "start_time": null,  (optional)
          "end_time": null     (optional)
        },
        ...
      ]
    }
    """
    if not os.path.isfile(batch_config_path):
        print(f"Error: Batch config not found: {batch_config_path}")
        sys.exit(1)

    with open(batch_config_path, "r") as f:
        config = json.load(f)

    jobs = config.get("jobs", [])
    if not jobs:
        print("Error: No jobs found in batch config.")
        sys.exit(1)

    print(f"Batch mode: {len(jobs)} job(s) found.\n")
    success = 0
    failed = 0

    for idx, job in enumerate(jobs):
        print(f"--- Job {idx + 1}/{len(jobs)}: {job.get('output', '?')} ---")

        video_paths = []
        offsets = []
        for n in range(1, 5):
            vp = job.get(f"video{n}")
            if vp:
                video_paths.append(vp)
                off_str = job.get(f"offset{n}")
                offsets.append(time_to_seconds(off_str) if off_str else 0.0)

        if len(video_paths) < 2:
            print(f"  Skipping: need at least video1 and video2.")
            failed += 1
            continue

        output_path = job.get("output")
        if not output_path:
            print(f"  Skipping: no output path specified.")
            failed += 1
            continue

        map_args = job.get("map", [])
        if len(map_args) != 4:
            print(f"  Skipping: need exactly 4 map entries.")
            failed += 1
            continue

        mapping = parse_mapping(map_args, len(video_paths))
        codec = job.get("codec", "XVID")
        fps_override = job.get("fps")
        start_time = time_to_seconds(job.get("start_time")) if job.get("start_time") else 0.0
        end_time = time_to_seconds(job.get("end_time")) if job.get("end_time") else None
        sync_mode = job.get("sync_mode", "time")
        hold_last = job.get("hold_last_frame", False)

        result = run_merge(
            video_paths=video_paths,
            offsets=offsets,
            mapping=mapping,
            output_path=output_path,
            codec=codec,
            fps_override=fps_override,
            start_time=start_time,
            end_time=end_time,
            sync_mode=sync_mode,
            hold_last_frame=hold_last,
            verbose=True,
        )

        if result is not None:
            success += 1
        else:
            failed += 1

        print()

    print(f"Batch complete: {success} succeeded, {failed} failed.")



def main():
    parser = argparse.ArgumentParser(
        description="Merge quadrants from up to 4 videos into one output video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
QUADRANT LAYOUT:
    +----+----+
    | TL | TR |
    +----+----+
    | BL | BR |
    +----+----+

MAPPING FORMAT:
    <output_quadrant>=<video_number>:<source_quadrant>
    Source quadrant: TL, TR, BL, BR, or FULL (entire frame scaled to fit)
    Video number: 1, 2, 3, or 4

TIME FORMAT:
    HH:MM:SS  or  MM:SS  or  SS  (e.g. 00:01:30, 1:30, or 90)

EXAMPLES:
    # Basic 2-video merge
    python quad_merge.py --video1 a.avi --video2 b.avi --output out.avi \\
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR

    # Use FULL source, with time offsets
    python quad_merge.py --video1 quad.avi --video2 cam.avi --output out.avi \\
        --map TL=1:TL TR=1:TR BL=1:BL BR=2:FULL \\
        --offset1 00:00:05 --offset2 00:00:00

    # Export only minutes 5-10
    python quad_merge.py --video1 a.avi --video2 b.avi --output out.avi \\
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR \\
        --start-time 00:05:00 --end-time 00:10:00

    # Save a preset
    python quad_merge.py --video1 a.avi --video2 b.avi --output out.avi \\
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR --save-preset my_config.json

    # Load a preset (overrides video/map args)
    python quad_merge.py --preset my_config.json --output out.avi

    # Preview only (exports a single JPEG frame, no full video)
    python quad_merge.py --video1 a.avi --video2 b.avi --output out.avi \\
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR --preview

    # Batch mode
    python quad_merge.py --batch batch_config.json

    # Sync mode: keep all videos time-aligned (default)
    python quad_merge.py --video1 a.avi --video2 b.avi --output out.avi \\
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR --sync-mode time

    # Sync mode: play each video at native framerate (no compensation)
    # Useful when you WANT slow-mo from a high-FPS source
    python quad_merge.py --video1 a.avi --video2 slowmo.avi --output out.avi \\
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR --sync-mode framerate
        """,
    )

    # Source videos
    parser.add_argument("--video1", default=None, help="Path to video 1")
    parser.add_argument("--video2", default=None, help="Path to video 2")
    parser.add_argument("--video3", default=None, help="Path to video 3 (optional)")
    parser.add_argument("--video4", default=None, help="Path to video 4 (optional)")

    # Per-video time offsets
    parser.add_argument("--offset1", default=None, metavar="TIME",
                        help="Start offset for video 1 (e.g. 00:00:05)")
    parser.add_argument("--offset2", default=None, metavar="TIME",
                        help="Start offset for video 2")
    parser.add_argument("--offset3", default=None, metavar="TIME",
                        help="Start offset for video 3")
    parser.add_argument("--offset4", default=None, metavar="TIME",
                        help="Start offset for video 4")

    # Output
    parser.add_argument("--output", default=None, help="Output video file path")
    parser.add_argument("--map", nargs=4, metavar="QUAD=VID:QUAD",
                        help="Four quadrant mappings")
    parser.add_argument("--codec", default="XVID",
                        help="FourCC codec (default: XVID). Common: XVID, MJPG, DIVX")
    parser.add_argument("--fps", type=float, default=None,
                        help="Override output FPS (default: video1 FPS)")

    # Frame range
    parser.add_argument("--start-time", default=None, metavar="TIME",
                        help="Export start time, e.g. 00:01:00")
    parser.add_argument("--end-time", default=None, metavar="TIME",
                        help="Export end time, e.g. 00:05:00")

    # Sync mode
    parser.add_argument("--sync-mode", default="time", choices=["time", "framerate"],
                        help="Sync mode: 'time' keeps videos in real-time sync "
                             "(skips/duplicates frames to match); 'framerate' reads one "
                             "frame per video per output frame with no compensation "
                             "(default: time)")
    parser.add_argument("--hold-last-frame", action="store_true",
                        help="When a video ends before others, freeze its last frame "
                             "until all videos are done. Without this flag, the merge "
                             "stops when any video runs out.")

    # Modes
    parser.add_argument("--preview", action="store_true",
                        help="Export only a single JPEG preview frame instead of full video")
    parser.add_argument("--batch", default=None, metavar="BATCH_JSON",
                        help="Run batch mode from a JSON config file")

    # Presets
    parser.add_argument("--preset", default=None, metavar="PRESET_JSON",
                        help="Load settings from a JSON preset file")
    parser.add_argument("--save-preset", default=None, metavar="PRESET_JSON",
                        help="Save current settings to a JSON preset file")

    args = parser.parse_args()

    # --- Batch mode ---
    if args.batch:
        run_batch(args.batch)
        return

    # --- Load preset (overrides individual args) ---
    if args.preset:
        preset = load_preset(args.preset)
        for key, val in preset.items():
            if val is not None:
                k = key.replace("-", "_")
                if not getattr(args, k, None):
                    setattr(args, k, val)

    # --- Validate required args ---
    if not args.video1 or not args.video2:
        parser.error("--video1 and --video2 are required (or use --preset / --batch)")
    if not args.output:
        parser.error("--output is required")
    if not args.map:
        parser.error("--map is required (4 entries)")

    # Build video path and offset lists
    video_paths = [args.video1, args.video2]
    offset_strs = [args.offset1, args.offset2]
    for vp, off in [(args.video3, args.offset3), (args.video4, args.offset4)]:
        if vp:
            video_paths.append(vp)
            offset_strs.append(off)

    offsets = [time_to_seconds(o) if o else 0.0 for o in offset_strs]

    # Validate files exist
    for i, vp in enumerate(video_paths):
        if not os.path.isfile(vp):
            print(f"Error: Video {i+1} not found: {vp}")
            sys.exit(1)

    mapping = parse_mapping(args.map, len(video_paths))

    start_time = time_to_seconds(args.start_time) if args.start_time else 0.0
    end_time = time_to_seconds(args.end_time) if args.end_time else None

    # Save preset if requested
    if args.save_preset:
        save_preset(args, args.save_preset)

    print(f"Merging {len(video_paths)} video(s) -> {args.output}")
    if args.preview:
        print("Preview mode: exporting single frame only.")

    result = run_merge(
        video_paths=video_paths,
        offsets=offsets,
        mapping=mapping,
        output_path=args.output,
        codec=args.codec,
        fps_override=args.fps,
        start_time=start_time,
        end_time=end_time,
        preview_only=args.preview,
        sync_mode=args.sync_mode,
        hold_last_frame=args.hold_last_frame,
        verbose=True,
    )

    if result is None:
        sys.exit(1)

    if not args.preview:
        print(f"\nDone! Wrote {result} frames to: {args.output}")


if __name__ == "__main__":
    main()
