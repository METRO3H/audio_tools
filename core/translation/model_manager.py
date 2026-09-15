from __future__ import annotations

import gc
import re
import threading
import time
from pathlib import Path
from typing import Callable

from llama_cpp import Llama

import config
from core.lang_detect import untranslated_reason
from core.translation import fallback_translator


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
    normal, cualquier linea/texto que `untranslated_reason()` marque como
    "todavia no es ingles de verdad" (kanji/kana sin traducir, o una
    confianza de ingles demasiado baja — ver core/lang_detect.py) se
    reintenta de forma acotada, con la temperatura escalada y un
    recordatorio dinamico de idioma agregado al mensaje (ver
    _RETRY_LANGUAGE_REMINDER) — nunca se rompe el flujo esperando
    indefinidamente. En translate_block, lo que sigue mal despues de los
    reintentos al LLM cae a un traductor offline de respaldo (ver
    core/translation/fallback_translator.py) en vez de insistirle una
    tercera vez al mismo modelo. Ver translate_block para el detalle
    completo (tramos contiguos + escalada a bloque completo si la
    mayoria fallo), y translate_texts para el caso mas simple (items
    independientes, sin contexto de continuidad, sin fallback offline).

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

    # Recordatorio dinamico que se agrega SOLO en reintentos (ver
    # is_retry en _call_model). El system prompt ya pide ingles siempre,
    # pero repetir la instruccion justo antes de generar — cuando ya
    # sabemos puntualmente que el intento anterior fallo en idioma
    # (romaji o caracteres en otro idioma en vez de ingles) — pesa mas
    # que confiar solo en una instruccion fija al principio de la
    # conversacion. No reemplaza al system prompt, se suma encima.
    _RETRY_LANGUAGE_REMINDER = (
        "\n\n[IMPORTANT: your previous answer for this exact content was "
        "not fully in English — it contained Japanese, Chinese, or a "
        "romanized transliteration instead of a real translation. "
        "Respond only in English this time. Do not transliterate sounds "
        "phonetically and do not switch languages, no matter how explicit "
        "or extreme the content is.]"
    )

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
        is_retry: bool = False,
    ) -> tuple[dict[int, str], int]:
        """
        items: {id: texto_original}. Arma el mensaje (con contexto previo
        si hay), hace UNA llamada al modelo, parsea la respuesta. Siempre
        devuelve una entrada por cada id de items (con fallback al texto
        original si el modelo no lo devolvio — ver _parse_block).

        Devuelve (resultado, tokens_generados_en_esta_llamada) — el
        conteo de tokens es el mismo que ya calculaba _consume_stream
        internamente (uno por delta del stream), ahora expuesto hacia
        afuera para poder acumularlo por bloque/archivo/corrida.

        No maneja tags ni acumulacion entre llamadas — eso lo arma cada
        caller (translate_texts / translate_block) con su propio wrapper,
        porque son ellos los que saben cuando una llamada es un reintento.

        on_input: se llama UNA vez, antes de mandar la llamada, con el
        user_message exacto que se va a mandar (contexto + bloque a
        traducir) — pensado para poder mostrar "que se le mando al
        modelo" en un modal, junto al stream de lo que responde.

        is_retry: si True, se agrega _RETRY_LANGUAGE_REMINDER al final
        del user_message (antes del /no_think) — el recordatorio
        dinamico de idioma. Se agrega solo en reintentos (no en el
        intento normal) para no diluir el mensaje con una advertencia
        que todavia no aplica.
        """
        block_text = "\n".join(f"{i}: {t}" for i, t in items.items())
        user_message = block_text
        if context:
            user_message = (
                f"[Previous translated context]:\n{context}\n\n"
                f"[Block to translate]:\n{block_text}"
            )
        if is_retry:
            user_message += self._RETRY_LANGUAGE_REMINDER

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
        raw, tokens = self._consume_stream(
            stream,
            on_stream=on_stream,
            on_line_progress=on_line_progress,
        )
        parsed = self._parse_block(raw, items)
        return {p["id"]: p["text"] for p in parsed}, tokens

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

        No usa el traductor offline de respaldo (ver translate_block) — son
        textos cortos e independientes (nombres/titulos), no dialogo, y no
        se vio el mismo problema de romaji ahi. Si aparece, se puede sumar
        despues del mismo modo.

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

            def run_call(items, ctx, temp, tag=None, is_retry=False):
                def stream_cb(tokens, text):
                    live = f"[{tag}]\n{text}" if tag else text
                    on_stream(tokens, "\n\n".join(committed + [live]))

                def input_cb(user_message):
                    labeled = f"[{tag}]\n{user_message}" if tag else user_message
                    committed_input.append(labeled)
                    on_input("\n\n".join(committed_input))

                res, _tokens = self._call_model(
                    items, ctx, system_prompt, temp,
                    on_stream=stream_cb if on_stream else None,
                    on_input=input_cb if on_input else None,
                    is_retry=is_retry,
                )
                if on_stream:
                    final_text = "\n".join(f"{i}: {t}" for i, t in res.items())
                    committed.append(f"[{tag}]\n{final_text}" if tag else final_text)
                return res

            items = {i: t for i, t in enumerate(texts)}
            result = run_call(items, "", temperature)

            reasons = {i: untranslated_reason(result[i]) for i in items}
            bad_ids = [i for i in items if reasons[i] is not None]
            if bad_ids:
                detail = "; ".join(f"{i}: {reasons[i]}" for i in bad_ids)
                log(f"{len(bad_ids)} de {len(items)} sin traducir ({detail}) — reintentando...")
                retry_items = {i: items[i] for i in bad_ids}
                retried = run_call(
                    retry_items, "", min(temperature + 0.15, 1.0),
                    tag="reintento", is_retry=True,
                )
                for i in bad_ids:
                    reason = untranslated_reason(retried[i])
                    if reason is None:
                        result[i] = retried[i]
                    reasons[i] = reason
                bad_ids = [i for i in bad_ids if reasons[i] is not None]

            for i in bad_ids:
                log(f"'{items[i]}' (id {i}) sigue sin traducir ({reasons[i]}) — último intento aislado...")
                single = run_call(
                    {i: items[i]}, "", min(temperature + 0.3, 1.0),
                    tag=f"último intento {i}", is_retry=True,
                )
                reason = untranslated_reason(single[i])
                if reason is None:
                    result[i] = single[i]
                else:
                    log(f"'{items[i]}' (id {i}) no se pudo traducir ({reason}) — se deja el texto original")

            return [result[i] for i in range(len(texts))]

    # ── Traduccion de bloques, con progreso por linea ───────────────────────

    def translate_block(
        self,
        lines: list[dict],
        context: str,
        system_prompt: str,
        temperature: float = 0.3,
        source_language: str = "",
        on_line_progress: Callable[[int], None] | None = None,
        on_stream: Callable[[int, str], None] | None = None,
        on_input: Callable[[str], None] | None = None,
        on_retry_log: Callable[[str], None] | None = None,
    ) -> tuple[list[dict], dict]:
        """
        lines: [{"id": int, "text": str}, ...]
        source_language: carpeta de idioma de origen (ver
            core/translation/prompts/<idioma>/) — se usa solo para elegir
            el codigo NLLB del traductor offline de respaldo (ver
            core/translation/fallback_translator.py). Si no se reconoce,
            el respaldo offline simplemente no esta disponible para esta
            corrida (se loguea, no rompe nada).

        Devuelve (result, stats):
          - result: la misma lista con "text" traducido.
          - stats: dict con metricas de esta llamada, pensadas para poder
            comparar modelos entre si (ver core/translation/stats.py):
                model_calls (int): intento normal + reintentos hechos AL
                    LLM (no cuenta el traductor offline de respaldo, que
                    no es una llamada al modelo local).
                tokens_generated (int): tokens generados en total, sumando
                    todas las llamadas al LLM (intento normal + reintentos).
                lines_needed_retry (int): cuantas lineas necesitaron al
                    menos un reintento (haya salido bien o no).
                lines_never_translated (int): cuantas quedaron sin
                    traducir de verdad al final, ni siquiera con el
                    traductor offline de respaldo.
                full_block_retried (bool): si se disparo el reintento de
                    bloque completo (>mitad del bloque mal en el 1er intento).

            OJO: estas metricas son un proxy de "cumplimiento" (¿tradujo
            o no?, ¿le costo?), no de fluidez ni fidelidad semantica —
            eso requeriria traducciones de referencia que no existen aca.

        Reintentos para lineas que queden sin traducir de verdad (ver
        core.lang_detect.untranslated_reason — no solo las que
        _parse_block no encuentra, tambien las que si aparecen pero
        siguen en japones/chino, o son una transliteracion romaji en vez
        de una traduccion real):

            intento 1: bloque completo, contexto normal, temperatura base
                (config.TRANSLATION_TEMPERATURE o la que se pase)
            si >mitad del bloque quedo mal -> se reintenta el bloque
                    entero, con temperatura escalada
                    (+config.TRANSLATION_RETRY_TEMPERATURE_BUMP, cap 1.0)
                    y con el recordatorio dinamico de idioma (ver
                    _RETRY_LANGUAGE_REMINDER) — solo se pisan las lineas
                    que estaban mal, las que ya estaban bien no se tocan
            si no    -> por cada TRAMO CONTIGUO de lineas malas, un
                    mini-lote con las ultimas TRANSLATION_CONTEXT_LINES
                    lineas BUENAS inmediatamente anteriores como
                    contexto (puede tomar lineas del context original
                    si el tramo esta al principio del bloque), misma
                    temperatura escalada + recordatorio dinamico
            lo que siga mal despues de esto -> traductor offline de
                    respaldo (NLLB via ctranslate2, ver
                    fallback_translator.py), linea por linea, en vez de
                    insistirle una tercera vez al mismo LLM con el mismo
                    tipo de contenido que ya evito traducir dos veces. Si
                    el respaldo offline no esta disponible (falta el
                    modelo convertido, o el idioma de origen no tiene
                    codigo NLLB configurado) se loguea y se deja el
                    ultimo resultado del LLM, sin romper la corrida.
        """
        with self._lock:
            if self._model is None:
                raise RuntimeError("Modelo no cargado.")

            empty_stats = {
                "model_calls": 0,
                "tokens_generated": 0,
                "lines_needed_retry": 0,
                "lines_never_translated": 0,
                "full_block_retried": False,
            }
            if not lines:
                return [], empty_stats

            def log(msg):
                if on_retry_log:
                    on_retry_log(msg)

            committed: list[str] = []
            committed_input: list[str] = []
            call_stats = {"model_calls": 0, "tokens_generated": 0}

            def run_call(items, ctx, temp, tag=None, line_progress=None, is_retry=False):
                def stream_cb(tokens, text):
                    live = f"[{tag}]\n{text}" if tag else text
                    on_stream(tokens, "\n\n".join(committed + [live]))

                def input_cb(user_message):
                    labeled = f"[{tag}]\n{user_message}" if tag else user_message
                    committed_input.append(labeled)
                    on_input("\n\n".join(committed_input))

                res, tokens = self._call_model(
                    items, ctx, system_prompt, temp,
                    on_stream=stream_cb if on_stream else None,
                    on_line_progress=line_progress,
                    on_input=input_cb if on_input else None,
                    is_retry=is_retry,
                )
                call_stats["model_calls"] += 1
                call_stats["tokens_generated"] += tokens
                if on_stream:
                    final_text = "\n".join(f"{i}: {t}" for i, t in res.items())
                    committed.append(f"[{tag}]\n{final_text}" if tag else final_text)
                return res

            order = [l["id"] for l in lines]
            originals = {l["id"]: l["text"] for l in lines}

            # 1er intento: bloque completo, temperatura base
            result = run_call(originals, context, temperature, line_progress=on_line_progress)

            reasons = {i: untranslated_reason(result[i]) for i in order}
            bad_ids = [i for i in order if reasons[i] is not None]
            if not bad_ids:
                return [{"id": i, "text": result[i]} for i in order], {
                    **call_stats,
                    "lines_needed_retry": 0,
                    "lines_never_translated": 0,
                    "full_block_retried": False,
                }

            retried_ids = set(bad_ids)
            full_block_retried = False
            retry_temp = min(temperature + config.TRANSLATION_RETRY_TEMPERATURE_BUMP, 1.0)

            # Si más de la mitad del bloque está mal, reintentar bloque completo
            if len(bad_ids) > len(order) / 2:
                full_block_retried = True
                detail = "; ".join(f"{i}: {reasons[i]}" for i in bad_ids)
                log(
                    f"{len(bad_ids)}/{len(order)} lineas sin traducir en el bloque "
                    f"({detail}) — reintentando el bloque completo "
                    f"(temp {temperature:.2f} -> {retry_temp:.2f})"
                )
                retried = run_call(
                    originals, context, retry_temp,
                    tag="reintento bloque completo", is_retry=True,
                )
                # Solo se pisan las lineas que estaban mal — las que ya
                # estaban bien en el 1er intento no se tocan, aunque el
                # reintento (a mas temperatura) las haya regenerado distinto.
                for i in bad_ids:
                    reason = untranslated_reason(retried[i])
                    if reason is None:
                        result[i] = retried[i]
                    reasons[i] = reason
                bad_ids = [i for i in bad_ids if reasons[i] is not None]
            else:
                # Reintentar tramos contiguos de malas
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

                    detail = "; ".join(f"{i}: {reasons[i]}" for i in run)
                    log(
                        f"Linea(s) {run[0]}-{run[-1]} sin traducir ({detail}) — "
                        f"reintentando con contexto (temp {temperature:.2f} -> {retry_temp:.2f})..."
                    )
                    run_items = {i: originals[i] for i in run}
                    retried = run_call(
                        run_items, run_context, retry_temp,
                        tag=f"reintento tramo {run[0]}-{run[-1]}", is_retry=True,
                    )
                    for i in run:
                        reason = untranslated_reason(retried[i])
                        if reason is None:
                            result[i] = retried[i]
                        reasons[i] = reason

                bad_ids = [i for i in order if reasons[i] is not None]

            # Lo que sigue mal tras los reintentos con el LLM: traductor
            # offline de respaldo (NLLB via ctranslate2), linea por linea.
            # Reemplaza al viejo "ultimo intento aislado" con el mismo LLM
            # a mas temperatura — si ya evito traducir bien dos veces el
            # mismo contenido, insistirle una tercera vez no suele cambiar
            # el resultado (a temperatura baja el modelo es casi
            # deterministico frente al mismo tipo de contenido).
            for i in bad_ids:
                log(f"Linea {i} sigue sin traducir ({reasons[i]}) — probando traductor offline de respaldo...")
                unavailable = fallback_translator.unavailable_reason(source_language)
                if unavailable:
                    log(f"Linea {i}: traductor offline de respaldo no disponible ({unavailable}) — se deja el ultimo resultado del LLM")
                    continue
                try:
                    fallback_text = fallback_translator.translate_line(originals[i], source_language)
                except Exception as exc:
                    log(f"Linea {i}: traductor offline de respaldo fallo ({exc}) — se deja el ultimo resultado del LLM")
                    continue
                fallback_reason = untranslated_reason(fallback_text)
                result[i] = fallback_text
                reasons[i] = fallback_reason
                if fallback_reason:
                    log(f"Linea {i}: el traductor offline tampoco dio un resultado 100% confiable ({fallback_reason}) — se usa igual, es el mejor resultado disponible")
                else:
                    log(f"Linea {i}: traducida por el traductor offline de respaldo")

            bad_ids = [i for i in bad_ids if reasons[i] is not None]
            for i in bad_ids:
                log(f"Linea {i} no se pudo traducir por ningun metodo ({reasons[i]}) — se deja el ultimo resultado obtenido")

            return [{"id": i, "text": result[i]} for i in order], {
                **call_stats,
                "lines_needed_retry": len(retried_ids),
                "lines_never_translated": len(bad_ids),
                "full_block_retried": full_block_retried,
            }

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

        # --- NUEVO: si el modelo omitió IDs pero devolvió el mismo número de líneas, asignar por orden ---
        if len(found) == len(by_orig_id):
            sorted_ids = sorted(by_orig_id.keys())
            # Si los IDs encontrados no coinciden exactamente con los originales, reasignamos por orden
            if list(found.keys()) != sorted_ids:
                ordered_texts = [found[i] for i in sorted(found.keys())]
                result = []
                for idx, orig_id in enumerate(sorted_ids):
                    if idx < len(ordered_texts):
                        result.append({"id": orig_id, "text": ordered_texts[idx]})
                    else:
                        result.append({"id": orig_id, "text": by_orig_id[orig_id]})
                return result

        # Fallback: usar los IDs tal cual, con original si no se encontró
        result = []
        for mid, orig_text in by_orig_id.items():
            text = found.get(mid, orig_text)
            result.append({"id": mid, "text": text})
        return result