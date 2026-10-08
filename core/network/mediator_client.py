
"""
Cliente del server mediador remoto (transcripción y traducción).

No depende de nada de ``core/transcription`` ni de ``core/translation``
a propósito — es una capa de transporte pura (descubrimiento, HTTP,
WebSocket). Quien traduce esto a la interfaz de un runner concreto es
``core/transcription/remote_whisper_runner.py`` (transcripción) y
``core/translation/remote_backend.py`` (traducción).

Requiere las librerías ``requests`` y ``websocket-client`` (ver
requirements.txt del proyecto).
"""
from __future__ import annotations

import json
import threading
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

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
        # más de 15s (cargando un modelo grande, generando un bloque
        # largo, transcribiendo un archivo largo) sin que eso sea un
        # problema real.
        self._ws_timeout = ws_timeout
        self._ws: ws_lib.WebSocket | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # ── HTTP — transcripción ─────────────────────────────────────────

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
        return _handle_job_creation_response(r)

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
        """DELETE /model — liberación forzada, sin importar el estado
        ni el tipo de trabajo (transcripción o traducción)."""
        r = requests.delete(f"{self.base_url}/model", timeout=self._http_timeout)
        r.raise_for_status()
        return r.json()

    # ── WebSocket — transcripción ────────────────────────────────────

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
        """Manda {"type": "cancel"} por el WS activo, si hay uno. Solo
        tiene sentido para transcripción (ver traducción más abajo:
        ahí cancelar es simplemente no mandar el siguiente "generate"
        y cerrar la sesión, no hay nada que interrumpir a mitad de
        camino del lado del mediador)."""
        if self._ws is not None:
            try:
                self._ws.send(json.dumps({"type": "cancel"}))
            except Exception:
                pass

    # ── HTTP — traducción ────────────────────────────────────────────

    def get_translation_models(self) -> list[str]:
        """GET /translation_models"""
        r = requests.get(f"{self.base_url}/translation_models", timeout=self._http_timeout)
        r.raise_for_status()
        return r.json()["models"]

    def create_translate_job(self, job_config: dict) -> dict:
        """
        POST /translate/jobs — {"model", "n_gpu_layers", "n_ctx"}.
        Devuelve {"job_id", "job_number", "ws_path"}. Mismos errores
        que create_job (MediatorBusyError/MediatorRejectedError).
        """
        r = requests.post(
            f"{self.base_url}/translate/jobs", json=job_config, timeout=self._http_timeout,
        )
        return _handle_job_creation_response(r)

    # ── WebSocket — traducción ───────────────────────────────────────
    #
    # A diferencia de transcripción (un job = subís archivos, el
    # mediador procesa todo solo y te va mandando resultados), acá el
    # mediador nunca corre un loop propio: cada bloque, título, o
    # nombre de archivo a traducir (y cada reintento) es UNA llamada
    # "generate" que dispara este cliente — el mediador solo ejecuta
    # esa llamada puntual contra el modelo y devuelve el streaming
    # crudo. Toda la lógica de bloques/reintentos/fallback sigue
    # viviendo en core/translation/model_manager.py, sin duplicarla acá
    # ni en el mediador.

    def open_translate_session(self, ws_path: str) -> dict | None:
        """
        Conecta el WS de una sesión de traducción y espera a que el
        mediador termine de cargar el modelo (bloqueante). Devuelve el
        snapshot de VRAM que reportó el mediador tras cargar (dict, o
        None si no pudo medirlo) — lo usa RemoteLlamaBackend para que
        las estadísticas de una corrida remota reflejen la GPU del
        mediador, no la de esta máquina.

        Lanza MediatorError si la carga falló o si el WS se cerró
        antes de estar listo.
        """
        url = f"ws://{self.host}:{self.port}{ws_path}"
        self._ws = ws_lib.create_connection(url, timeout=self._ws_timeout)
        while True:
            raw = self._ws.recv()
            if not raw:
                raise MediatorError("El mediador cerró la conexión mientras cargaba el modelo.")
            message = json.loads(raw)
            mtype = message.get("type")
            if mtype == "ready":
                return message.get("vram")
            if mtype == "error":
                raise MediatorError(message.get("message", "Error desconocido al cargar el modelo."))
            # cualquier otro tipo (no debería llegar ninguno antes de
            # "ready"/"error") se ignora.

    def generate(
        self, system_prompt: str, user_message: str, temperature: float,
    ) -> Iterator[dict]:
        """
        Manda {"type": "generate", ...} por la sesión ya abierta con
        open_translate_session(), y devuelve un generador de chunks
        con la MISMA forma que ``llama_cpp.Llama.create_chat_completion``
        en streaming — para que ``ModelManager._consume_stream`` (ver
        core/translation/model_manager.py) pueda leerlo exactamente
        igual que si el modelo estuviera cargado en este proceso, sin
        ningún caso especial para "es remoto".

        Bloqueante: se usa siempre desde el mismo thread donde corre
        la cola de traducción, y nunca hay dos generate() en vuelo al
        mismo tiempo sobre la misma sesión (ModelManager lo serializa
        con su lock, igual que hace con el modelo local).
        """
        if self._ws is None:
            raise MediatorError("No hay una sesión de traducción abierta con el mediador.")

        self._ws.send(json.dumps({
            "type": "generate",
            "system_prompt": system_prompt,
            "user_message": user_message,
            "temperature": temperature,
        }))

        while True:
            raw = self._ws.recv()
            if not raw:
                raise MediatorError("El mediador cerró la conexión durante la generación.")
            message = json.loads(raw)
            mtype = message.get("type")
            if mtype == "delta":
                yield {"choices": [{"delta": {"content": message["text"]}}]}
            elif mtype == "result":
                return
            elif mtype == "error":
                raise MediatorError(
                    message.get("message", "Error desconocido del mediador durante la generación.")
                )
            # cualquier otro tipo desconocido se ignora, por las dudas.

    def close_translate_session(self) -> None:
        """
        Cierra ordenadamente la sesión de traducción: avisa al
        mediador ({"type": "close"}) para que libere el modelo de
        inmediato (sin esperar el timeout de zombie) y cierra el WS.
        No lanza excepción aunque el mediador ya se haya ido — cerrar
        una sesión debe poder llamarse siempre, incluso tras un error.
        """
        if self._ws is None:
            return
        try:
            self._ws.send(json.dumps({"type": "close"}))
        except Exception:
            pass
        try:
            self._ws.close()
        except Exception:
            pass
        self._ws = None


def _handle_job_creation_response(r: requests.Response) -> dict:
    if r.status_code == 409:
        detail = _safe_detail(r)
        if "ocupado" in detail.lower() or "en curso" in detail.lower():
            raise MediatorBusyError(detail)
        raise MediatorRejectedError(detail)
    if r.status_code == 422:
        raise MediatorRejectedError(_safe_detail(r))

    r.raise_for_status()
    return r.json()


def _safe_detail(response: requests.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text
