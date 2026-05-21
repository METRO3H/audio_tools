import time
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import DEFAULT_BASE_FOLDER
from core.ffmpeg_runner import FFmpegRunner


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}min")
    parts.append(f"{s}seg")
    return " ".join(parts)


class BaseActionView(ctk.CTkFrame):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self._runner = runner
        self._on_log = on_log
        self._base_folder = DEFAULT_BASE_FOLDER
        self._start_time: float | None = None
        self._was_cancelled = False

    def _cancel(self):
        self._was_cancelled = True
        self._runner.cancel()

    def _build_base_folder_row(self, row: int, parent=None):
        p = parent or self
        ctk.CTkLabel(p, text="Carpeta base").grid(
            row=row, column=0, padx=12, pady=(12, 4), sticky="w")
        self._base_folder_label = ctk.CTkLabel(
            p, text=str(self._base_folder), anchor="w")
        self._base_folder_label.grid(
            row=row, column=1, padx=4, pady=(12, 4), sticky="ew")
        ctk.CTkButton(p, text="Cambiar", width=90, command=self._pick_base_folder).grid(
            row=row, column=2, padx=12, pady=(12, 4))

    def _pick_base_folder(self):
        folder = filedialog.askdirectory(initialdir=self._base_folder)
        if folder:
            self._base_folder = Path(folder)
            self._base_folder_label.configure(text=str(self._base_folder))
            self._on_base_folder_changed()

    def _on_base_folder_changed(self):
        pass

    def _build_run_button(self, row: int, text: str = "Ejecutar", parent=None):
        p = parent or self
        self._run_btn = ctk.CTkButton(
            p, text=text, command=self._run, state="disabled")
        self._run_btn.grid(row=row, column=0, columnspan=3, padx=12, pady=12)

    def _set_run_btn_enabled(self, enabled: bool):
        self._run_btn.configure(state="normal" if enabled else "disabled")

    def _execute(
        self,
        args: list[str],
        on_done: Callable[[bool], None],
        on_progress: Callable[[float], None] | None = None,
        duration: float | None = None,
    ):
        self._start_time = time.monotonic()
        self._was_cancelled = False
        self._runner.run(
            args=args,
            on_log=lambda line: self.after(0, lambda l=line: self._on_log(l)),
            on_done=lambda ok: self.after(0, lambda: on_done(ok)),
            on_progress=on_progress,
            duration=duration,
        )

    def _execute_sequential(
        self,
        args_list: list[list[str]],
        on_done: Callable[[bool], None],
        on_progress: Callable[[float], None] | None = None,
        on_file_start: Callable[[int], None] | None = None,
        on_file_done: Callable[[int], None] | None = None,
        durations: list[float] | None = None,
    ):
        self._start_time = time.monotonic()
        self._was_cancelled = False
        self._runner.run_sequential(
            args_list=args_list,
            on_log=lambda line: self.after(0, lambda l=line: self._on_log(l)),
            on_done=lambda ok: self.after(0, lambda: on_done(ok)),
            on_progress=on_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done,
            durations=durations,
        )

    def _log_summary(self, label: str = "Resumen"):
        """Imprime un bloque de resumen con el tiempo total de la acción."""
        if self._start_time is None:
            return
        elapsed = int(time.monotonic() - self._start_time)
        sep = "─" * 38
        self._on_log(sep)
        self._on_log(f"  {label}")
        self._on_log(f"  Tiempo total : {_format_duration(elapsed)}")
        self._on_log(sep)

    # Alias para compatibilidad con llamadas existentes
    def _log_elapsed_time(self):
        self._log_summary()

    def _build(self):
        raise NotImplementedError

    def _run(self):
        raise NotImplementedError
