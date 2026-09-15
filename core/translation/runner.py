from __future__ import annotations

import dataclasses
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import config
from core.hardware_info import get_vram_snapshot
from core.translation.model_manager import ModelManager
from core.translation import prompts
from core.translation import stats_db
from core.translation.prompts import build_system_prompt
from core.translation.srt import parse_srt, write_srt
from core.translation.stats import FileStats, RunStats


def _now_iso() -> str:
    """Timestamp UTC en ISO 8601, con precision de segundos."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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

    on_block_stream(file_index, text): texto crudo acumulado en vivo de
    CADA llamada al modelo durante la fase de bloques — el intento
    normal y cualquier reintento (ver translate_block en model_manager).
    Se acumula del lado del frontend por archivo, para poder abrir un
    modal con "que hizo el modelo para este archivo puntual".

    on_stats(run_id, stats): se llama UNA vez, al final de la cola (haya
    terminado bien, cancelada, o con error fatal) — incluso una corrida
    cancelada a mitad de camino se guarda, es un dato util para comparar
    modelos. run_id es el id de la fila insertada en la base de
    estadisticas (None si no se pudo guardar). stats es un dict con el
    detalle completo de la corrida, incluyendo un detalle por archivo
    (ver core/translation/stats.py:RunStats).
    """

    def __init__(self) -> None:
        self._manager = ModelManager()
        self._cancelled = False
        self._was_cancelled = False  # Indica si la cola fue cancelada

    # — API publica —

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
        glossary: str = "",
        model: str = "",
        n_gpu_layers: int | None = None,
        n_ctx: int | None = None,
        temperature: float | None = None,
        source_language: str = "",
        output_subfolder: str = "",
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
        on_queue_done: Callable[[int, int, bool], None] | None = None,  # MODIFICADO: añadir cancelled
        on_block_stream: Callable[[int, str], None] | None = None,
        on_block_input: Callable[[int, str], None] | None = None,
        on_system_prompt: Callable[[str], None] | None = None,
        on_stats: Callable[[int | None, dict], None] | None = None,
    ) -> None:
        self._cancelled = False
        self._was_cancelled = False
        threading.Thread(
            target=self._queue_worker,
            args=(
                files, raw_title, raw_publisher_info, base_prompt, glossary,
                model, n_gpu_layers, n_ctx, temperature,
                source_language, output_subfolder,
                on_log, on_phase, on_step, on_title, on_work_info,
                on_work_info_stream, on_title_stream, on_lines_progress,
                on_file_start, on_file_done, on_queue_progress, on_queue_done,
                on_block_stream, on_block_input, on_system_prompt, on_stats,
            ),
            daemon=True,
        ).start()

    # — Pipeline —

    def _queue_worker(
        self,
        files, raw_title, raw_publisher_info, base_prompt, glossary,
        model, n_gpu_layers, n_ctx, temperature,
        source_language, output_subfolder,
        on_log, on_phase, on_step, on_title, on_work_info,
        on_work_info_stream, on_title_stream, on_lines_progress,
        on_file_start, on_file_done, on_queue_progress, on_queue_done,
        on_block_stream, on_block_input, on_system_prompt, on_stats,
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

        # Se inicializan aca (no mas abajo) para que esten definidas en el
        # `finally` del final incluso si algo revienta antes de llegar a
        # esa parte del pipeline (ej. si self._manager.load() falla).
        succeeded = 0
        lines_total_global = 0
        translation_started_at = None

        run_stats = RunStats(
            started_at=_now_iso(),
            model=model,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            temperature=temp,
            source_language=source_language,
            output_subfolder=output_subfolder,
            total_files=total_files,
        )

        try:
            # 0 — Setup: carga de modelo
            phase("Cargando modelo...")
            log(f"Cargando modelo {model}...")
            load_started_at = time.time()
            self._manager.load(model, n_gpu_layers, n_ctx)
            run_stats.model_load_seconds = time.time() - load_started_at

            vram = get_vram_snapshot()
            if vram:
                run_stats.gpu_vendor = vram.vendor
                run_stats.gpu_name = vram.name
                run_stats.vram_used_mb = vram.used_mb
                run_stats.vram_total_mb = vram.total_mb
                run_stats.vram_measurement_method = vram.method

            translation_started_at = time.time()

            if self._cancelled:
                self._was_cancelled = True
                if on_queue_done:
                    on_queue_done(0, total_files, True)
                return

            # 0.5 — Pre-escaneo: cuantas lineas tiene cada archivo
            file_line_counts = []
            for input_srt, _ in files:
                try:
                    file_line_counts.append(len(parse_srt(input_srt)))
                except Exception:
                    file_line_counts.append(0)
            lines_total_global = sum(file_line_counts)

            # 1 — Work info
            work_info = ""
            if raw_publisher_info.strip():
                step("work_info", "active")
                phase("Generando work info...")
                log("Generando work info del publisher...")
                work_info = self._manager.generate_text(
                    prompts.get_shared_prompt("work_info_extraction"), raw_publisher_info.strip(),
                    temperature=temp,
                    on_stream=(lambda tokens, text: on_work_info_stream(text)) if on_work_info_stream else None,
                )
                log(f"Work info generado:\n{work_info}")
                if on_work_info:
                    on_work_info(work_info)
                step("work_info", "done")
            else:
                step("work_info", "skipped")

            if self._cancelled:
                self._was_cancelled = True
                if on_queue_done:
                    on_queue_done(0, total_files, True)
                return

            # 2 — Titulo
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
                    prompts.get_shared_prompt("title_translation"), user_msg,
                    temperature=temp,
                    on_stream=(lambda tokens, text: on_title_stream(text)) if on_title_stream else None,
                )
                log(f"Titulo: {title}")
                if on_title:
                    on_title(title)
                step("title", "done")
            else:
                step("title", "skipped")

            if self._cancelled:
                self._was_cancelled = True
                if on_queue_done:
                    on_queue_done(0, total_files, True)
                return

            # 3 — Prompt de sistema final
            system_prompt = build_system_prompt(base_prompt, glossary, title, work_info)

            # Emitir system prompt para el frontend
            if on_system_prompt:
                on_system_prompt(system_prompt)

            # 4 — Cola de archivos
            step("blocks", "active")
            lines_done_global_base = 0

            for idx, (input_srt, output_srt) in enumerate(files):
                if self._cancelled:
                    self._was_cancelled = True
                    break

                name = input_srt.name
                lines_total_file = file_line_counts[idx]
                log(f"\n-- Archivo {idx + 1}/{total_files}: {name}")
                file_started_at = time.time()
                if on_file_start:
                    on_file_start(idx, total_files, name, file_started_at)

                file_stats = FileStats(
                    file_name=name,
                    success=False,
                    lines_total=lines_total_file,
                    blocks_total=0,
                    elapsed_seconds=0.0,
                )

                try:
                    entries = parse_srt(input_srt)
                    payload = [{"id": e.index, "text": "\n".join(e.lines)} for e in entries]
                    blocks = [
                        payload[i:i + config.TRANSLATION_BLOCK_SIZE]
                        for i in range(0, len(payload), config.TRANSLATION_BLOCK_SIZE)
                    ]
                    n_blocks = len(blocks)
                    file_stats.blocks_total = n_blocks
                    log(f"{len(entries)} entradas -> {n_blocks} bloques")

                    context = ""
                    all_translated = []
                    lines_done_in_file_base = 0
                    block_history_text = ""
                    block_history_input = ""

                    for b_idx, block in enumerate(blocks):
                        if self._cancelled:
                            self._was_cancelled = True
                            break
                        phase(f"Traduciendo bloque {b_idx + 1}/{n_blocks}...")
                        log(f"  Bloque {b_idx + 1}/{n_blocks}...")

                        lines_done_in_file_base_snapshot = lines_done_in_file_base

                        def on_line_progress(n, _base=lines_done_in_file_base_snapshot):
                            if not on_lines_progress:
                                return
                            file_done = min(_base + n, lines_total_file)
                            global_done = min(lines_done_global_base + file_done, lines_total_global)
                            on_lines_progress(idx, file_done, lines_total_file, global_done, lines_total_global)

                        block_trace_box = [""]
                        block_input_box = [""]
                        block_header = f"═══ Bloque {b_idx + 1}/{n_blocks} ═══"
                        output_hist_snapshot = block_history_text
                        input_hist_snapshot = block_history_input

                        def on_block_text(tokens, text, _idx=idx, _header=block_header, _hist=output_hist_snapshot):
                            block_trace_box[0] = text
                            if on_block_stream:
                                live = f"{_header}\n{text}"
                                on_block_stream(_idx, (_hist + "\n\n" if _hist else "") + live)

                        def on_block_input_text(text, _idx=idx, _header=block_header, _hist=input_hist_snapshot):
                            block_input_box[0] = text
                            if on_block_input:
                                live = f"{_header}\n{text}"
                                on_block_input(_idx, (_hist + "\n\n" if _hist else "") + live)

                        translated, block_stats = self._manager.translate_block(
                            block, context, system_prompt,
                            temperature=temp, source_language=source_language,   # <- agregar este parametro
                            on_line_progress=on_line_progress,
                            on_stream=on_block_text, on_input=on_block_input_text, on_retry_log=log,
                        )
                        all_translated.extend(translated)

                        file_stats.tokens_generated += block_stats["tokens_generated"]
                        file_stats.model_calls += block_stats["model_calls"]
                        file_stats.lines_needed_retry += block_stats["lines_needed_retry"]
                        file_stats.lines_never_translated += block_stats["lines_never_translated"]
                        if block_stats["full_block_retried"]:
                            file_stats.blocks_full_retried += 1

                        block_history_text = (
                            (block_history_text + "\n\n" if block_history_text else "") +
                            f"{block_header}\n{block_trace_box[0]}"
                        )
                        block_history_input = (
                            (block_history_input + "\n\n" if block_history_input else "") +
                            f"{block_header}\n{block_input_box[0]}"
                        )

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
                        file_stats.elapsed_seconds = time.time() - file_started_at
                        run_stats.files.append(file_stats)
                        if on_file_done:
                            on_file_done(idx, False, time.time() - file_started_at)
                        break

                    by_id = {t["id"]: t["text"] for t in all_translated}
                    for entry in entries:
                        if entry.index in by_id:
                            entry.lines = by_id[entry.index].splitlines() or entry.lines

                    output_srt.parent.mkdir(parents=True, exist_ok=True)
                    write_srt(output_srt, entries)
                    log(f"Guardado: {output_srt}")
                    succeeded += 1
                    file_stats.success = True
                    file_stats.elapsed_seconds = time.time() - file_started_at
                    run_stats.files.append(file_stats)
                    if on_file_done:
                        on_file_done(idx, True, time.time() - file_started_at)

                except Exception as exc:
                    log(f"[error] {name}: {exc}")
                    file_stats.elapsed_seconds = time.time() - file_started_at
                    run_stats.files.append(file_stats)
                    if on_file_done:
                        on_file_done(idx, False, time.time() - file_started_at)

                lines_done_global_base += lines_total_file
                if on_queue_progress:
                    on_queue_progress(idx + 1, total_files)

            if self._cancelled:
                step("blocks", "skipped")
                self._was_cancelled = True
            else:
                step("blocks", "done")

            if on_queue_done:
                on_queue_done(succeeded, total_files, self._was_cancelled)

        except Exception as exc:
            log(f"[error fatal] {exc}")
            if on_queue_done:
                on_queue_done(0, total_files, self._was_cancelled)

        finally:
            # Se guarda pase lo que pase (cola completa, cancelada, o con
            # error fatal) — incluso una corrida cancelada a mitad de
            # camino es un dato util para comparar modelos.
            run_stats.finished_at = _now_iso()
            run_stats.cancelled = self._was_cancelled
            run_stats.succeeded_files = succeeded
            run_stats.total_lines = lines_total_global
            run_stats.total_blocks = sum(f.blocks_total for f in run_stats.files)
            run_stats.total_tokens_generated = sum(f.tokens_generated for f in run_stats.files)
            run_stats.total_model_calls = sum(f.model_calls for f in run_stats.files)
            run_stats.lines_needed_retry = sum(f.lines_needed_retry for f in run_stats.files)
            run_stats.lines_never_translated = sum(f.lines_never_translated for f in run_stats.files)
            run_stats.blocks_full_retried = sum(f.blocks_full_retried for f in run_stats.files)
            run_stats.translation_seconds = (
                time.time() - translation_started_at
                if translation_started_at is not None else 0.0
            )

            run_id = None
            try:
                run_id = stats_db.save_run(run_stats)
            except Exception as exc:
                log(f"[stats] no se pudo guardar la corrida en {config.TRANSLATION_STATS_DB}: {exc}")

            if on_stats:
                on_stats(run_id, dataclasses.asdict(run_stats))