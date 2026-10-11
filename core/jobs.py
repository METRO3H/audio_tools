"""
core/jobs.py
------------
Contrato común de ejecución de jobs: tools que corren en un hilo de fondo y
reportan su avance al frontend mediante eventos.

Piezas:
    FfmpegCommand         un comando de ffmpeg + lo que el progreso necesita saber
    JobEvents             emisor de los eventos de UN job (start/log/progress/done)
    job_id_from           lee el job_id de unas opciones sin validarlas
    job_errors            convierte cualquier excepción en done{success:false, error}
    job_cancelled         ¿terminó el job porque el usuario lo canceló?
    run_ffmpeg_commands   ejecuta una lista de comandos en un FFmpegRunner

Este módulo no conoce a pywebview: `emit` es cualquier callable
(evento, detalle) -> None. api.py lo conecta con window.evaluate_js y los
tests con una lista.

Eventos (los nombres `audiotools:*` no cambian; se añaden `start` y `job_id`):
    audiotools:start     { job_id, tool, total }
    audiotools:log       { job_id, message }
    audiotools:progress  { job_id, value, file_index, file_progress, completed, total }
    audiotools:done      { job_id, tool, success, cancelled, error? }

Cancelar NO es un error: llega como done{success:false, cancelled:true} y sin
`error`. `cancelled` solo puede ser true si success es false.

`job_id` lo genera el frontend y viaja en las opciones; así el frontend puede
descartar eventos rezagados de una ejecución anterior (p. ej. el `done` de un
job cancelado) sin carrera con la respuesta de la llamada.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

Emit = Callable[[str, dict], None]

_MAX_JOB_ID_LEN = 64


@dataclass(frozen=True)
class FfmpegCommand:
    """
    Un comando de ffmpeg listo para ejecutar.

    args      argumentos para ffmpeg (sin el binario)
    duration  duración esperada de la SALIDA en segundos; el runner la usa para
              convertir `time=` de ffmpeg en progreso. None/0 = sin progreso fino
    output    archivo que produce (informativo)
    label     nombre corto para mostrar/loguear
    """

    args: list[str]
    duration: Optional[float] = None
    output: Optional[Path] = None
    label: str = ""


class JobEvents:
    """Emisor de eventos de un único job. Todos los eventos llevan su job_id."""

    def __init__(self, emit: Emit, tool: str, job_id: Optional[str] = None):
        self._emit = emit
        self.tool = tool
        self.job_id = job_id

    def start(self, total: int) -> None:
        self._emit(
            "audiotools:start",
            {"job_id": self.job_id, "tool": self.tool, "total": total},
        )

    def log(self, message: str) -> None:
        self._emit("audiotools:log", {"job_id": self.job_id, "message": message})

    def progress(
        self,
        value: float,
        file_index: int,
        file_progress: float,
        completed: int,
        total: int,
    ) -> None:
        self._emit(
            "audiotools:progress",
            {
                "job_id": self.job_id,
                "value": value,
                "file_index": file_index,
                "file_progress": file_progress,
                "completed": completed,
                "total": total,
            },
        )

    def done(
        self,
        success: bool,
        error: Optional[str] = None,
        cancelled: bool = False,
    ) -> None:
        detail: dict[str, Any] = {
            "job_id": self.job_id,
            "tool": self.tool,
            "success": success,
            "cancelled": cancelled and not success,
        }
        if error is not None:
            detail["error"] = error
        self._emit("audiotools:done", detail)


def job_id_from(options: Any) -> Optional[str]:
    """
    Extrae el job_id de unas opciones SIN validarlas, para poder reportar
    errores de validación con el job_id correcto. Devuelve None si no hay uno
    utilizable.
    """
    if not isinstance(options, dict):
        return None
    job_id = options.get("job_id")
    if isinstance(job_id, str) and 0 < len(job_id) <= _MAX_JOB_ID_LEN:
        return job_id
    return None


def job_cancelled(runner: Any, success: bool) -> bool:
    """
    ¿El job terminó porque el usuario lo canceló? Solo si NO tuvo éxito: si se
    pidió cancelar justo cuando el job ya había terminado bien, cuenta como éxito.
    Los runners sin `was_cancelled` se consideran no cancelados.
    """
    return (not success) and bool(getattr(runner, "was_cancelled", False))


def describe_error(exc: BaseException) -> str:
    """Mensaje legible para el usuario. ValueError = error esperado y ya redactado."""
    if isinstance(exc, ValueError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


@contextmanager
def job_errors(events: JobEvents) -> Iterator[None]:
    """
    Cualquier excepción dentro del bloque se reporta como
    `log` + `done{success:false, error}` y NO se propaga.

    Sin esto, un fallo anterior al arranque del hilo (opciones inválidas,
    ffprobe que no puede leer el archivo...) llega al frontend como un rechazo
    sin capturar y la pantalla se queda en "Procesando...".
    """
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - es justo la red de seguridad
        message = describe_error(exc)
        events.log(f"[error] {message}")
        events.done(False, message)


def _sequential_callbacks(events: JobEvents, total: int):
    """
    Callbacks estándar para FFmpegRunner.run_sequential.

    Mantiene exactamente la semántica de progreso que tenía
    api._make_sequential_callbacks (que sigue en uso para las tools aún no
    migradas): `value` es el avance global; `file_progress`, el del archivo en
    curso.
    """
    state = {"current": 0}

    def on_log(message: str) -> None:
        events.log(message)

    def on_progress(value: float) -> None:
        current = state["current"]
        events.progress((current + value) / total, current, value, current, total)

    def on_file_start(index: int) -> None:
        state["current"] = index
        events.progress(index / total, index, 0, index, total)

    def on_file_done(index: int) -> None:
        events.progress((index + 1) / total, index, 1, index + 1, total)

    return on_log, on_progress, on_file_start, on_file_done


def run_ffmpeg_commands(runner, commands: list[FfmpegCommand], events: JobEvents) -> None:
    """
    Emite `start` y arranca los comandos, en orden, en el hilo del runner.
    Retorna de inmediato; `log`/`progress`/`done` llegan después por `events`.

    Lanza ValueError si no hay comandos (dentro de `job_errors` se convierte en
    un error visible).
    """
    if not commands:
        raise ValueError("No hay nada que procesar.")

    total = len(commands)
    on_log, on_progress, on_file_start, on_file_done = _sequential_callbacks(events, total)

    events.start(total)
    runner.run_sequential(
        args_list=[c.args for c in commands],
        on_log=on_log,
        on_done=lambda success: events.done(
            success, cancelled=job_cancelled(runner, success)
        ),
        on_progress=on_progress,
        on_file_start=on_file_start,
        on_file_done=on_file_done,
        durations=[c.duration for c in commands],
    )
