"""
Cliente del server mediador de transcripción remoto.

No depende de nada de ``core/transcription`` a propósito — es una capa
de transporte pura (descubrimiento, HTTP, WebSocket). Quien traduce
esto a la interfaz de un runner de transcripción es
``core/transcription/remote_whisper_runner.py``.

Requiere las librerías ``requests`` y ``websocket-client`` (ver
requirements.txt del proyecto).
"""
from __future__ import annotations

import json
import threading
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
import websocket as ws_lib

DISCOVERY_MAGIC = b"AUDIOTOOLS_DISCOVER?"
DISCOVERY_PORT = 50505  # debe coincidir con config.UDP_DISCOVERY_PORT del mediador
DISCOVERY_TIMEOUT = 2.0
DEFAULT_HTTP_TIMEOUT = 15.0
UPLOAD_SLOW_NOTICE_INTERVAL = 1200.0

class MediatorError(Exception):
    """Error genérico al hablar con el mediador."""


class MediatorBusyError(MediatorError):
    """El mediador respondió 409: ya hay un job en curso."""


class MediatorRejectedError(MediatorError):
    """El mediador rechazó la solicitud (config inválida, modelo no
    disponible, etc.) — 422 o 409 por motivos distintos a "ocupado"."""


@dataclass
class DiscoveredMediator:
    host: str
    port: int


def discover_mediator(timeout: float = DISCOVERY_TIMEOUT) -> DiscoveredMediator | None:
    """
    Manda un broadcast UDP con el magic que espera el mediador y
    espera su respuesta. Devuelve ``None`` si no contesta a tiempo —
    eso es un estado normal (todavía no lo prendiste), no un error.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.sendto(DISCOVERY_MAGIC, ("255.255.255.255", DISCOVERY_PORT))
        data, addr = sock.recvfrom(1024)
    except (socket.timeout, OSError):
        return None
    finally:
        sock.close()

    try:
        payload = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None

    if payload.get("service") != "audiotools-mediator":
        return None

    return DiscoveredMediator(host=addr[0], port=int(payload["port"]))


class MediatorClient:
    """
    Habla con un mediador ya localizado (host/puerto conocidos, sea
    porque los guardaste de una vez anterior o porque acabás de
    correr ``discover_mediator``).
    """

    def __init__(
        self,
        host: str,
        port: int,
        http_timeout: float = DEFAULT_HTTP_TIMEOUT,
        ws_timeout: float | None = None,
    ):
        self.host = host
        self.port = port
        self._http_timeout = http_timeout
        # None = sin timeout — el WS puede quedar en silencio muchísimo
        # más de 15s (cargando un modelo grande, o transcribiendo un
        # archivo largo) sin que eso sea un problema real.
        self._ws_timeout = ws_timeout
        self._ws: ws_lib.WebSocket | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # ── HTTP ─────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """GET /status — {"state": "idle"|"loading"|"busy", "model": ..., "job_id": ...}"""
        r = requests.get(f"{self.base_url}/status", timeout=self._http_timeout)
        r.raise_for_status()
        return r.json()

    def get_available_models(self) -> list[str]:
        """GET /whisper_models"""
        r = requests.get(f"{self.base_url}/whisper_models", timeout=self._http_timeout)
        r.raise_for_status()
        return r.json()["models"]

    def create_job(self, job_config: dict, files_expected: int) -> dict:
        """
        POST /jobs. Devuelve {"job_id", "job_number", "ws_path"}.

        Lanza MediatorBusyError si el mediador está ocupado, o
        MediatorRejectedError si rechazó la config (modelo no
        disponible, valores inválidos, etc.).
        """
        payload = dict(job_config, files_expected=files_expected)
        r = requests.post(f"{self.base_url}/jobs", json=payload, timeout=self._http_timeout)

        if r.status_code == 409:
            detail = _safe_detail(r)
            if "ocupado" in detail.lower() or "en curso" in detail.lower():
                raise MediatorBusyError(detail)
            raise MediatorRejectedError(detail)
        if r.status_code == 422:
            raise MediatorRejectedError(_safe_detail(r))

        r.raise_for_status()
        return r.json()

    def upload_file(
        self,
        job_id: str,
        file_path: Path,
        duration: float,
        on_slow: Callable[[float], None] | None = None,
        notice_interval: float = UPLOAD_SLOW_NOTICE_INTERVAL,
    ) -> dict:
        """POST /jobs/{job_id}/files — sube un archivo con su duración
        ya calculada del lado cliente.

        Sin timeout de envío/lectura: un archivo grande en una red
        lenta puede tardar mucho sin que eso sea un error real. Solo
        el connect tiene timeout (``self._http_timeout``) — si el
        mediador ni siquiera contesta el handshake, ahí sí fallamos
        rápido. Si la subida lleva más de ``notice_interval``
        segundos, se llama a ``on_slow(elapsed)`` una vez por
        intervalo (repite mientras siga en curso) para avisar sin
        cancelar nada.
        """
        url = f"{self.base_url}/jobs/{job_id}/files"
        file_path = Path(file_path)

        stop_event = threading.Event()
        watchdog_thread: threading.Thread | None = None

        if on_slow is not None:
            def _watchdog() -> None:
                elapsed = 0.0
                while not stop_event.wait(notice_interval):
                    elapsed += notice_interval
                    on_slow(elapsed)

            watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
            watchdog_thread.start()

        try:
            with open(file_path, "rb") as fh:
                files = {"file": (file_path.name, fh, "application/octet-stream")}
                data = {"duration": str(duration)}
                r = requests.post(
                    url, files=files, data=data,
                    timeout=(self._http_timeout, None),  # connect corto, read/write sin límite
                )
        finally:
            stop_event.set()
            if watchdog_thread is not None:
                watchdog_thread.join(timeout=1.0)

        r.raise_for_status()
        return r.json()

    def release_model(self) -> dict:
        """DELETE /model — liberación forzada, sin importar el estado."""
        r = requests.delete(f"{self.base_url}/model", timeout=self._http_timeout)
        r.raise_for_status()
        return r.json()

    # ── WebSocket ────────────────────────────────────────────────────

    def listen(self, ws_path: str, on_message: Callable[[dict], None]) -> None:
        """
        Se conecta al WS del job y llama a ``on_message(dict)`` por
        cada mensaje recibido, hasta que llegue un ``{"type": "done"}``
        o se cierre la conexión. Guarda la conexión activa para que
        ``request_cancel()`` pueda usarla mientras esto está corriendo
        (normalmente desde otro thread).
        """
        url = f"ws://{self.host}:{self.port}{ws_path}"
        self._ws = ws_lib.create_connection(url, timeout=self._ws_timeout)
        try:
            while True:
                raw = self._ws.recv()
                if not raw:
                    break
                message = json.loads(raw)
                on_message(message)
                if message.get("type") == "done":
                    break
        finally:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def request_cancel(self) -> None:
        """Manda {"type": "cancel"} por el WS activo, si hay uno."""
        if self._ws is not None:
            try:
                self._ws.send(json.dumps({"type": "cancel"}))
            except Exception:
                pass


def _safe_detail(response: requests.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text
