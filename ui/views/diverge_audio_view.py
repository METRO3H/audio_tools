from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.actions.diverge_audio import DivergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.models import DivergeAudioConfig
from ui.components.progress_panel import ProgressPanel
from ui.views.base_action_view import BaseActionView

FORMATS = ["mp3", "wav", "aac", "m4a", "ogg", "flac"]


class DivergeAudioView(BaseActionView):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, on_toggle_logs: Callable, **kwargs):
        super().__init__(parent, runner, on_log, **kwargs)
        self._on_toggle_logs = on_toggle_logs
        self._action = DivergeAudioAction()
        self._input_file: Path | None = None
        self._output_files: list[Path] = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._config_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._config_frame.grid(row=0, column=0, sticky="nsew")
        self._config_frame.grid_columnconfigure(1, weight=1)

        self._build_base_folder_row(row=0, parent=self._config_frame)

        ctk.CTkLabel(self._config_frame, text="Audio").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self._file_label = ctk.CTkLabel(self._config_frame, text="Sin seleccionar", anchor="w")
        self._file_label.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self._config_frame, text="Seleccionar", width=90, command=self._pick_file).grid(row=1, column=2, padx=12, pady=4)

        ctk.CTkLabel(self._config_frame, text="Intervalo (min)").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self._interval_entry = ctk.CTkEntry(self._config_frame, width=80)
        self._interval_entry.insert(0, "30")
        self._interval_entry.grid(row=2, column=1, padx=4, pady=4, sticky="w")

        ctk.CTkLabel(self._config_frame, text="Formato").grid(row=3, column=0, padx=12, pady=4, sticky="w")
        self._format_selector = ctk.CTkOptionMenu(self._config_frame, values=FORMATS, width=80)
        self._format_selector.set("mp3")
        self._format_selector.grid(row=3, column=1, padx=4, pady=4, sticky="w")

        self._build_run_button(row=4, text="Ejecutar diverge", parent=self._config_frame)

        self._progress_panel = ProgressPanel(self, on_toggle_logs=self._on_toggle_logs)
        self._progress_panel.grid(row=0, column=0, sticky="nsew")
        self._progress_panel.grid_remove()

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

        duration = get_duration(FFPROBE_BIN, self._input_file)
        args_list = self._action.build_args_list(config, duration)
        self._output_files = self._action.get_output_files(config, duration)
        part_durations = [end - start for start, end in self._action._calculate_segments(duration, interval)]

        filenames = [f.name for f in self._output_files]
        self._progress_panel.setup(filenames, title=self._input_file.stem)
        self._config_frame.grid_remove()
        self._progress_panel.grid()

        self._on_log(f"Dividiendo en {len(args_list)} partes...")
        self._execute_sequential(
            args_list=args_list,
            on_done=self._finish,
            on_progress=lambda v: self.after(0, lambda val=v: self._on_file_progress(val)),
            on_file_start=lambda i: self.after(0, lambda idx=i: self._progress_panel.set_file_active(filenames[idx])),
            on_file_done=lambda i: self.after(0, lambda idx=i: self._progress_panel.set_file_done(filenames[idx])),
            durations=part_durations,
        )

    def _on_file_progress(self, value: float):
        active = next((f for f in self._output_files if not self._progress_panel._file_rows.get(f.name, {}).get("done")), None)
        if active:
            self._progress_panel.set_file_progress(active.name, value)

    def _finish(self, success: bool):
        self._log_elapsed_time()
        if success:
            for f in self._output_files:
                self._progress_panel.set_file_done(f.name)
            self._progress_panel.show_success(
                "Diverge completado exitosamente",
                folder=self._base_folder / "parts",
                on_new_run=self._reset,
            )
            self._on_log("✓ Diverge completado.")
        else:
            self._progress_panel.show_error("Error al ejecutar el diverge. Ver logs para más detalle.")
            self._on_log("✗ Error en el diverge.")

    def _reset(self):
        self._input_file = None
        self._output_files = []
        self._file_label.configure(text="Sin seleccionar")
        self._set_run_btn_enabled(False)
        self._progress_panel.grid_remove()
        self._config_frame.grid()