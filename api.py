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
from core.actions.audio_to_video import AudioToVideoAction, ENCODERS
from core.transcription.transcribe_action import TranscribeAction
from core.transcription.whisper_runner import WhisperRunner
from core.ffmpeg_runner import FFmpegRunner
from core.media_info import get_duration, get_chapters
from core.models import (
    MergeAudioConfig,
    DivergeAudioConfig,
    AudioToVideoConfig,
    TranscribeConfig,
)

from util.image_optimizer import optimize_image, SUPPORTED_EXTS


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
            "transcribe_initial_prompt": config.TRANSCRIBE_INITIAL_PROMPT,
        }

    def get_duration(self, file_path: str) -> float:
        """Devuelve la duración en segundos de un archivo de audio/video."""
        return get_duration(config.FFPROBE_BIN, Path(file_path))

    def cancel(self) -> None:
        """Cancela la operación en curso. Usa kill() como fallback en Windows."""
        self._ffmpeg.cancel()
        self._whisper.cancel()

        # Fallback: si el proceso sigue vivo tras terminate(), lo mata
        import sys
        if sys.platform == "win32":
            proc = getattr(self._ffmpeg, '_process', None)
            if proc and proc.poll() is None:
                proc.kill()

    # ── Merge ──────────────────────────────────────────────────────────────────

    def run_merge(
        self,
        file_paths: list[str],
        output_path: str,
        base_folder: str,
        durations: list[float],
    ) -> None:
        config_ = MergeAudioConfig(
            input_files=_paths(file_paths),
            output_file=Path(output_path),
            base_folder=Path(base_folder),
        )
        action = MergeAudioAction()
        args = action.build_args(config_)
        total_duration = sum(durations)

        # Inferencia de archivo activo basada en tiempo acumulado
        active_idx = [0]
        accumulated = [0.0]  # tiempo acumulado antes del archivo activo

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_progress(value: float):
            # value = elapsed_global / total_duration (0..1)
            elapsed = value * total_duration

            # Determinar qué archivo está siendo procesado
            acc = 0.0
            for i, dur in enumerate(durations):
                if elapsed < acc + dur:
                    active_idx[0] = i
                    accumulated[0] = acc
                    break
                acc += dur
            else:
                active_idx[0] = len(durations) - 1
                accumulated[0] = total_duration - durations[-1]

            # Progreso individual del archivo activo
            file_dur = durations[active_idx[0]]
            file_elapsed = elapsed - accumulated[0]
            file_progress = min(file_elapsed / file_dur,
                                1.0) if file_dur > 0 else 0.0

            # Archivos completados = todos los anteriores al activo
            completed = active_idx[0]

            _emit(self._window, "audiotools:progress", {
                "value": value,
                "file_index": active_idx[0],
                "file_progress": file_progress,
                "completed": completed,
                "total": len(durations),
            })

        def on_done(success: bool):
            if success:
                action.add_chapters(
                    output_file=Path(output_path),
                    input_files=_paths(file_paths),
                    durations=durations,
                    ffmpeg_bin=config.FFMPEG_BIN,
                )
            else:
                # Elimina el archivo de salida incompleto si el proceso fue cancelado
                out = Path(output_path)
                if out.exists():
                    try:
                        out.unlink()
                    except Exception:
                        pass
            action.cleanup()
            _emit(self._window, "audiotools:done", {"success": success})

        self._ffmpeg.run(
            args=args,
            on_log=on_log,
            on_done=on_done,
            on_progress=on_progress,
            duration=total_duration,
        )

    # ── Diverge ────────────────────────────────────────────────────────────────

    def run_diverge(
        self,
        file_path: str,
        base_folder: str,
        interval_seconds: int,
        output_format: str,
        chapters: list[dict] | None = None,
    ) -> None:
        """
        Divide un archivo en segmentos.

        Parámetros JS:
            file_path        ruta absoluta del archivo fuente
            base_folder      carpeta base del proyecto
            interval_seconds duración de cada segmento en segundos (usado si chapters es None)
            output_format    extensión de salida
            chapters         lista de chapters (o null para intervalo fijo)
        """
        from core.models import DivergeAudioConfig

        input_file = Path(file_path)
        duration = get_duration(config.FFPROBE_BIN, input_file)

        config_ = DivergeAudioConfig(
            input_file=input_file,
            base_folder=Path(base_folder),
            interval_seconds=interval_seconds,
            output_format=output_format,
        )
        action = DivergeAudioAction()
        args_list = action.build_args_list(config_, duration, chapters or None)
        durations = [
            (ch["end"] - ch["start"]) if chapters else interval_seconds
            for ch in (chapters or [None] * len(args_list))
        ]

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_progress(value: float):
            _emit(self._window, "audiotools:progress", {"value": value})

        def on_file_start(i: int):
            _emit(self._window, "audiotools:progress", {
                "value": i / len(args_list),
                "file_index": i,
                "file_progress": 0,
                "completed": i,
                "total": len(args_list),
            })

        def on_file_done(i: int):
            _emit(self._window, "audiotools:progress", {
                "value": (i + 1) / len(args_list),
                "file_index": i,
                "file_progress": 1,
                "completed": i + 1,
                "total": len(args_list),
            })

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
        file_paths:       list[str],
        base_folder:      str,
        background_image: str | None = None,
        encoder:          str = "cpu",
        fps:              int = 1,
        crf:              int = 23,
        preset:           str = "medium",
        resolution:       str = "1280x720",
        copy_audio:       bool = True,
    ) -> None:
        from core.actions.audio_to_video import AudioToVideoAction
        from core.models import AudioToVideoConfig

        config_ = AudioToVideoConfig(
            input_files=_paths(file_paths),
            base_folder=Path(base_folder),
            background_image=Path(
                background_image) if background_image else None,
            encoder=encoder,
            fps=fps,
            crf=crf,
            preset=preset,
            resolution=resolution,
            copy_audio=copy_audio,
        )
        action = AudioToVideoAction()
        args_list = action.build_args_list(config_)
        durations = [
            get_duration(config.FFPROBE_BIN, f)
            for f in config_.input_files
        ]

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        progress_state = {'current': 0}

        def on_progress(value: float):
            current = progress_state['current']
            total = len(args_list)
            global_value = (current + value) / total
            print(
                f"[DEBUG] on_progress: value={value:.3f} current={current} global={global_value:.3f}", flush=True)
            _emit(self._window, "audiotools:progress", {
                "value":         global_value,
                "file_index":    current,
                "file_progress": value,
                "completed":     current,
                "total":         total,
            })

        def on_file_start(i: int):
            progress_state['current'] = i
            _emit(self._window, "audiotools:progress", {
                "value":         i / len(args_list),
                "file_index":    i,
                "file_progress": 0,
                "completed":     i,
                "total":         len(args_list),
            })

        def on_file_done(i: int):
            _emit(self._window, "audiotools:progress", {
                "value":         (i + 1) / len(args_list),
                "file_index":    i,
                "file_progress": 1,
                "completed":     i + 1,
                "total":         len(args_list),
            })

        def on_done(success: bool):
            elapsed = time.time() - start_time
            print(
                f"[DEBUG A2V] done success={success} elapsed={elapsed:.1f}s", flush=True)
            _emit(self._window, "audiotools:done", {"success": success})

        import time
        print(
            f"[DEBUG A2V] encoder={encoder} fps={fps} crf={crf} preset={preset} resolution={resolution} copy_audio={copy_audio}", flush=True)
        print(f"[DEBUG A2V] background_image={background_image}", flush=True)
        print(f"[DEBUG A2V] args_list[0]={args_list[0]}", flush=True)
        start_time = time.time()

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
        file_paths:               list[str],
        base_folder:              str,
        model_size:               str,
        device:                   str,
        compute_type:             str,
        output_subfolder:         str,
        beam_size:                int = 5,
        language:                 str = "ja",
        vad_filter:               bool = True,
        condition_on_previous_text: bool = False,
        word_timestamps:          bool = True,
        initial_prompt:           str = "",
        output_format:            str = "srt",
    ) -> None:
        from core.transcription.transcribe_action import TranscribeAction
        from core.models import TranscribeConfig

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
                language=language,
                vad_filter=vad_filter,
                condition_on_previous_text=condition_on_previous_text,
                word_timestamps=word_timestamps,
                initial_prompt=initial_prompt,
                output_format=output_format,
            )
            for p in file_paths
        ]

        progress_state = {'current': 0}

        def on_log(msg: str):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_progress(value: float):
            current = progress_state['current']
            total = len(configs)
            global_value = (current + value) / total
            _emit(self._window, "audiotools:progress", {
                "value":         global_value,
                "file_index":    current,
                "file_progress": value,
                "completed":     current,
                "total":         total,
            })

        def on_file_start(i: int):
            progress_state['current'] = i
            _emit(self._window, "audiotools:progress", {
                "value":         i / len(configs),
                "file_index":    i,
                "file_progress": 0,
                "completed":     i,
                "total":         len(configs),
            })

        def on_file_done(i: int, segments: list):
            out_path = action.get_output_path(
                configs[i].input_file,
                configs[i].base_folder,
                configs[i].output_subfolder,
                configs[i].output_format,
            )
            action.write_output(segments, out_path, configs[i].output_format)
            _emit(self._window, "audiotools:progress", {
                "value":         (i + 1) / len(configs),
                "file_index":    i,
                "file_progress": 1,
                "completed":     i + 1,
                "total":         len(configs),
            })

        def on_done(success: bool, all_segments: list):
            _emit(self._window, "audiotools:done", {"success": success})

        self._whisper.run_sequential(
            configs=configs,
            on_log=on_log,
            on_done=on_done,
            on_progress=on_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done,
        )

    # ── Diálogos nativos ───────────────────────────────────────────────────────
    def pick_files(self, file_types: list[str] | None = None, base_folder: str | None = None, media_type: str = 'audio') -> list[str]:
        if file_types:
            exts = ";".join(file_types)
            label = "Audio files" if media_type == 'audio' else "Video files"
            types = (f"{label} ({exts})", "All files (*.*)")
        else:
            types = ("All files (*.*)",)

        directory = str(config.DEFAULT_BASE_FOLDER)
        if base_folder:
            subfolder = 'audios' if media_type == 'audio' else 'videos'
            sub_dir = Path(base_folder) / subfolder
            directory = str(sub_dir) if sub_dir.is_dir() else base_folder

        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=types,
            directory=directory,
        )
        return list(result) if result else []

    def pick_image(self, base_folder: str | None = None) -> str | None:
        directory = str(config.DEFAULT_BASE_FOLDER)
        if base_folder:
            images_dir = Path(base_folder) / 'images'
            directory = str(images_dir) if images_dir.is_dir() else base_folder

        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Image files (*.png;*.jpg;*.jpeg;*.webp)",
                        "All files (*.*)"),
            directory=directory,
        )
        return result[0] if result else None

    def pick_folder(self) -> str | None:
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=str(config.DEFAULT_BASE_FOLDER),
        )
        return result[0] if result else None

    def scan_media_folder(self, folder_path: str, media_type: str) -> dict:
        """
        Escanea ./audios o ./videos según media_type ('audio' | 'video').
        Retorna { files: [...], error: str | None }
        """
        AUDIO_EXTS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.opus'}
        VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}

        exts = AUDIO_EXTS if media_type == 'audio' else VIDEO_EXTS
        subfolder = 'audios' if media_type == 'audio' else 'videos'
        target = Path(folder_path) / subfolder

        if not target.is_dir():
            return {'files': [], 'error': f'No existe la carpeta ./{subfolder}'}

        files = sorted(
            [f for f in target.iterdir() if f.is_file() and f.suffix.lower() in exts],
            key=lambda f: f.name,
        )
        return {'files': [str(f) for f in files], 'error': None}

    def get_file_info(self, file_path: str) -> dict:
        p = Path(file_path)
        size_mb = round(p.stat().st_size / (1024 * 1024), 2)
        try:
            duration = get_duration(config.FFPROBE_BIN, p)
        except (ValueError, Exception):
            duration = 0.0
        return {
            "name": p.name,
            "size_mb": size_mb,
            "duration_seconds": duration,
            "path": str(p),
        }

    def open_file(self, file_path: str) -> None:
        """Abre el archivo con la aplicación predeterminada del sistema."""
        import os
        os.startfile(file_path)

    def open_folder(self, file_path: str) -> None:
        """Abre la carpeta que contiene el archivo y lo selecciona."""
        import subprocess
        subprocess.Popen(['explorer', '/select,', file_path])

    def get_chapters_for_file(self, file_path: str) -> list[dict]:
        """
        Retorna los chapters de un archivo.
        Lista vacía si no tiene chapters.
        """
        return get_chapters(config.FFPROBE_BIN, Path(file_path))

    def get_file_for_diverge(self, base_folder: str) -> dict | None:
        """
        Auto-detecta el archivo a diverger en base_folder/audios/:
          1. Busca el archivo cuyo stem coincide con el nombre de la carpeta base
          2. Si no, retorna el de mayor duración
          3. Si no hay archivos, retorna None

        Retorna { name, size_mb, duration_seconds, path } o None.
        """
        AUDIO_EXTS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.opus'}
        base = Path(base_folder)
        audios_dir = base / 'audios'

        if not audios_dir.is_dir():
            return None

        files = [f for f in audios_dir.iterdir()
                 if f.is_file() and f.suffix.lower() in AUDIO_EXTS]
        if not files:
            return None

        # Prioridad 1: nombre igual al de la carpeta base
        folder_name = base.name
        match = next((f for f in files if f.stem == folder_name), None)
        target = match if match else max(
            files,
            key=lambda f: get_duration(config.FFPROBE_BIN, f)
        )

        return self.get_file_info(str(target))

    def detect_encoders(self) -> dict:
        import subprocess
        from core.actions.audio_to_video import ENCODERS

        available = {"cpu": True}
        for key, encoder in ENCODERS.items():
            if key == "cpu":
                continue
            try:
                result = subprocess.run(
                    [
                        str(config.FFMPEG_BIN),
                        "-f", "lavfi", "-i", "color=c=black:s=320x240:r=1",
                        "-t", "0.1",
                        "-c:v", encoder,
                        "-f", "null", "-",
                    ],
                    capture_output=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                available[key] = result.returncode == 0
            except Exception as e:
                print(f"[DEBUG] encoder={encoder} exception={e}", flush=True)
                available[key] = False

        return available

    def scan_images_folder(self, base_folder: str) -> dict | None:
        """
        Busca la imagen más pequeña en base_folder/images/.
        Si supera 200kb, la optimiza con image_optimizer.
        Retorna { path, name, optimized } o None si no hay imágenes.
        """
        from util.image_optimizer import optimize_image, SUPPORTED_EXTS

        images_dir = Path(base_folder) / "images"
        if not images_dir.is_dir():
            return None

        images = [
            f for f in images_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
            and "_opt" not in f.stem  # excluir las ya optimizadas
        ]
        if not images:
            return None

        smallest = min(images, key=lambda f: f.stat().st_size)
        optimized_path = optimize_image(smallest)
        optimized = optimized_path != smallest

        return {
            "path":      str(optimized_path),
            "name":      optimized_path.name,
            "optimized": optimized,
        }

    def scan_audio_parts_or_audios(self, base_folder: str) -> dict:
        """
        Busca audios en ./audios/parts primero.
        Si no existe o está vacía, busca en ./audios.
        Retorna { files: [...], source: str, error: str | None }
        """
        AUDIO_EXTS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.opus'}
        base = Path(base_folder)

        for subfolder in ['audios/parts', 'audios']:
            target = base / subfolder
            if not target.is_dir():
                continue
            files = sorted(
                [f for f in target.iterdir()
                 if f.is_file() and f.suffix.lower() in AUDIO_EXTS],
                key=lambda f: f.name,
            )
            if files:
                return {
                    'files':  [str(f) for f in files],
                    'source': f'./{subfolder}',
                    'error':  None,
                }

        return {
            'files':  [],
            'source': '',
            'error':  'No se encontraron audios en ./audios/parts ni ./audios',
        }
