import tkinter as tk
from typing import Callable

import customtkinter as ctk

from core.pipeline.base_step import BaseStep


class DragList(ctk.CTkFrame):

    def __init__(self, parent, on_active_change: Callable | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._available: list[BaseStep] = []
        self._active: list[BaseStep] = []
        self._on_active_change = on_active_change
        self._drag_step: BaseStep | None = None
        self._drag_from: str | None = None
        self._drag_from_index: int | None = None
        self._ghost: tk.Toplevel | None = None
        self._build()

    def set_available(self, steps: list[BaseStep]) -> None:
        self._available = list(steps)
        self._refresh()

    def get_active(self) -> list[BaseStep]:
        return list(self._active)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="Disponibles", font=ctk.CTkFont(size=12)).grid(row=0, column=0, pady=(8, 2))
        self._available_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._available_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._available_scroll.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(right, text="Pipeline activo", font=ctk.CTkFont(size=12)).grid(row=0, column=0, pady=(8, 2))
        self._active_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self._active_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._active_scroll.grid_columnconfigure(0, weight=1)

        self._refresh()

    def _refresh(self):
        for w in self._available_scroll.winfo_children():
            w.destroy()
        for w in self._active_scroll.winfo_children():
            w.destroy()
        for step in self._available:
            self._make_available_row(step)
        for i, step in enumerate(self._active):
            self._make_active_row(step, i)

    def _make_available_row(self, step: BaseStep):
        row = ctk.CTkFrame(self._available_scroll)
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(1, weight=1)

        handle = ctk.CTkLabel(row, text="⠿", width=20, text_color="gray")
        handle.grid(row=0, column=0, padx=(6, 0), pady=6)
        ctk.CTkLabel(row, text=step.name, anchor="w").grid(row=0, column=1, padx=8, pady=6, sticky="ew")
        ctk.CTkButton(row, text="→", width=32, command=lambda s=step: self._move_to_active(s)).grid(row=0, column=2, padx=(0, 6), pady=4)

        handle.bind("<ButtonPress-1>", lambda e, s=step: self._drag_start(e, s, "available", None))
        handle.bind("<B1-Motion>", self._drag_motion)
        handle.bind("<ButtonRelease-1>", self._drag_end)

    def _make_active_row(self, step: BaseStep, index: int):
        row = ctk.CTkFrame(self._active_scroll)
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(2, weight=1)

        handle = ctk.CTkLabel(row, text="⠿", width=20, text_color="gray")
        handle.grid(row=0, column=0, padx=(6, 0), pady=6)
        ctk.CTkLabel(row, text=str(index + 1), width=20).grid(row=0, column=1, padx=4, pady=6)
        ctk.CTkLabel(row, text=step.name, anchor="w").grid(row=0, column=2, padx=4, pady=6, sticky="ew")
        ctk.CTkButton(row, text="⚙", width=28, command=lambda s=step: self._open_config(s)).grid(row=0, column=3, padx=2, pady=4)
        ctk.CTkButton(row, text="✕", width=28, fg_color="transparent", command=lambda i=index: self._move_to_available(i)).grid(row=0, column=4, padx=(0, 6), pady=4)

        handle.bind("<ButtonPress-1>", lambda e, s=step, i=index: self._drag_start(e, s, "active", i))
        handle.bind("<B1-Motion>", self._drag_motion)
        handle.bind("<ButtonRelease-1>", self._drag_end)

    def _drag_start(self, event, step: BaseStep, source: str, index: int | None):
        self._drag_step = step
        self._drag_from = source
        self._drag_from_index = index
        self._ghost = tk.Toplevel(self)
        self._ghost.overrideredirect(True)
        self._ghost.attributes("-alpha", 0.75)
        tk.Label(self._ghost, text=f"  {step.name}  ", bg="#333", fg="white", padx=8, pady=4).pack()
        self._ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

    def _drag_motion(self, event):
        if self._ghost:
            self._ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

    def _drag_end(self, event):
        if self._ghost:
            self._ghost.destroy()
            self._ghost = None

        if not self._drag_step:
            return

        x, y = event.x_root, event.y_root
        target = self._get_drop_target(x, y)

        if target == "active" and self._drag_from == "available":
            self._move_to_active(self._drag_step)
        elif target == "available" and self._drag_from == "active":
            self._move_to_available(self._drag_from_index)
        elif target == "active" and self._drag_from == "active":
            drop_index = self._get_active_drop_index(y)
            if drop_index is not None and drop_index != self._drag_from_index:
                self._active.pop(self._drag_from_index)
                insert_at = min(drop_index, len(self._active))
                self._active.insert(insert_at, self._drag_step)
                self._refresh()
                if self._on_active_change:
                    self._on_active_change(self._active)

        self._drag_step = None
        self._drag_from = None
        self._drag_from_index = None

    def _get_drop_target(self, x: int, y: int) -> str | None:
        def over(widget) -> bool:
            wx, wy = widget.winfo_rootx(), widget.winfo_rooty()
            return wx <= x <= wx + widget.winfo_width() and wy <= y <= wy + widget.winfo_height()
        if over(self._active_scroll):
            return "active"
        if over(self._available_scroll):
            return "available"
        return None

    def _get_active_drop_index(self, y: int) -> int:
        rows = self._active_scroll.winfo_children()
        for i, row in enumerate(rows):
            ry = row.winfo_rooty()
            if y < ry + row.winfo_height() // 2:
                return i
        return len(rows)

    def _move_to_active(self, step: BaseStep):
        if step in self._available:
            self._available.remove(step)
        if step not in self._active:
            self._active.append(step)
        self._refresh()
        if self._on_active_change:
            self._on_active_change(self._active)

    def _move_to_available(self, index: int):
        step = self._active.pop(index)
        self._available.append(step)
        self._refresh()
        if self._on_active_change:
            self._on_active_change(self._active)

    def _open_config(self, step: BaseStep):
        step.open_config_modal(self.winfo_toplevel())