"""Appels à ffmpeg / ffprobe : commande de conversion, lecture des infos d'une vidéo, contrôle de la sortie."""

import json
import subprocess
from fractions import Fraction
from pathlib import Path

from model import Geometry, VideoInfo

DURATION_TOLERANCE_SECONDS = 0.5
# Sous Windows, ffmpeg ne doit pas ouvrir de console.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def build_ffmpeg_command(ffmpeg: str, source: Path, target: Path, geometry: Geometry) -> list[str]:
    filters = []
    if geometry.crop is not None:
        w, h, x, y = geometry.crop
        filters.append(f"crop={w}:{h}:{x}:{y}")
    filters.append(f"scale={geometry.width}:{geometry.height}:flags=area")
    if geometry.fps is not None:
        filters.append(f"fps={geometry.fps:g}")
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y",
        "-i", str(source),
        "-map", "0:v:0", "-an", "-sn", "-dn",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        str(target),
    ]  # fmt: skip


def parse_fraction(text: str) -> float:
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return 0.0
    return float(value)


def parse_probe(data: dict) -> VideoInfo:
    streams = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    if not videos:
        raise ValueError("aucun flux vidéo")
    video = videos[0]
    width, height = int(video["width"]), int(video["height"])
    rotation = 0
    for side in video.get("side_data_list", []):
        rotation = int(float(side.get("rotation", rotation)))
    if abs(rotation) % 180 == 90:  # ffmpeg applique la rotation : l'image affichée est tournée
        width, height = height, width
    fps = parse_fraction(video.get("avg_frame_rate", "0")) or parse_fraction(video.get("r_frame_rate", "0"))
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    return VideoInfo(
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        codec=video.get("codec_name", ""),
        video_streams=len(videos),
    )


def probe(ffprobe: str, path: Path) -> VideoInfo:
    result = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration"
            ":stream_side_data=rotation:format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
    )  # fmt: skip
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "ffprobe a échoué")
    return parse_probe(json.loads(result.stdout))


def check_output(info: VideoInfo, source: VideoInfo, geometry: Geometry) -> list[str]:
    """Écarts entre la sortie et ce qui était demandé ; liste vide si tout est conforme."""
    problems = []
    if info.video_streams != 1 or info.codec != "h264":
        problems.append(f"flux vidéo inattendu ({info.video_streams} flux, codec {info.codec})")
    if info.has_audio:
        problems.append("la sortie contient de l'audio")
    if (info.width, info.height) != (geometry.width, geometry.height):
        problems.append(f"taille {info.width}×{info.height} au lieu de {geometry.width}×{geometry.height}")
    expected_fps = geometry.fps if geometry.fps is not None else source.fps
    if abs(info.fps - expected_fps) > 0.05:
        problems.append(f"cadence {info.fps:g} au lieu de {expected_fps:g} i/s")
    if abs(info.duration - source.duration) > DURATION_TOLERANCE_SECONDS:
        problems.append(f"durée {info.duration:.1f} s au lieu de {source.duration:.1f} s")
    return problems
