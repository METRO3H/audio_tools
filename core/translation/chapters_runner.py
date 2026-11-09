from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from core.translation.base_runner import BaseTranslationRunner
from core.translation.model_manager import TranslationBackend
from core.translation import prompts


class ChaptersTranslateRunner(BaseTranslationRunner):
    """
    Traduce los títulos de los chapters embebidos en una cola de archivos de audio/video. NO
    escribe nada en disco — eso es trabajo de ChaptersAction.apply (core/translation/
    chapters_action.py), que corre después, solo sobre lo que el usuario confirma o edita en la
    vista previa (ver core/translation/job.py y api.py).

    Independiente de la tool de .srt: preset y work_info propios (un work_info para TODA la
    cola, generado una sola vez — se asume que los archivos pertenecen a la misma obra, misma
    idea que título/work_info en Translate SRT). Sin concepto de "título de la obra": acá no
    aplica.
    """

    def __init__(self, backend: TranslationBackend | None = None) -> None:
        super().__init__(backend)
        self._was_cancelled = False

    # ── API pública ──────────────────────────────────────────────────────

    def translate_queue(
        self,
        files: list[tuple[Path, list[dict]]],  # (path, chapters) por archivo
        raw_publisher_info: str = "",
        base_prompt: str = "",
        glossary: str = "",
        model: str = "",
        n_gpu_layers: int = 20,
        n_ctx: int = 4096,
        temperature: float = 0.3,
        on_log: Callable[[str], None] | None = None,
        on_phase: Callable[[str], None] | None = None,
        on_work_info: Callable[[str], None] | None = None,
        on_work_info_stream: Callable[[str], None] | None = None,
        on_file_start: Callable[[int, int, str, float], None] | None = None,
        on_file_titles: Callable[[int, list[dict]], None] | None = None,
        on_file_done: Callable[[int, bool, float], None] | None = None,
        on_queue_progress: Callable[[int, int], None] | None = None,
        on_queue_done: Callable[[int, int, bool, list], None] | None = None,
    ) -> None:
        self._cancelled = False
        self._was_cancelled = False
        threading.Thread(
            target=self._queue_worker,
            args=(
                files, raw_publisher_info, base_prompt, glossary, model, n_gpu_layers, n_ctx, temperature,
                on_log, on_phase, on_work_info, on_work_info_stream,
                on_file_start, on_file_titles, on_file_done, on_queue_progress, on_queue_done,
            ),
            daemon=True,
        ).start()

    # ── Worker ───────────────────────────────────────────────────────────

    def _queue_worker(
        self, files, raw_publisher_info, base_prompt, glossary, model, n_gpu_layers, n_ctx, temperature,
        on_log, on_phase, on_work_info, on_work_info_stream,
        on_file_start, on_file_titles, on_file_done, on_queue_progress, on_queue_done,
    ):
        def log(msg):
            if on_log: on_log(msg)

        def phase(msg):
            if on_phase: on_phase(msg)

        total = len(files)
        # (path, [{index, start, end, original_title, translated_title}]) por archivo ya
        # traducido — es lo que termina en audiotools:translation:preview_ready.
        results: list[tuple[Path, list[dict]]] = []

        try:
            phase("Cargando modelo...")
            log(f"Cargando modelo {model}...")
            self._manager.load(model, n_gpu_layers, n_ctx)
            if self._cancelled:
                self._was_cancelled = True
                if on_queue_done: on_queue_done(0, total, True, results)
                return

            work_info = ""
            if raw_publisher_info.strip():
                phase("Generando work info...")
                log("Generando work info del publisher (chapters)...")
                work_info = self._manager.generate_text(
                    prompts.get_shared_prompt("work_info_extraction"),
                    raw_publisher_info.strip(),
                    temperature=temperature,
                    on_stream=(lambda tokens, text: on_work_info_stream(text)) if on_work_info_stream else None,
                )
                log(f"Work info generado:\n{work_info}")
                if on_work_info: on_work_info(work_info)

            if self._cancelled:
                self._was_cancelled = True
                if on_queue_done: on_queue_done(0, total, True, results)
                return

            system_prompt = prompts.build_short_text_prompt(base_prompt, glossary, work_info)

            succeeded = 0
            for idx, (path, chapters) in enumerate(files):
                if self._cancelled:
                    self._was_cancelled = True
                    break

                started_at = time.time()
                if on_file_start: on_file_start(idx, total, path.name, started_at)

                phase(f"Traduciendo {len(chapters)} títulos de «{path.name}»...")
                log(f"Traduciendo {len(chapters)} títulos de capítulo de «{path.name}»...")
                titles = [ch["title"] for ch in chapters]
                translated_titles = self._manager.translate_texts(
                    titles, system_prompt, temperature=temperature, on_retry_log=log,
                )

                file_result = [
                    {
                        "index": ch["index"], "start": ch["start"], "end": ch["end"],
                        "original_title": ch["title"], "translated_title": new_title,
                    }
                    for ch, new_title in zip(chapters, translated_titles)
                ]
                for row in file_result:
                    log(f"  [{row['index']}] {row['original_title']} -> {row['translated_title']}")
                results.append((path, file_result))

                if on_file_titles: on_file_titles(idx, file_result)
                succeeded += 1
                if on_file_done: on_file_done(idx, True, time.time() - started_at)
                if on_queue_progress: on_queue_progress(idx + 1, total)

            if on_queue_done:
                on_queue_done(succeeded, total, self._was_cancelled, results)

        except Exception as exc:
            log(f"[error fatal] {exc}")
            if on_queue_done:
                on_queue_done(0, total, self._was_cancelled, results)
