import threading
from pathlib import Path
from typing import Callable


COMPUTE_TYPES_BY_DEVICE: dict[str, list[str]] = {
    "cuda": ["float16", "int8_float16", "int8"],
    "cpu":  ["float32", "int8"],
}

DEVICES     = ["cuda", "cpu"]
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"]
LANGUAGES   = {
    "auto": None,
    "ja":   "ja",
    "zh":   "zh",
    "ko":   "ko",
    "es":   "es",
    "en":   "en",
}

DEFAULT_MODEL_SIZE            = "medium"
DEFAULT_DEVICE                = "cuda"
DEFAULT_COMPUTE_TYPE          = "int8_float16"
DEFAULT_LANGUAGE              = "ja"
DEFAULT_VAD_FILTER            = True
DEFAULT_CONDITION_ON_PREV     = False
DEFAULT_WORD_TIMESTAMPS       = True
DEFAULT_BEAM_SIZE             = 5


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

    def run_sequential(
        self,
        configs: list,
        on_log: Callable[[str], None],
        on_done: Callable[[bool, list], None],
        on_progress: Callable[[float], None] | None = None,
        on_file_start: Callable[[int], None] | None = None,
        on_file_done: Callable[[int, list], None] | None = None,
    ) -> None:
        self._cancelled = False
        thread = threading.Thread(
            target=self._sequential_worker,
            args=(configs, on_log, on_done, on_progress,
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
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )
            self._model_key = key
        return self._model

    def _transcribe_file(
        self,
        model,
        config,
        on_log: Callable,
        on_progress: Callable | None,
    ) -> list | None:
        on_log(f"Transcribiendo {config.input_file.name}...")

        language = LANGUAGES.get(config.language)  # None = auto-detect

        segments_gen, info = model.transcribe(
            str(config.input_file),
            language=language,
            beam_size=config.beam_size,
            vad_filter=config.vad_filter,
            condition_on_previous_text=config.condition_on_previous_text,
            word_timestamps=config.word_timestamps,
            initial_prompt=config.initial_prompt or None,
        )

        detected = info.language
        prob     = info.language_probability
        on_log(f"Idioma detectado: '{detected}' (probabilidad {prob:.4f})")

        collected = []
        for segment in segments_gen:
            if self._cancelled:
                return None
            collected.append(segment)
            on_log(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text.strip()}")
            if on_progress and config.total_duration > 0:
                on_progress(min(segment.end / config.total_duration, 1.0))

        if on_progress:
            on_progress(1.0)

        return collected

    def _sequential_worker(
        self,
        configs: list,
        on_log: Callable,
        on_done: Callable,
        on_progress: Callable | None,
        on_file_start: Callable | None,
        on_file_done: Callable | None,
    ):
        try:
            cfg0 = configs[0]
            on_log(f"Cargando modelo '{cfg0.model_size}' en {cfg0.device} ({cfg0.compute_type})...")
            model = self._get_model(cfg0.model_size, cfg0.device, cfg0.compute_type)

            all_segments: list[list] = []

            for i, cfg in enumerate(configs):
                if self._cancelled:
                    on_done(False, all_segments)
                    return

                if on_file_start:
                    on_file_start(i)

                segments = self._transcribe_file(model, cfg, on_log, on_progress)
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
