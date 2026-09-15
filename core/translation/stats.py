from __future__ import annotations

"""
core/translation/stats.py
---------------------------
Estructuras de datos para las estadisticas de una corrida de traduccion
de .srt (una "corrida" = una cola completa procesada con un mismo
modelo + config). Pensadas para poder comparar modelos entre si — ver
core/translation/stats_db.py para la persistencia en sqlite.

RunStats se va completando progresivamente durante el pipeline (ver
core/translation/runner.py:TranslateRunner._queue_worker), por eso casi
todos los campos tienen default — arrancan en su valor "vacio" y se
pisan a medida que la corrida avanza.
"""

from dataclasses import dataclass, field


@dataclass
class FileStats:
    """Detalle de UN archivo .srt dentro de una corrida."""

    file_name: str
    success: bool
    lines_total: int
    blocks_total: int
    elapsed_seconds: float

    tokens_generated: int = 0
    model_calls: int = 0             # intento normal + reintentos, sumado en todos los bloques
    lines_needed_retry: int = 0       # necesitaron >=1 reintento (haya salido bien o no)
    lines_never_translated: int = 0    # se rindieron tras todos los reintentos
    blocks_full_retried: int = 0        # bloques que dispararon el reintento de bloque completo


@dataclass
class RunStats:
    """Una corrida completa (una cola = un modelo + una config)."""

    started_at: str            # ISO 8601 UTC
    model: str                  # nombre del .gguf
    n_gpu_layers: int
    n_ctx: int
    temperature: float
    source_language: str
    output_subfolder: str
    total_files: int

    finished_at: str = ""
    cancelled: bool = False
    succeeded_files: int = 0
    total_lines: int = 0
    total_blocks: int = 0

    # Rendimiento
    model_load_seconds: float = 0.0
    translation_seconds: float = 0.0     # sin la carga del modelo
    total_tokens_generated: int = 0
    total_model_calls: int = 0

    # Confiabilidad (proxy de cumplimiento, no de calidad semantica —
    # ver discusion en core/translation/model_manager.py:translate_block)
    lines_needed_retry: int = 0
    lines_never_translated: int = 0
    blocks_full_retried: int = 0

    # Hardware (solo NVIDIA por ahora — ver core/hardware_info.py).
    # None si no se pudo medir (no hay GPU NVIDIA, pynvml no instalado, etc.)
    gpu_vendor: str | None = None
    gpu_name: str | None = None
    vram_used_mb: float | None = None
    vram_total_mb: float | None = None
    vram_measurement_method: str | None = None

    files: list[FileStats] = field(default_factory=list)