# Vehicle Distance Analysis Tool (VDA)

A self-contained offline video analysis tool for extracting time-vs-distance data from vehicle-mounted cameras.

## Features

- **Video Loading**: Supports AVI, MP4, MKV, MOV formats
- **Quad-View Handling**: Auto-detects 2x2 composite frames, lets you select which quadrant to analyze (or use full-screen video)
- **Vehicle Detection**: YOLOv8-based detection of cars, trucks, buses, motorcycles
- **Persistent Tracking**: Vehicles maintain consistent IDs across frames
- **Lane Line Detection**: Classical CV approach (Canny + Hough + polynomial fitting)
- **Distance Estimation**: Camera geometry-based distance to vehicles and lane edges
- **Interactive GUI**: Tkinter-based desktop app with frame scrubbing, vehicle selection by clicking
- **CSV Export**: Time-series data (frame, time, vehicle_id, distance, lateral_offset)
- **Annotated Video Export**: Replay with bounding boxes, IDs, distances, and lane lines overlaid

## Camera Support

### Built-in Presets
- **Axis F2015-RE**: 3.1mm focal, 108° HFOV, 58° VFOV (default)
- **Auto-Estimate**: Estimates FOV from resolution (assumes ~90° HFOV typical for vehicle cameras)
- **Custom**: Enter your own HFOV, VFOV, mount height, and tilt angle

### Resolution
The tool adapts to any video resolution. When using quad-view, each sub-view is automatically sized to half the frame dimensions.

## Installation (Offline-Capable)

### On a machine with internet access:

```bash
# 1. Clone or copy this directory
# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download the YOLOv8 model (first run will auto-download, 
#    or download manually for offline use)
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

### For offline target machines:

```bash
# On internet-connected machine: download all packages
pip download -r requirements.txt -d ./packages/

# Copy the entire project folder (including ./packages/) to target machine

# On target machine:
python -m venv venv
source venv/bin/activate
pip install --no-index --find-links=./packages/ -r requirements.txt
```

### YOLOv8 Model for Offline Use

The `yolov8n.pt` file (~6MB) must be present in the working directory. It will auto-download on first run if internet is available, or you can manually place it.

## Usage

### Interactive GUI

```bash
# Launch with GUI
python run_analysis.py

# Or launch with a video pre-loaded
python run_analysis.py path/to/video.avi

# Alternative (module syntax)
python -m video_analysis
python -m video_analysis path/to/video.avi
```

### Workflow

1. **Open Video** - File → Open Video (or provide path on command line)
2. **Select View** - If quad-view is detected, choose which quadrant to analyze. For full-screen videos, leave on "Full Frame"
3. **Configure Camera** - Select preset (Axis F2015-RE, Auto-Estimate, or Custom) and set mount height
4. **Run Detection** - Click "Run Detection" to process all frames (progress bar shows status)
5. **Select Vehicles** - Click on bounding boxes in the video to select/deselect vehicles of interest, or use the vehicle list on the right
6. **Review** - Scrub through frames with the slider, play/pause, and review distance readouts
7. **Export** - Export CSV data and/or annotated video for selected vehicles

### Camera Settings

| Parameter | Description | Default |
|-----------|-------------|---------|
| Preset | Camera model preset | Axis F2015-RE |
| HFOV | Horizontal field of view (degrees) | 108° |
| VFOV | Vertical field of view (degrees) | 58° |
| Mount Height | Camera height above road (meters) | 1.4m |
| Tilt Down | Downward tilt angle (degrees) | 0° |

### Output Files

- `vehicle_distances.csv` - Per-frame distance data for each vehicle
- `lane_distances.csv` - Per-frame lane offset measurements
- `analysis_summary.csv` - Per-vehicle statistics (min/max/avg distance, duration tracked)
- `annotated_output.mp4` - Video replay with overlaid annotations

## CSV Format

### vehicle_distances.csv
```
frame, time_sec, vehicle_id, class, distance_m, lateral_offset_m, confidence, bbox_x1, bbox_y1, bbox_x2, bbox_y2
0, 0.000, 1, car, 25.30, 1.20, 0.85, 400, 300, 550, 420
```

### lane_distances.csv
```
frame, time_sec, left_lane_offset_m, right_lane_offset_m, lane_width_m
0, 0.000, 1.85, 1.85, 3.70
```

## Technical Notes

- **Distance Method**: Combined approach using known vehicle width (~1.8m for cars) and ground-plane geometry. More reliable at close range using ground plane, switches to width-based at longer range.
- **Temporal Smoothing**: Distance values are smoothed over 5 frames to reduce jitter.
- **Detection Model**: YOLOv8 nano (fast, ~6MB). Upgrade to `yolov8s.pt` or `yolov8m.pt` for better accuracy at the cost of speed.
- **Wide-Angle Correction**: The camera model accounts for the wide 108° FOV of the Axis sensor.

## Project Structure

```
video_analysis/
├── __init__.py          # Package info
├── __main__.py          # Module entry point
├── core/
│   ├── config.py        # Camera presets and configurations
│   ├── camera_model.py  # Pinhole camera model + distance math
│   ├── video_loader.py  # Video I/O
│   └── quad_splitter.py # Quad-view frame splitting
├── detection/
│   ├── vehicle_detector.py   # YOLOv8 wrapper
│   ├── tracker.py            # IoU-based multi-object tracker
│   ├── lane_detector.py      # Classical lane detection
│   └── distance_estimator.py # Distance computation
├── ui/
│   └── app.py           # Tkinter GUI application
└── export/
    ├── csv_export.py    # CSV data export
    └── video_export.py  # Annotated video generation
```

## Troubleshooting

- **"Cannot open video"**: Ensure the video codec is supported. Install `ffmpeg` for broader codec support.
- **No detections**: Try lowering confidence threshold (edit in the code: `confidence_threshold=0.2`).
- **Inaccurate distances**: Verify camera mount height and FOV settings match your setup.
- **Slow processing**: Use `yolov8n.pt` (nano) for speed. Processing time is roughly 10-30 FPS depending on hardware.
- **tkinter not found**: Install with `sudo apt install python3-tk` (Linux) or reinstall Python with Tk support.
