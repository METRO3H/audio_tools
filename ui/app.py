import customtkinter as ctk

from config import APP_TITLE, APP_WIDTH, APP_HEIGHT, APPEARANCE, COLOR_THEME, FFMPEG_BIN
from core.ffmpeg_runner import FFmpegRunner
from ui.components.log_panel import LogPanel
from ui.views.merge_audio_view import MergeAudioView
from ui.views.diverge_audio_view import DivergeAudioView
from ui.views.audio_to_video_view import AudioToVideoView
from ui.views.pipeline_view import PipelineView


class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self._runner = FFmpegRunner(FFMPEG_BIN)
        self._logs_visible = False
        self._configure_window()
        self._build()

    def _configure_window(self):
        ctk.set_appearance_mode(APPEARANCE)
        ctk.set_default_color_theme(COLOR_THEME)
        self.title(APP_TITLE)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(APP_WIDTH, APP_HEIGHT)

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.log_panel = LogPanel(self)

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        tabs.add("Merge")
        tabs.add("Diverge")
        tabs.add("Audio a Video")
        tabs.add("Pipeline")

        MergeAudioView(tabs.tab("Merge"), runner=self._runner, on_log=self.log_panel.append, on_toggle_logs=self.log_panel.toggle).pack(fill="both", expand=True)
        DivergeAudioView(tabs.tab("Diverge"), runner=self._runner, on_log=self.log_panel.append, on_toggle_logs=self.log_panel.toggle).pack(fill="both", expand=True)
        AudioToVideoView(tabs.tab("Audio a Video"), runner=self._runner, on_log=self.log_panel.append, on_toggle_logs=self.log_panel.toggle).pack(fill="both", expand=True)
        PipelineView(tabs.tab("Pipeline"), runner=self._runner, on_log=self.log_panel.append).pack(fill="both", expand=True)

    def _toggle_logs(self):
        self.log_panel.toggle()
