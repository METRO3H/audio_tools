from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import DEFAULT_BASE_FOLDER
from core.ffmpeg_runner import FFmpegRunner


class BaseActionView(ctk.CTkFrame):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self._runner = runner
        self._on_log = on_log
        self._base_folder = DEFAULT_BASE_FOLDER

    # ── Carpeta base ──────────────────────────────────────────────────────────

    def _build_base_folder_row(self, row: int):
        ctk.CTkLabel(self, text="Carpeta base").grid(row=row, column=0, padx=12, pady=(12, 4), sticky="w")
        self._base_folder_label = ctk.CTkLabel(self, text=str(self._base_folder), anchor="w")
        self._base_folder_label.grid(row=row, column=1, padx=4, pady=(12, 4), sticky="ew")
        ctk.CTkButton(self, text="Cambiar", width=90, command=self._pick_base_folder).grid(row=row, column=2, padx=12, pady=(12, 4))

    def _pick_base_folder(self):
        folder = filedialog.askdirectory(initialdir=self._base_folder)
        if folder:
            self._base_folder = Path(folder)
            self._base_folder_label.configure(text=str(self._base_folder))
            self._on_base_folder_changed()

    def _on_base_folder_changed(self):
        pass

    # ── Botón ejecutar ────────────────────────────────────────────────────────

    def _build_run_button(self, row: int, text: str = "Ejecutar"):
        self._run_btn = ctk.CTkButton(self, text=text, command=self._run, state="disabled")
        self._run_btn.grid(row=row, column=0, columnspan=3, padx=12, pady=12)

    def _set_run_btn_enabled(self, enabled: bool):
        self._run_btn.configure(state="normal" if enabled else "disabled")

    # ── Ejecución ─────────────────────────────────────────────────────────────

    def _execute(self, args: list[str], on_done: Callable[[bool], None]):
        self._set_run_btn_enabled(False)
        self._runner.run(
            args=args,
            on_log=lambda line: self.after(0, lambda l=line: self._on_log(l)),
            on_done=lambda ok: self.after(0, lambda: on_done(ok)),
        )

    # ── Subclases implementan estos ───────────────────────────────────────────

    def _build(self):
        raise NotImplementedError

    def _run(self):
        raise NotImplementedError