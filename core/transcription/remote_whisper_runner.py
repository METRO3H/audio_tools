"""
Runner que habla con el mediador remoto en vez de cargar faster-whisper
en este mismo proceso.

Tiene el mismo contrato público que ``WhisperRunner``
(``core/transcription/whisper_runner.py``): ``run_sequential``,
``cancel``, ``unload``, con exactamente la misma firma de callbacks —
para que ``AudioToolsAPI.run_transcribe()`` pueda instanciar cualquiera
de los dos sin cambiar cómo arma los callbacks ni cómo escribe los
archivos de salida (``on_file_done`` sigue recibiendo objetos con
``.start``/``.end``/``.text``, ya sea que vengan de faster-whisper
local o del mediador).
"""
from __future__ import annotations

import threading
from typing import Callable

from core.network.mediator_client import (
    MediatorBusyError,
    MediatorClient,
    MediatorError,
    MediatorRejectedError,
)


class SimpleSegment:
    """
    Envoltorio liviano para que un segmento que llegó como dict desde
    el mediador (``{"start":..., "end":..., "text":...}``) tenga los
    mismos atributos que un ``Segment`` real de faster-whisper — lo
    único que usan ``build_srt``/``build_vtt``/``build_txt`` en
    ``transcribe_action.py``.
    """

    __slots__ = ("start", "end", "text")

    def __init__(self, start: float, end: float, text: str):
        self.start = start
        self.end = end
        self.text = text


class RemoteWhisperRunner:
    """
    Un runner nuevo por corrida (igual que se instanciaría un
    ``WhisperRunner``), apuntando a un mediador ya localizado — el
    descubrimiento en sí no es responsabilidad de esta clase.
    """

    def __init__(self, host: str, port: int):
        self._client = MediatorClient(host, port)
        self._cancelled = False
        self.was_cancelled = False  # lo chequea api.py después de on_done

    # ── API pública — misma firma que WhisperRunner.run_sequential ──

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
        self.was_cancelled = False
        thread = threading.Thread(
            target=self._run,
            args=(configs, on_log, on_done, on_progress, on_file_start, on_file_done),
            daemon=True,
        )
        thread.start()

    def cancel(self) -> None:
        self._cancelled = True
        self._client.request_cancel()

    def unload(self) -> None:
        """
        No-op de este lado: el mediador libera su propio modelo apenas
        termina (o se cancela) el job — acá no hay nada cargado que
        descargar. Existe solo para que la interfaz calce con
        WhisperRunner.unload(), por si algo en api.py lo llama
        genéricamente sin saber qué runner tiene enfrente.
        """
        pass

    # ── internals ──────────────────────────────────────────────────

    def _run(
        self,
        configs: list,
        on_log: Callable,
        on_done: Callable,
        on_progress: Callable | None,
        on_file_start: Callable | None,
        on_file_done: Callable | None,
    ) -> None:
        all_segments: list[list] = []
        try:
            cfg0 = configs[0]
            # model_size/device/compute_type/language/etc. son de nivel
            # de lote (todas las configs del batch comparten esto,
            # igual que asume hoy WhisperRunner.run_sequential local) —
            # lo que varía por archivo es input_file/total_duration.
            job_config = {
                "model_size": cfg0.model_size,
                "device": cfg0.device,
                "compute_type": cfg0.compute_type,
                "language": cfg0.language,
                "vad_filter": cfg0.vad_filter,
                "condition_on_previous_text": cfg0.condition_on_previous_text,
                "word_timestamps": cfg0.word_timestamps,
                "beam_size": cfg0.beam_size,
                "initial_prompt": cfg0.initial_prompt,
            }

            on_log(f"Conectando con el mediador en {self._client.host}:{self._client.port}...")
            try:
                job = self._client.create_job(job_config, files_expected=len(configs))
            except MediatorBusyError as exc:
                on_log(f"[error] El mediador está ocupado: {exc}")
                on_done(False, [])
                return
            except MediatorRejectedError as exc:
                on_log(f"[error] El mediador rechazó la solicitud: {exc}")
                on_done(False, [])
                return

            if self._cancelled:
                self.was_cancelled = True
                on_done(False, [])
                return

            on_log(f"Job #{job['job_number']} aceptado, subiendo archivos...")
            for cfg in configs:
                if self._cancelled:
                    self.was_cancelled = True
                    on_done(False, all_segments)
                    return
                on_log(f"Subiendo {cfg.input_file.name}...")
                self._client.upload_file(
                    job["job_id"], cfg.input_file, cfg.total_duration,
                    on_slow=lambda elapsed: on_log(
                        f"[aviso] Sigue subiendo {cfg.input_file.name} — "
                        f"lleva {elapsed / 60:.0f} min, esperando (puede ser normal en redes lentas)..."
                    ),
                )

            success = True

            def handle_message(message: dict) -> None:
                nonlocal success
                msg_type = message.get("type")

                if msg_type == "log":
                    on_log(message["message"])
                elif msg_type == "file_start":
                    if on_file_start:
                        on_file_start(message["file_index"])
                elif msg_type == "progress":
                    # ojo: "file_progress" (0-1 del archivo actual), NO
                    # "value" (0-1 del lote) — es lo que espera
                    # on_progress, igual que WhisperRunner en local.
                    if on_progress:
                        on_progress(message["file_progress"])
                elif msg_type == "result":
                    segments = [SimpleSegment(**s) for s in message["segments"]]
                    all_segments.append(segments)
                    if on_file_done:
                        on_file_done(message["file_index"], segments)
                elif msg_type == "error":
                    on_log(f"[error] {message['message']}")
                    success = False
                elif msg_type == "done":
                    if not message.get("success", False):
                        success = False
                    if message.get("cancelled", False):
                        self.was_cancelled = True
                # "file_received" no tiene equivalente local — se ignora.

            self._client.listen(job["ws_path"], handle_message)
            on_done(success and not self._cancelled, all_segments)

        except MediatorError as exc:
            on_log(f"[error] {exc}")
            on_done(False, all_segments)
        except Exception as exc:  # mismo criterio amplio que usa WhisperRunner local
            on_log(f"[error] {exc}")
            on_done(False, all_segments)
