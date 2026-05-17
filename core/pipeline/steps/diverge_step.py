from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.actions.diverge_audio import DivergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.models import DivergeAudioConfig
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext

if TYPE_CHECKING:
    from core.pipeline.step_hooks import StepProgressHooks

FORMATS = ["mp3", "wav", "aac", "m4a", "ogg", "flac"]


class DivergeStep(BaseStep):

    def __init__(self):
        self._action = DivergeAudioAction()
        self._interval_minutes: int = 30
        self._output_format: str = "mp3"

    @property
    def name(self) -> str:
        return "Diverge"

    def open_config_modal(self, parent: ctk.CTk) -> None:
        modal = ctk.CTkToplevel(parent)
        modal.title("Configuración — Diverge")
        modal.geometry("380x180")
        modal.grab_set()
        modal.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(modal, text="Intervalo (min)").grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        interval_entry = ctk.CTkEntry(modal, width=80)
        interval_entry.insert(0, str(self._interval_minutes))
        interval_entry.grid(row=0, column=1, padx=16, pady=(16, 8), sticky="w")

        ctk.CTkLabel(modal, text="Formato").grid(row=1, column=0, padx=16, pady=8, sticky="w")
        fmt = ctk.CTkOptionMenu(modal, values=FORMATS, width=80)
        fmt.set(self._output_format)
        fmt.grid(row=1, column=1, padx=16, pady=8, sticky="w")

        def save():
            try:
                self._interval_minutes = int(interval_entry.get().strip())
            except ValueError:
                pass
            self._output_format = fmt.get()
            modal.destroy()

        ctk.CTkButton(modal, text="Guardar", command=save).grid(
            row=2, column=0, columnspan=2, padx=16, pady=16
        )

    def execute(
        self,
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool, PipelineContext], None],
        hooks: "StepProgressHooks | None" = None,
    ) -> None:
        input_file = context.current_files[0]
        interval_seconds = self._interval_minutes * 60
        config = DivergeAudioConfig(
            input_file=input_file,
            base_folder=context.base_folder,
            interval_seconds=interval_seconds,
            output_format=self._output_format,
        )
        duration = get_duration(FFPROBE_BIN, input_file)
        args_list = self._action.build_args_list(config, duration)
        output_files = self._action.get_output_files(config, duration)
        part_durations = [
            end - start
            for start, end in self._action._calculate_segments(duration, interval_seconds)
        ]
        filenames = [f.name for f in output_files]

        # ── Hooks: setup y callbacks de progreso ──────────────────────
        if hooks and hooks.on_setup:
            hooks.on_setup(filenames, input_file.stem)

        active_idx = [0]

        def on_file_start(i: int):
            active_idx[0] = i
            if hooks and hooks.on_file_active:
                hooks.on_file_active(filenames[i])

        def on_progress(value: float):
            if hooks:
                if hooks.on_file_progress:
                    hooks.on_file_progress(filenames[active_idx[0]], value)
                if hooks.on_pipeline_progress:
                    hooks.on_pipeline_progress(
                        (active_idx[0] + value) / len(output_files)
                    )

        def on_file_done_cb(i: int):
            if hooks and hooks.on_file_done:
                hooks.on_file_done(filenames[i])

        # ── Ejecución ─────────────────────────────────────────────────
        def done(success: bool):
            if success:
                context.current_files = output_files
            on_done(success, context)

        runner.run_sequential(
            args_list=args_list,
            on_log=on_log,
            on_done=done,
            on_progress=on_progress if hooks else None,
            on_file_start=on_file_start if hooks else None,
            on_file_done=on_file_done_cb if hooks else None,
            durations=part_durations,
        )