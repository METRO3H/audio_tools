from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from core.actions.audio_to_video import AudioToVideoAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import AudioToVideoConfig
from ui.views.base_action_view import BaseActionView


class AudioToVideoView(BaseActionView):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, **kwargs):
        super().__init__(parent, runner, on_log, **kwargs)
        self._action = AudioToVideoAction()
        self._selected_files: list[Path] = []
        self._background_image: Path | None = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        self._build_base_folder_row(row=0)

        ctk.CTkLabel(self, text="Audios").grid(row=1, column=0, padx=12, pady=4, sticky="nw")
        self._files_box = ctk.CTkTextbox(self, height=120, state="disabled")
        self._files_box.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self, text="Seleccionar", width=90, command=self._pick_files).grid(row=1, column=2, padx=12, pady=4, sticky="n")

        ctk.CTkLabel(self, text="Imagen fondo").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self._image_label = ctk.CTkLabel(self, text="Negra por defecto", anchor="w")
        self._image_label.grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self, text="Elegir", width=90, command=self._pick_image).grid(row=2, column=2, padx=12, pady=4)

        self._build_run_button(row=3, text="Convertir a video")

    def _pick_files(self):
        files = filedialog.askopenfilenames(
            initialdir=self._base_folder,
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac")],
        )
        if files:
            self._selected_files = sorted(Path(f) for f in files)
            self._refresh_files_box()
            self._set_run_btn_enabled(True)

    def _pick_image(self):
        file = filedialog.askopenfilename(
            initialdir=self._base_folder,
            filetypes=[("Imagen", "*.jpg *.jpeg *.png *.bmp")],
        )
        if file:
            self._background_image = Path(file)
            self._image_label.configure(text=self._background_image.name)

    def _run(self):
        if not self._selected_files:
            return

        config = AudioToVideoConfig(
            input_files=self._selected_files,
            base_folder=self._base_folder,
            background_image=self._background_image,
        )

        args_list = self._action.build_args_list(config)
        self._on_log(f"Convirtiendo {len(args_list)} archivo(s) a video...")
        self._execute_sequential(args_list, self._finish)

    def _finish(self, success: bool):
        self._set_run_btn_enabled(True)
        self._on_log("✓ Conversión completada." if success else "✗ Error en la conversión.")

    def _refresh_files_box(self):
        self._files_box.configure(state="normal")
        self._files_box.delete("1.0", "end")
        for f in self._selected_files:
            self._files_box.insert("end", f.name + "\n")
        self._files_box.configure(state="disabled")