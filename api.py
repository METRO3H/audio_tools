"""
api.py
------
Clase expuesta a pywebview como window.pywebview.api.*

Cada método público es llamable desde el frontend JS.
Los eventos de progreso se emiten de vuelta al frontend via
window.evaluate_js(), disparando CustomEvents que Svelte escucha.

Convención de eventos JS:
    audiotools:log       { detail: { message: str } }
    audiotools:progress  { detail: { value: float } }
    audiotools:file      { detail: { index: int, done: bool } }
    audiotools:done      { detail: { success: bool } }
"""

import json
import threading
from pathlib import Path

import webview

import config
from core.actions.merge_audio import MergeAudioAction
from core.actions.diverge_audio import DivergeAudioAction
from core.actions.audio_to_video import AudioToVideoAction
from core.transcription.transcribe_action import TranscribeAction
from core.transcription.whisper_runner import WhisperRunner
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration
from core.models import (
    MergeAudioConfig,
    DivergeAudioConfig,
    AudioToVideoConfig,
    TranscribeConfig,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _emit(window: webview.Window, event: str, detail: dict) -> None:
    """Emite un CustomEvent al frontend desde cualquier hilo."""
    payload = json.dumps(detail)
    js = (
        f"window.dispatchEvent("
        f"new CustomEvent('{event}', {{ detail: {payload} }})"
        f");"
    )
    window.evaluate_js(js)


def _paths(raw: list[str]) -> list[Path]:
    return [Path(p) for p in raw]


# ── API ────────────────────────────────────────────────────────────────────────

class AudioToolsAPI:
    """
    Instancia única compartida con pywebview.
    Todos los métodos públicos son accesibles desde JS.
    """

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._ffmpeg = FFmpegRunner(config.FFMPEG_BIN)
        self._whisper = WhisperRunner()

    def set_window(self, window: webview.Window) -> None:
        """Llamado desde main.py una vez que la ventana está lista."""
        self._window = window

    # ── Utilidades ─────────────────────────────────────────────────────────────

    def get_config(self) -> dict:
        """Devuelve la configuración base al frontend."""
        return {
            "default_base_folder": str(config.DEFAULT_BASE_FOLDER),
        }

    def get_duration(self, file_path: str) -> float:
        """Devuelve la duración en segundos de un archivo de audio/video."""
        return get_duration(config.FFPROBE_BIN, Path(file_path))

    def cancel(self) -> None:
        """Cancela la operación ffmpeg en curso."""
        self._ffmpeg.cancel()
        self._whisper.cancel()

    # ── Merge ──────────────────────────────────────────────────────────────────

    def run_merge(
        self,
        file_paths: list[str],
        output_path: str,
        base_folder: str,
    ) -> None:
        """
        Fusiona varios archivos de audio en uno.

        Parámetros JS:
            file_paths   lista de rutas absolutas
            output_path  ruta del archivo de salida
            base_folder  carpeta base del proyecto
        """
        config_ = MergeAudioConfig(
            input_files=_paths(file_paths),
            output_file=Path(output_path),
            base_folder=Path(base_folder),
        )
        action = MergeAudioAction()
        args = action.build_args(config_)

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_progress(value: float):
            _emit(self._window, "audiotools:progress", {"value": value})

        def on_done(success: bool):
            if success:
                action.add_chapters(config_)
            action.cleanup()
            _emit(self._window, "audiotools:done", {"success": success})

        self._ffmpeg.run(
            args=args,
            on_log=on_log,
            on_done=on_done,
            on_progress=on_progress,
        )

    # ── Diverge ────────────────────────────────────────────────────────────────

    def run_diverge(
        self,
        file_path: str,
        base_folder: str,
        interval_seconds: int,
        output_format: str,
    ) -> None:
        """
        Divide un archivo de audio en segmentos de igual duración.

        Parámetros JS:
            file_path        ruta absoluta del archivo fuente
            base_folder      carpeta base del proyecto
            interval_seconds duración de cada segmento en segundos
            output_format    extensión de salida (ej: "mp3", "opus")
        """
        input_file = Path(file_path)
        duration = get_duration(config.FFPROBE_BIN, input_file)

        config_ = DivergeAudioConfig(
            input_file=input_file,
            base_folder=Path(base_folder),
            interval_seconds=interval_seconds,
            output_format=output_format,
        )
        action = DivergeAudioAction()
        args_list = action.build_args_list(config_, duration)
        durations = [interval_seconds] * len(args_list)

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_progress(value: float):
            _emit(self._window, "audiotools:progress", {"value": value})

        def on_file_start(i: int):
            _emit(self._window, "audiotools:file", {"index": i, "done": False})

        def on_file_done(i: int):
            _emit(self._window, "audiotools:file", {"index": i, "done": True})

        def on_done(success: bool):
            _emit(self._window, "audiotools:done", {"success": success})

        self._ffmpeg.run_sequential(
            args_list=args_list,
            on_log=on_log,
            on_done=on_done,
            on_progress=on_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done,
            durations=durations,
        )

    # ── Audio to Video ─────────────────────────────────────────────────────────

    def run_audio_to_video(
        self,
        file_paths: list[str],
        base_folder: str,
        background_image: str | None = None,
    ) -> None:
        """
        Convierte archivos de audio a video con imagen de fondo estática.

        Parámetros JS:
            file_paths         lista de rutas de audio
            base_folder        carpeta base del proyecto
            background_image   ruta de la imagen (o null)
        """
        config_ = AudioToVideoConfig(
            input_files=_paths(file_paths),
            base_folder=Path(base_folder),
            background_image=Path(background_image) if background_image else None,
        )
        action = AudioToVideoAction()
        args_list = action.build_args_list(config_)
        durations = [
            get_duration(config.FFPROBE_BIN, f)
            for f in config_.input_files
        ]

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_progress(value: float):
            _emit(self._window, "audiotools:progress", {"value": value})

        def on_file_start(i: int):
            _emit(self._window, "audiotools:file", {"index": i, "done": False})

        def on_file_done(i: int):
            _emit(self._window, "audiotools:file", {"index": i, "done": True})

        def on_done(success: bool):
            _emit(self._window, "audiotools:done", {"success": success})

        self._ffmpeg.run_sequential(
            args_list=args_list,
            on_log=on_log,
            on_done=on_done,
            on_progress=on_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done,
            durations=durations,
        )

    # ── Transcribe ─────────────────────────────────────────────────────────────

    def run_transcribe(
        self,
        file_paths: list[str],
        base_folder: str,
        model_size: str,
        device: str,
        compute_type: str,
        output_subfolder: str,
        beam_size: int = 5,
    ) -> None:
        """
        Transcribe archivos de audio usando faster-whisper.

        Parámetros JS:
            file_paths       lista de rutas de audio
            base_folder      carpeta base del proyecto
            model_size       "tiny" | "base" | "small" | "medium" | "large-v3"
            device           "cpu" | "cuda"
            compute_type     "int8" | "float16" | "float32"
            output_subfolder subcarpeta donde se guardan los .srt
            beam_size        beam size para el decoder (default 5)
        """
        action = TranscribeAction()
        configs = [
            TranscribeConfig(
                input_file=Path(p),
                base_folder=Path(base_folder),
                total_duration=get_duration(config.FFPROBE_BIN, Path(p)),
                model_size=model_size,
                device=device,
                compute_type=compute_type,
                output_subfolder=output_subfolder,
                beam_size=beam_size,
            )
            for p in file_paths
        ]

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_progress(value: float):
            _emit(self._window, "audiotools:progress", {"value": value})

        def on_file_start(i: int):
            _emit(self._window, "audiotools:file", {"index": i, "done": False})

        def on_file_done(i: int, segments: list):
            _emit(self._window, "audiotools:file", {"index": i, "done": True})

        def on_done(success: bool, all_segments: list):
            _emit(self._window, "audiotools:done", {"success": success})

        self._whisper.run_sequential(
            configs=configs,
            on_log=on_log,
            on_progress=on_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done,
            on_done=on_done,
        )

    # ── Diálogos nativos ───────────────────────────────────────────────────────

    def pick_files(self, file_types: list[str] | None = None) -> list[str]:
        """
        Abre el diálogo nativo de selección de archivos.
        Devuelve lista de rutas absolutas (strings) o [] si se canceló.

        Parámetros JS:
            file_types  lista de extensiones (ej: ["*.mp3", "*.opus"])
                        o null para todos los archivos
        """
        types = tuple(file_types) if file_types else webview.OPEN_DIALOG
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=(("Audio files", " ".join(file_types)),) if file_types else (),
        )
        return list(result) if result else []

    def pick_folder(self) -> str | None:
        """
        Abre el diálogo nativo de selección de carpeta.
        Devuelve la ruta o null si se canceló.
        """
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def pick_image(self) -> str | None:
        """
        Abre el diálogo nativo para seleccionar una imagen de fondo.
        Devuelve la ruta o null si se canceló.
        """
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=(("Images", "*.png *.jpg *.jpeg *.webp"),),
        )
        return result[0] if result else None