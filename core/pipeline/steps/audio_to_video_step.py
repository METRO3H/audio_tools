from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from core.actions.audio_to_video import AudioToVideoAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import AudioToVideoConfig
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext


class AudioToVideoStep(BaseStep):

    def __init__(self):
        self._action = AudioToVideoAction()
        self._background_image: Path | None = None

    @property
    def name(self) -> str:
        return "Audio a Video"

    def open_config_modal(self, parent: ctk.CTk) -> None:
        modal = ctk.CTkToplevel(parent)
        modal.title("Configuración — Audio a Video")
        modal.geometry("420x140")
        modal.grab_set()
        modal.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(modal, text="Imagen fondo").grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        img_label = ctk.CTkLabel(
            modal,
            text=self._background_image.name if self._background_image else "Negra por defecto",
            anchor="w",
        )
        img_label.grid(row=0, column=1, padx=8, pady=(16, 8), sticky="ew")

        def pick():
            file = filedialog.askopenfilename(
                filetypes=[("Imagen", "*.jpg *.jpeg *.png *.bmp")]
            )
            if file:
                self._background_image = Path(file)
                img_label.configure(text=self._background_image.name)

        ctk.CTkButton(modal, text="Elegir", width=90, command=pick).grid(row=0, column=2, padx=16, pady=(16, 8))
        ctk.CTkButton(modal, text="Cerrar", command=modal.destroy).grid(
            row=1, column=0, columnspan=3, padx=16, pady=16
        )

    def execute(
        self,
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool, PipelineContext], None],
    ) -> None:
        config = AudioToVideoConfig(
            input_files=context.current_files,
            base_folder=context.base_folder,
            background_image=self._background_image,
        )
        args_list = self._action.build_args_list(config)

        def done(success: bool):
            on_done(success, context)

        runner.run_sequential(args_list=args_list, on_log=on_log, on_done=done)