# Building a Standalone Windows .exe

This guide explains how to package the Vehicle Distance Analysis Tool
as a standalone `.exe` that runs on Windows without Python installed.

## Prerequisites (Build Machine Only)

You need a Windows machine with:
- Python 3.9+ installed
- Internet access (to download packages)

## Quick Build Steps

```cmd
:: 1. Open CMD and navigate to project
cd C:\Users\ntcna\ADT

:: 2. Create and activate a virtual environment
python -m venv build_env
build_env\Scripts\activate

:: 3. Install CPU-only PyTorch (MUCH smaller than full PyTorch)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

:: 4. Install remaining dependencies
pip install ultralytics opencv-python numpy Pillow scipy pyinstaller

:: 5. Download the YOLOv8 model
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

:: 6. Build the exe
python build_exe.py
```

## Output

After a successful build (5-10 minutes), you'll find:

```
dist/
  VehicleDistanceAnalysis/
    VehicleDistanceAnalysis.exe    ← Run this!
    yolov8n.pt                     ← Model weights (bundled)
    ... (supporting DLLs and files)
```

## Distributing to Target Machines

1. **Copy the entire** `dist/VehicleDistanceAnalysis/` folder to a USB drive or network share
2. On the target machine, paste the folder anywhere (Desktop, C:\Tools, etc.)
3. **Double-click** `VehicleDistanceAnalysis.exe` to run
4. No Python, no internet, no installation needed!

## Size Expectations

| Configuration | Approximate Size |
|---------------|-----------------|
| CPU-only PyTorch (recommended) | ~500-700 MB |
| Full PyTorch with CUDA | ~2-3 GB |

## Troubleshooting

### "Windows protected your PC" (SmartScreen)
- Click "More info" → "Run anyway"
- This happens because the exe isn't signed

### Antivirus flags
- Some antivirus software flags PyInstaller-built exes as suspicious
- Add the folder to your antivirus exclusion list
- This is a known issue with all PyInstaller applications

### Slow startup (~5-10 seconds)
- Normal for PyInstaller apps — it extracts files on first run
- Subsequent runs may be faster depending on caching

### Missing DLL errors
- Ensure you built on a similar Windows version to the target
- Build on Windows 10 for maximum compatibility

### "Failed to execute script"
- Run from CMD instead of double-clicking to see error messages:
  ```cmd
  cd path\to\VehicleDistanceAnalysis
  VehicleDistanceAnalysis.exe
  ```

## Single-File .exe (Alternative)

If you prefer one file instead of a folder, change `--onedir` to `--onefile` 
in `build_exe.py`. Trade-offs:
- **Pro**: Single file, easier to distribute
- **Con**: 15-30 second startup (must extract to temp folder each run)
- **Con**: Larger file size
- **Con**: Antivirus more likely to flag single-file exes

## Updating the Model

To use a more accurate (but larger/slower) model:
1. Replace `yolov8n.pt` with `yolov8s.pt` or `yolov8m.pt`
2. Update the filename in `build_exe.py` (the `--add-data` line)
3. Rebuild

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| yolov8n.pt (nano) | 6 MB | Fastest | Good |
| yolov8s.pt (small) | 22 MB | Fast | Better |
| yolov8m.pt (medium) | 50 MB | Moderate | Best |
