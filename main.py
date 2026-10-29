"""Convertit des vidéos de la pièce en MP4 H.264 sans audio, rejouables par `vision` (--video).

Interface tkinter, conversion par ffmpeg. Sortie : <nom>_processed.mp4 dans le dossier de la source.
"""

from convert_videos import run_app

if __name__ == "__main__":
    run_app()
