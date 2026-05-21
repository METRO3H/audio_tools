from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.transcription.transcribe_action import TranscribeAction
from core.transcription.whisper_runner import (
    COMPUTE_TYPES_BY_DEVICE,
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_MODEL_SIZE,
    DEVICES,
    MODEL_SIZES,
    WhisperRunner,
)
from ui.components.progress_panel import ProgressPanel
from ui.views.base_action_view import BaseActionView

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


class TranscribeView(BaseActionView):

    def __init__(
        self,
        parent,
        runner: FFmpegRunner,
        whisper_runner: WhisperRunner,
        on_log: Callable,
        on_toggle_logs: Callable,
        **kwargs,
    ):
        super().__init__(parent, runner, on_log, **kwargs)
        self._whisper_runner = whisper_runner
        self._on_toggle_logs = on_toggle_logs
        self._action = TranscribeAction()
        self._input_file: Path | None = None
        self._segments: list = []
        self._build()

    # ── Cancelación (usa whisper_runner, no ffmpeg_runner) ────────────

    def _cancel(self):
        self._was_cancelled = True
        self._whisper_runner.cancel()

    # ── Build ─────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._config_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._config_frame.grid(row=0, column=0, sticky="nsew")
        self._config_frame.grid_columnconfigure(1, weight=1)

        # Carpeta base
        self._build_base_folder_row(row=0, parent=self._config_frame)

        # Audio
        ctk.CTkLabel(self._config_frame, text="Audio").grid(
            row=1, column=0, padx=12, pady=4, sticky="w")
        self._file_label = ctk.CTkLabel(
            self._config_frame, text="Sin seleccionar", anchor="w")
        self._file_label.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(
            self._config_frame, text="Seleccionar", width=90, command=self._pick_file
        ).grid(row=1, column=2, padx=12, pady=4)

        # Subcarpeta de salida
        ctk.CTkLabel(self._config_frame, text="Subcarpeta").grid(
            row=2, column=0, padx=12, pady=4, sticky="w")
        self._subfolder_entry = ctk.CTkEntry(
            self._config_frame, placeholder_text="japanese")
        self._subfolder_entry.insert(0, "japanese")
        self._subfolder_entry.grid(row=2, column=1, padx=4, pady=4, sticky="ew")

        # Modelo
        ctk.CTkLabel(self._config_frame, text="Modelo").grid(
            row=3, column=0, padx=12, pady=4, sticky="w")
        self._model_selector = ctk.CTkOptionMenu(
            self._config_frame, values=MODEL_SIZES, width=140,
        )
        self._model_selector.set(DEFAULT_MODEL_SIZE)
        self._model_selector.grid(row=3, column=1, padx=4, pady=4, sticky="w")

        # Device
        ctk.CTkLabel(self._config_frame, text="Device").grid(
            row=4, column=0, padx=12, pady=4, sticky="w")
        self._device_selector = ctk.CTkOptionMenu(
            self._config_frame, values=DEVICES, width=140,
            command=self._on_device_changed,
        )
        self._device_selector.set(DEFAULT_DEVICE)
        self._device_selector.grid(row=4, column=1, padx=4, pady=4, sticky="w")

        # Compute type (filtrado según device)
        ctk.CTkLabel(self._config_frame, text="Compute type").grid(
            row=5, column=0, padx=12, pady=4, sticky="w")
        self._compute_selector = ctk.CTkOptionMenu(
            self._config_frame,
            values=COMPUTE_TYPES_BY_DEVICE[DEFAULT_DEVICE],
            width=140,
        )
        self._compute_selector.set(DEFAULT_COMPUTE_TYPE)
        self._compute_selector.grid(row=5, column=1, padx=4, pady=4, sticky="w")

        self._build_run_button(row=6, text="Transcribir", parent=self._config_frame)

        self._progress_panel = ProgressPanel(
            self, on_toggle_logs=self._on_toggle_logs, on_cancel=self._cancel
        )
        self._progress_panel.grid(row=0, column=0, sticky="nsew")
        self._progress_panel.grid_remove()

    # ── Callbacks de UI ───────────────────────────────────────────────

    def _on_device_changed(self, device: str):
        """Actualiza las opciones de compute_type al cambiar el device."""
        options = COMPUTE_TYPES_BY_DEVICE[device]
        self._compute_selector.configure(values=options)
        self._compute_selector.set(options[0])

    def _audios_dir(self) -> Path:
        candidate = self._base_folder / "audios"
        return candidate if candidate.is_dir() else self._base_folder

    def _pick_file(self):
        file = filedialog.askopenfilename(
            initialdir=self._audios_dir(),
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac")],
        )
        if file:
            self._input_file = Path(file)
            self._file_label.configure(text=self._input_file.name)
            self._set_run_btn_enabled(True)

    # ── Ejecución ─────────────────────────────────────────────────────

    def _run(self):
        if not self._input_file:
            return

        subfolder   = self._subfolder_entry.get().strip() or "japanese"
        model_size  = self._model_selector.get()
        device      = self._device_selector.get()
        compute     = self._compute_selector.get()
        output_path = self._action.get_output_path(
            self._input_file, self._base_folder, subfolder
        )
        total_dur   = get_duration(FFPROBE_BIN, self._input_file)

        self._segments = []
        self._output_path = output_path

        self._progress_panel.setup(
            [self._input_file.name], title=self._input_file.stem
        )
        self._progress_panel.set_file_active(self._input_file.name)
        self._config_frame.grid_remove()
        self._progress_panel.grid()

        self._on_log(f"Iniciando transcripción: {self._input_file.name}")
        self._start_time = __import__("time").monotonic()
        self._was_cancelled = False

        def on_progress(v: float):
            self.after(0, lambda val=v: (
                self._progress_panel.set_file_progress(self._input_file.name, val)
            ))

        def on_segment(seg):
            self._segments.append(seg)

        def on_done(success: bool):
            self.after(0, lambda: self._finish(success))

        self._whisper_runner.run(
            input_file=self._input_file,
            total_duration=total_dur,
            model_size=model_size,
            device=device,
            compute_type=compute,
            beam_size=5,
            on_log=lambda line: self.after(0, lambda l=line: self._on_log(l)),
            on_done=on_done,
            on_progress=on_progress,
            on_segment=on_segment,
        )

    def _finish(self, success: bool):
        self._log_summary("Resumen — Transcripción")

        if self._was_cancelled:
            self._on_log("⏹ Transcripción cancelada por el usuario.")
            self._progress_panel.show_cancelled(
                "Transcripción cancelada", on_new_run=self._reset
            )
            return

        if success:
            self._progress_panel.set_file_done(self._input_file.name)
            # Escribir SRT con los segmentos recolectados
            self._action.write_srt(self._segments, self._output_path)
            self._on_log(f"✓ SRT guardado en: {self._output_path}")
            self._progress_panel.show_success(
                "Transcripción completada exitosamente",
                folder=self._output_path.parent,
                on_new_run=self._reset,
            )
        else:
            self._progress_panel.show_error(
                "Error en la transcripción. Ver logs para más detalle."
            )
            self._on_log("✗ Error en la transcripción.")

    def _reset(self):
        self._input_file = None
        self._segments = []
        self._file_label.configure(text="Sin seleccionar")
        self._set_run_btn_enabled(False)
        self._progress_panel.grid_remove()
        self._config_frame.grid()
