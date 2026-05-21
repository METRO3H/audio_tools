import threading
from pathlib import Path
from typing import Callable


# Compute types disponibles según device
COMPUTE_TYPES_BY_DEVICE: dict[str, list[str]] = {
    "cuda": ["float16", "int8_float16", "int8"],
    "cpu":  ["float32", "int8"],
}

DEVICES      = ["cuda", "cpu"]
MODEL_SIZES  = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"]

DEFAULT_MODEL_SIZE   = "medium"
DEFAULT_DEVICE       = "cuda"
DEFAULT_COMPUTE_TYPE = "int8_float16"


class WhisperRunner:
    """
    Runner para faster-whisper.

    Carga el modelo una sola vez y lo reutiliza mientras la configuración
    (model_size, device, compute_type) no cambie.
    """

    def __init__(self):
        self._model = None
        self._model_key: tuple | None = None
        self._cancelled = False

    # ── API pública ───────────────────────────────────────────────────

    def run(
        self,
        input_file: Path,
        total_duration: float,
        model_size: str,
        device: str,
        compute_type: str,
        beam_size: int,
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
        on_progress: Callable[[float], None] | None = None,
        on_segment: Callable[[object], None] | None = None,
    ) -> None:
        self._cancelled = False
        thread = threading.Thread(
            target=self._worker,
            args=(input_file, total_duration, model_size, device, compute_type,
                  beam_size, on_log, on_done, on_progress, on_segment),
            daemon=True,
        )
        thread.start()

    def run_sequential(
        self,
        input_files: list[Path],
        durations: list[float],
        model_size: str,
        device: str,
        compute_type: str,
        beam_size: int,
        on_log: Callable[[str], None],
        on_done: Callable[[bool, list], None],
        on_progress: Callable[[float], None] | None = None,
        on_segment: Callable[[object], None] | None = None,
        on_file_start: Callable[[int], None] | None = None,
        on_file_done: Callable[[int, list], None] | None = None,
    ) -> None:
        """
        Procesa una lista de archivos de forma secuencial en un thread.
        on_done recibe (success, all_segments_per_file: list[list])
        on_file_done recibe (index, segments_for_file: list)
        """
        self._cancelled = False
        thread = threading.Thread(
            target=self._sequential_worker,
            args=(input_files, durations, model_size, device, compute_type,
                  beam_size, on_log, on_done, on_progress, on_segment,
                  on_file_start, on_file_done),
            daemon=True,
        )
        thread.start()

    def cancel(self) -> None:
        self._cancelled = True

    # ── Internals ─────────────────────────────────────────────────────

    def _get_model(self, model_size: str, device: str, compute_type: str):
        key = (model_size, device, compute_type)
        if self._model is None or self._model_key != key:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
            self._model_key = key
        return self._model

    def _transcribe_file(
        self,
        model,
        input_file: Path,
        total_duration: float,
        beam_size: int,
        on_log: Callable,
        on_progress: Callable | None,
        on_segment: Callable | None,
    ) -> list | None:
        """
        Transcribe un único archivo. Devuelve la lista de segmentos o None
        si fue cancelado o hubo error.
        """
        on_log(f"Transcribiendo {input_file.name}...")
        segments_gen, info = model.transcribe(str(input_file), beam_size=beam_size)
        on_log(
            f"Idioma detectado: '{info.language}' "
            f"(probabilidad {info.language_probability:.4f})"
        )
        collected = []
        for segment in segments_gen:
            if self._cancelled:
                return None
            collected.append(segment)
            on_log(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text.strip()}")
            if on_progress and total_duration > 0:
                on_progress(min(segment.end / total_duration, 1.0))
            if on_segment:
                on_segment(segment)
        if on_progress:
            on_progress(1.0)
        return collected

    def _worker(
        self,
        input_file: Path,
        total_duration: float,
        model_size: str,
        device: str,
        compute_type: str,
        beam_size: int,
        on_log: Callable,
        on_done: Callable,
        on_progress: Callable | None,
        on_segment: Callable | None,
    ):
        try:
            on_log(f"Cargando modelo '{model_size}' en {device} ({compute_type})...")
            model = self._get_model(model_size, device, compute_type)
            segments = self._transcribe_file(
                model, input_file, total_duration, beam_size,
                on_log, on_progress, on_segment,
            )
            if segments is None:
                on_done(False)
                return
            on_done(True)
        except Exception as e:
            on_log(f"[error] {e}")
            on_done(False)

    def _sequential_worker(
        self,
        input_files: list[Path],
        durations: list[float],
        model_size: str,
        device: str,
        compute_type: str,
        beam_size: int,
        on_log: Callable,
        on_done: Callable,
        on_progress: Callable | None,
        on_segment: Callable | None,
        on_file_start: Callable | None,
        on_file_done: Callable | None,
    ):
        try:
            on_log(f"Cargando modelo '{model_size}' en {device} ({compute_type})...")
            model = self._get_model(model_size, device, compute_type)

            all_segments: list[list] = []

            for i, (f, dur) in enumerate(zip(input_files, durations)):
                if self._cancelled:
                    on_done(False, all_segments)
                    return

                if on_file_start:
                    on_file_start(i)

                segments = self._transcribe_file(
                    model, f, dur, beam_size, on_log, on_progress, on_segment,
                )
                if segments is None:
                    on_done(False, all_segments)
                    return

                all_segments.append(segments)
                if on_file_done:
                    on_file_done(i, segments)

            on_done(True, all_segments)

        except Exception as e:
            on_log(f"[error] {e}")
            on_done(False, [])