"""Interface tkinter du convertisseur."""

import json
import queue
import shutil
from pathlib import Path

from converter import Converter, format_duration
from ffmpeg_tools import probe
from model import VIDEO_EXTENSIONS, Geometry, VideoInfo, is_processed, output_geometry, output_path

# Choix des listes déroulantes : libellé -> valeur (None = celle de la source).
WIDTHS = {"Originale": None, "1920": 1920, "1280": 1280, "960": 960, "640": 640}
RATIOS = {"Original": None, "16:9": (16, 9), "4:3": (4, 3), "1:1": (1, 1)}
FPS = {"Originale": None, "30": 30, "25": 25, "15": 15, "10": 10, "5": 5}
DEFAULT_WIDTH, DEFAULT_RATIO, DEFAULT_FPS = "1280", "Original", "30"


def run_app() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Convertisseur vidéo pour vision")
    root.geometry("900x620")
    root.minsize(700, 500)

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    files: dict[Path, VideoInfo] = {}
    events: queue.Queue = queue.Queue()
    state: dict[str, Converter | None] = {"converter": None}

    # --- Sélection ---
    selection = ttk.LabelFrame(root, text="Vidéos", padding=8)
    selection.pack(fill="both", expand=True, padx=10, pady=(10, 5))
    buttons = ttk.Frame(selection)
    buttons.pack(fill="x")
    columns = ("duration", "source", "output")
    tree = ttk.Treeview(selection, columns=columns, height=8)
    tree.heading("#0", text="Fichier")
    tree.heading("duration", text="Durée")
    tree.heading("source", text="Source")
    tree.heading("output", text="Sortie")
    tree.column("#0", width=380)
    tree.column("duration", width=70, anchor="e")
    tree.column("source", width=150)
    tree.column("output", width=200)
    scroll = ttk.Scrollbar(selection, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True, pady=(8, 0))
    scroll.pack(side="right", fill="y", pady=(8, 0))

    # --- Réglages ---
    settings = ttk.LabelFrame(root, text="Réglages (tous les fichiers)", padding=8)
    settings.pack(fill="x", padx=10, pady=5)
    width_var = tk.StringVar(value=DEFAULT_WIDTH)
    ratio_var = tk.StringVar(value=DEFAULT_RATIO)
    fps_var = tk.StringVar(value=DEFAULT_FPS)
    combos = []
    for column, (label, var, choices) in enumerate(
        (("Résolution (largeur)", width_var, WIDTHS), ("Ratio", ratio_var, RATIOS), ("Cadence (i/s)", fps_var, FPS))
    ):
        ttk.Label(settings, text=label).grid(row=0, column=column, sticky="w", padx=(0, 20))
        combo = ttk.Combobox(settings, textvariable=var, values=list(choices), state="readonly", width=14)
        combo.grid(row=1, column=column, sticky="w", padx=(0, 20))
        combos.append(combo)
    ttk.Label(
        settings,
        text="Ratio différent de la source : recadrage centré. Jamais d'agrandissement ni de cadence plus haute.",
        foreground="gray",
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # --- Conversion ---
    run = ttk.LabelFrame(root, text="Conversion", padding=8)
    run.pack(fill="both", padx=10, pady=(5, 10))
    controls = ttk.Frame(run)
    controls.pack(fill="x")
    status = tk.StringVar(value="")
    file_bar = ttk.Progressbar(run, maximum=1.0)
    total_bar = ttk.Progressbar(run, maximum=1.0)
    ttk.Label(run, textvariable=status).pack(fill="x", pady=(6, 0))
    file_bar.pack(fill="x", pady=2)
    total_bar.pack(fill="x", pady=2)
    log_box = tk.Text(run, height=9, state="disabled", wrap="word")
    log_box.pack(fill="both", expand=True, pady=(6, 0))

    def log(message: str) -> None:
        log_box.configure(state="normal")
        log_box.insert("end", message + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    def current_geometry(info: VideoInfo) -> Geometry:
        return output_geometry(info, WIDTHS[width_var.get()], RATIOS[ratio_var.get()], FPS[fps_var.get()])

    def refresh_outputs(*_) -> None:
        for path, info in files.items():
            tree.set(str(path), "output", current_geometry(info).describe(info.fps))
        update_buttons()

    def add(paths) -> None:
        if not ffprobe:
            return
        root.configure(cursor="watch")
        root.update_idletasks()
        try:
            for path in paths:
                path = Path(path).resolve()
                if path in files:
                    continue
                try:
                    info = probe(ffprobe, path)
                except (ValueError, json.JSONDecodeError) as error:
                    log(f"Ignoré {path.name} : {error}")
                    continue
                files[path] = info
                tree.insert(
                    "", "end", iid=str(path), text=str(path),
                    values=(format_duration(info.duration), f"{info.width}×{info.height} {info.fps:g} i/s", ""),
                )  # fmt: skip
        finally:
            root.configure(cursor="")
        refresh_outputs()

    def add_files() -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))
        add(filedialog.askopenfilenames(
            title="Choisir des vidéos",
            filetypes=[("Vidéos", patterns), ("Tous les fichiers", "*.*")],
        ))  # fmt: skip

    def add_folder() -> None:
        folder = filedialog.askdirectory(title="Choisir un dossier de vidéos")
        if not folder:
            return
        videos = sorted(
            p for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS and not is_processed(p)
        )  # fmt: skip
        if not videos:
            log(f"Aucune vidéo à convertir dans {folder}")
        add(videos)

    def remove_selected() -> None:
        for iid in tree.selection():
            files.pop(Path(iid), None)
            tree.delete(iid)
        update_buttons()

    def clear() -> None:
        files.clear()
        tree.delete(*tree.get_children())
        update_buttons()

    def start() -> None:
        if not (ffmpeg and ffprobe):
            return
        jobs = [(path, info, current_geometry(info)) for path, info in files.items()]
        existing = [path for path, _, _ in jobs if output_path(path).exists()]
        if existing:
            names = "\n".join(output_path(p).name for p in existing[:10])
            answer = messagebox.askyesnocancel(
                "Fichiers déjà convertis",
                f"{len(existing)} sortie(s) existe(nt) déjà :\n{names}\n\n"
                "Oui : écraser\nNon : ignorer ces vidéos\nAnnuler : ne rien lancer",
            )
            if answer is None:
                return
            if answer is False:
                jobs = [job for job in jobs if job[0] not in existing]
        if not jobs:
            log("Rien à convertir.")
            return
        converter = Converter(ffmpeg, ffprobe, jobs, events)
        state["converter"] = converter
        total_bar.configure(value=0)
        file_bar.configure(value=0)
        update_buttons()
        converter.start()

    def cancel() -> None:
        if state["converter"] is not None:
            state["converter"].stop()
            status.set("Annulation…")

    add_buttons = (
        ttk.Button(buttons, text="Ajouter des fichiers…", command=add_files),
        ttk.Button(buttons, text="Ajouter un dossier…", command=add_folder),
    )
    add_buttons[0].pack(side="left")
    add_buttons[1].pack(side="left", padx=6)
    remove_button = ttk.Button(buttons, text="Retirer la sélection", command=remove_selected)
    remove_button.pack(side="right")
    clear_button = ttk.Button(buttons, text="Vider", command=clear)
    clear_button.pack(side="right", padx=6)
    convert_button = ttk.Button(controls, text="Convertir", command=start)
    convert_button.pack(side="left")
    cancel_button = ttk.Button(controls, text="Annuler", command=cancel)
    cancel_button.pack(side="left", padx=6)

    def update_buttons() -> None:
        busy = state["converter"] is not None
        ready = bool(files) and ffmpeg and ffprobe and not busy
        convert_button.configure(state="normal" if ready else "disabled")
        cancel_button.configure(state="normal" if busy else "disabled")
        for widget in (remove_button, clear_button, *combos):
            widget.configure(state=("readonly" if widget in combos else "normal") if not busy else "disabled")
        for button in add_buttons:
            button.configure(state="disabled" if busy or not ffprobe else "normal")

    for var in (width_var, ratio_var, fps_var):
        var.trace_add("write", refresh_outputs)

    progress = {"number": 0, "total": 1}

    def poll() -> None:
        try:
            while True:
                kind, *args = events.get_nowait()
                if kind == "file":
                    number, total, source = args
                    progress.update(number=number, total=total)
                    status.set(f"Fichier {number} / {total} : {source.name}")
                    file_bar.configure(value=0)
                    total_bar.configure(value=(number - 1) / total)
                elif kind == "progress":
                    file_bar.configure(value=args[0])
                    total_bar.configure(value=(progress["number"] - 1 + args[0]) / progress["total"])
                elif kind == "log":
                    log(args[0])
                elif kind == "finished":
                    done, failed, cancelled = args
                    state["converter"] = None
                    end = "annulé" if cancelled else "terminé"
                    status.set(f"{end.capitalize()} : {done} converti(s), {failed} échec(s).")
                    log(f"— {end} : {done} converti(s), {failed} échec(s)")
                    update_buttons()
        except queue.Empty:
            pass
        root.after(100, poll)

    def on_close() -> None:
        converter = state["converter"]
        if converter is not None:
            if not messagebox.askyesno("Conversion en cours", "Arrêter la conversion et quitter ?"):
                return
            converter.stop()
            converter.thread.join(10)  # le fichier partiel est supprimé par le thread
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    if not (ffmpeg and ffprobe):
        log("ffmpeg / ffprobe introuvables dans le PATH. Installer avec : winget install Gyan.FFmpeg, puis relancer.")
        messagebox.showerror("ffmpeg introuvable", "ffmpeg et ffprobe doivent être dans le PATH.\nwinget install Gyan.FFmpeg")
    update_buttons()
    poll()
    root.mainloop()
