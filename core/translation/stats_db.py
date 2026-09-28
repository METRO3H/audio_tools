from __future__ import annotations

"""
core/translation/stats_db.py
-------------------------------
Persistencia en sqlite de las estadisticas de corridas de traduccion de
.srt. Dos tablas:

    runs        una fila por corrida completa (una cola = un modelo +
                una config). Para "comparar modelos" es la tabla que
                importa — agrupar por `model` da promedios de tiempo,
                tokens/seg, confiabilidad, etc.
    run_files   una fila por archivo dentro de esa corrida, para poder
                bajar al detalle si algun archivo puntual se comporto
                distinto al resto.

Se abre una conexion NUEVA en cada llamada a save_run() — no se comparte
una conexion entre threads, porque _queue_worker (quien llama a esto)
corre en un thread de background separado del thread principal de la UI,
y sqlite3 no es thread-safe por default entre threads distintos.
"""

import sqlite3
from contextlib import closing

import config
from core.translation.stats import RunStats

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at              TEXT NOT NULL,
    finished_at             TEXT NOT NULL,
    model                   TEXT NOT NULL,
    n_gpu_layers            INTEGER NOT NULL,
    n_ctx                   INTEGER NOT NULL,
    temperature             REAL NOT NULL,
    source_language         TEXT,
    output_subfolder        TEXT,
    cancelled               INTEGER NOT NULL,
    total_files             INTEGER NOT NULL,
    succeeded_files         INTEGER NOT NULL,
    total_lines             INTEGER NOT NULL,
    total_blocks            INTEGER NOT NULL,
    model_load_seconds      REAL NOT NULL,
    translation_seconds     REAL NOT NULL,
    total_tokens_generated  INTEGER NOT NULL,
    total_model_calls       INTEGER NOT NULL,
    lines_needed_retry      INTEGER NOT NULL,
    lines_never_translated  INTEGER NOT NULL,
    blocks_full_retried     INTEGER NOT NULL,
    gpu_vendor              TEXT,
    gpu_name                TEXT,
    vram_used_mb            REAL,
    vram_total_mb           REAL,
    vram_measurement_method TEXT
);

CREATE TABLE IF NOT EXISTS run_files (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                  INTEGER NOT NULL REFERENCES runs(id),
    file_name               TEXT NOT NULL,
    success                 INTEGER NOT NULL,
    lines_total             INTEGER NOT NULL,
    blocks_total            INTEGER NOT NULL,
    elapsed_seconds         REAL NOT NULL,
    tokens_generated        INTEGER NOT NULL,
    model_calls             INTEGER NOT NULL,
    lines_needed_retry      INTEGER NOT NULL,
    lines_never_translated  INTEGER NOT NULL,
    blocks_full_retried     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_files_run_id ON run_files (run_id);
CREATE INDEX IF NOT EXISTS idx_runs_model ON runs (model);
"""


def _connect() -> sqlite3.Connection:
    config.TRANSLATION_STATS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.TRANSLATION_STATS_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def save_run(stats: RunStats) -> int:
    """
    Guarda una corrida completa (con el detalle por archivo) en una sola
    transaccion. Devuelve el id de la fila insertada en `runs`.
    """
    with closing(_connect()) as conn:
        _ensure_schema(conn)
        with conn:
            cur = conn.execute(
                """
                INSERT INTO runs (
                    started_at, finished_at, model, n_gpu_layers, n_ctx,
                    temperature, source_language, output_subfolder,
                    cancelled, total_files, succeeded_files, total_lines,
                    total_blocks, model_load_seconds, translation_seconds,
                    total_tokens_generated, total_model_calls,
                    lines_needed_retry, lines_never_translated,
                    blocks_full_retried, gpu_vendor, gpu_name,
                    vram_used_mb, vram_total_mb, vram_measurement_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stats.started_at, stats.finished_at, stats.model,
                    stats.n_gpu_layers, stats.n_ctx, stats.temperature,
                    stats.source_language, stats.output_subfolder,
                    int(stats.cancelled), stats.total_files,
                    stats.succeeded_files, stats.total_lines,
                    stats.total_blocks, stats.model_load_seconds,
                    stats.translation_seconds, stats.total_tokens_generated,
                    stats.total_model_calls, stats.lines_needed_retry,
                    stats.lines_never_translated, stats.blocks_full_retried,
                    stats.gpu_vendor, stats.gpu_name, stats.vram_used_mb,
                    stats.vram_total_mb, stats.vram_measurement_method,
                ),
            )
            run_id = cur.lastrowid

            if stats.files:
                conn.executemany(
                    """
                    INSERT INTO run_files (
                        run_id, file_name, success, lines_total,
                        blocks_total, elapsed_seconds, tokens_generated,
                        model_calls, lines_needed_retry,
                        lines_never_translated, blocks_full_retried
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id, f.file_name, int(f.success),
                            f.lines_total, f.blocks_total,
                            f.elapsed_seconds, f.tokens_generated,
                            f.model_calls, f.lines_needed_retry,
                            f.lines_never_translated, f.blocks_full_retried,
                        )
                        for f in stats.files
                    ],
                )
        return run_id