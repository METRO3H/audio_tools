
"""
Backend de ``ModelManager`` (ver core/translation/model_manager.py) que
habla con el mediador remoto en vez de cargar el GGUF en este proceso.

Capa fina entre ``MediatorClient`` (transporte puro — ver
core/network/mediator_client.py) y ``ModelManager`` (que arma bloques,
reintentos, contexto y fallback exactamente igual sin importar si el
backend es local o remoto): acá solo se traduce el ciclo de
carga/descarga/generación a las llamadas HTTP/WS del mediador. Ninguna
lógica de traducción vive en este archivo.

Mismo espíritu que ``core/transcription/remote_whisper_runner.py``
(que hace lo mismo para whisper), pero al nivel de "un backend
inyectable" en vez de "un runner completo", porque acá SÍ hay lógica
de reintentos que vale la pena no duplicar entre local y remoto (a
diferencia de transcribir, donde no hay retry/validación de por medio).
"""
from __future__ import annotations

from core.hardware_info import VramSnapshot
from core.network.mediator_client import MediatorClient


class RemoteLlamaBackend:
    """Un backend nuevo por corrida (igual que se instanciaría un
    ``TranslateRunner``/``ChaptersTranslateRunner``/
    ``FilenameTranslateRunner`` local), apuntando a un mediador ya
    localizado — el descubrimiento en sí no es responsabilidad de esta
    clase (ver ``AudioToolsAPI.check_remote_translation_server`` en
    api.py, análogo a ``check_remote_server`` para transcripción)."""

    def __init__(self, host: str, port: int):
        self._client = MediatorClient(host, port)
        self._session_open = False
        self._model_key: tuple | None = None
        self._vram: VramSnapshot | None = None

    def list_models(self) -> list[str]:
        return self._client.get_translation_models()

    def load(self, model: str, n_gpu_layers: int, n_ctx: int) -> None:
        key = (model, n_gpu_layers, n_ctx)
        if self._session_open and self._model_key == key:
            return
        if self._session_open:
            self.unload()

        job = self._client.create_translate_job({
            "model": model, "n_gpu_layers": n_gpu_layers, "n_ctx": n_ctx,
        })
        vram_dict = self._client.open_translate_session(job["ws_path"])
        self._session_open = True
        self._model_key = key
        self._vram = VramSnapshot(**vram_dict) if vram_dict else None

    def unload(self) -> None:
        if self._session_open:
            self._client.close_translate_session()
        self._session_open = False
        self._model_key = None
        self._vram = None

    def is_loaded(self) -> bool:
        return self._session_open

    def get_vram_snapshot(self) -> VramSnapshot | None:
        """Lo que reportó el MEDIADOR al cargar (ver
        open_translate_session) — nunca la GPU de esta máquina, que ni
        siquiera hace falta que tenga una."""
        return self._vram

    def create_chat_completion(self, messages, temperature, max_tokens=-1, stream=True):
        # messages ya viene armado por ModelManager exactamente igual
        # que para el backend local — incluyendo el sufijo /no_think en
        # el mensaje de usuario (ver ModelManager._NO_THINK_SUFFIX) —
        # así que acá alcanza con extraer system/user y mandarlos tal
        # cual; el mediador no aplica ningún default ni post-proceso
        # propio.
        system_prompt = messages[0]["content"]
        user_message = messages[1]["content"]
        return self._client.generate(system_prompt, user_message, temperature)
