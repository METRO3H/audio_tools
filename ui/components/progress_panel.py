import subprocess
import tkinter as tk
from pathlib import Path
from typing import Callable

import customtkinter as ctk


class GradientBar(tk.Canvas):

    def __init__(self, parent, height=14, **kwargs):
        super().__init__(parent, height=height, bd=0, highlightthickness=0, **kwargs)
        self._value = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value: float):
        self._value = max(0.0, min(1.0, value))
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1:
            return

        bg = "#2b2b2b" if self._is_dark() else "#e0e0e0"
        self.create_rectangle(0, 0, w, h, fill=bg, outline="", tags="bg")

        r1 = self._create_round_rect(0, 0, w, h, radius=h // 2)
        self.create_polygon(r1, fill=bg, outline="", smooth=True)

        fill_w = int(w * self._value)
        if fill_w > 4:
            steps = max(fill_w, 1)
            for i in range(steps):
                t = i / steps
                r = int(78 + (167 - 78) * t)
                g = int(168 + (139 - 168) * t)
                b = int(245 + (250 - 245) * t)
                color = f"#{r:02x}{g:02x}{b:02x}"
                self.create_rectangle(i, 0, i + 1, h, fill=color, outline="")

            clip = self._create_round_rect(0, 0, fill_w, h, radius=h // 2)
            self.create_polygon(clip, fill="", outline="", smooth=True)

    def _create_round_rect(self, x1, y1, x2, y2, radius):
        return [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]

    def _is_dark(self):
        return ctk.get_appearance_mode().lower() == "dark"


class ProgressPanel(ctk.CTkFrame):

    def __init__(self, parent, on_toggle_logs: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_toggle_logs = on_toggle_logs
        self._file_count = 0
        self._completed = 0
        self._file_rows: dict[str, dict] = {}
        self._file_list: list[str] = []
        self._build()

    def setup(self, files: list[str], title: str = "") -> None:
        self._file_rows = {}
        self._file_list = files
        self._completed = 0
        self._file_count = len(files)
        self._title_label.configure(text=title)
        self._pct_label.configure(text="0%")
        self._files_label.configure(text=f"0 / {self._file_count} archivos completados")
        self._general_bar.set(0)
        self._refresh_file_list()
        self._hide_state()
        self.after(200, self._update_scrollbar_visibility)

    def set_file_active(self, filename: str) -> None:
        self._update_dot(filename, "active")
        row = self._file_rows.get(filename)
        if row:
            row["tag"].grid_remove()
            row["name"].configure(text_color=("gray10", "#e0e0e0"), font=ctk.CTkFont(size=13, weight="bold"))
        self._show_file_bar(filename)
        self._pulse_filename = filename
        self._pulse_state = True
        self._animate_pulse()
        
    def _animate_pulse(self):
        row = self._file_rows.get(getattr(self, "_pulse_filename", None))
        if not row or row.get("done"):
            return
        colors = [
            ("#4ea8f5", "#4ea8f5"),
            ("#7abcf7", "#7abcf7"),
            ("#aad4fa", "#aad4fa"),
            ("#7abcf7", "#7abcf7"),
        ]
        idx = getattr(self, "_pulse_step", 0)
        row["dot"].configure(text_color=colors[idx % len(colors)])
        self._pulse_step = (idx + 1) % len(colors)
        self._pulse_job = self.after(300, self._animate_pulse)

    def set_file_progress(self, filename: str, value: float) -> None:
        row = self._file_rows.get(filename)
        if row:
            row["bar"].set(value)
            row["pct"].configure(text=f"{int(value * 100)}%")
            general = (self._completed + value) / self._file_count
            self._set_general_progress(general)

    def set_file_done(self, filename: str) -> None:
        row = self._file_rows.get(filename)
        if not row or row.get("done"):
            return
        row["done"] = True
        if hasattr(self, "_pulse_job"):
            self.after_cancel(self._pulse_job)
        self._update_dot(filename, "done")
        row["name"].configure(text_color=("gray40", "gray70"), font=ctk.CTkFont(size=13, weight="normal"))
        row["tag"].grid_remove()
        self._hide_file_bar(filename)
        self._completed += 1
        self._set_general_progress(self._completed / self._file_count)
        self._files_label.configure(text=f"{self._completed} / {self._file_count} archivos completados")

    def show_success(self, message: str, folder: Path, on_new_run: Callable) -> None:
        self._state_frame.configure(fg_color=("gray90", "#1a3a2a"))
        self._state_label.configure(
            text=f"✓  {message}",
            text_color=("darkgreen", "#4caf80"),
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._state_frame.grid()
        self._action_frame.grid()
        self._open_folder_btn.configure(command=lambda: self._open_folder(folder))
        self._new_run_btn.configure(command=on_new_run)

    def show_error(self, message: str) -> None:
        self._state_frame.configure(fg_color=("gray90", "#3a1a1a"))
        self._state_label.configure(
            text=f"✕  {message}",
            text_color=("darkred", "#f28b82"),
            font=ctk.CTkFont(size=12),
        )
        self._state_frame.grid()
        self._action_frame.grid_remove()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)

        self._title_label = ctk.CTkLabel(header, text="", anchor="w", font=ctk.CTkFont(size=18, weight="bold"))
        self._title_label.grid(row=0, column=0, sticky="w")

        log_btn = ctk.CTkButton(
            header,
            text="",
            image=self._make_log_icon(),
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=("gray85", "gray25"),
            command=self._on_toggle_logs,
        )
        log_btn.grid(row=0, column=1)

        self._pct_label = ctk.CTkLabel(
            self, text="0%",
            font=ctk.CTkFont(size=52, weight="bold"),
            text_color=("#4ea8f5", "#4ea8f5"),
            anchor="w",
        )
        self._pct_label.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 6))

        self._general_bar = GradientBar(self, height=14, bg="#1a1a1a" if ctk.get_appearance_mode().lower() == "dark" else "#f0f0f0")
        self._general_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 6))

        self._files_label = ctk.CTkLabel(self, text="0 / 0 archivos completados", anchor="w", font=ctk.CTkFont(size=13))
        self._files_label.grid(row=3, column=0, sticky="w", padx=20)


        separator = ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30"))
        separator.grid(row=5, column=0, sticky="ew", padx=20, pady=14)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=6, column=0, sticky="nsew", padx=20)
        self._scroll.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        self._state_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._state_frame.grid(row=7, column=0, sticky="ew", padx=20, pady=(12, 4))
        self._state_frame.grid_columnconfigure(0, weight=1)
        self._state_label = ctk.CTkLabel(self._state_frame, text="", anchor="w")
        self._state_label.grid(row=0, column=0, sticky="ew", padx=14, pady=10)
        self._state_frame.grid_remove()

        self._action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._action_frame.grid(row=8, column=0, pady=(0, 16))
        self._open_folder_btn = ctk.CTkButton(self._action_frame, text="Abrir carpeta")
        self._open_folder_btn.grid(row=0, column=0, padx=8)
        self._new_run_btn = ctk.CTkButton(self._action_frame, text="Nueva ejecución", fg_color="transparent", border_width=1)
        self._new_run_btn.grid(row=0, column=1, padx=8)
        self._action_frame.grid_remove()

    def _refresh_file_list(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._file_rows = {}
        for filename in self._file_list:
            self._make_file_row(filename)
        self.after(100, self._update_scrollbar_visibility)
        
    def _update_scrollbar_visibility(self):
        try:
            scrollbar = self._scroll._scrollbar
            if self._scroll._parent_canvas.winfo_height() >= self._scroll._parent_canvas.winfo_reqheight():
                scrollbar.grid_remove()
            else:
                scrollbar.grid()
        except Exception:
            pass

    def _make_file_row(self, filename: str):
        frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        frame.pack(fill="x", pady=8)
        frame.grid_columnconfigure(2, weight=1)

        dot = ctk.CTkLabel(frame, text="●", width=20, font=ctk.CTkFont(size=14), text_color="gray")
        dot.grid(row=0, column=0, padx=(0, 10))

        tag = ctk.CTkLabel(frame, text="", anchor="w", font=ctk.CTkFont(size=14, weight="bold"), text_color=("#4ea8f5", "#4ea8f5"), width=0)
        tag.grid(row=0, column=1)
        tag.grid_remove()

        name = ctk.CTkLabel(frame, text=filename, anchor="w", font=ctk.CTkFont(size=14))
        name.grid(row=0, column=2, sticky="ew")

        pct = ctk.CTkLabel(frame, text="", width=52, font=ctk.CTkFont(size=14, weight="bold"), text_color=("#4ea8f5", "#4ea8f5"))
        pct.grid(row=0, column=3, padx=(4, 0))

        bar = GradientBar(frame, height=6, bg="#1a1a1a" if ctk.get_appearance_mode().lower() == "dark" else "#f0f0f0")
        bar.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        bar.grid_remove()

        self._file_rows[filename] = {"dot": dot, "tag": tag, "name": name, "bar": bar, "pct": pct}

    def _update_dot(self, filename: str, state: str):
        row = self._file_rows.get(filename)
        if not row:
            return
        colors = {
            "active": ("#4ea8f5", "#4ea8f5"),
            "done": ("#4caf80", "#4caf80"),
            "pending": ("gray", "gray"),
        }
        row["dot"].configure(text_color=colors.get(state, ("gray", "gray")))

    def _update_label(self, filename: str, text: str, text_color=None) -> None:
        row = self._file_rows.get(filename)
        if row:
            row["name"].configure(text=text, **({"text_color": text_color} if text_color else {}))

    def _show_file_bar(self, filename: str):
        row = self._file_rows.get(filename)
        if row:
            row["bar"].grid()

    def _hide_file_bar(self, filename: str):
        row = self._file_rows.get(filename)
        if row:
            row["bar"].grid_remove()
            row["pct"].configure(text="")

    def _set_general_progress(self, value: float):
        self._general_bar.set(value)
        self._pct_label.configure(text=f"{int(value * 100)}%")

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