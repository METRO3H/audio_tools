import time
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from core.ffmpeg_runner import FFmpegRunner
from core.pipeline.context import PipelineContext
from core.pipeline.executor import PipelineExecutor
from core.pipeline.step_hooks import StepProgressHooks
from core.pipeline.steps.audio_to_video_step import AudioToVideoStep
from core.pipeline.steps.diverge_step import DivergeStep
from core.pipeline.steps.merge_step import MergeStep
from ui.components.drag_list import DragList
from ui.components.pipeline_progress_panel import PipelineProgressPanel
from ui.views.base_action_view import BaseActionView
from util.image_optimizer import optimize_image

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class PipelineView(BaseActionView):

    def __init__(
        self,
        parent,
        runner: FFmpegRunner,
        on_log: Callable,
        on_toggle_logs: Callable,
        **kwargs,
    ):
        super().__init__(parent, runner, on_log, **kwargs)
        self._on_toggle_logs = on_toggle_logs
        self._executor = PipelineExecutor()
        self._selected_files: list[Path] = []
        self._atv_step = AudioToVideoStep()   # referencia estable para pre-configurar imagen
        self._build()

    # ── Build ─────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Config frame ─────────────────────────────────────────────
        self._config_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._config_frame.grid(row=0, column=0, sticky="nsew")
        self._config_frame.grid_columnconfigure(0, weight=1)
        self._config_frame.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self._config_frame, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        top.grid_columnconfigure(1, weight=1)

        # Fila 0: carpeta base
        ctk.CTkLabel(top, text="Carpeta base").grid(
            row=0, column=0, padx=(0, 8), pady=(0, 4), sticky="w"
        )
        self._base_folder_label = ctk.CTkLabel(
            top, text=str(self._base_folder), anchor="w"
        )
        self._base_folder_label.grid(row=0, column=1, padx=4, pady=(0, 4), sticky="ew")
        ctk.CTkButton(
            top, text="Cambiar", width=90, command=self._pick_base_folder
        ).grid(row=0, column=2, pady=(0, 4))

        # Fila 1: selección de archivos
        ctk.CTkLabel(top, text="Archivos").grid(
            row=1, column=0, padx=(0, 8), pady=4, sticky="w"
        )
        self._files_label = ctk.CTkLabel(top, text="Sin seleccionar", anchor="w")
        self._files_label.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(
            top, text="Seleccionar", width=90, command=self._pick_files
        ).grid(row=1, column=2, pady=4)

        # Fila 2: indicador de auto-detección de audios (oculto por defecto)
        self._audio_hint = ctk.CTkLabel(
            top, text="", anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=("#2e7d32", "#4caf80"),
        )
        self._audio_hint.grid(row=2, column=1, padx=4, pady=(0, 2), sticky="ew")
        self._audio_hint.grid_remove()

        # Fila 3: indicador de auto-detección de imagen (oculto por defecto)
        self._image_hint = ctk.CTkLabel(
            top, text="", anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=("#2e7d32", "#4caf80"),
        )
        self._image_hint.grid(row=3, column=1, padx=4, pady=(0, 4), sticky="ew")
        self._image_hint.grid_remove()

        self._drag_list = DragList(
            self._config_frame,
            on_active_change=lambda _: self._update_run_btn(),
        )
        self._drag_list.set_available([MergeStep(), DivergeStep(), self._atv_step])
        self._drag_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)

        self._build_run_button(
            row=2, text="Ejecutar pipeline", parent=self._config_frame
        )

        # ── Panel de progreso ─────────────────────────────────────────
        self._pipeline_panel = PipelineProgressPanel(
            self, on_toggle_logs=self._on_toggle_logs, on_cancel=self._cancel
        )
        self._pipeline_panel.grid(row=0, column=0, sticky="nsew")
        self._pipeline_panel.grid_remove()

    # ── Auto-detección ────────────────────────────────────────────────

    def _audios_dir(self) -> Path:
        candidate = self._base_folder / "audios"
        return candidate if candidate.is_dir() else self._base_folder

    def _on_base_folder_changed(self):
        self._autoselect_audios()
        self._autoselect_image()
        self._update_run_btn()

    def _autoselect_audios(self):
        audios_dir = self._base_folder / "audios"
        self._audio_hint.grid_remove()
        if not audios_dir.is_dir():
            return
        files = sorted(
            [f for f in audios_dir.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS],
            key=lambda f: f.name,
        )
        if files:
            self._selected_files = files
            self._files_label.configure(
                text=f"{len(files)} archivo(s) seleccionado(s)"
            )
            self._audio_hint.configure(
                text=f"✓ {len(files)} audio(s) detectado(s) automáticamente desde ./audios"
            )
            self._audio_hint.grid()

    def _autoselect_image(self):
        images_dir = self._base_folder / "images"
        self._image_hint.grid_remove()
        self._atv_step.set_background_image(None)

        if not images_dir.is_dir():
            return
        candidates = [
            f for f in images_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]
        if not candidates:
            return

        smallest = min(candidates, key=lambda f: f.stat().st_size)
        optimized = optimize_image(smallest)
        self._atv_step.set_background_image(optimized)

        suffix = " (optimizada)" if optimized != smallest else ""
        self._image_hint.configure(
            text=f"✓ Imagen detectada automáticamente: {optimized.name}{suffix}"
        )
        self._image_hint.grid()

    # ── File picking ─────────────────────────────────────────────────

    def _pick_files(self):
        files = filedialog.askopenfilenames(
            initialdir=self._audios_dir(),
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac")],
        )
        if files:
            self._selected_files = sorted(Path(f) for f in files)
            self._files_label.configure(
                text=f"{len(self._selected_files)} archivo(s) seleccionado(s)"
            )
            # Al elegir manualmente se oculta el hint de auto-detección
            self._audio_hint.grid_remove()
            self._update_run_btn()

    def _update_run_btn(self):
        ready = bool(self._selected_files) and bool(self._drag_list.get_active())
        self._set_run_btn_enabled(ready)

    # ── Execution ─────────────────────────────────────────────────────

    def _run(self):
        steps = self._drag_list.get_active()
        if not steps or not self._selected_files:
            return

        self._start_time = time.monotonic()
        self._was_cancelled = False
        context = PipelineContext(
            base_folder=self._base_folder,
            current_files=list(self._selected_files),
        )

        step_names = [s.name for s in steps]
        self._pipeline_panel.setup(step_names, title=self._base_folder.name)
        self._config_frame.grid_remove()
        self._pipeline_panel.grid()

        self._on_log(f"Iniciando pipeline con {len(steps)} paso(s)...")

        panel = self._pipeline_panel

        def get_hooks(i: int) -> StepProgressHooks:
            step_panel = panel.get_step_panel(i)

            def on_setup(fns: list[str], title: str):
                def do():
                    step_panel.setup(fns, title)
                    panel.step_start(i)
                self.after(0, do)

            def on_file_active(fn: str):
                self.after(0, lambda f=fn: step_panel.set_file_active(f))

            def on_file_progress(fn: str, v: float):
                self.after(0, lambda f=fn, val=v: step_panel.set_file_progress(f, val))

            def on_file_done(fn: str):
                self.after(0, lambda f=fn: step_panel.set_file_done(f))

            def on_pipeline_progress(v: float):
                self.after(0, lambda val=v: panel.update_pipeline_progress(i, val))

            return StepProgressHooks(
                on_setup=on_setup,
                on_file_active=on_file_active,
                on_file_progress=on_file_progress,
                on_file_done=on_file_done,
                on_pipeline_progress=on_pipeline_progress,
            )

        def on_step_done(idx: int, success: bool):
            step_panel = panel.get_step_panel(idx)
            files = step_panel._file_list if hasattr(step_panel, "_file_list") else []
            for fn in files:
                self.after(0, lambda f=fn: step_panel.set_file_done(f))
            self.after(0, lambda i=idx, s=success: panel.step_done(i, s))

        self._executor.execute(
            steps=steps,
            context=context,
            runner=self._runner,
            on_log=lambda line: self.after(0, lambda l=line: self._on_log(l)),
            on_done=lambda ok: self.after(0, lambda: self._finish(ok)),
            get_hooks=get_hooks,
            on_step_done=on_step_done,
        )

    def _finish(self, success: bool):
        self._log_elapsed_time()
        if self._was_cancelled:
            self._on_log("⏹ Pipeline cancelado por el usuario.")
            self._pipeline_panel.show_cancelled("Pipeline cancelado", on_new_run=self._reset)
            return
        if success:
            self._pipeline_panel.show_success(
                "Pipeline completado exitosamente",
                folder=self._base_folder,
                on_new_run=self._reset,
            )
            self._on_log("✓ Pipeline completado.")
        else:
            self._pipeline_panel.show_error("Error en el pipeline. Ver logs para más detalle.")
            self._on_log("✗ Error en el pipeline.")

    def _reset(self):
        self._selected_files = []
        self._files_label.configure(text="Sin seleccionar")
        self._audio_hint.grid_remove()
        self._image_hint.grid_remove()
        # Crear nueva instancia de AudioToVideoStep para limpiar estado
        self._atv_step = AudioToVideoStep()
        self._drag_list.set_available([MergeStep(), DivergeStep(), self._atv_step])
        self._set_run_btn_enabled(False)
        self._pipeline_panel.grid_remove()
        self._config_frame.grid()