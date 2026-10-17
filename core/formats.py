"""
core/formats.py
---------------
Formatos de salida admitidos. Fuente única: el backend los valida y se los
entrega al frontend con get_config(), que ya no mantiene sus propias listas.

El primer formato de cada tipo es el que se usa por defecto.
"""

AUDIO_OUTPUT_FORMATS: tuple[str, ...] = ("mp3", "wav", "aac", "m4a", "ogg", "flac", "opus")
VIDEO_OUTPUT_FORMATS: tuple[str, ...] = ("mp4", "mkv", "avi", "mov", "webm")

_BY_MEDIA_TYPE = {
    "audio": AUDIO_OUTPUT_FORMATS,
    "video": VIDEO_OUTPUT_FORMATS,
}


def output_formats(media_type: str) -> tuple[str, ...]:
    """Formatos válidos para "audio" o "video"."""
    return _BY_MEDIA_TYPE[media_type]


def default_output_format(media_type: str) -> str:
    return _BY_MEDIA_TYPE[media_type][0]


def extensions(media_type: str) -> set[str]:
    """Extensiones con punto (".mp3") de los archivos de ese tipo."""
    return {f".{fmt}" for fmt in _BY_MEDIA_TYPE[media_type]}


def as_config() -> dict[str, list[str]]:
    """Forma que recibe el frontend."""
    return {media_type: list(formats) for media_type, formats in _BY_MEDIA_TYPE.items()}
