"""
core/video_encoding.py
----------------------
Qué sabe codificar la tool Audio→Video: encoders, presets, fps y resoluciones.
Fuente única: el backend valida las opciones contra estas listas y se las
entrega al frontend con get_config(), que ya no mantiene las suyas.

Encoders (ids estables: se guardan en localStorage):
    cpu     libx264
    nvidia  h264_nvenc
    amd     h264_amf
    intel   h264_qsv

Qué encoders hay REALMENTE disponibles depende de la máquina y se averigua con
`detect_available` (lanza ffmpeg, es lento: quien lo llama debería cachearlo).
"""

from __future__ import annotations

import subprocess
from typing import Callable

from core.process import NO_WINDOW

# id -> nombre del encoder en ffmpeg
ENCODERS: dict[str, str] = {
    "cpu": "libx264",
    "nvidia": "h264_nvenc",
    "amd": "h264_amf",
    "intel": "h264_qsv",
}

ENCODER_LABELS: dict[str, str] = {
    "cpu": "CPU (libx264)",
    "nvidia": "NVIDIA (nvenc)",
    "amd": "AMD (amf)",
    "intel": "Intel (qsv)",
}

# Del más al menos deseable cuando el usuario no ha elegido ninguno.
ENCODER_PRIORITY: tuple[str, ...] = ("nvidia", "amd", "intel", "cpu")

PRESETS: dict[str, tuple[str, ...]] = {
    "cpu": ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"),
    "nvidia": ("p1", "p2", "p3", "p4", "p5", "p6", "p7"),
    "amd": ("fast", "medium", "slow"),
    "intel": ("fast", "medium", "slow"),
}

DEFAULT_PRESETS: dict[str, str] = {
    "cpu": "medium",
    "nvidia": "p4",
    "amd": "medium",
    "intel": "medium",
}

FPS_OPTIONS: tuple[int, ...] = (1, 24, 30, 60)
RESOLUTIONS: tuple[str, ...] = ("1280x720", "1920x1080", "3840x2160")

# Rango del parámetro de calidad (crf / cq / qp): menor es mejor.
QUALITY_RANGE: tuple[int, int] = (0, 51)


def as_config() -> dict:
    """Forma que recibe el frontend (listas y diccionarios planos)."""
    return {
        "encoders": [{"id": key, "label": ENCODER_LABELS[key]} for key in ENCODERS],
        "encoder_priority": list(ENCODER_PRIORITY),
        "presets": {key: list(values) for key, values in PRESETS.items()},
        "default_presets": dict(DEFAULT_PRESETS),
        "fps": list(FPS_OPTIONS),
        "resolutions": list(RESOLUTIONS),
        "quality_range": list(QUALITY_RANGE),
    }


def detect_available(ffmpeg_bin, run: Callable = subprocess.run) -> dict[str, bool]:
    """
    Prueba cada encoder codificando 0,1 s de video negro. `cpu` se da siempre por
    disponible. Nunca lanza: un encoder que falla, no existe o tarda más de 5 s
    cuenta como no disponible. `run` se inyecta para poder probarlo sin ffmpeg.
    """
    available: dict[str, bool] = {"cpu": True}
    for key, encoder in ENCODERS.items():
        if key == "cpu":
            continue
        try:
            result = run(
                [
                    str(ffmpeg_bin),
                    "-f", "lavfi", "-i", "color=c=black:s=320x240:r=1",
                    "-t", "0.1",
                    "-c:v", encoder,
                    "-f", "null", "-",
                ],
                capture_output=True,
                timeout=5,
                creationflags=NO_WINDOW,
            )
            available[key] = result.returncode == 0
        except Exception:  # noqa: BLE001 - cualquier fallo = no disponible
            available[key] = False
    return available


class EncoderProbe:
    """
    Qué encoders hay en esta máquina, averiguado UNA sola vez: detectarlo lanza ffmpeg
    varias veces (hasta 5 s por encoder) y el resultado no cambia mientras la app esté abierta.
    """

    def __init__(self, ffmpeg_bin, run: Callable = subprocess.run):
        self._ffmpeg_bin = ffmpeg_bin
        self._run = run
        self._available: dict[str, bool] | None = None

    def available(self) -> dict[str, bool]:
        if self._available is None:
            self._available = detect_available(self._ffmpeg_bin, self._run)
        return dict(self._available)  # copia: quien lo reciba no puede alterar la caché
