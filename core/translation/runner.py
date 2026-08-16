from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import config
from core.translation.model_manager import ModelManager
from core.translation import prompts
from core.translation.prompts import build_system_prompt
from core.translation.srt import parse_srt, write_srt


class TranslateRunner:
    """
    Pipeline de traduccion sobre archivos .srt, con el modelo cargado en
    el propio proceso (sin server, sin cliente remoto).

    Orden del pipeline (una sola vez por cola, no por archivo):
        1. work_info   (si hay raw_publisher_info)
        2. titulo      (usa work_info como contexto adicional, si hay raw_title)
        3. system prompt final = build_system_prompt(base_prompt, titulo, work_info)
        4. cada archivo se traduce en bloques de TRANSLATION_BLOCK_SIZE lineas,
           pasando como contexto las ultimas TRANSLATION_CONTEXT_LINES lineas
           ya traducidas del bloque anterior.

    on_step(step_key, status): checklist de fases de alto nivel.
        step_key en {"work_info", "title", "blocks"}
        status   en {"active", "done", "skipped"}

    on_work_info_stream(text) / on_title_stream(text): texto COMPLETO
    acumulado en vivo mientras el modelo genera work_info/titulo (para
    un textarea que se va llenando).

    on_lines_progress(file_index, lines_done_file, lines_total_file,
                       lines_done_global, lines_total_global): progreso
    por lineas durante la fase de bloques, tanto del archivo actual como
    acumulado de toda la cola. Las lineas totales se pre-calculan antes
    de arrancar a traducir, parseando todos los .srt de la cola.

    on_file_start(idx, total, name, started_at): started_at es un
    timestamp epoch (time.time()) tomado justo antes de arrancar ESE
    archivo — no incluye la carga del modelo ni work_info/titulo, que
    corren una sola vez antes del loop.

    on_file_done(idx, success, elapsed): elapsed en segundos, medido
    desde el started_at de ese mismo archivo.
    """

    def __init__(self) -> None:
        self._manager = ModelManager()
        self._cancelled = False

    # ── API publica ──────────────────────────────────────────────────────

    def list_models(self) -> list[str]:
        return self._manager.list_models()

    def unload(self) -> None:
        self._manager.unload()

    def cancel(self) -> None:
        self._cancelled = True

    def run_queue(
        self,
        files: list[tuple[Path, Path]],
        raw_title: str = "",
        raw_publisher_info: str = "",
        base_prompt: str = "",
        model: str = "",
        n_gpu_layers: int | None = None,
        n_ctx: int | None = None,
        temperature: float | None = None,
        on_log: Callable[[str], None] | None = None,
        on_phase: Callable[[str], None] | None = None,
        on_step: Callable[[str, str], None] | None = None,
        on_title: Callable[[str], None] | None = None,
        on_work_info: Callable[[str], None] | None = None,
        on_work_info_stream: Callable[[str], None] | None = None,
        on_title_stream: Callable[[str], None] | None = None,
        on_lines_progress: Callable[[int, int, int, int, int], None] | None = None,
        on_file_start: Callable[[int, int, str, float], None] | None = None,
        on_file_done: Callable[[int, bool, float], None] | None = None,
        on_queue_progress: Callable[[int, int], None] | None = None,
        on_queue_done: Callable[[int, int], None] | None = None,
    ) -> None:
        self._cancelled = False
        threading.Thread(
            target=self._queue_worker,
            args=(
                files, raw_title, raw_publisher_info, base_prompt,
                model, n_gpu_layers, n_ctx, temperature,
                on_log, on_phase, on_step, on_title, on_work_info,
                on_work_info_stream, on_title_stream, on_lines_progress,
                on_file_start, on_file_done, on_queue_progress, on_queue_done,
            ),
            daemon=True,
        ).start()

    # ── Pipeline ─────────────────────────────────────────────────────────

    def _queue_worker(
        self,
        files, raw_title, raw_publisher_info, base_prompt,
        model, n_gpu_layers, n_ctx, temperature,
        on_log, on_phase, on_step, on_title, on_work_info,
        on_work_info_stream, on_title_stream, on_lines_progress,
        on_file_start, on_file_done, on_queue_progress, on_queue_done,
    ):
        def log(msg):
            if on_log:
                on_log(msg)

        def phase(msg):
            if on_phase:
                on_phase(msg)

        def step(key, status):
            if on_step:
                on_step(key, status)

        n_gpu_layers = n_gpu_layers if n_gpu_layers is not None else config.TRANSLATION_N_GPU_LAYERS
        n_ctx        = n_ctx        if n_ctx        is not None else config.TRANSLATION_N_CTX
        temp         = temperature  if temperature  is not None else config.TRANSLATION_TEMPERATURE
        total_files  = len(files)

        try:
            # 0 ── Setup: carga de modelo
            phase("Cargando modelo...")
            log(f"Cargando modelo {model}...")
            self._manager.load(model, n_gpu_layers, n_ctx)
            if self._cancelled:
                if on_queue_done: on_queue_done(0, total_files)
                return

            # 0.5 ── Pre-escaneo: cuantas lineas tiene cada archivo, para
            # poder calcular progreso global/por-archivo antes de traducir.
            file_line_counts = []
            for input_srt, _ in files:
                try:
                    file_line_counts.append(len(parse_srt(input_srt)))
                except Exception:
                    file_line_counts.append(0)
            lines_total_global = sum(file_line_counts)

            # 1 ── Work info primero (memoria persistente para todo el archivo)
            work_info = ""
            if raw_publisher_info.strip():
                step("work_info", "active")
                phase("Generando work info...")
                log("Generando work info del publisher...")
                work_info = self._manager.generate_text(
                    prompts.get_system_prompt("srt", "work_info_extraction"), raw_publisher_info.strip(),
                    temperature=temp,
                    on_stream=(lambda tokens, text: on_work_info_stream(text)) if on_work_info_stream else None,
                )
                log(f"Work info generado:\n{work_info}")
                if on_work_info: on_work_info(work_info)
                step("work_info", "done")
            else:
                step("work_info", "skipped")

            if self._cancelled:
                if on_queue_done: on_queue_done(0, total_files)
                return

            # 2 ── Titulo (usando work_info como contexto, si existe)
            title = ""
            if raw_title.strip():
                step("title", "active")
                phase("Traduciendo titulo...")
                log("Traduciendo titulo...")
                user_msg = raw_title.strip()
                if work_info:
                    user_msg = (
                        f"[Work info for context]:\n{work_info}\n\n"
                        f"[Title to translate]:\n{raw_title.strip()}"
                    )
                title = self._manager.generate_text(
                    prompts.get_system_prompt("srt", "title_translation"), user_msg,
                    temperature=temp,
                    on_stream=(lambda tokens, text: on_title_stream(text)) if on_title_stream else None,
                )
                log(f"Titulo: {title}")
                if on_title: on_title(title)
                step("title", "done")
            else:
                step("title", "skipped")

            if self._cancelled:
                if on_queue_done: on_queue_done(0, total_files)
                return

            # 3 ── Prompt de sistema final, armado una sola vez para toda la cola
            system_prompt = build_system_prompt(base_prompt, title, work_info)

            # 4 ── Cola de archivos
            step("blocks", "active")
            succeeded = 0
            lines_done_global_base = 0  # lineas de archivos ya terminados

            for idx, (input_srt, output_srt) in enumerate(files):
                if self._cancelled:
                    break

                name = input_srt.name
                lines_total_file = file_line_counts[idx]
                log(f"\n-- Archivo {idx + 1}/{total_files}: {name}")
                file_started_at = time.time()
                if on_file_start: on_file_start(idx, total_files, name, file_started_at)

                try:
                    entries = parse_srt(input_srt)
                    payload = [{"id": e.index, "text": "\n".join(e.lines)} for e in entries]
                    blocks = [
                        payload[i:i + config.TRANSLATION_BLOCK_SIZE]
                        for i in range(0, len(payload), config.TRANSLATION_BLOCK_SIZE)
                    ]
                    n_blocks = len(blocks)
                    log(f"{len(entries)} entradas -> {n_blocks} bloques")

                    context = ""
                    all_translated = []
                    lines_done_in_file_base = 0  # lineas de bloques ya terminados en este archivo

                    for b_idx, block in enumerate(blocks):
                        if self._cancelled:
                            break
                        phase(f"Traduciendo bloque {b_idx + 1}/{n_blocks}...")
                        log(f"  Bloque {b_idx + 1}/{n_blocks}...")

                        # closure fresca por bloque, para que el offset base sea el correcto
                        lines_done_in_file_base_snapshot = lines_done_in_file_base

                        def on_line_progress(n, _base=lines_done_in_file_base_snapshot):
                            if not on_lines_progress:
                                return
                            file_done = min(_base + n, lines_total_file)
                            global_done = min(lines_done_global_base + file_done, lines_total_global)
                            on_lines_progress(idx, file_done, lines_total_file, global_done, lines_total_global)

                        translated = self._manager.translate_block(
                            block, context, system_prompt,
                            temperature=temp, on_line_progress=on_line_progress,
                        )
                        all_translated.extend(translated)

                        translated_text = "\n".join(
                            f"  [{l['id']}] {l['text']}" for l in translated
                        )
                        log(f"  Bloque {b_idx + 1}/{n_blocks} traducido:\n{translated_text}")

                        lines_done_in_file_base += len(block)
                        if on_lines_progress:
                            file_done = min(lines_done_in_file_base, lines_total_file)
                            global_done = min(lines_done_global_base + file_done, lines_total_global)
                            on_lines_progress(idx, file_done, lines_total_file, global_done, lines_total_global)

                        last = translated[-config.TRANSLATION_CONTEXT_LINES:]
                        context = "\n".join(f"{l['id']}: {l['text']}" for l in last)

                    if self._cancelled:
                        if on_file_done: on_file_done(idx, False, time.time() - file_started_at)
                        break

                    by_id = {t["id"]: t["text"] for t in all_translated}
                    for entry in entries:
                        if entry.index in by_id:
                            entry.lines = by_id[entry.index].splitlines() or entry.lines

                    output_srt.parent.mkdir(parents=True, exist_ok=True)
                    write_srt(output_srt, entries)
                    log(f"Guardado: {output_srt}")
                    succeeded += 1
                    if on_file_done: on_file_done(idx, True, time.time() - file_started_at)

                except Exception as exc:
                    log(f"[error] {name}: {exc}")
                    if on_file_done: on_file_done(idx, False, time.time() - file_started_at)

                lines_done_global_base += lines_total_file
                if on_queue_progress: on_queue_progress(idx + 1, total_files)

            if self._cancelled:
                step("blocks", "skipped")  # el frontend lo reinterpreta como "cancelado" si estaba activo
            else:
                step("blocks", "done")

            if on_queue_done: on_queue_done(succeeded, total_files)

        except Exception as exc:
            log(f"[error fatal] {exc}")
            if on_queue_done: on_queue_done(0, total_files)