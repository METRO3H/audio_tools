from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from config import FFMPEG_BIN, FFPROBE_BIN
from core.actions.merge_audio import MergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.models import MergeAudioConfig
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext

if TYPE_CHECKING:
    from core.pipeline.step_hooks import StepProgressHooks

FORMATS = ["mp3", "wav", "aac", "m4a", "ogg", "flac"]


class MergeStep(BaseStep):

    def __init__(self):
        self._action = MergeAudioAction()
        self._output_name: str = "merged"
        self._output_format: str = "mp3"

    @property
    def name(self) -> str:
        return "Merge"

    def open_config_modal(self, parent: ctk.CTk) -> None:
        modal = ctk.CTkToplevel(parent)
        modal.title("Configuración — Merge")
        modal.geometry("380x160")
        modal.grab_set()
        modal.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(modal, text="Nombre salida").grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        name_frame = ctk.CTkFrame(modal, fg_color="transparent")
        name_frame.grid(row=0, column=1, padx=16, pady=(16, 8), sticky="ew")
        name_frame.grid_columnconfigure(0, weight=1)

        name_entry = ctk.CTkEntry(name_frame, placeholder_text="nombre de carpeta base")
        name_entry.insert(0, self._output_name if self._output_name != "merged" else "")
        name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        fmt = ctk.CTkOptionMenu(name_frame, values=FORMATS, width=80)
        fmt.set(self._output_format)
        fmt.grid(row=0, column=1)

        def save():
            value = name_entry.get().strip()
            self._output_name = value if value else "merged"
            self._output_format = fmt.get()
            modal.destroy()

        ctk.CTkButton(modal, text="Guardar", command=save).grid(
            row=1, column=0, columnspan=2, padx=16, pady=16
        )

    def execute(
        self,
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool, PipelineContext], None],
        hooks: "StepProgressHooks | None" = None,
    ) -> None:
        name = (
            self._output_name
            if self._output_name != "merged"
            else context.base_folder.name
        )
        output_file = (
            context.current_files[0].parent / f"{name}.{self._output_format}"
        )
        config = MergeAudioConfig(
            input_files=context.current_files,
            output_file=output_file,
            base_folder=context.base_folder,
        )

        # Duraciones para progress tracking y para add_chapters al finalizar
        durations = [get_duration(FFPROBE_BIN, f) for f in context.current_files]
        duration_total = sum(durations)
        filenames = [f.name for f in context.current_files]

        args = self._action.build_args(config, on_log=on_log)   # ← mismo comando original

        # ── Hooks ────────────────────────────────────────────────────
        on_progress_cb = None

        if hooks:
            if hooks.on_setup:
                hooks.on_setup(filenames, output_file.stem)
            if hooks.on_file_active and filenames:
                hooks.on_file_active(filenames[0])

            current_idx = [0]

            def on_progress_cb(value: float):
                elapsed = value * duration_total
                cumulative = 0.0
                for i, (fname, dur) in enumerate(zip(filenames, durations)):
                    if elapsed <= cumulative + dur:
                        if i != current_idx[0]:
                            for j in range(current_idx[0], i):
                                if hooks.on_file_done:
                                    hooks.on_file_done(filenames[j])
                            current_idx[0] = i
                            if hooks.on_file_active:
                                hooks.on_file_active(fname)
                        file_progress = (elapsed - cumulative) / dur if dur > 0 else 0
                        if hooks.on_file_progress:
                            hooks.on_file_progress(fname, file_progress)
                        break
                    cumulative += dur
                if hooks.on_pipeline_progress:
                    hooks.on_pipeline_progress(value)

        # ── Ejecución ─────────────────────────────────────────────────
        input_files_snapshot = list(context.current_files)   # copia antes de modificar

        def done(success: bool):
            if success:
                # add_chapters corre en el worker thread: sin bloquear la UI
                self._action.add_chapters(
                    output_file, input_files_snapshot, durations, FFMPEG_BIN
                )
                context.current_files = [output_file]
            self._action.cleanup()
            on_done(success, context)

        runner.run(
            args=args,
            on_log=on_log,
            on_done=done,
            on_progress=on_progress_cb,
            duration=duration_total,
        )