"""
core/translation/job.py
------------------------
Lo que une las opciones de Translate (SRT) con un TranslateRunner (local o con un
RemoteLlamaBackend):

    resolve_translate   opciones -> TranslatePlan (una salida por .srt, con colisiones resueltas)
    run_translate_job   arranca el runner y traduce sus 16 callbacks a los eventos del contrato

Está aparte de api.py para poder probarlo con un runner falso, sin pywebview.

TranslateRunner.run_queue tiene muchos más callbacks que WhisperRunner.run_sequential (ver
core/translation/runner.py): además de start/log/progress/done (el contrato genérico) y
`audiotools:file` (igual que Transcribe), expone el detalle propio del pipeline de traducción
— fases, work_info/título en vivo, progreso por línea, la salida cruda de cada llamada al
modelo y las estadísticas de la corrida. Esos quedan en eventos `audiotools:translate:*`
propios, con el mismo nombre que ya tenían antes del contrato (no se tocan en este commit; la
unificación de las familias de eventos de las 3 tools de traducción se deja para el cierre de
las 3, ver HANDOFF sección 8):

    audiotools:translate:queue_started     { started_at }
    audiotools:translate:phase             { phase }
    audiotools:translate:step              { step, status }
    audiotools:translate:title             { title }
    audiotools:translate:work_info         { work_info }
    audiotools:translate:work_info_stream  { text }
    audiotools:translate:title_stream      { text }
    audiotools:translate:lines             { file_index, lines_done_file, lines_total_file,
                                              lines_done_global, lines_total_global }
    audiotools:translate:block_stream      { file_index, text }
    audiotools:translate:block_input       { file_index, text }
    audiotools:translate:system_prompt     { text, sections }
    audiotools:translate:stats             { run_id, ...RunStats }
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from core.jobs import Emit, JobEvents
from core.models import TranslateOptions
from core.translation.translate_action import TranslateAction, TranslatePlan


def resolve_translate(opts: TranslateOptions) -> TranslatePlan:
    """
    Resuelve las opciones a un plan (una salida por .srt) y comprueba lo que de otro modo solo
    se descubriría tarde y mal: que existan la carpeta base y los .srt de entrada.
    """
    base_folder = Path(opts.base_folder)
    if not base_folder.is_dir():
        raise ValueError(f"La carpeta base no existe: {base_folder}")
    paths = [Path(p) for p in opts.file_paths]
    for path in paths:
        if not path.is_file():
            raise ValueError(f"No se encontró el archivo «{path.name}».")
    return TranslateAction().plan(paths, base_folder, opts.output_subfolder)


def run_translate_job(
    runner,
    plan: TranslatePlan,
    opts: TranslateOptions,
    events: JobEvents,
    emit: Emit,
    on_finished: Callable[[], None] | None = None,
) -> None:
    """
    Emite `start` y arranca `runner.run_queue` (en su propio hilo, ver TranslateRunner). Retorna
    de inmediato; `log`/`progress`/`done` (y los `audiotools:translate:*` de arriba) llegan
    después.

    `on_finished` se llama tras el `done` (para soltar lo que api.py retenga del runner remoto,
    igual que en core/transcription/job.py).

    Nota de paridad con el comportamiento actual (no es una regresión de este commit): si el
    pipeline falla antes de llegar a traducir ningún archivo (p. ej. el modelo no carga),
    TranslateRunner._queue_worker lo captura con un log y `on_queue_done(0, total, cancelled)`,
    sin texto de error — así que `done` llega aquí como `success:false` pero SIN `error`
    (a diferencia de Transcribe, que sí lo reporta en `done.error`). Es el mismo vacío que tenía
    el run_translate() legado; no se inventa un mensaje que el runner no da.
    """
    total = len(plan.files)
    queue_started_at = time.time()
    events.start(total)
    emit("audiotools:translate:queue_started", {"started_at": queue_started_at})

    def on_phase(msg: str) -> None:
        emit("audiotools:translate:phase", {"phase": msg})

    def on_step(step: str, status: str) -> None:
        emit("audiotools:translate:step", {"step": step, "status": status})

    def on_title(title: str) -> None:
        emit("audiotools:translate:title", {"title": title})

    def on_work_info(info: str) -> None:
        emit("audiotools:translate:work_info", {"work_info": info})

    def on_work_info_stream(text: str) -> None:
        emit("audiotools:translate:work_info_stream", {"text": text})

    def on_title_stream(text: str) -> None:
        emit("audiotools:translate:title_stream", {"text": text})

    def on_lines_progress(
        file_index: int,
        lines_done_file: int,
        lines_total_file: int,
        lines_done_global: int,
        lines_total_global: int,
    ) -> None:
        emit("audiotools:translate:lines", {
            "file_index": file_index,
            "lines_done_file": lines_done_file,
            "lines_total_file": lines_total_file,
            "lines_done_global": lines_done_global,
            "lines_total_global": lines_total_global,
        })

    def on_file_start(idx: int, total: int, name: str, started_at: float) -> None:
        emit("audiotools:file", {"job_id": events.job_id, "index": idx, "done": False, "started_at": started_at})

    def on_file_done(idx: int, success: bool, elapsed: float) -> None:
        emit("audiotools:file", {"job_id": events.job_id, "index": idx, "done": True, "elapsed": elapsed})

    def on_queue_progress(done: int, queue_total: int) -> None:
        events.progress((done / queue_total) if queue_total else 0, done, 0, done, queue_total)

    def on_queue_done(succeeded: int, queue_total: int, cancelled: bool) -> None:
        success = succeeded > 0 and not cancelled
        events.done(success, cancelled=cancelled, elapsed=time.time() - queue_started_at)
        if on_finished is not None:
            on_finished()

    def on_block_stream(file_index: int, text: str) -> None:
        emit("audiotools:translate:block_stream", {"file_index": file_index, "text": text})

    def on_block_input(file_index: int, text: str) -> None:
        emit("audiotools:translate:block_input", {"file_index": file_index, "text": text})

    def on_system_prompt(text: str, sections: dict) -> None:
        emit("audiotools:translate:system_prompt", {"text": text, "sections": sections})

    def on_stats(run_id: int | None, stats: dict) -> None:
        emit("audiotools:translate:stats", {"run_id": run_id, **stats})

    events.start(total)
    runner.run_queue(
        files=[(item.path, item.output) for item in plan.files],
        raw_title=opts.raw_title,
        raw_publisher_info=opts.raw_publisher_info,
        base_prompt=opts.base_prompt,
        glossary=opts.glossary,
        model=opts.model,
        n_gpu_layers=opts.n_gpu_layers,
        n_ctx=opts.n_ctx,
        temperature=opts.temperature,
        source_language=opts.source_language,
        output_subfolder=opts.output_subfolder,
        on_log=events.log,
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
