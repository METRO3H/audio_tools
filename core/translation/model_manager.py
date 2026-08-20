from __future__ import annotations

import gc
import re
import threading
import time
from pathlib import Path
from typing import Callable

from llama_cpp import Llama

import config
from core.lang_detect import looks_untranslated


class ModelManager:
    """
    Envoltorio sobre llama-cpp-python. Carga un modelo GGUF en el propio
    proceso (sin server) y expone generacion de texto simple y traduccion
    de bloques de subtitulos.

    Usa stream=True internamente: no para cortar la generacion con un
    timeout (llama.cpp no soporta timeouts nativos por llamada), sino
    para poder emitir progreso en vivo mientras la llamada esta en curso,
    sin interrumpir nada. Tres usos del streaming:

      - generate_text (work_info / titulo): on_stream(tokens, texto_acumulado)
        entrega el texto COMPLETO generado hasta el momento, pensado para
        alimentar un textarea que se va llenando en vivo.

      - translate_texts / translate_block: on_stream igual que arriba —
        el intento normal se manda sin prefijo (para no romper la vista
        actual), cualquier reintento se manda con un tag ("[reintento
        tramo 111-113]") para poder distinguirlo en un log.

      - translate_block ademas expone on_line_progress(n): cuantas lineas
        del bloque ("N: texto") ya se ven completas en el stream (se
        detecta una linea como completa cuando aparece el marcador de la
        SIGUIENTE linea). Solo se usa en el intento normal — los
        reintentos operan sobre subconjuntos chicos y no deberian mover
        la barra de progreso del bloque completo.

    Reintentos (translate_texts y translate_block): despues del intento
    normal, cualquier linea/texto que `looks_untranslated()` marque como
    "todavia en el idioma original" se reintenta de forma acotada — nunca
    se rompe el flujo esperando indefinidamente. Ver translate_block para
    el detalle (tramos contiguos + escalada a bloque completo si la
    mayoria fallo), y translate_texts para el caso mas simple (items
    independientes, sin contexto de continuidad).

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

    # ── Helper compartido: una sola llamada al modelo + parseo ─────────────

    def _call_model(
        self,
        items: dict[int, str],
        context: str,
        system_prompt: str,
        temperature: float,
        on_stream: Callable[[int, str], None] | None = None,
        on_line_progress: Callable[[int], None] | None = None,
        on_input: Callable[[str], None] | None = None,
    ) -> dict[int, str]:
        """
        items: {id: texto_original}. Arma el mensaje (con contexto previo
        si hay), hace UNA llamada al modelo, parsea la respuesta. Siempre
        devuelve una entrada por cada id de items (con fallback al texto
        original si el modelo no lo devolvio — ver _parse_block).

        No maneja tags ni acumulacion entre llamadas — eso lo arma cada
        caller (translate_texts / translate_block) con su propio wrapper,
        porque son ellos los que saben cuando una llamada es un reintento.

        on_input: se llama UNA vez, antes de mandar la llamada, con el
        user_message exacto que se va a mandar (contexto + bloque a
        traducir) — pensado para poder mostrar "que se le mando al
        modelo" en un modal, junto al stream de lo que responde.
        """
        block_text = "\n".join(f"{i}: {t}" for i, t in items.items())
        user_message = block_text
        if context:
            user_message = (
                f"[Previous translated context]:\n{context}\n\n"
                f"[Block to translate]:\n{block_text}"
            )

        if on_input:
            on_input(user_message)

        stream = self._model.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message + self._NO_THINK_SUFFIX},
            ],
            temperature=temperature,
            max_tokens=-1,
            stream=True,
        )
        raw, _ = self._consume_stream(
            stream,
            on_stream=on_stream,
            on_line_progress=on_line_progress,
        )
        parsed = self._parse_block(raw, items)
        return {p["id"]: p["text"] for p in parsed}

    # ── Traduccion de textos cortos e independientes (chapters/filenames) ──

    def translate_texts(
        self,
        texts: list[str],
        system_prompt: str,
        temperature: float = 0.3,
        on_stream: Callable[[int, str], None] | None = None,
        on_input: Callable[[str], None] | None = None,
        on_retry_log: Callable[[str], None] | None = None,
    ) -> list[str]:
        """
        Traduce una lista de textos cortos e independientes entre si (nombres
        de archivo, titulos de capitulo, etc.) — a diferencia de
        translate_block, no hay contexto de continuidad entre ellos (no son
        lineas consecutivas de un dialogo), asi que el reintento es directo:
        se juntan todos los que fallaron en un solo mini-lote (no hace falta
        que sean contiguos, el orden no importa aca), mismo prompt, sin
        contexto extra. Si alguno sigue mal, ultimo recurso aislado.

        on_stream recibe, en cada emision, el historial COMPLETO de esta
        llamada — intento normal + cualquier reintento, cada uno separado
        y tagueado — no solo lo que esta generando la sub-llamada actual.
        Asi un modal que escuche esto puede mostrar todo lo que paso, sin
        que un reintento pise lo que ya se vio del intento anterior.
        on_input: mismo mecanismo pero para lo que se MANDA al modelo (no
        lo que responde) — util para un tab de "input" al lado del de
        "output" en ese mismo modal.
        """
        with self._lock:
            if self._model is None:
                raise RuntimeError("Modelo no cargado.")
            if not texts:
                return []

            def log(msg):
                if on_retry_log:
                    on_retry_log(msg)

            committed: list[str] = []
            committed_input: list[str] = []

            def run_call(items, ctx, temp, tag=None):
                def stream_cb(tokens, text):
                    live = f"[{tag}]\n{text}" if tag else text
                    on_stream(tokens, "\n\n".join(committed + [live]))

                def input_cb(user_message):
                    labeled = f"[{tag}]\n{user_message}" if tag else user_message
                    committed_input.append(labeled)
                    on_input("\n\n".join(committed_input))

                res = self._call_model(
                    items, ctx, system_prompt, temp,
                    on_stream=stream_cb if on_stream else None,
                    on_input=input_cb if on_input else None,
                )
                if on_stream:
                    final_text = "\n".join(f"{i}: {t}" for i, t in res.items())
                    committed.append(f"[{tag}]\n{final_text}" if tag else final_text)
                return res

            items = {i: t for i, t in enumerate(texts)}
            result = run_call(items, "", temperature)

            bad_ids = [i for i in items if looks_untranslated(result[i])]
            if bad_ids:
                log(f"{len(bad_ids)} de {len(items)} sin traducir — reintentando...")
                retry_items = {i: items[i] for i in bad_ids}
                retried = run_call(retry_items, "", min(temperature + 0.15, 1.0), tag="reintento")
                for i in bad_ids:
                    if not looks_untranslated(retried[i]):
                        result[i] = retried[i]
                bad_ids = [i for i in bad_ids if looks_untranslated(result[i])]

            for i in bad_ids:
                log(f"'{items[i]}' (id {i}) sigue sin traducir — último intento aislado...")
                single = run_call({i: items[i]}, "", min(temperature + 0.3, 1.0), tag=f"último intento {i}")
                if not looks_untranslated(single[i]):
                    result[i] = single[i]
                else:
                    log(f"'{items[i]}' (id {i}) no se pudo traducir — se deja el texto original")

            return [result[i] for i in range(len(texts))]

    # ── Traduccion de bloques, con progreso por linea ───────────────────────

    def translate_block(
        self,
        lines: list[dict],
        context: str,
        system_prompt: str,
        temperature: float = 0.3,
        on_line_progress: Callable[[int], None] | None = None,
        on_stream: Callable[[int, str], None] | None = None,
        on_input: Callable[[str], None] | None = None,
        on_retry_log: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """
        lines: [{"id": int, "text": str}, ...]
        Devuelve la misma lista con "text" traducido.

        Reintentos acotados para lineas que queden sin traducir de verdad
        (ver core.lang_detect.looks_untranslated — no solo las que
        _parse_block no encuentra, tambien las que si aparecen pero
        siguen en japones/chino, o romanizadas):

            intento 1: bloque completo, contexto normal (como siempre)
            si >mitad del bloque quedo mal -> se reintenta el bloque
                     entero (con nota de que es un reintento)
            si no    -> por cada TRAMO CONTIGUO de lineas malas, un
                     mini-lote con las ultimas TRANSLATION_CONTEXT_LINES
                     lineas BUENAS inmediatamente anteriores como
                     contexto (puede tomar lineas del context original
                     si el tramo esta al principio del bloque) — las
                     lineas buenas que ya estaban bien no se retocan
            si una linea individual sigue mal despues de eso -> ultimo
                     recurso: prompt aislado, sin contexto, sin formato
                     de lote, temperatura mas alta

        on_stream recibe, en cada emision, el historial COMPLETO de este
        bloque — intento normal + cualquier reintento, cada uno separado
        y tagueado ("[reintento tramo 111-113]") — no solo la sub-llamada
        actual, para que un modal pueda mostrar todo sin que un reintento
        pise lo que ya se vio antes.
        on_input: mismo mecanismo pero para lo que se MANDA al modelo (no
        lo que responde) — util para un tab de "input" al lado del de
        "output" en ese mismo modal.
        on_retry_log: mensajes cortos de que se esta reintentando, para
        mandarlos al log general del archivo.
        """
        with self._lock:
            if self._model is None:
                raise RuntimeError("Modelo no cargado.")
            if not lines:
                return []

            def log(msg):
                if on_retry_log:
                    on_retry_log(msg)

            committed: list[str] = []
            committed_input: list[str] = []

            def run_call(items, ctx, temp, tag=None, line_progress=None):
                def stream_cb(tokens, text):
                    live = f"[{tag}]\n{text}" if tag else text
                    on_stream(tokens, "\n\n".join(committed + [live]))

                def input_cb(user_message):
                    labeled = f"[{tag}]\n{user_message}" if tag else user_message
                    committed_input.append(labeled)
                    on_input("\n\n".join(committed_input))

                res = self._call_model(
                    items, ctx, system_prompt, temp,
                    on_stream=stream_cb if on_stream else None,
                    on_line_progress=line_progress,
                    on_input=input_cb if on_input else None,
                )
                if on_stream:
                    final_text = "\n".join(f"{i}: {t}" for i, t in res.items())
                    committed.append(f"[{tag}]\n{final_text}" if tag else final_text)
                return res

            order = [l["id"] for l in lines]
            originals = {l["id"]: l["text"] for l in lines}

            result = run_call(originals, context, temperature, line_progress=on_line_progress)

            bad_ids = [i for i in order if looks_untranslated(result[i])]
            if not bad_ids:
                return [{"id": i, "text": result[i]} for i in order]

            if len(bad_ids) > len(order) / 2:
                log(f"{len(bad_ids)}/{len(order)} lineas sin traducir en el bloque — reintentando el bloque completo")
                retried = run_call(originals, context, min(temperature + 0.15, 1.0), tag="reintento bloque completo")
                for i in order:
                    if not looks_untranslated(retried[i]):
                        result[i] = retried[i]
                bad_ids = [i for i in order if looks_untranslated(result[i])]
            else:
                bad_set = set(bad_ids)
                runs: list[list[int]] = []
                current: list[int] = []
                for i in order:
                    if i in bad_set:
                        current.append(i)
                    elif current:
                        runs.append(current)
                        current = []
                if current:
                    runs.append(current)

                context_lines = context.strip().splitlines() if context else []

                for run in runs:
                    start_pos = order.index(run[0])
                    good_before = [
                        f"{i}: {result[i]}" for i in order[:start_pos] if i not in bad_set
                    ]
                    run_context = "\n".join(
                        (context_lines + good_before)[-config.TRANSLATION_CONTEXT_LINES:]
                    )

                    log(f"Linea(s) {run[0]}-{run[-1]} sin traducir — reintentando con contexto...")
                    run_items = {i: originals[i] for i in run}
                    retried = run_call(
                        run_items, run_context, temperature,
                        tag=f"reintento tramo {run[0]}-{run[-1]}",
                    )
                    for i in run:
                        if not looks_untranslated(retried[i]):
                            result[i] = retried[i]

                bad_ids = [i for i in order if looks_untranslated(result[i])]

            for i in bad_ids:
                log(f"Linea {i} sigue sin traducir — último intento aislado...")
                single = run_call(
                    {i: originals[i]}, "", min(temperature + 0.3, 1.0),
                    tag=f"último intento línea {i}",
                )
                if not looks_untranslated(single[i]):
                    result[i] = single[i]
                else:
                    log(f"Linea {i} no se pudo traducir después de varios intentos — se deja el texto original")

            return [{"id": i, "text": result[i]} for i in order]

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
