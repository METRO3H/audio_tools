from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.actions.audio_to_video import AudioToVideoAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import AudioToVideoConfig
from core.media_info import get_duration
from ui.components.progress_panel import ProgressPanel
from ui.views.base_action_view import BaseActionView


class AudioToVideoView(BaseActionView):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, on_toggle_logs: Callable, **kwargs):
        super().__init__(parent, runner, on_log, **kwargs)
        self._on_toggle_logs = on_toggle_logs
        self._action = AudioToVideoAction()
        self._selected_files: list[Path] = []
        self._background_image: Path | None = None
        self._output_files: list[Path] = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._config_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._config_frame.grid(row=0, column=0, sticky="nsew")
        self._config_frame.grid_columnconfigure(1, weight=1)

        self._build_base_folder_row(row=0, parent=self._config_frame)

        ctk.CTkLabel(self._config_frame, text="Audios").grid(
            row=1, column=0, padx=12, pady=4, sticky="nw")
        self._files_box = ctk.CTkTextbox(
            self._config_frame, height=120, state="disabled")
        self._files_box.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self._config_frame, text="Seleccionar", width=90, command=self._pick_files).grid(
            row=1, column=2, padx=12, pady=4, sticky="n")

        ctk.CTkLabel(self._config_frame, text="Imagen fondo").grid(
            row=2, column=0, padx=12, pady=4, sticky="w")
        self._image_label = ctk.CTkLabel(
            self._config_frame, text="Negra por defecto", anchor="w")
        self._image_label.grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self._config_frame, text="Elegir", width=90,
                      command=self._pick_image).grid(row=2, column=2, padx=12, pady=4)

        self._build_run_button(
            row=3, text="Convertir a video", parent=self._config_frame)

        # on_cancel conecta el botón Detener del ProgressPanel con self._cancel
        self._progress_panel = ProgressPanel(
            self, on_toggle_logs=self._on_toggle_logs, on_cancel=self._cancel
        )
        self._progress_panel.grid(row=0, column=0, sticky="nsew")
        self._progress_panel.grid_remove()

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
        self._output_files = self._action.get_output_files(config)
        self._durations = [get_duration(FFPROBE_BIN, f)
                           for f in self._selected_files]
        filenames = [f.name for f in self._selected_files]

        self._progress_panel.setup(filenames, title=self._base_folder.name)
        self._config_frame.grid_remove()
        self._progress_panel.grid()

        self._on_log(f"Convirtiendo {len(args_list)} archivo(s) a video...")
        self._execute_sequential(
            args_list=args_list,
            on_done=self._finish,
            on_progress=lambda v: self.after(
                0, lambda val=v: self._on_file_progress(val)),
            on_file_start=lambda i: self.after(
                0, lambda idx=i: self._progress_panel.set_file_active(filenames[idx])),
            on_file_done=lambda i: self.after(
                0, lambda idx=i: self._progress_panel.set_file_done(filenames[idx])),
            durations=self._durations,
        )

    def _on_file_progress(self, value: float):
        active = next(
            (f for f in self._selected_files if not self._progress_panel._file_rows.get(f.name, {}).get("done")),
            None
        )
        if active:
            self._progress_panel.set_file_progress(active.name, value)

    def _finish(self, success: bool):
        self._log_elapsed_time()
        if self._was_cancelled:
            self._on_log("⏹ Conversión cancelada por el usuario.")
            self._progress_panel.show_cancelled(
                "Conversión cancelada",
                on_new_run=self._reset,
            )
            return
        if success:
            for f in self._selected_files:
                self._progress_panel.set_file_done(f.name)
            self._progress_panel.show_success(
                "Conversión completada exitosamente",
                folder=self._base_folder / "translation",
                on_new_run=self._reset,
            )
            self._on_log("✓ Conversión completada.")
        else:
            self._progress_panel.show_error(
                "Error en la conversión. Ver logs para más detalle.")
            self._on_log("✗ Error en la conversión.")

    def _reset(self):
        self._selected_files = []
        self._output_files = []
        self._background_image = None
        self._image_label.configure(text="Negra por defecto")
        self._files_box.configure(state="normal")
        self._files_box.delete("1.0", "end")
        self._files_box.configure(state="disabled")
        self._set_run_btn_enabled(False)
        self._progress_panel.grid_remove()
        self._config_frame.grid()

    def _refresh_files_box(self):
        self._files_box.configure(state="normal")
        self._files_box.delete("1.0", "end")
        for f in self._selected_files:
            self._files_box.insert("end", f.name + "\n")
        self._files_box.configure(state="disabled")