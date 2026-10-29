# Video converter for `vision`

Small GUI tool that turns room recordings (e.g. Insta360 `.mov` captures) into lightweight MP4 files that the music-assistant `vision` project can replay with `--video` (people counting with YOLO / YOLO-pose, motion and brightness measures).

## Requirements

- Python 3.10+ with `tkinter` (included in the standard Windows installer)
- `ffmpeg` and `ffprobe` on the `PATH` (`winget install Gyan.FFmpeg`)

No other dependency.

## Usage

```
python main.py
```

1. **Add files…** (multi-select) or **Add folder…** (every video in the folder; files already ending with `_processed` are skipped).
2. Pick the **resolution** (output width), **ratio** and **frame rate**. The _Output_ column shows the result for each file.
3. Click **Convert**. Each video is written next to its source as `<name>_processed.mp4`.

The UI labels are in French.

## Output

- MP4, H.264 (`crf 23`, `yuv420p`), `+faststart`
- No audio, no subtitles, no metadata (date, device, GPS are stripped)
- Same duration as the source: no trimming, so timestamps in `vision`'s `--csv` match the original video
- A different ratio is obtained by **center cropping**. Black bars would skew the brightness measure, and stretching would distort people.
- Never upscaled, and the frame rate is never raised above the source
- Each output is checked with `ffprobe` (codec, size, frame rate, no audio, duration); any mismatch is logged

Cancelling or a failed conversion deletes the partial file. A failed file does not stop the batch.

## Recommended settings for `vision`

| Setting    | Value                                                                    | Why                                                                      |
| ---------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| Resolution | `1280`                                                                   | same as the Insta360 Link 2C webcam; `vision` downsizes to 640 px itself |
| Ratio      | `16:9` to match the webcam, or `Original` to keep the whole frame        |                                                                          |
| Frame rate | `30` (webcam) or `10` (lighter; `vision` analyzes one frame every 1–2 s) |                                                                          |

Example: a 3 min 20 s capture (1420×1080, 60 fps, 64 MB) gives a 1280×720, 30 fps file of 18 MB in about 15 s.

Then copy the file into `vision/videos/` (ignored by Git) and run:

```
uv run src/main.py --video videos/<name>_processed.mp4
```

## Files

| File               | Content                                                             |
| ------------------ | ------------------------------------------------------------------- |
| `main.py`          | entry point                                                         |
| `convert_videos.py` | tkinter UI                                                         |
| `converter.py`     | batch conversion thread (progress, cancel, partial file cleanup)    |
| `ffmpeg_tools.py`  | ffmpeg command, ffprobe parsing, output check                       |
| `model.py`         | `VideoInfo`, `Geometry`, crop/size computation, output naming       |

## Tests

```
uvx pytest -q
```

The tests cover the pure logic (crop and size, frame rate cap, ffmpeg command, output name, ffprobe parsing, output check) and never call ffmpeg.
