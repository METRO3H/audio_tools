from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.actions.diverge_audio import DivergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.models import DivergeAudioConfig
from ui.views.base_action_view import BaseActionView

FORMATS = ["mp3", "wav", "aac", "m4a", "ogg", "flac"]


class DivergeAudioView(BaseActionView):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, **kwargs):
        super().__init__(parent, runner, on_log, **kwargs)
        self._action = DivergeAudioAction()
        self._input_file: Path | None = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        self._build_base_folder_row(row=0)

        ctk.CTkLabel(self, text="Audio").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self._file_label = ctk.CTkLabel(self, text="Sin seleccionar", anchor="w")
        self._file_label.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self, text="Seleccionar", width=90, command=self._pick_file).grid(row=1, column=2, padx=12, pady=4)

        ctk.CTkLabel(self, text="Intervalo (min)").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        interval_frame = ctk.CTkFrame(self, fg_color="transparent")
        interval_frame.grid(row=2, column=1, padx=4, pady=4, sticky="w")
        self._interval_entry = ctk.CTkEntry(interval_frame, width=80)
        self._interval_entry.insert(0, "30")
        self._interval_entry.grid(row=0, column=0, padx=(0, 12))

        ctk.CTkLabel(self, text="Formato").grid(row=3, column=0, padx=12, pady=4, sticky="w")
        self._format_selector = ctk.CTkOptionMenu(self, values=FORMATS, width=80)
        self._format_selector.set("mp3")
        self._format_selector.grid(row=3, column=1, padx=4, pady=4, sticky="w")

        self._build_run_button(row=4, text="Ejecutar diverge")

    def _pick_file(self):
        file = filedialog.askopenfilename(
            initialdir=self._base_folder,
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac")],
        )
        if file:
            self._input_file = Path(file)
            self._file_label.configure(text=self._input_file.name)
            self._set_run_btn_enabled(True)

    def _run(self):
        if not self._input_file:
            return

        try:
            interval = int(self._interval_entry.get().strip()) * 60
        except ValueError:
            self._on_log("✗ El intervalo debe ser un número entero.")
            return

        config = DivergeAudioConfig(
            input_file=self._input_file,
            base_folder=self._base_folder,
            interval_seconds=interval,
            output_format=self._format_selector.get(),
        )

        self._on_log("Obteniendo duración del audio...")
        duration = get_duration(FFPROBE_BIN, self._input_file)
        args_list = self._action.build_args_list(config, duration)
        self._on_log(f"Dividiendo en {len(args_list)} partes...")

        self._execute_sequential(args_list, self._finish)

    def _finish(self, success: bool):
        self._set_run_btn_enabled(True)
        self._log_elapsed_time()
        self._on_log("✓ Diverge completado." if success else "✗ Error en el diverge.")