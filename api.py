"""
api.py
------
Clase expuesta a pywebview como window.pywebview.api.*

Cada método público es llamable desde el frontend JS.
Los eventos de progreso se emiten de vuelta al frontend via
window.evaluate_js(), disparando CustomEvents que Svelte escucha.

Convención de eventos JS:
    audiotools:log               { detail: { message: str } }
    audiotools:progress          { detail: { value: float } }
    audiotools:file              { detail: { index: int, done: bool, started_at?: float, elapsed?: float } }
    audiotools:done              { detail: { success: bool, elapsed?: float, cancelled?: bool } }
    audiotools:translate:stats   { detail: { run_id: int|null, ...RunStats } } — una vez, al terminar
    audiotools:translate:block_stream  { detail: { file_index: int, text: str } }
    audiotools:translate:block_input   { detail: { file_index: int, text: str } }
    audiotools:translate:system_prompt { detail: { text: str } }

Los campos started_at/elapsed en audiotools:file y elapsed en audiotools:done
son opcionales — hoy solo los manda run_translate() (.srt). started_at es un
timestamp epoch (segundos) que manda el backend al arrancar un archivo, para
que el frontend arme un contador en vivo sin pedirle nada mas al backend;
elapsed es el tiempo final medido por el propio backend (mas preciso que
calcularlo en JS).

Las tres tools de traduccion (.srt, chapters, filenames) aceptan
remote_host/remote_port opcionales, igual que run_transcribe(): si vienen
dados, el modelo se carga y corre en el mediador de la LAN en vez de esta
PC. Arma bloques, reintentos, contexto y el fallback offline siguen
corriendo en este proceso sin importar el modo — lo unico que cambia es
donde se ejecuta cada llamada puntual al modelo (ver
core/translation/remote_backend.py). Por eso los eventos que emite cada
tool son EXACTAMENTE los mismos en local y en remoto.
"""

import json
import sys
import time
from pathlib import Path
import os
import subprocess
import sys

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
from pathlib import Path
from core.translation.runner import TranslateRunner
from core.translation.chapters_runner import ChaptersTranslateRunner
from core.translation.filenames_runner import FilenameTranslateRunner
from core.translation import prompts as translation_prompts

from util.image_optimizer import optimize_image, SUPPORTED_EXTS

# — Constantes compartidas —————————————————————————————————————————————————
_AUDIO_EXTS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.opus'}
_VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}

# — Helpers —————————————————————————————————————————————————————————————————


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


def _make_sequential_callbacks(window: webview.Window, total: int):
    """
    Genera los callbacks estándar para run_sequential.
    Retorna (on_log, on_progress, on_file_start, on_file_done, on_done_wrapper)
    donde on_done_wrapper llama a on_done(success) con el resultado.
    """
    progress_state = {'current': 0}

    def on_log(msg: str):
        _emit(window, "audiotools:log", {"message": msg})

    def on_progress(value: float):
        current = progress_state['current']
        global_value = (current + value) / total
        _emit(window, "audiotools:progress", {
            "value":         global_value,
            "file_index":    current,
            "file_progress": value,
            "completed":     current,
            "total":         total,
        })

    def on_file_start(i: int):
        progress_state['current'] = i
        _emit(window, "audiotools:progress", {
            "value":         i / total,
            "file_index":    i,
            "file_progress": 0,
            "completed":     i,
            "total":         total,
        })

    def on_file_done(i: int):
        _emit(window, "audiotools:progress", {
            "value":         (i + 1) / total,
            "file_index":    i,
            "file_progress": 1,
            "completed":     i + 1,
            "total":         total,
        })

    return on_log, on_progress, on_file_start, on_file_done

# — API —————————————————————————————————————————————————————————————————————


class AudioToolsAPI:
    """
    Instancia única compartida con pywebview.
    Todos los métodos públicos son accesibles desde JS.
    """

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._ffmpeg = FFmpegRunner(config.FFMPEG_BIN)
        self._whisper = WhisperRunner()
        self._translate_runner = TranslateRunner()
        self._chapters_runner = ChaptersTranslateRunner()
        self._filenames_runner = FilenameTranslateRunner()
        # RemoteWhisperRunner, o TranslateRunner/ChaptersTranslateRunner/
        # FilenameTranslateRunner con un RemoteLlamaBackend, en curso —
        # nunca más de uno a la vez (todas las tools son mutuamente
        # excluyentes en esta ventana), así que un solo slot alcanza.
        self._active_remote_runner = None

    def set_window(self, window: webview.Window) -> None:
        """Llamado desde main.py una vez que la ventana está lista."""
        self._window = window

    # — Utilidades ———————————————————————————————————————————————————————————

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
        self._translate_runner.cancel()
        self._chapters_runner.cancel()
        self._filenames_runner.cancel()
        if self._active_remote_runner is not None:
            self._active_remote_runner.cancel()

        # Fallback: si el proceso sigue vivo tras terminate(), lo mata
        if sys.platform == "win32":
            proc = getattr(self._ffmpeg, '_process', None)
            if proc and proc.poll() is None:
                proc.kill()

    def _unload_all_translation_models(self, except_: str | None = None) -> None:
        """
        Coordinación de VRAM entre los 3 traductores LLM (srt/chapters/
        filenames), cada uno con su propio ModelManager/proceso. 'except_'
        deja cargado el que está por arrancar; el resto se descarga.

        Solo tiene sentido llamarla cuando la tool que está por arrancar
        va a cargar su modelo EN ESTA MISMA MÁQUINA — si va a correr
        contra un mediador remoto, no compite por esta VRAM local (ver
        run_translate/run_translate_chapters/run_translate_filenames_preview,
        que la saltan por completo en modo remoto, igual que ya hace
        run_transcribe con self._whisper.unload()).
        """
        if except_ != "srt":
            self._translate_runner.unload()
        if except_ != "chapters":
            self._chapters_runner.unload()
        if except_ != "filenames":
            self._filenames_runner.unload()

    # — Merge —————————————————————————————————————————————————————————————————

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

    # — Diverge ———————————————————————————————————————————————————————————————

    def run_diverge(
        self,
        file_path: str,
        base_folder: str,
        output_folder: str,
        interval_seconds: int,
        output_format: str,
        chapters: list[dict] | None = None,
        media_type: str = "audio",
        use_subfolder: bool = True,
    ) -> None:
        """
        Divide un archivo en segmentos.

        Parámetros JS:
            file_path        ruta absoluta del archivo fuente
            base_folder      carpeta base del proyecto (naming en modo audio)
            output_folder    carpeta donde se escriben los segmentos
            interval_seconds duración de cada segmento en segundos (usado si chapters es None)
            output_format    extensión de salida
            chapters         lista de chapters (o null para intervalo fijo)
            media_type       "audio" | "video"
            use_subfolder    si True, escribe en {output_folder}/audios|videos/parts
        """

        input_file = Path(file_path)
        duration = get_duration(config.FFPROBE_BIN, input_file)

        config_ = DivergeAudioConfig(
            input_file=input_file,
            base_folder=Path(base_folder),
            output_folder=Path(output_folder),
            interval_seconds=interval_seconds,
            output_format=output_format,
            media_type=media_type,
            use_subfolder=use_subfolder,
        )
        action = DivergeAudioAction()
        args_list = action.build_args_list(config_, duration, chapters or None)
        durations = [
            (ch["end"] - ch["start"]) if chapters else interval_seconds
            for ch in (chapters or [None] * len(args_list))
        ]

        on_log, on_progress, on_file_start, on_file_done = _make_sequential_callbacks(
            self._window, len(args_list)
        )

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

    # — Audio to Video ——————————————————————————————————————————————————————

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

        on_log, on_progress, on_file_start, on_file_done = _make_sequential_callbacks(
            self._window, len(args_list)
        )

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

    # — Transcribe ——————————————————————————————————————————————————————————

    def check_remote_server(self) -> dict:
        """
        Busca el mediador en la red (discovery UDP) y, si lo encuentra,
        pregunta su estado y qué modelos de WHISPER tiene disponibles —
        todo en un solo llamado para que la card remota del frontend no
        necesite tres viajes separados. Nunca lanza excepción: cualquier
        problema de red se traduce en {"found": False}.
        """
        from core.network.mediator_client import MediatorClient, discover_mediator

        found = discover_mediator()
        if found is None:
            return {"found": False}

        try:
            client = MediatorClient(found.host, found.port)
            status = client.get_status()
            models = client.get_available_models()
        except Exception:
            return {"found": False}

        return {
            "found": True,
            "host": found.host,
            "port": found.port,
            "state": status["state"],
            "busy_model": status["model"],
            "models": models,
        }

    def check_remote_translation_server(self) -> dict:
        """
        Igual que check_remote_server(), pero para traducción: mismo
        descubrimiento y mismo /status (el mediador solo soporta un job
        a la vez sea cual sea el tipo, así que "ocupado" significa lo
        mismo para las dos), pero devuelve los modelos .gguf disponibles
        en vez de los de whisper. Nunca lanza excepción.
        """
        from core.network.mediator_client import MediatorClient, discover_mediator

        found = discover_mediator()
        if found is None:
            return {"found": False}

        try:
            client = MediatorClient(found.host, found.port)
            status = client.get_status()
            models = client.get_translation_models()
        except Exception:
            return {"found": False}

        return {
            "found": True,
            "host": found.host,
            "port": found.port,
            "state": status["state"],
            "busy_model": status["model"],
            "models": models,
        }

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
        remote_host:              str | None = None,
        remote_port:              int | None = None,
    ) -> None:
        """
        Si remote_host/remote_port vienen dados, transcribe contra el
        mediador en vez de cargar faster-whisper en este proceso — todo
        lo demás (armado de configs, escritura de archivos de salida,
        eventos al frontend) es idéntico en ambos casos.
        """
        from core.transcription.transcribe_action import TranscribeAction
        from core.models import TranscribeConfig

        is_remote = remote_host is not None and remote_port is not None

        if is_remote:
            from core.transcription.remote_whisper_runner import RemoteWhisperRunner
            runner = RemoteWhisperRunner(remote_host, remote_port)
            self._active_remote_runner = runner
        else:
            # Solo tiene sentido liberar VRAM local de traducción cuando
            # el modelo de whisper también va a cargarse en esta misma
            # máquina — un mediador remoto no compite por esa memoria.
            self._unload_all_translation_models()
            runner = self._whisper

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

        on_log, on_progress, on_file_start, _ = _make_sequential_callbacks(
            self._window, len(configs)
        )

        base_on_log = on_log
        base_on_file_start = on_file_start
        current_file_index = {"value": None}

        def on_log(message: str):
            # Conserva los logs globales y, además, los asocia al archivo
            # que se está procesando para mostrarlos en su modal en vivo.
            base_on_log(message)

            file_index = current_file_index["value"]
            if file_index is None:
                # Durante la preparación/subida aún puede no haber llegado
                # el evento file_start. Si el mensaje menciona un archivo,
                # lo asociamos a ese archivo; si no, al primero del lote.
                file_index = next(
                    (
                        i for i, cfg in enumerate(configs)
                        if cfg.input_file.name in message
                    ),
                    0,
                )

            _emit(self._window, "audiotools:transcribe:file_log", {
                "file_index": file_index,
                "message": message,
            })

        def on_file_start(index: int):
            current_file_index["value"] = index
            base_on_file_start(index)

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
            detail = {"success": success}
            if is_remote and getattr(runner, "was_cancelled", False):
                detail["cancelled"] = True
            _emit(self._window, "audiotools:done", detail)
            if is_remote:
                self._active_remote_runner = None

        runner.run_sequential(
            configs=configs,
            on_log=on_log,
            on_done=on_done,
            on_progress=on_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done,
        )

    # — Diálogos nativos ———————————————————————————————————————————————————

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

        exts = _AUDIO_EXTS if media_type == 'audio' else _VIDEO_EXTS
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
        base = Path(base_folder)
        audios_dir = base / 'audios'

        if not audios_dir.is_dir():
            return None

        files = [f for f in audios_dir.iterdir()
                 if f.is_file() and f.suffix.lower() in _AUDIO_EXTS]
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
        base = Path(base_folder)

        for subfolder in ['audios/parts', 'audios']:
            target = base / subfolder
            if not target.is_dir():
                continue
            files = sorted(
                [f for f in target.iterdir()
                 if f.is_file() and f.suffix.lower() in _AUDIO_EXTS],
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

    def scan_translate_input(self, base_folder: str) -> dict:
        """
        Busca .srt en ./transcriptions/japanese primero, luego ./transcriptions/chinese.
        Retorna { files: [...], source: str, error: str | None }
        """
        base = Path(base_folder)
        for lang in ('japanese', 'chinese'):
            target = base / 'transcriptions' / lang
            if not target.is_dir():
                continue
            files = sorted(
                [f for f in target.iterdir() if f.is_file()
                 and f.suffix.lower() == '.srt'],
                key=lambda f: f.name,
            )
            if files:
                return {'files': [str(f) for f in files], 'source': lang, 'error': None}

        return {
            'files': [],
            'source': '',
            'error': 'No se encontraron .srt en ./transcriptions/japanese ni ./transcriptions/chinese',
        }

    # — Translate: .srt —————————————————————————————————————————————————

    def run_translate(
        self,
        file_paths: list[str],
        base_folder: str,
        output_subfolder: str = "english",
        raw_title: str = "",
        raw_publisher_info: str = "",
        base_prompt: str = "",
        glossary: str = "",
        model: str = "",
        n_gpu_layers: int | None = None,
        n_ctx: int | None = None,
        temperature: float | None = None,
        source_language: str = "",
        remote_host: str | None = None,
        remote_port: int | None = None,
    ) -> None:
        """
        Traduce una cola de .srt (todos deben pertenecer a la misma obra,
        ya que titulo/work_info se generan una sola vez para toda la corrida).
        Salida en {base_folder}/transcriptions/{output_subfolder}.

        Si remote_host/remote_port vienen dados, el modelo se carga y
        corre en el mediador en vez de esta PC — ver el docstring del
        módulo, arriba.
        """
        is_remote = remote_host is not None and remote_port is not None

        if is_remote:
            from core.translation.remote_backend import RemoteLlamaBackend
            runner = TranslateRunner(backend=RemoteLlamaBackend(remote_host, remote_port))
            self._active_remote_runner = runner
        else:
            self._whisper.unload()
            self._unload_all_translation_models(except_="srt")
            runner = self._translate_runner

        out_dir = Path(base_folder) / "transcriptions" / output_subfolder
        files = [(Path(p), out_dir / Path(p).name) for p in file_paths]

        # Arranca ahora mismo (antes de la carga del modelo) — es el
        # timestamp que se usa para el tiempo TOTAL del proceso, que si
        # incluye la carga del modelo. Los timestamps por archivo son
        # otros, propios de cada uno (ver on_file_start mas abajo), y esos
        # NO incluyen la carga del modelo porque arrancan recien cuando el
        # archivo empieza a procesarse de verdad.
        queue_started_at = time.time()
        _emit(self._window, "audiotools:translate:queue_started",
              {"started_at": queue_started_at})

        def on_log(msg):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_phase(msg):
            _emit(self._window, "audiotools:translate:phase", {"phase": msg})

        def on_step(step, status):
            _emit(self._window, "audiotools:translate:step",
                  {"step": step, "status": status})

        def on_title(title):
            _emit(self._window, "audiotools:translate:title", {"title": title})

        def on_work_info(info):
            _emit(self._window, "audiotools:translate:work_info",
                  {"work_info": info})

        def on_work_info_stream(text):
            _emit(self._window, "audiotools:translate:work_info_stream",
                  {"text": text})

        def on_title_stream(text):
            _emit(self._window, "audiotools:translate:title_stream",
                  {"text": text})

        def on_lines_progress(file_index, lines_done_file, lines_total_file, lines_done_global, lines_total_global):
            _emit(self._window, "audiotools:translate:lines", {
                "file_index": file_index,
                "lines_done_file": lines_done_file,
                "lines_total_file": lines_total_file,
                "lines_done_global": lines_done_global,
                "lines_total_global": lines_total_global,
            })

        def on_file_start(idx, total, name, started_at):
            _emit(self._window, "audiotools:file",
                  {"index": idx, "done": False, "started_at": started_at})

        def on_file_done(idx, success, elapsed):
            _emit(self._window, "audiotools:file",
                  {"index": idx, "done": True, "elapsed": elapsed})

        def on_queue_progress(done, total):
            _emit(self._window, "audiotools:progress", {
                "value": (done / total) if total else 0, "file_index": done,
                "file_progress": 0, "completed": done, "total": total,
            })

        def on_queue_done(succeeded, total, cancelled):
            success = succeeded > 0 and not cancelled
            _emit(self._window, "audiotools:done", {
                "success": success,
                "cancelled": cancelled,
                "elapsed": time.time() - queue_started_at,
            })
            if is_remote:
                self._active_remote_runner = None

        def on_block_stream(file_index, text):
            _emit(self._window, "audiotools:translate:block_stream",
                  {"file_index": file_index, "text": text})

        def on_block_input(file_index, text):
            _emit(self._window, "audiotools:translate:block_input",
                  {"file_index": file_index, "text": text})

        def on_system_prompt(text):
            _emit(self._window, "audiotools:translate:system_prompt",
                  {"text": text})

        def on_stats(run_id, stats):
            _emit(self._window, "audiotools:translate:stats",
                  {"run_id": run_id, **stats})

        runner.run_queue(
            files=files,
            raw_title=raw_title,
            raw_publisher_info=raw_publisher_info,
            base_prompt=base_prompt,
            glossary=glossary,
            model=model,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            temperature=temperature,
            source_language=source_language,
            output_subfolder=output_subfolder,
            on_log=on_log,
            on_phase=on_phase,
            on_step=on_step,
            on_title=on_title,
            on_work_info=on_work_info,
            on_work_info_stream=on_work_info_stream,
            on_title_stream=on_title_stream,
            on_lines_progress=on_lines_progress,
            on_file_start=on_file_start,
            on_file_done=on_file_done,
            on_queue_progress=on_queue_progress,
            on_queue_done=on_queue_done,
            on_block_stream=on_block_stream,
            on_block_input=on_block_input,
            on_system_prompt=on_system_prompt,
            on_stats=on_stats,
        )

    def cancel_translate(self) -> None:
        self._translate_runner.cancel()
        if self._active_remote_runner is not None:
            self._active_remote_runner.cancel()

    def list_translation_models(self) -> list[str]:
        return self._translate_runner.list_models()

    # — Translate: chapters ——————————————————————————————————————

    def run_translate_chapters(
        self,
        file_path: str,
        output_path: str,
        chapters: list[dict],
        raw_publisher_info: str,
        base_prompt: str,
        glossary: str = "",
        model: str = "",
        n_gpu_layers: int | None = None,
        n_ctx: int | None = None,
        temperature: float | None = None,
        remote_host: str | None = None,
        remote_port: int | None = None,
    ) -> None:
        """
        Traduce los titulos de los chapters embebidos en file_path y genera
        una copia en output_path con esos titulos ya traducidos (re-mux,
        sin re-codificar). Independiente de la cola de .srt: preset y
        work_info propios.

        Si remote_host/remote_port vienen dados, el modelo se carga y
        corre en el mediador — el re-mux con ffmpeg (que necesita el
        archivo en esta máquina) sigue siendo siempre local.
        """
        is_remote = remote_host is not None and remote_port is not None

        if is_remote:
            from core.translation.remote_backend import RemoteLlamaBackend
            runner = ChaptersTranslateRunner(backend=RemoteLlamaBackend(remote_host, remote_port))
            self._active_remote_runner = runner
        else:
            self._whisper.unload()
            self._unload_all_translation_models(except_="chapters")
            runner = self._chapters_runner

        def on_log(msg):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_phase(msg):
            _emit(self._window, "audiotools:chapters:phase", {"phase": msg})

        def on_work_info(info):
            _emit(self._window, "audiotools:chapters:work_info",
                  {"work_info": info})

        def on_work_info_stream(text):
            _emit(self._window, "audiotools:chapters:work_info_stream",
                  {"text": text})

        def on_done(success):
            _emit(self._window, "audiotools:chapters:done",
                  {"success": success})
            if is_remote:
                self._active_remote_runner = None

        runner.run(
            input_file=Path(file_path),
            output_file=Path(output_path),
            chapters=chapters,
            raw_publisher_info=raw_publisher_info,
            base_prompt=base_prompt,
            glossary=glossary,
            model=model,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            temperature=temperature,
            on_log=on_log,
            on_phase=on_phase,
            on_work_info=on_work_info,
            on_work_info_stream=on_work_info_stream,
            on_done=on_done,
        )

    def cancel_translate_chapters(self) -> None:
        self._chapters_runner.cancel()
        if self._active_remote_runner is not None:
            self._active_remote_runner.cancel()

    # — Translate: nombres de archivo ——————————————————————————

    def scan_filenames_folder(self, folder: str) -> list[dict]:
        """
        Escanea `folder` recursivamente y detecta el idioma de cada nombre
        de archivo (sin IA). Ver FilenameTranslateRunner.scan().
        """
        return self._filenames_runner.scan(Path(folder))

    def run_translate_filenames_preview(
        self,
        files: list[dict],
        raw_publisher_info: str,
        base_prompt: str,
        glossary: str = "",
        model: str = "",
        n_gpu_layers: int | None = None,
        n_ctx: int | None = None,
        temperature: float | None = None,
        remote_host: str | None = None,
        remote_port: int | None = None,
    ) -> None:
        """
        Traduce (en background) los nombres marcados como needs_translation
        en `files` (resultado de scan_filenames_folder). NO renombra nada
        todavia — emite audiotools:filenames:preview_done con el resultado
        para que el frontend muestre la vista previa con checkboxes antes
        de aplicar nada a disco.

        Si remote_host/remote_port vienen dados, el modelo se carga y
        corre en el mediador — scan()/apply_renames() (que tocan el disco
        del cliente) siguen siendo siempre locales.
        """
        is_remote = remote_host is not None and remote_port is not None

        if is_remote:
            from core.translation.remote_backend import RemoteLlamaBackend
            runner = FilenameTranslateRunner(backend=RemoteLlamaBackend(remote_host, remote_port))
            self._active_remote_runner = runner
        else:
            self._whisper.unload()
            self._unload_all_translation_models(except_="filenames")
            runner = self._filenames_runner

        def on_log(msg):
            _emit(self._window, "audiotools:log", {"message": msg})

        def on_phase(msg):
            _emit(self._window, "audiotools:filenames:phase", {"phase": msg})

        def on_work_info(info):
            _emit(self._window, "audiotools:filenames:work_info",
                  {"work_info": info})

        def on_work_info_stream(text):
            _emit(self._window, "audiotools:filenames:work_info_stream",
                  {"text": text})

        def on_translate_stream(text):
            _emit(self._window, "audiotools:filenames:translate_stream",
                  {"text": text})

        import threading

        def worker():
            try:
                result = runner.translate_preview(
                    files=files,
                    raw_publisher_info=raw_publisher_info,
                    base_prompt=base_prompt,
                    glossary=glossary,
                    model=model,
                    n_gpu_layers=n_gpu_layers,
                    n_ctx=n_ctx,
                    temperature=temperature,
                    on_log=on_log,
                    on_phase=on_phase,
                    on_work_info=on_work_info,
                    on_work_info_stream=on_work_info_stream,
                    on_translate_stream=on_translate_stream,
                )
                _emit(self._window, "audiotools:filenames:preview_done", {
                    "success": True, "files": result,
                })
            except Exception as exc:
                _emit(self._window, "audiotools:log",
                      {"message": f"[error] {exc}"})
                _emit(self._window, "audiotools:filenames:preview_done", {
                    "success": False, "files": [],
                })
            finally:
                if is_remote:
                    self._active_remote_runner = None

        threading.Thread(target=worker, daemon=True).start()

    def cancel_translate_filenames(self) -> None:
        self._filenames_runner.cancel()
        if self._active_remote_runner is not None:
            self._active_remote_runner.cancel()

    def apply_filename_renames(self, renames: list[list[str]]) -> dict:
        """
        renames: [[old_path, new_name], ...] — solo los que el usuario dejo
        confirmados en la vista previa. Devuelve
        { renamed: [{old, new}], errors: [{path, error}] }.
        """
        pairs = [(r[0], r[1]) for r in renames]
        return self._filenames_runner.apply_renames(pairs)

    # — Translate: prompts por idioma ———————————————————————

    def list_prompt_languages(self) -> list[str]:
        return translation_prompts.list_languages()

    def get_translation_prompt(self, language: str, kind: str) -> str:
        return translation_prompts.get_translation_prompt(language, kind)

    def save_translation_prompt(self, language: str, kind: str, content: str) -> None:
        translation_prompts.save_translation_prompt(language, kind, content)

    def get_glossary(self, language: str) -> str:
        return translation_prompts.get_glossary(language)

    def save_glossary(self, language: str, content: str) -> None:
        translation_prompts.save_glossary(language, content)

    def open_directory(self, path: str) -> None:
        """Abre la carpeta con el explorador de archivos del sistema."""

        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
