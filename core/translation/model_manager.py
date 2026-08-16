from __future__ import annotations

import gc
import re
import threading
import time
from pathlib import Path
from typing import Callable

from llama_cpp import Llama

import config


class ModelManager:
    """
    Envoltorio sobre llama-cpp-python. Carga un modelo GGUF en el propio
    proceso (sin server) y expone generacion de texto simple y traduccion
    de bloques de subtitulos.

    Usa stream=True internamente: no para cortar la generacion con un
    timeout (llama.cpp no soporta timeouts nativos por llamada), sino
    para poder emitir progreso en vivo mientras la llamada esta en curso,
    sin interrumpir nada. Dos usos distintos del streaming:

      - generate_text (work_info / titulo): on_stream(tokens, texto_acumulado)
        entrega el texto COMPLETO generado hasta el momento, pensado para
        alimentar un textarea que se va llenando en vivo.

      - translate_block: on_line_progress(n) entrega cuantas lineas del
        bloque ("N: texto") ya se ven completas en el stream (se detecta
        una linea como completa cuando aparece el marcador de la SIGUIENTE
        linea). Es una cuenta aproximada pensada para una barra de progreso,
        no para mostrar texto.

    El lock cubre tanto load()/unload() como la inferencia, para evitar
    que un unload() dispare mientras otro hilo sigue leyendo el modelo
    a mitad de una llamada (no es seguro a nivel del binding en C).
    """

    _LINE_MARKER = re.compile(r"(?m)^\s*\d+\s*:")
    _THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

    # Qwen3 (y algunos otros modelos con "modo pensamiento") reconocen este
    # comando literal en el ultimo turno de usuario como un pedido soft de
    # saltarse el razonamiento. No es 100% infalible — por eso ademas
    # _strip_thinking() actua como red de seguridad en _consume_stream.
    _NO_THINK_SUFFIX = "\n\n/no_think"

    def __init__(self) -> None:
        self._model: Llama | None = None
        self._model_key: tuple | None = None
        self._lock = threading.RLock()

    # ── Ciclo de vida ────────────────────────────────────────────────────

    def list_models(self) -> list[str]:
        if not config.TRANSLATION_MODELS_DIR.exists():
            return []
        return sorted(p.name for p in config.TRANSLATION_MODELS_DIR.glob("*.gguf"))

    def load(self, model: str, n_gpu_layers: int, n_ctx: int) -> None:
        key = (model, n_gpu_layers, n_ctx)
        with self._lock:
            if self._model is not None and self._model_key == key:
                return
            if self._model is not None:
                self._unload_unsafe()

            model_path = config.TRANSLATION_MODELS_DIR / model
            if not model_path.exists():
                raise FileNotFoundError(f"Modelo no encontrado: {model_path}")

            self._model = Llama(
                model_path=str(model_path),
                n_gpu_layers=n_gpu_layers,
                n_ctx=n_ctx,
                chat_format="chatml",
                verbose=False,
            )
            self._model_key = key

    def unload(self) -> None:
        with self._lock:
            self._unload_unsafe()

    def _unload_unsafe(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
            self._model_key = None
            gc.collect()

    def is_loaded(self) -> bool:
        with self._lock:
            return self._model is not None

    # ── Generacion simple (titulo / work_info), con texto completo en vivo ──

    def generate_text(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        on_stream: Callable[[int, str], None] | None = None,
    ) -> str:
        with self._lock:
            if self._model is None:
                raise RuntimeError("Modelo no cargado.")

            stream = self._model.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message + self._NO_THINK_SUFFIX},
                ],
                temperature=temperature,
                max_tokens=-1,
                stream=True,
            )

            text, _ = self._consume_stream(stream, on_stream=on_stream)
            return text.strip()

    # ── Traduccion de textos cortos e independientes (chapters/filenames) ──

    def translate_texts(
        self,
        texts: list[str],
        system_prompt: str,
        temperature: float = 0.3,
        on_stream: Callable[[int, str], None] | None = None,
    ) -> list[str]:
        """
        Traduce una lista de textos cortos e independientes entre si (nombres
        de archivo, titulos de capitulo, etc.) — a diferencia de
        translate_block, no hay contexto de continuidad entre ellos (no son
        lineas consecutivas de un dialogo). Reusa el mismo formato "id: texto"
        y el mismo parser que translate_block, en un unico batch.

        on_stream (opcional): mismo mecanismo que generate_text — entrega el
        texto crudo acumulado ("0: nombre\\n1: nombre...") a medida que el
        modelo lo genera, para poder mostrarlo en vivo en el frontend.
        """
        with self._lock:
            if self._model is None:
                raise RuntimeError("Modelo no cargado.")
            if not texts:
                return []

            by_orig_id = {i: t for i, t in enumerate(texts)}
            block_text = "\n".join(f"{i}: {t}" for i, t in enumerate(texts))

            stream = self._model.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": block_text + self._NO_THINK_SUFFIX},
                ],
                temperature=temperature,
                max_tokens=-1,
                stream=True,
            )

            raw, _ = self._consume_stream(stream, on_stream=on_stream)
            parsed = self._parse_block(raw, by_orig_id)
            by_id = {p["id"]: p["text"] for p in parsed}
            return [by_id[i] for i in range(len(texts))]

    # ── Traduccion de bloques, con progreso por linea ───────────────────────

    def translate_block(
        self,
        lines: list[dict],
        context: str,
        system_prompt: str,
        temperature: float = 0.3,
        on_line_progress: Callable[[int], None] | None = None,
    ) -> list[dict]:
        """
        lines: [{"id": int, "text": str}, ...]
        Devuelve la misma lista con "text" traducido. Si el modelo no
        devuelve una linea esperada (o devuelve algo mal formado), se
        usa el texto original de esa linea como fallback.
        """
        with self._lock:
            if self._model is None:
                raise RuntimeError("Modelo no cargado.")

            by_orig_id = {l["id"]: l["text"] for l in lines}
            block_text = "\n".join(f"{l['id']}: {l['text']}" for l in lines)

            user_message = block_text
            if context:
                user_message = (
                    f"[Previous translated context]:\n{context}\n\n"
                    f"[Block to translate]:\n{block_text}"
                )

            stream = self._model.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message + self._NO_THINK_SUFFIX},
                ],
                temperature=temperature,
                max_tokens=-1,
                stream=True,
            )

            raw, _ = self._consume_stream(stream, on_line_progress=on_line_progress)
            return self._parse_block(raw, by_orig_id)

    # ── Helpers ──────────────────────────────────────────────────────────

    @classmethod
    def _consume_stream(
        cls,
        stream,
        on_stream: Callable[[int, str], None] | None = None,
        on_line_progress: Callable[[int], None] | None = None,
    ) -> tuple[str, int]:
        text = ""
        tokens = 0
        lines_done = 0
        last_emit = time.monotonic()

        for chunk in stream:
            delta = chunk["choices"][0]["delta"].get("content", "")
            if not delta:
                continue
            text += delta
            tokens += 1

            if on_line_progress:
                # Cada nuevo marcador "N:" que aparece indica que la linea
                # anterior quedo completa (la ultima linea vista puede seguir
                # generandose todavia, por eso el -1).
                matches = len(cls._LINE_MARKER.findall(text))
                new_lines_done = max(0, matches - 1)
                if new_lines_done > lines_done:
                    lines_done = new_lines_done
                    on_line_progress(lines_done)

            if on_stream and (time.monotonic() - last_emit) >= 0.4:
                on_stream(tokens, text)
                last_emit = time.monotonic()

        if on_stream:
            on_stream(tokens, text)

        return cls._strip_thinking(text), tokens

    @classmethod
    def _strip_thinking(cls, text: str) -> str:
        """
        Red de seguridad ademas de /no_think: si el modelo igual penso (o
        el bloque quedo sin cerrar porque se quedo sin contexto a mitad de
        pensar), esto se ejecuta SOLO sobre lo que se usa para parsear/
        devolver — lo que ya se le mostro en vivo a on_stream() no se toca,
        para no perder la visibilidad del razonamiento en el frontend.
        """
        text = cls._THINK_BLOCK_RE.sub("", text)
        idx = text.lower().find("<think>")
        if idx != -1:
            # <think> sin cerrar: se quedo pensando y nunca llego a
            # responder. Todo lo que sigue es razonamiento a medio
            # terminar, no hay nada real que parsear ahi.
            text = text[:idx]
        return text

    @staticmethod
    def _parse_block(raw: str, by_orig_id: dict[int, str]) -> list[dict]:
        pattern = re.compile(r"^\s*(\d+)\s*:\s*(.*)$")
        found: dict[int, str] = {}
        current_id: int | None = None
        current_lines: list[str] = []

        def flush():
            if current_id is not None:
                found[current_id] = "\n".join(current_lines).strip()

        for row in raw.splitlines():
            m = pattern.match(row)
            if m:
                flush()
                current_id = int(m.group(1))
                current_lines = [m.group(2)]
            elif current_id is not None:
                current_lines.append(row)
        flush()

        result = []
        for mid, orig_text in by_orig_id.items():
            text = found.get(mid, orig_text)
            result.append({"id": mid, "text": text})
        return result