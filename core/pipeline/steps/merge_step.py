from pathlib import Path
from typing import Callable

import customtkinter as ctk

from core.actions.merge_audio import MergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import MergeAudioConfig
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext

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
    ) -> None:
        name = self._output_name if self._output_name != "merged" else context.base_folder.name
        output_file = (
            context.current_files[0].parent
            / f"{name}.{self._output_format}"
        )
        config = MergeAudioConfig(
            input_files=context.current_files,
            output_file=output_file,
            base_folder=context.base_folder,
        )
        args = self._action.build_args(config)

        def done(success: bool):
            self._action.cleanup()
            if success:
                context.current_files = [output_file]
            on_done(success, context)

        runner.run(args=args, on_log=on_log, on_done=done)