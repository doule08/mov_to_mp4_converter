import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ffmpeg_tools import build_ffmpeg_command, check_output, parse_probe  # noqa: E402
from model import Geometry, VideoInfo, is_processed, output_geometry, output_path  # noqa: E402

INSTA = VideoInfo(width=1420, height=1080, fps=60.0, duration=200.28, has_audio=True, codec="h264")


def test_original_keeps_everything():
    assert output_geometry(INSTA, None, None, None) == Geometry(None, 1420, 1080, None)


def test_width_keeps_source_ratio_with_even_height():
    g = output_geometry(INSTA, 1280, None, 30)
    assert (g.crop, g.width, g.height, g.fps) == (None, 1280, 974, 30.0)
    g = output_geometry(INSTA, 640, None, None)
    assert (g.width, g.height) == (640, 486)


def test_16_9_crops_height_centered():
    g = output_geometry(INSTA, 1280, (16, 9), 30)
    assert g.crop == (1420, 798, 0, 141)
    assert (g.width, g.height) == (1280, 720)


def test_narrower_ratio_crops_width_centered():
    wide = VideoInfo(1920, 1080, 30.0, 10.0, False)
    g = output_geometry(wide, None, (4, 3), None)
    assert g.crop == (1440, 1080, 240, 0)
    assert (g.width, g.height) == (1440, 1080)
    g = output_geometry(wide, None, (1, 1), None)
    assert g.crop == (1080, 1080, 420, 0)


def test_never_upscales():
    g = output_geometry(INSTA, 1920, None, None)
    assert (g.width, g.height) == (1420, 1080)
    g = output_geometry(INSTA, 1920, (16, 9), None)
    assert (g.width, g.height) == (1420, 798)


def test_fps_capped_at_source():
    slow = VideoInfo(1280, 720, 25.0, 10.0, False)
    assert output_geometry(slow, None, None, 30).fps is None
    assert output_geometry(slow, None, None, 25).fps is None
    assert output_geometry(slow, None, None, 10).fps == 10.0


def test_command_strips_audio_metadata_and_orders_filters():
    g = output_geometry(INSTA, 1280, (16, 9), 30)
    cmd = build_ffmpeg_command("ffmpeg", Path("in.mov"), Path("in_processed.mp4"), g)
    assert cmd[0] == "ffmpeg"
    assert cmd[-1] == "in_processed.mp4"
    for flag in ("-an", "-sn", "-dn"):
        assert flag in cmd
    assert cmd[cmd.index("-map") + 1] == "0:v:0"
    assert cmd[cmd.index("-map_metadata") + 1] == "-1"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-vf") + 1] == "crop=1420:798:0:141,scale=1280:720:flags=area,fps=30"
    assert "-t" not in cmd and "-ss" not in cmd  # durée intacte


def test_command_without_crop_or_fps():
    g = output_geometry(INSTA, None, None, None)
    cmd = build_ffmpeg_command("ffmpeg", Path("a.mov"), Path("a_processed.mp4"), g)
    assert cmd[cmd.index("-vf") + 1] == "scale=1420:1080:flags=area"


def test_output_path_and_processed_detection():
    out = output_path(Path("C:/videos/2026-10-29 11-27-17.mov"))
    assert out == Path("C:/videos/2026-10-29 11-27-17_processed.mp4")
    assert is_processed(out)
    assert not is_processed(Path("C:/videos/2026-10-29 11-27-17.mov"))


def test_parse_probe_reads_fps_audio_and_rotation():
    data = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
             "avg_frame_rate": "30000/1001", "side_data_list": [{"rotation": -90}]},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "12.5"},
    }  # fmt: skip
    info = parse_probe(data)
    assert (info.width, info.height) == (1080, 1920)
    assert abs(info.fps - 29.97) < 0.01
    assert info.duration == 12.5 and info.has_audio and info.codec == "h264"


def test_check_output():
    g = output_geometry(INSTA, 1280, (16, 9), 30)
    good = VideoInfo(1280, 720, 30.0, 200.3, False, "h264")
    assert check_output(good, INSTA, g) == []
    bad = VideoInfo(1280, 720, 60.0, 150.0, True, "h264")
    problems = check_output(bad, INSTA, g)
    assert len(problems) == 3
