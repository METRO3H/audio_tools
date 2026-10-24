"""
core/transcription/options.py
-----------------------------
Qué sabe hacer la tool Transcribe: modelos, dispositivos, compute types, idiomas,
beam sizes y formatos de salida. Fuente única: el backend valida las opciones contra
estas listas y se las entrega al frontend con get_config(), que ya no mantiene las suyas.

Módulo liviano a propósito: NO importa faster_whisper, así que se puede usar (y probar)
sin cargar el modelo.

Idiomas: el valor interno es el código de faster-whisper (`ja`, `zh`), pero lo que se muestra
al usuario es el nombre completo (`japanese`, `chinese`), que además es la carpeta de salida
por defecto.
"""

from __future__ import annotations

import re

from core.filenames import sanitize_name
from core.transcription.transcribe_action import OUTPUT_FORMATS

MODEL_SIZES: tuple[str, ...] = ("tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3")
DEVICES: tuple[str, ...] = ("cuda", "cpu")
COMPUTE_TYPES: dict[str, tuple[str, ...]] = {
    "cuda": ("float16", "int8_float16", "int8"),
    "cpu": ("float32", "int8"),
}
BEAM_SIZES: tuple[int, ...] = tuple(range(1, 11))

# código de faster-whisper -> nombre que se muestra (y carpeta de salida por defecto)
LANGUAGES: dict[str, str] = {
    "ja": "japanese",
    "zh": "chinese",
}

DEFAULTS: dict = {
    "model_size": "large-v3",
    "device": "cuda",
    "compute_type": "int8_float16",
    "beam_size": 5,
    "language": "ja",
    "vad_filter": True,
    "condition_on_previous_text": False,
    "word_timestamps": True,
    "output_format": "srt",
}


def as_config(initial_prompt: str = "") -> dict:
    """
    Forma que recibe el frontend. `initial_prompt` es el valor de config.py: el que se usa
    mientras el usuario no haya escrito uno propio.
    """
    return {
        "model_sizes": list(MODEL_SIZES),
        "devices": list(DEVICES),
        "compute_types": {device: list(values) for device, values in COMPUTE_TYPES.items()},
        "beam_sizes": list(BEAM_SIZES),
        "languages": [{"code": code, "label": label} for code, label in LANGUAGES.items()],
        "output_formats": list(OUTPUT_FORMATS),
        "defaults": {**DEFAULTS, "initial_prompt": initial_prompt},
    }


_SUBFOLDER_HELP = "La subcarpeta debe ser un solo nombre de carpeta, sin rutas (por ejemplo «japanese»)."
_DRIVE = re.compile(r"^[A-Za-z]:")


def resolve_subfolder(raw: str | None, language: str) -> str:
    """
    La carpeta (dentro de <base>/transcriptions) donde se escriben las transcripciones.

    Vacía o ausente: la del idioma. Es un SOLO nombre de carpeta: se rechazan separadores,
    rutas absolutas, `.` y `..` (de lo contrario `../../x` escribiría fuera de la carpeta base).
    Los caracteres que Windows no admite se sustituyen con el sanitizador compartido.
    """
    text = (raw or "").strip()
    if not text:
        return LANGUAGES[language]

    if "/" in text or "\\" in text or _DRIVE.match(text) or text in (".", ".."):
        raise ValueError(_SUBFOLDER_HELP)

    clean = sanitize_name(text).rstrip(". ")  # Windows no admite punto ni espacio al final
    if not clean:
        raise ValueError(f"La subcarpeta «{text}» no es un nombre válido.")
    return clean
