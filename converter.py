"""Conversion d'un lot de vidéos dans un thread, sans dépendance à l'interface."""

import queue
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from ffmpeg_tools import NO_WINDOW, build_ffmpeg_command, check_output, probe
from model import Geometry, VideoInfo, output_path


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_size(size: int) -> str:
    return f"{size / 1024**2:.1f} Mo"


class Cancelled(Exception):
    pass


class Converter:
    """Convertit une liste de vidéos dans un thread ; envoie ses nouvelles à l'interface par une file."""

    def __init__(self, ffmpeg: str, ffprobe: str, jobs: list[tuple[Path, VideoInfo, Geometry]], events: queue.Queue):
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        self.jobs = jobs
        self.events = events
        self.cancel = threading.Event()
        self.process: subprocess.Popen | None = None
        self.thread = threading.Thread(target=self.run, name="conversion", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.cancel.set()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def emit(self, kind: str, *args) -> None:
        self.events.put((kind, *args))

    def run(self) -> None:
        done = failed = 0
        for number, (source, info, geometry) in enumerate(self.jobs, start=1):
            if self.cancel.is_set():
                break
            self.emit("file", number, len(self.jobs), source)
            try:
                self.convert(source, info, geometry)
                done += 1
            except Cancelled:
                self.emit("log", f"Annulé : {source.name}")
                break
            except Exception as error:  # un fichier en échec n'arrête pas le lot
                failed += 1
                self.emit("log", f"ÉCHEC {source.name} : {error}")
        self.emit("finished", done, failed, self.cancel.is_set())

    def convert(self, source: Path, info: VideoInfo, geometry: Geometry) -> None:
        target = output_path(source)
        command = build_ffmpeg_command(self.ffmpeg, source, target, geometry)
        self.emit("log", f"→ {source.name} : {info.width}×{info.height} {info.fps:g} i/s → {geometry.describe(info.fps)}")
        started = time.monotonic()
        errors: deque[str] = deque(maxlen=15)
        try:
            process = self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
            )  # fmt: skip
            stdout, stderr = process.stdout, process.stderr
            assert stdout is not None and stderr is not None  # PIPE demandés
            # stderr lu à part : sinon ffmpeg bloque quand le tampon est plein.
            reader = threading.Thread(target=lambda: errors.extend(stderr), daemon=True)
            reader.start()
            for line in stdout:
                key, _, value = line.strip().partition("=")
                if key == "out_time_us" and value.isdigit() and info.duration > 0:
                    self.emit("progress", min(1.0, int(value) / 1e6 / info.duration))
            code = self.process.wait()
            reader.join(2)
            if self.cancel.is_set():
                raise Cancelled
            if code != 0:
                raise RuntimeError(" | ".join(line.strip() for line in errors if line.strip()) or f"code {code}")
        except BaseException:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()
                self.process.wait()
            target.unlink(missing_ok=True)  # jamais de fichier partiel
            raise
        finally:
            self.process = None

        self.emit("progress", 1.0)
        elapsed = time.monotonic() - started
        self.emit(
            "log",
            f"✓ {target.name} en {format_duration(elapsed)} "
            f"({format_size(source.stat().st_size)} → {format_size(target.stat().st_size)})",
        )
        try:
            problems = check_output(probe(self.ffprobe, target), info, geometry)
        except ValueError as error:
            problems = [f"relecture impossible : {error}"]
        for problem in problems:
            self.emit("log", f"  ⚠ {problem}")
