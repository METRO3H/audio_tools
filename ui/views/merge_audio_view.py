from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from config import FFPROBE_BIN
from core.actions.merge_audio import MergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.models import MergeAudioConfig
from ui.components.progress_panel import ProgressPanel
from ui.views.base_action_view import BaseActionView

FORMATS = ["mp3", "wav", "aac", "m4a", "ogg", "flac"]


class MergeAudioView(BaseActionView):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, on_toggle_logs: Callable, **kwargs):
        super().__init__(parent, runner, on_log, **kwargs)
        self._on_toggle_logs = on_toggle_logs
        self._action = MergeAudioAction()
        self._selected_files: list[Path] = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._config_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._config_frame.grid(row=0, column=0, sticky="nsew")
        self._config_frame.grid_columnconfigure(1, weight=1)

        self._build_base_folder_row(row=0, parent=self._config_frame)

        ctk.CTkLabel(self._config_frame, text="Archivos").grid(row=1, column=0, padx=12, pady=4, sticky="nw")
        self._files_box = ctk.CTkTextbox(self._config_frame, height=120, state="disabled")
        self._files_box.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self._config_frame, text="Seleccionar", width=90, command=self._pick_files).grid(row=1, column=2, padx=12, pady=4, sticky="n")

        ctk.CTkLabel(self._config_frame, text="Nombre salida").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        name_frame = ctk.CTkFrame(self._config_frame, fg_color="transparent")
        name_frame.grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        name_frame.grid_columnconfigure(0, weight=1)
        self._output_name_entry = ctk.CTkEntry(name_frame, placeholder_text="nombre del archivo")
        self._output_name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._format_selector = ctk.CTkOptionMenu(name_frame, values=FORMATS, width=80)
        self._format_selector.set("mp3")
        self._format_selector.grid(row=0, column=1)

        self._build_run_button(row=3, text="Ejecutar merge", parent=self._config_frame)

        self._progress_panel = ProgressPanel(self, on_toggle_logs=self._on_toggle_logs)
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
            self._suggest_output_name()
            self._set_run_btn_enabled(True)

    def _run(self):
        output_file = self._build_output_path()
        if not output_file:
            return

        self._durations = [get_duration(FFPROBE_BIN, f) for f in self._selected_files]
        self._total_duration = sum(self._durations)
        self._current_file_index = 0

        filenames = [f.name for f in self._selected_files]
        self._progress_panel.setup(filenames, title=output_file.stem)
        self._progress_panel.set_file_active(self._selected_files[0].name)
        self._config_frame.grid_remove()
        self._progress_panel.grid()

        config = MergeAudioConfig(
            input_files=self._selected_files,
            output_file=output_file,
            base_folder=self._base_folder,
        )

        self._on_log("Iniciando merge...")
        self._execute(
            args=self._action.build_args(config),
            on_done=self._finish,
            on_progress=lambda v: self.after(0, lambda val=v: self._on_progress(val)),
            duration=self._total_duration,
        )

    def _on_progress(self, value: float):
        elapsed = value * self._total_duration
        cumulative = 0.0
        for i, (f, dur) in enumerate(zip(self._selected_files, self._durations)):
            if elapsed <= cumulative + dur:
                if i != self._current_file_index:
                    for j in range(self._current_file_index, i):
                        self._progress_panel.set_file_done(self._selected_files[j].name)
                    self._current_file_index = i
                    self._progress_panel.set_file_active(f.name)
                file_progress = (elapsed - cumulative) / dur if dur > 0 else 0
                self._progress_panel.set_file_progress(f.name, file_progress)
                break
            cumulative += dur

    def _finish(self, success: bool):
        self._action.cleanup()
        self._log_elapsed_time()
        if success:
            for f in self._selected_files:
                self._progress_panel.set_file_done(f.name)
            self._progress_panel.show_success(
                "Merge completado exitosamente",
                folder=self._base_folder,
                on_new_run=self._reset,
            )
            self._on_log("✓ Merge completado.")
        else:
            self._progress_panel.show_error("Error al ejecutar el merge. Ver logs para más detalle.")
            self._on_log("✗ Error en el merge.")

    def _reset(self):
        self._selected_files = []
        self._output_name_entry.delete(0, "end")
        self._files_box.configure(state="normal")
        self._files_box.delete("1.0", "end")
        self._files_box.configure(state="disabled")
        self._set_run_btn_enabled(False)
        self._progress_panel.grid_remove()
        self._config_frame.grid()

    def _suggest_output_name(self):
        self._output_name_entry.delete(0, "end")
        self._output_name_entry.insert(0, self._base_folder.name)

    def _build_output_path(self) -> Path | None:
        name = self._output_name_entry.get().strip()
        if not name:
            return None
        fmt = self._format_selector.get()
        folder = self._selected_files[0].parent
        return folder / f"{name}.{fmt}"

    def _refresh_files_box(self):
        self._files_box.configure(state="normal")
        self._files_box.delete("1.0", "end")
        for f in self._selected_files:
            self._files_box.insert("end", f.name + "\n")
        self._files_box.configure(state="disabled")