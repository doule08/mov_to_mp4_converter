"""Description d'une vidéo et calcul de la géométrie de sortie (logique pure, sans ffmpeg)."""

from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".mkv", ".avi"}
SUFFIX = "_processed"


@dataclass(frozen=True)
class VideoInfo:
    width: int  # après rotation éventuelle, telle qu'affichée
    height: int
    fps: float
    duration: float  # secondes
    has_audio: bool
    codec: str = ""
    video_streams: int = 1


@dataclass(frozen=True)
class Geometry:
    crop: tuple[int, int, int, int] | None  # largeur, hauteur, x, y ; None = image entière
    width: int
    height: int
    fps: float | None  # None = cadence de la source conservée

    def describe(self, source_fps: float) -> str:
        fps = self.fps if self.fps is not None else source_fps
        return f"{self.width}×{self.height}, {fps:g} i/s, sans audio"


def even(value: float) -> int:
    """Nombre pair le plus proche (exigé par H.264 en yuv420p)."""
    return max(2, round(value / 2) * 2)


def output_geometry(
    info: VideoInfo,
    width: int | None,
    ratio: tuple[int, int] | None,
    fps: int | None,
) -> Geometry:
    """Recadrage centré vers le ratio, puis réduction ; jamais d'agrandissement ni de cadence plus haute que la source."""
    crop_w, crop_h = info.width, info.height
    if ratio is not None:
        a, b = ratio
        if info.width * b > info.height * a:  # source plus large que le ratio
            crop_w = info.height * a / b
        else:
            crop_h = info.width * b / a
    crop_w, crop_h = min(even(crop_w), info.width), min(even(crop_h), info.height)
    crop = None
    if (crop_w, crop_h) != (info.width, info.height):
        crop = (crop_w, crop_h, (info.width - crop_w) // 2, (info.height - crop_h) // 2)

    out_w = even(crop_w if width is None else min(width, crop_w))
    # Ratio choisi : hauteur exacte (1280 en 16:9 → 720), pas celle du recadrage arrondi.
    out_h = even(out_w * ratio[1] / ratio[0] if ratio is not None else out_w * crop_h / crop_w)

    out_fps = None if fps is None or fps >= info.fps else float(fps)
    return Geometry(crop, out_w, out_h, out_fps)


def output_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}{SUFFIX}.mp4")


def is_processed(path: Path) -> bool:
    return path.stem.endswith(SUFFIX)
