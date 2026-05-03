import time
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import DEFAULT_BASE_FOLDER
from core.ffmpeg_runner import FFmpegRunner
from core.pipeline.context import PipelineContext
from core.pipeline.executor import PipelineExecutor
from core.pipeline.steps.audio_to_video_step import AudioToVideoStep
from core.pipeline.steps.diverge_step import DivergeStep
from core.pipeline.steps.merge_step import MergeStep
from ui.components.drag_list import DragList
from ui.views.base_action_view import BaseActionView


class PipelineView(BaseActionView):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, **kwargs):
        super().__init__(parent, runner, on_log, **kwargs)
        self._executor = PipelineExecutor()
        self._selected_files: list[Path] = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Carpeta base").grid(row=0, column=0, padx=(0, 8), pady=(0, 4), sticky="w")
        self._base_folder_label = ctk.CTkLabel(top, text=str(self._base_folder), anchor="w")
        self._base_folder_label.grid(row=0, column=1, padx=4, pady=(0, 4), sticky="ew")
        ctk.CTkButton(top, text="Cambiar", width=90, command=self._pick_base_folder).grid(row=0, column=2, pady=(0, 4))

        ctk.CTkLabel(top, text="Archivos").grid(row=1, column=0, padx=(0, 8), pady=4, sticky="w")
        self._files_label = ctk.CTkLabel(top, text="Sin seleccionar", anchor="w")
        self._files_label.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(top, text="Seleccionar", width=90, command=self._pick_files).grid(row=1, column=2, pady=4)

        self._drag_list = DragList(self, on_active_change=lambda _: self._update_run_btn())
        self._drag_list.set_available([MergeStep(), DivergeStep(), AudioToVideoStep()])
        self._drag_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)

        self._build_run_button(row=2, text="Ejecutar pipeline")

    def _pick_files(self):
        files = filedialog.askopenfilenames(
            initialdir=self._base_folder,
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac")],
        )
        if files:
            self._selected_files = sorted(Path(f) for f in files)
            self._files_label.configure(text=f"{len(self._selected_files)} archivo(s) seleccionado(s)")
            self._update_run_btn()

    def _update_run_btn(self):
        ready = bool(self._selected_files) and bool(self._drag_list.get_active())
        self._set_run_btn_enabled(ready)

    def _run(self):
        steps = self._drag_list.get_active()
        if not steps or not self._selected_files:
            return

        self._start_time = time.monotonic()
        context = PipelineContext(
            base_folder=self._base_folder,
            current_files=list(self._selected_files),
        )
        self._set_run_btn_enabled(False)
        self._on_log(f"Iniciando pipeline con {len(steps)} paso(s)...")
        self._executor.execute(
            steps=steps,
            context=context,
            runner=self._runner,
            on_log=lambda line: self.after(0, lambda l=line: self._on_log(l)),
            on_done=lambda ok: self.after(0, lambda: self._finish(ok)),
        )

    def _finish(self, success: bool):
        self._set_run_btn_enabled(True)
        self._log_elapsed_time()
        self._on_log("✓ Pipeline completado." if success else "✗ Error en el pipeline.")