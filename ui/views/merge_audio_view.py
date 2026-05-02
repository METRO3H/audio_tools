from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from core.actions.merge_audio import MergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import MergeAudioConfig
from ui.views.base_action_view import BaseActionView

FORMATS = ["mp3", "wav", "aac", "m4a", "ogg", "flac"]


class MergeAudioView(BaseActionView):

    def __init__(self, parent, runner: FFmpegRunner, on_log: Callable, **kwargs):
        super().__init__(parent, runner, on_log, **kwargs)
        self._action = MergeAudioAction()
        self._selected_files: list[Path] = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        self._build_base_folder_row(row=0)

        ctk.CTkLabel(self, text="Archivos").grid(row=1, column=0, padx=12, pady=4, sticky="nw")
        self._files_box = ctk.CTkTextbox(self, height=120, state="disabled")
        self._files_box.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(self, text="Seleccionar", width=90, command=self._pick_files).grid(row=1, column=2, padx=12, pady=4, sticky="n")

        ctk.CTkLabel(self, text="Nombre salida").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        name_frame.grid_columnconfigure(0, weight=1)
        self._output_name_entry = ctk.CTkEntry(name_frame, placeholder_text="nombre del archivo")
        self._output_name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._format_selector = ctk.CTkOptionMenu(name_frame, values=FORMATS, width=80)
        self._format_selector.set("mp3")
        self._format_selector.grid(row=0, column=1)

        self._build_run_button(row=3, text="Ejecutar merge")

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
        config = MergeAudioConfig(
            input_files=self._selected_files,
            output_file=output_file,
            base_folder=self._base_folder,
        )
        self._on_log("Iniciando merge...")
        self._execute(
            args=self._action.build_args(config),
            on_done=self._finish,
        )

    def _finish(self, success: bool):
        self._action.cleanup()
        self._set_run_btn_enabled(True)
        self._log_elapsed_time()
        self._on_log("✓ Merge completado." if success else "✗ Error en el merge.")

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