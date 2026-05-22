from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from ui.components.progress_panel import GradientBar, ProgressPanel, _format_duration


class PipelineProgressPanel(ctk.CTkFrame):
    """
    Panel de ejecución del pipeline.

    Estructura visible:
    ┌──────────────────────────────────────────────┐
    │  Título del pipeline    [Detener]  [Logs]     │  ← header
    │  52%  (barra general del pipeline)            │  ← progreso global
    │  1 / 3 pasos completados                      │
    ├──────────────────────────────────────────────┤
    │  [1. Merge ✓]  →  [2. Diverge ●]  →  [🔒 3] │  ← tab pills
    ├──────────────────────────────────────────────┤
    │                                              │
    │   ProgressPanel del step seleccionado        │
    │                                              │
    └──────────────────────────────────────────────┘
    """

    # ── Init ─────────────────────────────────────────────────────────

    def __init__(self, parent, on_toggle_logs: Callable, on_cancel: Callable | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_toggle_logs = on_toggle_logs
        self._on_cancel = on_cancel

        self._steps: list[str] = []
        self._total_steps: int = 0
        self._step_done: list[bool] = []
        self._step_progress: list[float] = []
        self._current_step: int = -1
        self._selected_tab: int = 0

        self._tab_btns: list[ctk.CTkButton] = []
        self._progress_panels: dict[int, ProgressPanel] = {}
        self._placeholders: dict[int, ctk.CTkFrame] = {}

        self._build()

    # ── Public API ───────────────────────────────────────────────────

    def setup(self, step_names: list[str], title: str = "") -> None:
        """Inicializa el panel antes de lanzar la ejecución."""
        for p in self._progress_panels.values():
            p.destroy()
        for ph in self._placeholders.values():
            ph.destroy()
        self._progress_panels = {}
        self._placeholders = {}
        self._tab_btns = []

        self._steps = step_names
        self._total_steps = len(step_names)
        self._step_done = [False] * self._total_steps
        self._step_progress = [0.0] * self._total_steps
        self._current_step = -1
        self._selected_tab = 0

        self._title_label.configure(text=title)
        self._pct_label.configure(text="0%")
        self._general_bar.set(0)
        self._steps_label.configure(text=f"0 / {self._total_steps} pasos completados")
        self._hide_state()

        # Mostrar botón Detener al iniciar
        if hasattr(self, "_stop_btn"):
            self._stop_btn.configure(state="normal")
            self._stop_btn.grid()

        self._content_frame.grid_columnconfigure(0, weight=1)
        self._content_frame.grid_rowconfigure(0, weight=1)
        for i in range(self._total_steps):
            ph = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            ph.grid(row=0, column=0, sticky="nsew")
            ph.grid_remove()
            ctk.CTkLabel(
                ph,
                text=f"🔒  Esperando pasos anteriores...",
                font=ctk.CTkFont(size=14),
                text_color=("gray55", "gray45"),
                anchor="w",
            ).pack(padx=20, pady=40, fill="x")
            self._placeholders[i] = ph

            p = ProgressPanel(self._content_frame, on_toggle_logs=None)
            p.grid(row=0, column=0, sticky="nsew")
            p.grid_remove()
            self._progress_panels[i] = p

        self._build_tabs()
        self._show_content(0)

    def get_step_panel(self, index: int) -> ProgressPanel:
        return self._progress_panels[index]

    def step_start(self, index: int) -> None:
        self._current_step = index
        self._refresh_tabs()
        self._select_tab(index, force=True)

    def step_done(self, index: int, success: bool) -> None:
        self._step_done[index] = True
        self._step_progress[index] = 1.0
        completed = sum(self._step_done)
        self._steps_label.configure(
            text=f"{completed} / {self._total_steps} pasos completados"
        )
        self._recalculate_pipeline_bar()
        self._refresh_tabs()
        if self._selected_tab == index:
            self._show_content(index)

    def update_pipeline_progress(self, step_index: int, step_progress: float) -> None:
        self._step_progress[step_index] = step_progress
        self._recalculate_pipeline_bar()

    def show_success(self, message: str, folder: Path, on_new_run: Callable, timing_text: str | None = None) -> None:
        self._hide_stop_btn()
        self._state_frame.configure(fg_color=("gray90", "#1a3a2a"))
        self._state_label.configure(
            text=f"✓  {message}",
            text_color=("darkgreen", "#4caf80"),
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._show_timing(timing_text, ("darkgreen", "#4caf80"))
        self._state_frame.grid()
        self._action_frame.grid()
        self._open_folder_btn.grid(row=0, column=0, padx=8)
        self._new_run_btn.grid(row=0, column=1, padx=8)
        self._open_folder_btn.configure(command=lambda: self._open_folder(folder))
        self._new_run_btn.configure(command=on_new_run)

    def show_error(self, message: str, timing_text: str | None = None) -> None:
        self._hide_stop_btn()
        self._state_frame.configure(fg_color=("gray90", "#3a1a1a"))
        self._state_label.configure(
            text=f"✕  {message}",
            text_color=("darkred", "#f28b82"),
            font=ctk.CTkFont(size=12),
        )
        self._show_timing(timing_text, ("darkred", "#f28b82"))
        self._state_frame.grid()
        self._action_frame.grid_remove()

    def show_cancelled(self, message: str, on_new_run: Callable, timing_text: str | None = None) -> None:
        self._hide_stop_btn()
        self._state_frame.configure(fg_color=("gray90", "#2a2a2a"))
        self._state_label.configure(
            text=f"⏹  {message}",
            text_color=("gray50", "gray50"),
            font=ctk.CTkFont(size=13),
        )
        self._show_timing(timing_text, ("gray50", "gray50"))
        self._state_frame.grid()
        self._action_frame.grid()
        self._open_folder_btn.grid_remove()
        self._new_run_btn.grid(row=0, column=0, padx=8)
        self._new_run_btn.configure(command=on_new_run)

    # ── Build ─────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)

        self._title_label = ctk.CTkLabel(
            header, text="", anchor="w",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self._title_label.grid(row=0, column=0, sticky="w")

        col = 1
        if self._on_cancel:
            self._stop_btn = ctk.CTkButton(
                header,
                text="Detener",
                width=72, height=28,
                fg_color="transparent",
                border_width=1,
                border_color=("#e57373", "#c62828"),
                text_color=("#c62828", "#ef9a9a"),
                hover_color=("gray85", "gray25"),
                command=self._on_cancel,
            )
            self._stop_btn.grid(row=0, column=col, padx=(0, 6))
            col += 1

        ctk.CTkButton(
            header, text="", image=self._make_log_icon(),
            width=28, height=28,
            fg_color="transparent", hover_color=("gray85", "gray25"),
            command=self._on_toggle_logs,
        ).grid(row=0, column=col)

        # Porcentaje global del pipeline
        self._pct_label = ctk.CTkLabel(
            self, text="0%",
            font=ctk.CTkFont(size=52, weight="bold"),
            text_color=("#4ea8f5", "#4ea8f5"),
            anchor="w",
        )
        self._pct_label.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 6))

        is_dark = ctk.get_appearance_mode().lower() == "dark"
        self._general_bar = GradientBar(
            self, height=14,
            bg="#1a1a1a" if is_dark else "#f0f0f0",
        )
        self._general_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 6))

        self._steps_label = ctk.CTkLabel(
            self, text="0 / 0 pasos completados",
            anchor="w", font=ctk.CTkFont(size=13),
        )
        self._steps_label.grid(row=3, column=0, sticky="w", padx=20)

        # Contenedor de tabs + contenido
        tabs_outer = ctk.CTkFrame(self, fg_color="transparent")
        tabs_outer.grid(row=4, column=0, sticky="nsew", padx=20, pady=(14, 0))
        tabs_outer.grid_columnconfigure(0, weight=1)
        tabs_outer.grid_rowconfigure(2, weight=1)

        self._tab_bar = ctk.CTkFrame(tabs_outer, fg_color="transparent")
        self._tab_bar.grid(row=0, column=0, sticky="w", pady=(0, 8))

        ctk.CTkFrame(tabs_outer, height=1, fg_color=("gray80", "gray30")).grid(
            row=1, column=0, sticky="ew", pady=(0, 0)
        )

        self._content_frame = ctk.CTkFrame(tabs_outer, fg_color="transparent")
        self._content_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self._content_frame.grid_columnconfigure(0, weight=1)
        self._content_frame.grid_rowconfigure(0, weight=1)

        # Estado final (éxito / error / cancelado)
        self._state_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._state_frame.grid(row=5, column=0, sticky="ew", padx=20, pady=(4, 0))
        self._state_frame.grid_columnconfigure(0, weight=1)
        self._state_label = ctk.CTkLabel(self._state_frame, text="", anchor="w")
        self._state_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        # Tabla de timings por step — se puebla dinámicamente al finalizar
        self._timing_frame = ctk.CTkFrame(self._state_frame, fg_color="transparent")
        self._timing_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self._timing_frame.grid_remove()
        self._state_frame.grid_remove()

        # Botones de acción
        self._action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._action_frame.grid(row=6, column=0, pady=(4, 16))
        self._open_folder_btn = ctk.CTkButton(self._action_frame, text="Abrir carpeta")
        self._open_folder_btn.grid(row=0, column=0, padx=8)
        self._new_run_btn = ctk.CTkButton(
            self._action_frame, text="Nueva ejecución",
            fg_color="transparent", border_width=1,
        )
        self._new_run_btn.grid(row=0, column=1, padx=8)
        self._action_frame.grid_remove()

    # ── Tab management ────────────────────────────────────────────────

    def _build_tabs(self):
        for w in self._tab_bar.winfo_children():
            w.destroy()
        self._tab_btns = []

        for i, name in enumerate(self._steps):
            if i > 0:
                ctk.CTkLabel(
                    self._tab_bar, text="→",
                    text_color=("gray50", "gray50"),
                    font=ctk.CTkFont(size=14),
                ).pack(side="left", padx=4)

            btn = ctk.CTkButton(
                self._tab_bar,
                text=f"{i + 1}. {name}",
                width=max(90, len(name) * 9 + 30),
                height=32,
                command=lambda idx=i: self._select_tab(idx),
            )
            btn.pack(side="left", padx=2)
            self._tab_btns.append(btn)

        self._refresh_tabs()

    def _refresh_tabs(self):
        for i, btn in enumerate(self._tab_btns):
            if self._step_done[i]:
                btn.configure(
                    fg_color=("gray90", "#1e3a2a"),
                    text_color=("#2e7d32", "#4caf80"),
                    border_width=1,
                    border_color=("#4caf80", "#4caf80"),
                    state="normal",
                )
            elif i == self._current_step:
                btn.configure(
                    fg_color=("#4ea8f5", "#4ea8f5"),
                    text_color=("white", "white"),
                    border_width=0,
                    state="normal",
                )
            else:
                btn.configure(
                    fg_color=("gray85", "#2b2b2b"),
                    text_color=("gray55", "gray40"),
                    border_width=1,
                    border_color=("gray75", "gray35"),
                    state="disabled",
                )

    def _select_tab(self, index: int, force: bool = False):
        is_done = index < len(self._step_done) and self._step_done[index]
        is_active = index == self._current_step
        if not force and not (is_done or is_active):
            return
        self._selected_tab = index
        self._show_content(index)

    # ── Content switching ─────────────────────────────────────────────

    def _show_content(self, index: int):
        for p in self._progress_panels.values():
            p.grid_remove()
        for ph in self._placeholders.values():
            ph.grid_remove()

        is_done = self._step_done[index] if index < len(self._step_done) else False
        is_active = index == self._current_step

        if is_done or is_active:
            self._progress_panels[index].grid(row=0, column=0, sticky="nsew")
        else:
            self._placeholders[index].grid(row=0, column=0, sticky="nsew")

    # ── Pipeline bar calculation ──────────────────────────────────────

    def _recalculate_pipeline_bar(self):
        completed = sum(self._step_done)
        active_progress = (
            self._step_progress[self._current_step]
            if 0 <= self._current_step < self._total_steps and not self._step_done[self._current_step]
            else 0.0
        )
        total = (completed + active_progress) / self._total_steps if self._total_steps else 0
        self._general_bar.set(total)
        self._pct_label.configure(text=f"{int(total * 100)}%")

    # ── Helpers ───────────────────────────────────────────────────────

    def _show_timing_summary(
        self,
        step_timings: list | None,
        total_elapsed: int | None,
    ) -> None:
        """Puebla _timing_frame con una tabla de tiempos por step + total."""
        # Limpiar widgets anteriores
        for w in self._timing_frame.winfo_children():
            w.destroy()

        if not step_timings and total_elapsed is None:
            self._timing_frame.grid_remove()
            return

        self._timing_frame.grid_columnconfigure(1, weight=1)
        row = 0

        if step_timings:
            max_name = max((len(n) for n, _ in step_timings), default=0)
            for name, elapsed in step_timings:
                ctk.CTkLabel(
                    self._timing_frame,
                    text=name,
                    anchor="w",
                    font=ctk.CTkFont(size=12),
                    text_color=("gray40", "gray65"),
                    width=max_name * 8,
                ).grid(row=row, column=0, sticky="w", pady=1)
                ctk.CTkLabel(
                    self._timing_frame,
                    text=_format_duration(elapsed),
                    anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=("gray30", "gray75"),
                ).grid(row=row, column=1, sticky="w", padx=(12, 0), pady=1)
                row += 1

            # Separador
            ctk.CTkFrame(
                self._timing_frame, height=1, fg_color=("gray75", "gray35")
            ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 4))
            row += 1

        if total_elapsed is not None:
            ctk.CTkLabel(
                self._timing_frame,
                text="Total",
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray20", "gray85"),
            ).grid(row=row, column=0, sticky="w", pady=1)
            ctk.CTkLabel(
                self._timing_frame,
                text=f"⏱  {_format_duration(total_elapsed)}",
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("#4ea8f5", "#4ea8f5"),
            ).grid(row=row, column=1, sticky="w", padx=(12, 0), pady=1)

        self._timing_frame.grid()

    def _hide_stop_btn(self):
        if hasattr(self, "_stop_btn"):
            self._stop_btn.grid_remove()

    def _hide_state(self):
        self._state_frame.grid_remove()
        self._action_frame.grid_remove()

    def _open_folder(self, folder: Path):
        subprocess.Popen(f'explorer "{folder}"')

    def _make_log_icon(self) -> ctk.CTkImage:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (28, 28), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for y in [8, 14, 20]:
            w = 18 if y < 20 else 12
            d.rectangle([5, y, 5 + w, y + 2], fill=(150, 150, 150, 200))
        return ctk.CTkImage(light_image=img, dark_image=img, size=(18, 18))