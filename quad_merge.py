#!/usr/bin/env python3
"""
Quad-Box Video Merger
=====================
Takes two AVI videos that are each in a 2x2 quad-box layout,
lets you pick which quadrant from which source video maps to
each quadrant of the output, then exports the merged result.

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

    The --map argument defines the output layout:
        <output_quadrant>=<source_video>:<source_quadrant>

    Example: TL=2:BR means "output's top-left gets video 2's bottom-right"
    Example: BL=2:FULL means "output's bottom-left gets all of video 2 scaled to fit"

    Valid quadrant names: TL, TR, BL, BR, FULL
    Valid video sources: 1, 2
"""

import argparse
import sys
import cv2
import numpy as np


QUADRANT_NAMES = ["TL", "TR", "BL", "BR"]
SOURCE_QUADRANTS = ["TL", "TR", "BL", "BR", "FULL"]


def parse_mapping(map_args):
    """
    Parse mapping arguments like 'TL=1:TR' into a dict.
    Returns: {output_quad: (video_index, source_quad)}
        video_index is 0-based internally (0 or 1)
        source_quad can be TL, TR, BL, BR, or FULL
    """
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
            if vid_num not in (1, 2):
                print(f"Error: Video number must be 1 or 2, got '{vid_num}'")
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
        frames: list of two frames [frame_from_video1, frame_from_video2]
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
        description="Merge quadrants from two quad-box AVI videos into one output video.",
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

Examples:
    python quad_merge.py --video1 cam1.avi --video2 cam2.avi --output merged.avi \\
        --map TL=1:TL TR=1:TR BL=2:BL BR=2:BR

    This takes the top row from video 1 and the bottom row from video 2.

    python quad_merge.py --video1 quad.avi --video2 fullscreen.avi --output merged.avi \\
        --map TL=1:TL TR=1:TR BL=1:BL BR=2:FULL

    This takes 3 quadrants from video 1, and scales all of video 2 into the bottom-right.
        """,
    )

    parser.add_argument("--video1", required=True, help="Path to first input AVI video")
    parser.add_argument("--video2", required=True, help="Path to second input AVI video")
    parser.add_argument("--output", required=True, help="Path for output AVI video")
    parser.add_argument(
        "--map",
        nargs=4,
        required=True,
        metavar="QUAD=VID:QUAD",
        help="Four quadrant mappings, e.g. TL=1:TL TR=2:TR BL=1:BL BR=2:FULL (use FULL for entire frame)",
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

    # Parse the quadrant mapping
    mapping = parse_mapping(args.map)

    # Open input videos
    cap1 = cv2.VideoCapture(args.video1)
    cap2 = cv2.VideoCapture(args.video2)

    if not cap1.isOpened():
        print(f"Error: Cannot open video1: {args.video1}")
        sys.exit(1)
    if not cap2.isOpened():
        print(f"Error: Cannot open video2: {args.video2}")
        sys.exit(1)

    # Get video properties
    w1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    h1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps1 = cap1.get(cv2.CAP_PROP_FPS)
    total1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))

    w2 = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
    h2 = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps2 = cap2.get(cv2.CAP_PROP_FPS)
    total2 = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"Video 1: {w1}x{h1} @ {fps1:.2f} FPS, {total1} frames")
    print(f"Video 2: {w2}x{h2} @ {fps2:.2f} FPS, {total2} frames")

    # Output dimensions match video1 (or the larger of the two)
    out_w = max(w1, w2)
    out_h = max(h1, h2)
    # Ensure even dimensions for codec compatibility
    out_w = out_w + (out_w % 2)
    out_h = out_h + (out_h % 2)

    out_fps = args.fps if args.fps else fps1
    total_frames = min(total1, total2)

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
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()

        if not ret1 or not ret2:
            break

        # Resize frames to match output dimensions if needed
        if frame1.shape[1] != out_w or frame1.shape[0] != out_h:
            frame1 = cv2.resize(frame1, (out_w, out_h))
        if frame2.shape[1] != out_w or frame2.shape[0] != out_h:
            frame2 = cv2.resize(frame2, (out_w, out_h))

        output_frame = build_output_frame([frame1, frame2], mapping, (out_w, out_h))
        writer.write(output_frame)

        frame_count += 1
        if frame_count % 100 == 0:
            pct = (frame_count / total_frames) * 100 if total_frames > 0 else 0
            print(f"  {frame_count}/{total_frames} frames ({pct:.1f}%)")

    # Cleanup
    cap1.release()
    cap2.release()
    writer.release()

    print(f"\nDone! Wrote {frame_count} frames to: {args.output}")


if __name__ == "__main__":
    main()
