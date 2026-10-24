"""
core/transcription/job.py
-------------------------
Lo que une las opciones de Transcribe con un runner (local o del mediador):

    resolve_transcribe   opciones -> una TranscribeConfig por archivo (con duraciones resueltas)
    run_transcription    arranca el runner y traduce sus callbacks a los eventos del contrato

Está aparte de api.py para poder probarlo con un runner falso, sin pywebview.

Eventos que emite (ver core/jobs.py), además del `audiotools:transcribe:file_log` propio de esta
tool, que asocia cada mensaje al archivo que se está procesando:

    audiotools:transcribe:file_log   { job_id, file_index, message }
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.jobs import JobEvents, job_cancelled
from core.models import TranscribeConfig, TranscribeOptions
from core.transcription.transcribe_action import TranscribeAction, TranscribePlan


def resolve_transcribe(
    opts: TranscribeOptions, get_duration: Callable[[Path], float]
) -> list[TranscribeConfig]:
    """
    Resuelve las opciones a una configuración por archivo y comprueba lo que de otro modo
    solo se descubriría tarde y mal: que existan la carpeta base y los audios. La sonda de
    duración (ffprobe) llega inyectada para probar esto sin ffprobe.

    Se usan las duraciones que ya trae el frontend; solo se consulta ffprobe para las que
    faltan o son 0.
    """
    base_folder = Path(opts.base_folder)
    if not base_folder.is_dir():
        raise ValueError(f"La carpeta base no existe: {base_folder}")
    for path in map(Path, opts.file_paths):
        if not path.is_file():
            raise ValueError(f"No se encontró el archivo «{path.name}».")

    known = opts.durations or [None] * len(opts.file_paths)
    durations: list[float] = []
    for path, duration in zip(map(Path, opts.file_paths), known):
        if duration is not None and duration > 0:
            durations.append(float(duration))
            continue
        try:
            durations.append(float(get_duration(path)))
        except ValueError as exc:
            raise ValueError(
                f"No se pudo leer la duración de «{path.name}». "
                "¿El archivo está dañado o su formato no es compatible?"
            ) from exc
    return opts.to_configs(durations)


def run_transcription(
    runner,
    configs: list[TranscribeConfig],
    plan: TranscribePlan,
    events: JobEvents,
    emit_file_log: Callable[[int, str], None],
    on_finished: Callable[[], None] | None = None,
) -> None:
    """
    Emite `start` y arranca `runner.run_sequential` (en su propio hilo). Retorna de inmediato;
    `log`/`progress`/`done` llegan después por `events`.

    Cada transcripción se escribe en la ruta que dice `plan` en cuanto su archivo termina.
    `on_finished` se llama tras el `done` (para soltar lo que api.py retenga del runner).
    Si escribir una salida falla, el runner lo captura y el job termina con ese error.
    """
    action = TranscribeAction()
    total = len(configs)
    state = {"current": None}  # índice del archivo en curso; None hasta el primer file_start

    def current_index() -> int:
        return state["current"] or 0

    def on_log(message: str) -> None:
        events.log(message)
        index = state["current"]
        if index is None:
            # Durante la preparación o la subida aún no llegó file_start: si el mensaje nombra un
            # archivo se asocia a ese; si no, al primero del lote.
            index = next((i for i, cfg in enumerate(configs) if cfg.input_file.name in message), 0)
        emit_file_log(index, message)

    def on_file_start(index: int) -> None:
        state["current"] = index
        events.progress(index / total, index, 0, index, total)

    def on_progress(value: float) -> None:
        current = current_index()
        events.progress((current + value) / total, current, value, current, total)

    def on_file_done(index: int, segments: list) -> None:
        action.write_output(segments, plan.files[index].output, configs[index].output_format)
        events.progress((index + 1) / total, index, 1, index + 1, total)

    def on_done(success: bool, all_segments: list, error: str | None = None) -> None:
        events.done(success, error=error, cancelled=job_cancelled(runner, success))
        if on_finished is not None:
            on_finished()

    events.start(total)
    runner.run_sequential(
        configs=configs,
        on_log=on_log,
        on_done=on_done,
        on_progress=on_progress,
        on_file_start=on_file_start,
        on_file_done=on_file_done,
    )
