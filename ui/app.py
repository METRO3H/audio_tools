import customtkinter as ctk

from config import APP_TITLE, APP_WIDTH, APP_HEIGHT, APPEARANCE, COLOR_THEME, FFMPEG_BIN
from core.ffmpeg_runner import FFmpegRunner
from ui.components.log_panel import LogPanel
from ui.views.merge_audio_view import MergeAudioView


class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self._runner = FFmpegRunner(FFMPEG_BIN)
        self._configure_window()
        self._build()

    def _configure_window(self):
        ctk.set_appearance_mode(APPEARANCE)
        ctk.set_default_color_theme(COLOR_THEME)
        self.title(APP_TITLE)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(APP_WIDTH, APP_HEIGHT)

    def _build(self):
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.log_panel = LogPanel(self)
        self.log_panel.grid(row=1, column=0, sticky="nsew", padx=12, pady=(6, 12))

        self.action_frame = MergeAudioView(self, runner=self._runner, on_log=self.log_panel.append)
        self.action_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))