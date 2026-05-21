from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.actions.audio_to_video import AudioToVideoAction
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.models import AudioToVideoConfig
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext

if TYPE_CHECKING:
    from core.pipeline.step_hooks import StepProgressHooks


class AudioToVideoStep(BaseStep):

    def __init__(self):
        self._action = AudioToVideoAction()
        self._background_image: Path | None = None

    @property
    def name(self) -> str:
        return "Audio a Video"

    def set_background_image(self, path: Path | None) -> None:
        self._background_image = path

    def open_config_modal(self, parent: ctk.CTk) -> None:
        modal = ctk.CTkToplevel(parent)
        modal.title("Configuración — Audio a Video")
        modal.geometry("420x100")
        modal.grab_set()
        modal.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(modal, text="Imagen fondo").grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w"
        )
        img_label = ctk.CTkLabel(
            modal,
            text=self._background_image.name if self._background_image else "Negra por defecto",
            anchor="w",
        )
        img_label.grid(row=0, column=1, padx=8, pady=(16, 8), sticky="ew")

        def pick():
            file = filedialog.askopenfilename(
                filetypes=[("Imagen", "*.jpg *.jpeg *.png *.bmp *.webp")]
            )
            if file:
                self._background_image = Path(file)
                img_label.configure(text=self._background_image.name)
                modal.destroy()

        ctk.CTkButton(modal, text="Elegir", width=90, command=pick).grid(
            row=0, column=2, padx=16, pady=(16, 8)
        )

    def execute(
        self,
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool, PipelineContext], None],
        hooks: "StepProgressHooks | None" = None,
    ) -> None:
        config = AudioToVideoConfig(
            input_files=context.current_files,
            base_folder=context.base_folder,
            background_image=self._background_image,
        )
        args_list = self._action.build_args_list(config)
        output_files = self._action.get_output_files(config)
        filenames = [f.name for f in context.current_files]

        durations: list[float] | None = None
        if hooks:
            durations = [get_duration(FFPROBE_BIN, f) for f in context.current_files]
            if hooks.on_setup:
                hooks.on_setup(filenames, context.base_folder.name)

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
                        (active_idx[0] + value) / len(filenames)
                    )

        def on_file_done_cb(i: int):
            if hooks and hooks.on_file_done:
                hooks.on_file_done(filenames[i])

        def done(success: bool):
            if success:
                # AudioToVideo produce videos → actualizar current_files con los videos
                # pero preservar audio_files para que TranscribeStep los encuentre
                context.current_files = output_files
                # context.audio_files se deja intacto intencionalmente
            on_done(success, context)

        runner.run_sequential(
            args_list=args_list,
            on_log=on_log,
            on_done=done,
            on_progress=on_progress if hooks else None,
            on_file_start=on_file_start if hooks else None,
            on_file_done=on_file_done_cb if hooks else None,
            durations=durations,
        )