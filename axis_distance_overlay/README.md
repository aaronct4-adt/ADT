# Axis Distance Overlay Tool

A standalone tool for generating and applying distance marker overlays on Axis F1194 video encoder channels. Uses green tape placed on the road at known distances, automatically detects the tape positions in a camera snapshot, and creates a transparent overlay with distance labels.

## Overview

**Use case:** You place green tape on the road at known intervals (e.g., 0m, 5m, 10m). This tool captures a snapshot from the Axis encoder, detects the tape lines, and generates a permanent overlay showing distance markers on the live video feed.

**Target hardware:** Axis F1194 Main Unit (quad channel), AXIS OS 11.1.55+

## Quick Start (Target Computer - No Python Needed)

1. Transfer `AxisDistanceOverlay.exe` and `config.json` to the target computer
2. Connect the computer to the Axis encoder via Ethernet
3. Place green tape on the road at your desired distance intervals
4. Double-click `AxisDistanceOverlay.exe`
5. Select the encoder IP and camera channel
6. Click **Connect & Capture**
7. Click **Auto-Detect Lines**
8. Verify/adjust distances, then click **Generate & Apply Overlay**

## Building the Executable

Run this on a computer WITH Python 3.8+ and internet access.


### Windows

```batch
cd axis_distance_overlay
build_exe.bat
```

### Linux/Mac

```bash
cd axis_distance_overlay
chmod +x build_exe.sh
./build_exe.sh
```

The output will be in the `dist/` folder:
- **Windows:** `dist/AxisDistanceOverlay.exe`
- **Linux:** `dist/AxisDistanceOverlay`

Transfer the executable and `config.json` to your target computer.

## Configuration

Edit `config.json` (place it next to the .exe) to customize behavior:

```json
{
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
```

### Configuration Parameters

| Parameter | Description |
|-----------|-------------|
| `encoder_ips` | List of encoder IP addresses shown in the dropdown |
| `username` / `password` | Axis encoder credentials |
| `distances_meters` | Default distance values auto-filled for detected lines |
| `tape_color_hsv_lower` | Lower HSV bound for green tape detection [H, S, V] |
| `tape_color_hsv_upper` | Upper HSV bound for green tape detection [H, S, V] |
| `overlay_line_color` | Overlay line color [R, G, B, Alpha] |
| `overlay_text_color` | Overlay text color [R, G, B, Alpha] |
| `overlay_line_thickness` | Line thickness in pixels |
| `overlay_font_size` | Font size for distance labels |
| `min_tape_width_ratio` | Minimum tape width as ratio of image width (0.0-1.0) |
| `snapshot_timeout` | HTTP request timeout in seconds |


## Usage Guide

### Step 1: Prepare the Road

Place green tape horizontally across the road at your desired distance intervals. Default setup:
- **0 meters** (baseline/reference)
- **5 meters**
- **10 meters**

Tips for best detection:
- Use bright/fluorescent green tape
- Make tape as wide as possible across the road
- Ensure good lighting (avoid deep shadows on the tape)
- Tape should contrast well against the road surface

### Step 2: Connect to Encoder

1. Launch the tool
2. Select the encoder IP from the dropdown (or choose "Custom..." to enter manually)
3. Select the camera channel (1-4)
4. Click **Connect & Capture**

### Step 3: Detect Lines

**Automatic mode (recommended):**
- Click **Auto-Detect Lines**
- The tool will find green tape lines and mark them with red lines on the preview

**Manual mode (fallback):**
- Click directly on the snapshot image where you want overlay lines
- Lines appear where you click

**Combining both:** You can auto-detect first, then click to add additional lines.

### Step 4: Assign Distances

- After lines are detected, distance entry fields appear below the image
- Enter the correct distance (in meters) for each line
- Lines are ordered top-to-bottom (furthest to nearest in typical forward-facing views)
- Click the **X** button next to any line to remove it

### Step 5: Apply Overlay

- Click **Generate & Apply Overlay**
- The tool creates a transparent PNG with white lines and distance labels
- Uploads it to the encoder and activates it on the selected camera channel
- The overlay persists until removed or the encoder is rebooted

### Removing Overlays

- Click **Remove All Overlays** to clear all image overlays from the encoder
- Overlays can also be managed through the Axis web interface

## How It Works

1. **Snapshot capture** via VAPIX `/axis-cgi/jpg/image.cgi`
2. **Color detection** using OpenCV HSV color space filtering for green tape
3. **Line extraction** via contour analysis and horizontal structure filtering
4. **Overlay generation** using Pillow to create a transparent PNG at native resolution
5. **Upload** via VAPIX `/axis-cgi/uploadoverlayimage.cgi`
6. **Activation** via VAPIX Dynamic Overlay API (`addImage` method)

## Troubleshooting

### Auto-detection finds no lines
- Verify tape is visible in the snapshot (check the preview image)
- Adjust `tape_color_hsv_lower` and `tape_color_hsv_upper` in config.json
- HSV ranges: H=0-180, S=0-255, V=0-255 (OpenCV convention)
- For green tape, typical H range is 35-85
- Reduce `min_tape_width_ratio` if tape doesn't span much of the frame
- Use manual mode as a fallback

### Connection fails
- Verify Ethernet cable is connected
- Ping the encoder IP address
- Check username/password (default: root/root)
- Ensure no firewall is blocking HTTP (port 80)

### Overlay doesn't appear
- Check if overlay limit is reached (use Remove All Overlays)
- Verify the camera channel number is correct (1-4)
- Check the Axis web interface for overlay status

### Wrong colors detected
- If detecting non-tape objects, narrow the HSV range
- If missing tape, widen the HSV range or lower the S/V minimums
- Test with different lighting conditions

## Network Setup

The target computer connects directly to the Axis encoder via Ethernet. No internet is required on the target computer. Typical setup:

```
[Computer] --Ethernet--> [Axis F1194 Encoder] --Coax/Ethernet--> [Cameras]
```

Default encoder IPs: `195.0.100.1`, `195.0.100.2`

Ensure the computer's IP is on the same subnet (e.g., `195.0.100.x`).

## File Structure

```
axis_distance_overlay/
├── distance_overlay.py   # Main application source
├── config.json           # Configuration (customize this)
├── requirements.txt      # Python dependencies
├── build_exe.bat         # Windows build script
├── build_exe.sh          # Linux/Mac build script
└── README.md             # This file
```

## Dependencies (Build Machine Only)

- Python 3.8+
- opencv-python (image processing, tape detection)
- numpy (array operations)
- Pillow (overlay image generation)
- requests (HTTP API calls to encoder)
- pyinstaller (packaging into standalone .exe)
- tkinter (GUI, included with Python)
