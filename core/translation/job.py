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
modelo y las estadísticas de la corrida. Esos van en la familia `audiotools:translation:*`,
compartida por las 3 tools de traducción (paso 3.2 del traspaso: núcleo común phase /
work_info / work_info_stream / preview_ready, más extensiones por tool). Eventos de SRT:

    audiotools:translation:queue_started     { started_at }
    audiotools:translation:phase             { phase }
    audiotools:translation:step              { step, status }
    audiotools:translation:title             { title }
    audiotools:translation:work_info         { work_info }
    audiotools:translation:work_info_stream  { text }
    audiotools:translation:title_stream      { text }
    audiotools:translation:lines             { file_index, lines_done_file, lines_total_file,
                                              lines_done_global, lines_total_global }
    audiotools:translation:block_stream      { file_index, text }
    audiotools:translation:block_input       { file_index, text }
    audiotools:translation:system_prompt     { text, sections }
    audiotools:translation:stats             { run_id, ...RunStats }

Chapters (ver run_translate_chapters_job) y Filenames (ver run_translate_filenames_job) usan
el mismo núcleo común (phase, work_info, work_info_stream, preview_ready) más una extensión
propia cada una — ninguna tiene concepto de título de la obra, y ninguna escribe nada en disco:
las dos terminan en `audiotools:translation:preview_ready` con lo traducido, para que el
usuario confirme o edite (ver ChaptersAction.apply / api.apply_filename_renames) antes de que
algo se escriba de verdad:

    audiotools:translation:file_titles       { file_index, chapters }   solo Chapters
    audiotools:translation:name_stream       { text }                   solo Filenames
    audiotools:translation:preview_ready     { job_id, files }          Chapters y Filenames

Como el nombre es compartido, un listener en una vista no garantiza que otra lo use (ver
tests/test_translation_event_sync.py).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from core.jobs import Emit, JobEvents, describe_error
from core.models import ChaptersOptions, FilenamesOptions, TranslateOptions
from core.translation.chapters_action import ChaptersAction, ChaptersPlan
from core.translation.translate_action import TranslateAction, TranslatePlan


def resolve_translate_chapters(opts: ChaptersOptions, get_chapters) -> ChaptersPlan:
    """
    Resuelve las opciones de Chapters a un plan (los capítulos de cada archivo, leídos pero sin
    tocar nada). `get_chapters` llega inyectada (ver ChaptersAction.plan) para poder probar esto
    sin ffprobe.
    """
    paths = [Path(p) for p in opts.file_paths]
    for path in paths:
        if not path.is_file():
            raise ValueError(f"No se encontró el archivo «{path.name}».")
    return ChaptersAction().plan(get_chapters, paths)


def run_translate_chapters_job(
    runner,
    plan,
    opts: ChaptersOptions,
    events: JobEvents,
    emit: Emit,
    on_finished: Callable[[], None] | None = None,
) -> None:
    """
    Arranca runner.translate_queue (en su propio hilo). A diferencia de run_translate_job (SRT),
    esto NO escribe nada en disco: termina en audiotools:translation:preview_ready con los títulos
    traducidos de toda la cola, para que el usuario confirme o edite antes de que
    api.apply_translated_chapters (ChaptersAction.apply) escriba de verdad — ver el docstring de
    ChaptersOptions para el porqué de este diseño.

    `done` llega igual que en Transcribe/SRT (success/cancelled/error), pero acá success=true
    significa "la cola terminó de traducir", no "ya quedó escrito" — eso es
    audiotools:translation:preview_ready, que llega junto (ver on_queue_done más abajo: emite los
    dos, preview_ready primero).
    """
    total = len(plan.files)
    events.start(total)

    def on_phase(msg: str) -> None:
        emit("audiotools:translation:phase", {"phase": msg})

    def on_work_info(info: str) -> None:
        emit("audiotools:translation:work_info", {"work_info": info})

    def on_work_info_stream(text: str) -> None:
        emit("audiotools:translation:work_info_stream", {"text": text})

    def on_file_start(idx: int, total_: int, name: str, started_at: float) -> None:
        emit("audiotools:file", {"job_id": events.job_id, "index": idx, "done": False, "started_at": started_at})

    def on_file_titles(idx: int, rows: list[dict]) -> None:
        emit("audiotools:translation:file_titles", {"file_index": idx, "chapters": rows})

    def on_file_done(idx: int, success: bool, elapsed: float) -> None:
        emit("audiotools:file", {"job_id": events.job_id, "index": idx, "done": True, "elapsed": elapsed})

    def on_queue_progress(done: int, queue_total: int) -> None:
        events.progress((done / queue_total) if queue_total else 0, done, 0, done, queue_total)

    def on_queue_done(succeeded: int, queue_total: int, cancelled: bool, results: list) -> None:
        success = succeeded > 0 and not cancelled
        if success:
            emit("audiotools:translation:preview_ready", {
                "job_id": events.job_id,
                "files": [
                    {"path": str(path), "name": path.name, "chapters": rows}
                    for path, rows in results
                ],
            })
        events.done(success, cancelled=cancelled)
        if on_finished is not None:
            on_finished()

    runner.translate_queue(
        files=[(item.path, item.chapters) for item in plan.files],
        raw_publisher_info=opts.raw_publisher_info,
        base_prompt=opts.base_prompt,
        glossary=opts.glossary,
        model=opts.model,
        n_gpu_layers=opts.n_gpu_layers,
        n_ctx=opts.n_ctx,
        temperature=opts.temperature,
        on_log=events.log,
        on_phase=on_phase,
        on_work_info=on_work_info,
        on_work_info_stream=on_work_info_stream,
        on_file_start=on_file_start,
        on_file_titles=on_file_titles,
        on_file_done=on_file_done,
        on_queue_progress=on_queue_progress,
        on_queue_done=on_queue_done,
    )


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
    de inmediato; `log`/`progress`/`done` (y los `audiotools:translation:*` de arriba) llegan
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
    emit("audiotools:translation:queue_started", {"started_at": queue_started_at})

    def on_phase(msg: str) -> None:
        emit("audiotools:translation:phase", {"phase": msg})

    def on_step(step: str, status: str) -> None:
        emit("audiotools:translation:step", {"step": step, "status": status})

    def on_title(title: str) -> None:
        emit("audiotools:translation:title", {"title": title})

    def on_work_info(info: str) -> None:
        emit("audiotools:translation:work_info", {"work_info": info})

    def on_work_info_stream(text: str) -> None:
        emit("audiotools:translation:work_info_stream", {"text": text})

    def on_title_stream(text: str) -> None:
        emit("audiotools:translation:title_stream", {"text": text})

    def on_lines_progress(
        file_index: int,
        lines_done_file: int,
        lines_total_file: int,
        lines_done_global: int,
        lines_total_global: int,
    ) -> None:
        emit("audiotools:translation:lines", {
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
        emit("audiotools:translation:block_stream", {"file_index": file_index, "text": text})

    def on_block_input(file_index: int, text: str) -> None:
        emit("audiotools:translation:block_input", {"file_index": file_index, "text": text})

    def on_system_prompt(text: str, sections: dict) -> None:
        emit("audiotools:translation:system_prompt", {"text": text, "sections": sections})

    def on_stats(run_id: int | None, stats: dict) -> None:
        emit("audiotools:translation:stats", {"run_id": run_id, **stats})

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


def run_translate_filenames_job(
    runner,
    opts: FilenamesOptions,
    events: JobEvents,
    emit: Emit,
    on_finished: Callable[[], None] | None = None,
) -> None:
    """
    A diferencia de run_translate_job/run_translate_chapters_job, FilenameTranslateRunner.
    translate_preview() es SÍNCRONO (ver su propio docstring: "el caller es responsable de
    invocarlo desde un hilo propio, tal como hace api.py") — ese hilo se arma acá, no en
    translate_preview ni en api.py.

    No hay "plan" ni "resolve" propios: files ya viene resuelto (es el resultado de
    scan_filenames_folder, que el frontend llama aparte — esa detección de idioma no usa IA y es
    instantánea, así que no se repite acá).

    NO escribe nada en disco: termina en audiotools:translation:preview_ready con los nombres
    traducidos (editables del lado del frontend), para que el usuario confirme antes de que
    api.apply_filename_renames renombre de verdad. Si se cancela a mitad de camino, runner.
    cancelled lo distingue de un éxito real (ver el docstring de esa property: translate_preview
    retorna la misma forma en los dos casos).
    """
    events.start(len(opts.files))

    def on_phase(msg: str) -> None:
        emit("audiotools:translation:phase", {"phase": msg})

    def on_work_info(info: str) -> None:
        emit("audiotools:translation:work_info", {"work_info": info})

    def on_work_info_stream(text: str) -> None:
        emit("audiotools:translation:work_info_stream", {"text": text})

    def on_translate_stream(text: str) -> None:
        emit("audiotools:translation:name_stream", {"text": text})

    def worker() -> None:
        try:
            result = runner.translate_preview(
                files=opts.files,
                raw_publisher_info=opts.raw_publisher_info,
                base_prompt=opts.base_prompt,
                glossary=opts.glossary,
                model=opts.model,
                n_gpu_layers=opts.n_gpu_layers,
                n_ctx=opts.n_ctx,
                temperature=opts.temperature,
                on_log=events.log,
                on_phase=on_phase,
                on_work_info=on_work_info,
                on_work_info_stream=on_work_info_stream,
                on_translate_stream=on_translate_stream,
            )
            if runner.cancelled:
                events.done(False, cancelled=True)
            else:
                emit("audiotools:translation:preview_ready", {"job_id": events.job_id, "files": result})
                events.done(True)
        except Exception as exc:
            message = describe_error(exc)
            events.log(f"[error] {message}")
            events.done(False, error=message)
        finally:
            if on_finished is not None:
                on_finished()

    threading.Thread(target=worker, daemon=True).start()
