#!/usr/bin/env python3
"""
Quad-Box Video Merger
=====================
Takes up to three AVI videos that are each in a 2x2 quad-box layout
(or full-screen), lets you pick which quadrant from which source video
maps to each quadrant of the output, then exports the merged result.

You can also use FULL to take the entire frame from a video
and scale it into one of the output quadrants (useful for
single-camera full-screen videos).

Quadrant layout:
    +----+----+
    | TL | TR |
    +----+----+
    | BL | BR |
    +----+----+

Usage:
    python quad_merge.py --video1 input1.avi --video2 input2.avi --output merged.avi \
        --map TL=1:TL TR=2:TR BL=1:BL BR=2:BR

    python quad_merge.py --video1 input1.avi --video2 input2.avi --video3 input3.avi \
        --output merged.avi --map TL=1:TL TR=2:TR BL=3:BL BR=3:FULL

    The --map argument defines the output layout:
        <output_quadrant>=<source_video>:<source_quadrant>

    Example: TL=2:BR means "output's top-left gets video 2's bottom-right"
    Example: BL=3:FULL means "output's bottom-left gets all of video 3 scaled to fit"

    Valid quadrant names: TL, TR, BL, BR, FULL
    Valid video sources: 1, 2, 3
"""

import argparse
import sys
import cv2
import numpy as np


QUADRANT_NAMES = ["TL", "TR", "BL", "BR"]
SOURCE_QUADRANTS = ["TL", "TR", "BL", "BR", "FULL"]
MAX_VIDEOS = 3


def parse_mapping(map_args, num_videos):
    """
    Parse mapping arguments like 'TL=1:TR' into a dict.
    Returns: {output_quad: (video_index, source_quad)}
        video_index is 0-based internally (0, 1, or 2)
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

            mapping[out_quad] = (vid_num - 1, src_quad)  # store 0-based index
        except ValueError:
            print(f"Error: Invalid mapping format '{entry}'. Expected format: TL=1:TR or TL=1:FULL")
            sys.exit(1)

    # Ensure all 4 output quadrants are mapped
    for q in QUADRANT_NAMES:
        if q not in mapping:
            print(f"Error: Output quadrant '{q}' is not mapped. All 4 must be specified.")
            sys.exit(1)

    return mapping


def extract_quadrant(frame, quadrant_name):
    """
    Extract a quadrant from a frame, or return the full frame.
    Frame is split into 4 equal parts based on its dimensions.
    If quadrant_name is "FULL", the entire frame is returned.
    """
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
    """
    Build the output frame by assembling quadrants from source frames.

    Args:
        frames: list of frames [frame_from_video1, frame_from_video2, ...]
        mapping: {output_quad: (video_index, source_quad)}
        output_size: (width, height) of the output video
    """
    out_w, out_h = output_size
    mid_x = out_w // 2
    mid_y = out_h // 2
    quad_size = (mid_x, mid_y)  # width, height of each quadrant

    output = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    for out_quad, (vid_idx, src_quad) in mapping.items():
        src_frame = frames[vid_idx]
        quadrant_img = extract_quadrant(src_frame, src_quad)

        # Resize quadrant to fit the output slot
        quadrant_img = cv2.resize(quadrant_img, quad_size)

        # Place into output
        if out_quad == "TL":
            output[0:mid_y, 0:mid_x] = quadrant_img
        elif out_quad == "TR":
            output[0:mid_y, mid_x:out_w] = quadrant_img
        elif out_quad == "BL":
            output[mid_y:out_h, 0:mid_x] = quadrant_img
        elif out_quad == "BR":
            output[mid_y:out_h, mid_x:out_w] = quadrant_img

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Merge quadrants from up to three quad-box AVI videos into one output video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quadrant Layout:
    +----+----+
    | TL | TR |
    +----+----+
    | BL | BR |
    +----+----+

Mapping Format:
    <output_quadrant>=<video_number>:<source_quadrant>

    Source quadrant can be: TL, TR, BL, BR, or FULL
    Use FULL to scale the entire source video into one output quadrant.
    Video number can be 1, 2, or 3 (if --video3 is provided).

Examples:
    python quad_merge.py --video1 cam1.avi --video2 cam2.avi --output merged.avi \\
        --map TL=1:TL TR=1:TR BL=2:BL BR=2:BR

    This takes the top row from video 1 and the bottom row from video 2.

    python quad_merge.py --video1 quad.avi --video2 fullscreen.avi --output merged.avi \\
        --map TL=1:TL TR=1:TR BL=1:BL BR=2:FULL

    This takes 3 quadrants from video 1, and scales all of video 2 into the bottom-right.

    python quad_merge.py --video1 a.avi --video2 b.avi --video3 c.avi --output merged.avi \\
        --map TL=1:TL TR=2:TR BL=3:BL BR=3:FULL

    This mixes quadrants from all three source videos.
        """,
    )

    parser.add_argument("--video1", required=True, help="Path to first input video")
    parser.add_argument("--video2", required=True, help="Path to second input video")
    parser.add_argument("--video3", default=None, help="Path to third input video (optional)")
    parser.add_argument("--output", required=True, help="Path for output AVI video")
    parser.add_argument(
        "--map",
        nargs=4,
        required=True,
        metavar="QUAD=VID:QUAD",
        help="Four quadrant mappings, e.g. TL=1:TL TR=2:TR BL=3:BL BR=3:FULL",
    )
    parser.add_argument(
        "--codec",
        default="XVID",
        help="FourCC codec for output (default: XVID). Common: XVID, MJPG, DIVX",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Output FPS (default: use video1's FPS)",
    )

    args = parser.parse_args()

    # Determine how many videos we have
    video_paths = [args.video1, args.video2]
    if args.video3:
        video_paths.append(args.video3)
    num_videos = len(video_paths)

    # Parse the quadrant mapping
    mapping = parse_mapping(args.map, num_videos)

    # Validate that mapping doesn't reference video3 if it wasn't provided
    for out_q, (vid_idx, src_q) in mapping.items():
        if vid_idx >= num_videos:
            print(f"Error: Mapping references video {vid_idx + 1} but --video3 was not provided.")
            sys.exit(1)

    # Open input videos
    caps = []
    for i, path in enumerate(video_paths):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print(f"Error: Cannot open video{i + 1}: {path}")
            sys.exit(1)
        caps.append(cap)

    # Get video properties
    video_info = []
    for i, cap in enumerate(caps):
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_info.append({"w": w, "h": h, "fps": fps, "total": total})
        print(f"Video {i + 1}: {w}x{h} @ {fps:.2f} FPS, {total} frames")

    # Output dimensions: use the largest of all inputs
    out_w = max(info["w"] for info in video_info)
    out_h = max(info["h"] for info in video_info)
    # Ensure even dimensions for codec compatibility
    out_w = out_w + (out_w % 2)
    out_h = out_h + (out_h % 2)

    out_fps = args.fps if args.fps else video_info[0]["fps"]
    total_frames = min(info["total"] for info in video_info)

    print(f"Output: {out_w}x{out_h} @ {out_fps:.2f} FPS, {total_frames} frames")
    print(f"Mapping:")
    for out_q in QUADRANT_NAMES:
        vid_idx, src_q = mapping[out_q]
        print(f"  Output {out_q} <- Video {vid_idx + 1} : {src_q}")

    # Set up output writer
    fourcc = cv2.VideoWriter_fourcc(*args.codec)
    writer = cv2.VideoWriter(args.output, fourcc, out_fps, (out_w, out_h))

    if not writer.isOpened():
        print(f"Error: Cannot open output video writer for: {args.output}")
        print(f"  Codec: {args.codec}, Size: {out_w}x{out_h}")
        sys.exit(1)

    # Process frames
    frame_count = 0
    print("\nProcessing...")

    while True:
        frames = []
        all_ok = True
        for cap in caps:
            ret, frame = cap.read()
            if not ret:
                all_ok = False
                break
            frames.append(frame)

        if not all_ok:
            break

        # Resize frames to match output dimensions if needed
        for i in range(len(frames)):
            if frames[i].shape[1] != out_w or frames[i].shape[0] != out_h:
                frames[i] = cv2.resize(frames[i], (out_w, out_h))

        output_frame = build_output_frame(frames, mapping, (out_w, out_h))
        writer.write(output_frame)

        frame_count += 1
        if frame_count % 100 == 0:
            pct = (frame_count / total_frames) * 100 if total_frames > 0 else 0
            print(f"  {frame_count}/{total_frames} frames ({pct:.1f}%)")

    # Cleanup
    for cap in caps:
        cap.release()
    writer.release()

    print(f"\nDone! Wrote {frame_count} frames to: {args.output}")


if __name__ == "__main__":
    main()
