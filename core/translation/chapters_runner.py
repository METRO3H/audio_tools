from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

import config
from core.translation.model_manager import ModelManager
from core.translation import prompts

_CHAPTER_TASK_INSTRUCTIONS = (
    "Translate each numbered chapter title into English, faithfully and "
    "without censoring explicit content. Output only the translations in "
    "the same numbered format, one per line."
)


class ChaptersTranslateRunner:
    """
    Traduce los titulos de los chapters embebidos en un archivo de audio/
    video, y genera una COPIA del archivo con esos titulos ya traducidos.

    Reusa exactamente el mismo mecanismo que MergeAudioAction.add_chapters:
    escribe un archivo FFMETADATA1 con bloques [CHAPTER], y usa
    `ffmpeg -map_metadata 1 -c copy` para re-muxear sin re-codificar nada.
    La unica diferencia es que aca el START/END ya existe (viene de
    get_chapters()) y lo que cambia es el titulo.

    Independiente de la tool de .srt: preset y work_info propios (sin
    concepto de "titulo de la obra", eso no aplica aca).
    """

    _METADATA_FILE = Path("_chapters_translate_metadata.txt")

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

    def run(
        self,
        input_file: Path,
        output_file: Path,
        chapters: list[dict],
        raw_publisher_info: str,
        base_prompt: str,
        model: str,
        n_gpu_layers: int | None = None,
        n_ctx: int | None = None,
        temperature: float | None = None,
        on_log: Callable[[str], None] | None = None,
        on_phase: Callable[[str], None] | None = None,
        on_work_info: Callable[[str], None] | None = None,
        on_work_info_stream: Callable[[str], None] | None = None,
        on_done: Callable[[bool], None] | None = None,
    ) -> None:
        self._cancelled = False
        threading.Thread(
            target=self._worker,
            args=(
                input_file, output_file, chapters, raw_publisher_info, base_prompt,
                model, n_gpu_layers, n_ctx, temperature,
                on_log, on_phase, on_work_info, on_work_info_stream, on_done,
            ),
            daemon=True,
        ).start()

    # ── Worker ───────────────────────────────────────────────────────────

    def _worker(
        self, input_file, output_file, chapters, raw_publisher_info, base_prompt,
        model, n_gpu_layers, n_ctx, temperature,
        on_log, on_phase, on_work_info, on_work_info_stream, on_done,
    ):
        def log(msg):
            if on_log: on_log(msg)

        def phase(msg):
            if on_phase: on_phase(msg)

        n_gpu_layers = n_gpu_layers if n_gpu_layers is not None else config.TRANSLATION_N_GPU_LAYERS
        n_ctx        = n_ctx        if n_ctx        is not None else config.TRANSLATION_N_CTX
        temp         = temperature  if temperature  is not None else config.TRANSLATION_TEMPERATURE

        try:
            phase("Cargando modelo...")
            log(f"Cargando modelo {model}...")
            self._manager.load(model, n_gpu_layers, n_ctx)
            if self._cancelled:
                if on_done: on_done(False)
                return

            work_info = ""
            if raw_publisher_info.strip():
                phase("Generando work info...")
                log("Generando work info del publisher (chapters)...")
                work_info = self._manager.generate_text(
                    prompts.get_system_prompt("chapters", "work_info_extraction"),
                    raw_publisher_info.strip(),
                    temperature=temp,
                    on_stream=(lambda tokens, text: on_work_info_stream(text)) if on_work_info_stream else None,
                )
                log(f"Work info generado:\n{work_info}")
                if on_work_info: on_work_info(work_info)

            if self._cancelled:
                if on_done: on_done(False)
                return

            phase(f"Traduciendo {len(chapters)} titulos de capitulo...")
            log(f"Traduciendo {len(chapters)} titulos de capitulo...")
            system_prompt = prompts.build_short_text_prompt(
                _CHAPTER_TASK_INSTRUCTIONS, base_prompt, work_info,
            )
            titles = [ch["title"] for ch in chapters]
            translated_titles = self._manager.translate_texts(titles, system_prompt, temperature=temp)

            for ch, new_title in zip(chapters, translated_titles):
                log(f"  [{ch['index']}] {ch['title']} -> {new_title}")

            if self._cancelled:
                if on_done: on_done(False)
                return

            phase("Escribiendo archivo con chapters traducidos...")
            log("Re-muxeando archivo con los titulos traducidos...")
            self._write_metadata(chapters, translated_titles)

            temp_out = output_file.with_suffix(".chapters_tmp" + output_file.suffix)
            try:
                result = subprocess.run(
                    [
                        str(config.FFMPEG_BIN), "-y",
                        "-i", str(input_file),
                        "-i", str(self._METADATA_FILE),
                        "-map_metadata", "1",
                        "-c", "copy",
                        str(temp_out),
                    ],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0 and temp_out.exists():
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    temp_out.replace(output_file)
                    log(f"Guardado: {output_file}")
                    if on_done: on_done(True)
                else:
                    stderr = result.stderr.decode(errors="ignore") if result.stderr else ""
                    log(f"[error] ffmpeg fallo: {stderr}")
                    if on_done: on_done(False)
            finally:
                if temp_out.exists():
                    temp_out.unlink()
                if self._METADATA_FILE.exists():
                    self._METADATA_FILE.unlink()

        except Exception as exc:
            log(f"[error fatal] {exc}")
            if on_done: on_done(False)

    def _write_metadata(self, chapters: list[dict], translated_titles: list[str]) -> None:
        lines = [";FFMETADATA1", ""]
        for ch, title in zip(chapters, translated_titles):
            start_ms = int(ch["start"] * 1000)
            end_ms = int(ch["end"] * 1000)
            safe_title = title.replace("\n", " ").strip()
            lines += [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={safe_title}",
                "",
            ]
        self._METADATA_FILE.write_text("\n".join(lines), encoding="utf-8")
