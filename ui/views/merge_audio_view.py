from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import DEFAULT_BASE_FOLDER
from core.actions.merge_audio import MergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import MergeAudioConfig


class MergeAudioView(ctk.CTkFrame):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self._runner = runner
        self._on_log = on_log
        self._action = MergeAudioAction()
        self._base_folder = DEFAULT_BASE_FOLDER
        self._selected_files: list[Path] = []
        self._output_file: Path | None = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        # ── Carpeta base ──────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Carpeta base").grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        self._base_folder_label = ctk.CTkLabel(self, text=str(self._base_folder), anchor="w")
        self._base_folder_label.grid(row=0, column=1, padx=4, pady=(12, 4), sticky="ew")
        ctk.CTkButton(self, text="Cambiar", width=90, command=self._pick_base_folder).grid(row=0, column=2, padx=12, pady=(12, 4))

        # ── Selección de archivos ─────────────────────────────────────────────
        ctk.CTkLabel(self, text="Archivos").grid(row=1, column=0, padx=12, pady=4, sticky="nw")
        self._files_box = ctk.CTkTextbox(self, height=120, state="disabled")
        self._files_box.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self, text="Seleccionar", width=90, command=self._pick_files).grid(row=1, column=2, padx=12, pady=4, sticky="n")

        # ── Archivo de salida ─────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Guardar como").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self._output_label = ctk.CTkLabel(self, text="Sin seleccionar", anchor="w")
        self._output_label.grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self, text="Elegir", width=90, command=self._pick_output).grid(row=2, column=2, padx=12, pady=4)

        # ── Botón ejecutar ────────────────────────────────────────────────────
        self._run_btn = ctk.CTkButton(self, text="Ejecutar merge", command=self._run, state="disabled")
        self._run_btn.grid(row=3, column=0, columnspan=3, padx=12, pady=12)

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _pick_base_folder(self):
        folder = filedialog.askdirectory(initialdir=self._base_folder)
        if folder:
            self._base_folder = Path(folder)
            self._base_folder_label.configure(text=str(self._base_folder))

    def _pick_files(self):
        files = filedialog.askopenfilenames(
            initialdir=self._base_folder,
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac")],
        )
        if files:
            self._selected_files = sorted(Path(f) for f in files)
            self._refresh_files_box()
            self._update_run_btn()

    def _pick_output(self):
        file = filedialog.asksaveasfilename(
            initialdir=self._base_folder,
            defaultextension=".mp3",
            filetypes=[("MP3", "*.mp3"), ("WAV", "*.wav")],
        )
        if file:
            self._output_file = Path(file)
            self._output_label.configure(text=str(self._output_file))
            self._update_run_btn()

    def _run(self):
        config = MergeAudioConfig(
            input_files=self._selected_files,
            output_file=self._output_file,
            base_folder=self._base_folder,
        )
        self._run_btn.configure(state="disabled")
        self._on_log("Iniciando merge...")
        self._runner.run(
            args=self._action.build_args(config),
            on_log=lambda line: self.after(0, lambda l=line: self._on_log(l)),
            on_done=lambda ok: self.after(0, lambda: self._finish(ok)),
        )

    def _finish(self, success: bool):
        self._action.cleanup()
        self._run_btn.configure(state="normal")
        self._on_log("✓ Merge completado." if success else "✗ Error en el merge.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_files_box(self):
        self._files_box.configure(state="normal")
        self._files_box.delete("1.0", "end")
        for f in self._selected_files:
            self._files_box.insert("end", f.name + "\n")
        self._files_box.configure(state="disabled")

    def _update_run_btn(self):
        ready = self._selected_files and self._output_file is not None
        self._run_btn.configure(state="normal" if ready else "disabled")