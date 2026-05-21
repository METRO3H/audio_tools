from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext
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

if TYPE_CHECKING:
    from core.pipeline.step_hooks import StepProgressHooks


class TranscribeStep(BaseStep):

    def __init__(self, whisper_runner: WhisperRunner):
        self._whisper_runner = whisper_runner
        self._action = TranscribeAction()
        self._model_size   = DEFAULT_MODEL_SIZE
        self._device       = DEFAULT_DEVICE
        self._compute_type = DEFAULT_COMPUTE_TYPE
        self._subfolder    = "japanese"

    @property
    def name(self) -> str:
        return "Transcribir"

    # ── Modal de configuración ────────────────────────────────────────

    def open_config_modal(self, parent: ctk.CTk) -> None:
        modal = ctk.CTkToplevel(parent)
        modal.title("Configuración — Transcribir")
        modal.geometry("420x260")
        modal.grab_set()
        modal.grid_columnconfigure(1, weight=1)

        # Subcarpeta
        ctk.CTkLabel(modal, text="Subcarpeta").grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        subfolder_entry = ctk.CTkEntry(modal)
        subfolder_entry.insert(0, self._subfolder)
        subfolder_entry.grid(row=0, column=1, padx=8, pady=(16, 8), sticky="ew",
                             columnspan=2)

        # Modelo
        ctk.CTkLabel(modal, text="Modelo").grid(
            row=1, column=0, padx=16, pady=8, sticky="w")
        model_selector = ctk.CTkOptionMenu(modal, values=MODEL_SIZES)
        model_selector.set(self._model_size)
        model_selector.grid(row=1, column=1, padx=8, pady=8, sticky="w",
                            columnspan=2)

        # Device
        ctk.CTkLabel(modal, text="Device").grid(
            row=2, column=0, padx=16, pady=8, sticky="w")
        device_selector = ctk.CTkOptionMenu(
            modal, values=DEVICES,
            command=lambda d: _update_compute(d),
        )
        device_selector.set(self._device)
        device_selector.grid(row=2, column=1, padx=8, pady=8, sticky="w",
                             columnspan=2)

        # Compute type
        ctk.CTkLabel(modal, text="Compute type").grid(
            row=3, column=0, padx=16, pady=8, sticky="w")
        compute_selector = ctk.CTkOptionMenu(
            modal, values=COMPUTE_TYPES_BY_DEVICE[self._device])
        compute_selector.set(self._compute_type)
        compute_selector.grid(row=3, column=1, padx=8, pady=8, sticky="w",
                              columnspan=2)

        def _update_compute(device: str):
            opts = COMPUTE_TYPES_BY_DEVICE[device]
            compute_selector.configure(values=opts)
            compute_selector.set(opts[0])

        def _save():
            self._subfolder    = subfolder_entry.get().strip() or "japanese"
            self._model_size   = model_selector.get()
            self._device       = device_selector.get()
            self._compute_type = compute_selector.get()
            modal.destroy()

        ctk.CTkButton(modal, text="Guardar", command=_save).grid(
            row=4, column=0, columnspan=3, pady=(16, 16)
        )

    # ── Ejecución ─────────────────────────────────────────────────────

    def execute(
        self,
        context: PipelineContext,
        runner: FFmpegRunner,          # no se usa, requerido por la interfaz
        on_log: Callable[[str], None],
        on_done: Callable[[bool, PipelineContext], None],
        hooks: "StepProgressHooks | None" = None,
    ) -> None:
        # Leer audio_files si están disponibles (para cuando AudioToVideo
        # precedió a este step), si no caer a current_files.
        input_files = context.audio_files if context.audio_files else context.current_files
        durations   = [get_duration(FFPROBE_BIN, f) for f in input_files]
        filenames   = [f.name for f in input_files]

        if hooks and hooks.on_setup:
            hooks.on_setup(filenames, context.base_folder.name)

        active_idx = [0]

        def on_file_start(i: int):
            active_idx[0] = i
            if hooks and hooks.on_file_active:
                hooks.on_file_active(filenames[i])

        def on_progress(v: float):
            if hooks:
                if hooks.on_file_progress:
                    hooks.on_file_progress(filenames[active_idx[0]], v)
                if hooks.on_pipeline_progress:
                    hooks.on_pipeline_progress(
                        (active_idx[0] + v) / len(input_files)
                    )

        def on_file_done_cb(i: int, segments: list):
            # Escribir el SRT inmediatamente al terminar cada archivo
            srt_path = self._action.get_output_path(
                input_files[i], context.base_folder, self._subfolder
            )
            self._action.write_srt(segments, srt_path)
            on_log(f"✓ SRT guardado: {srt_path}")
            if hooks and hooks.on_file_done:
                hooks.on_file_done(filenames[i])

        def on_done_cb(success: bool, all_segments: list):
            if not success:
                on_done(False, context)
                return
            # Actualizar el contexto con los SRT generados
            srt_files = [
                self._action.get_output_path(f, context.base_folder, self._subfolder)
                for f in input_files
            ]
            new_context = PipelineContext(
                base_folder=context.base_folder,
                current_files=srt_files,
            )
            on_done(True, new_context)

        self._whisper_runner.run_sequential(
            input_files=input_files,
            durations=durations,
            model_size=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
            beam_size=5,
            on_log=on_log,
            on_done=on_done_cb,
            on_progress=on_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done_cb,
        )