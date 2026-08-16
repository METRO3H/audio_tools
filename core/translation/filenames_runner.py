from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable

import config
from core.lang_detect import detect_language
from core.translation.model_manager import ModelManager
from core.translation import prompts

_FILENAME_TASK_INSTRUCTIONS = (
    "Translate each numbered file or folder name (without any file "
    "extension) into a concise English name. Preserve any leading "
    "numbering/ordering exactly as given. Do not use characters invalid "
    'in Windows file names (\\ / : * ? " < > |). Output only the '
    "translated names in the same numbered format, one per line."
)

_INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*]')


class FilenameTranslateRunner:
    """
    Traduce nombres de archivo y de carpeta dentro de una carpeta, de forma
    recursiva.

    Flujo en dos pasos, separado a proposito para que el frontend pueda
    mostrar una vista previa (arbol con checkboxes) antes de tocar nada:

        1. scan(folder)              -> detecta idioma por archivo/carpeta,
                                          sin IA
        2. translate_preview(files)  -> traduce SOLO los que hacen falta
        3. apply_renames(pairs)      -> renombra en disco lo que el usuario
                                          dejo confirmado

    Independiente de la tool de .srt y de chapters: preset y work_info
    propios.
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

    def scan(self, folder: Path) -> list[dict]:
        """
        Recorre `folder` recursivamente. Para cada archivo o carpeta,
        detecta el idioma de su nombre via lang_detect — sin usar el
        modelo. En archivos se ignora la extension para la deteccion (solo
        importa el stem); en carpetas se usa el nombre completo, ya que no
        hay concepto de extension. Marca needs_translation=False para lo
        que ya parece estar en ingles (o texto vacio/no detectable), asi
        el batch de traduccion no gasta tiempo en lo que no lo necesita.
        """
        results = []
        for p in sorted(folder.rglob("*")):
            is_dir = p.is_dir()
            name_for_lang = p.name if is_dir else p.stem
            lang = detect_language(name_for_lang)
            needs = lang is not None and lang != "en"
            results.append({
                "path": str(p),
                "relative_path": str(p.relative_to(folder)),
                "name": p.name,
                "is_dir": is_dir,
                "detected_lang": lang,
                "needs_translation": needs,
            })
        return results

    def translate_preview(
        self,
        files: list[dict],
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
        on_translate_stream: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """
        Corre de forma SINCRONICA (el caller es responsable de invocarlo
        desde un hilo propio, tal como hace api.py). Devuelve la misma
        lista de entrada con "translated_name" agregado — igual al nombre
        original si needs_translation era False.
        """
        def log(msg):
            if on_log: on_log(msg)

        def phase(msg):
            if on_phase: on_phase(msg)

        n_gpu_layers = n_gpu_layers if n_gpu_layers is not None else config.TRANSLATION_N_GPU_LAYERS
        n_ctx        = n_ctx        if n_ctx        is not None else config.TRANSLATION_N_CTX
        temp         = temperature  if temperature  is not None else config.TRANSLATION_TEMPERATURE

        to_translate = [f for f in files if f["needs_translation"]]
        if not to_translate:
            log("Ningun archivo/carpeta necesita traduccion segun el detector de idioma.")
            return [{**f, "translated_name": f["name"]} for f in files]

        phase("Cargando modelo...")
        log(f"Cargando modelo {model}...")
        self._manager.load(model, n_gpu_layers, n_ctx)
        if self._cancelled:
            return [{**f, "translated_name": f["name"]} for f in files]

        work_info = ""
        if raw_publisher_info.strip():
            phase("Generando work info...")
            log("Generando work info del publisher (filenames)...")
            work_info = self._manager.generate_text(
                prompts.get_system_prompt("filenames", "work_info_extraction"),
                raw_publisher_info.strip(),
                temperature=temp,
                on_stream=(lambda tokens, text: on_work_info_stream(text)) if on_work_info_stream else None,
            )
            log(f"Work info generado:\n{work_info}")
            if on_work_info: on_work_info(work_info)

        if self._cancelled:
            return [{**f, "translated_name": f["name"]} for f in files]

        phase(f"Traduciendo {len(to_translate)} nombres...")
        log(f"Traduciendo {len(to_translate)} nombres de archivo/carpeta...")
        system_prompt = prompts.build_short_text_prompt(
            _FILENAME_TASK_INSTRUCTIONS, base_prompt, work_info,
        )
        # Para carpetas se traduce el nombre completo (no hay extension que
        # separar); para archivos, solo el stem.
        names_to_translate = [
            f["name"] if f["is_dir"] else Path(f["name"]).stem
            for f in to_translate
        ]
        translated_names = self._manager.translate_texts(
            names_to_translate, system_prompt, temperature=temp,
            on_stream=(lambda tokens, text: on_translate_stream(text)) if on_translate_stream else None,
        )

        translated_by_path = {}
        for f, new_name in zip(to_translate, translated_names):
            safe_name = self._sanitize(new_name)
            if f["is_dir"]:
                translated_by_path[f["path"]] = safe_name
            else:
                ext = Path(f["name"]).suffix
                translated_by_path[f["path"]] = f"{safe_name}{ext}"
            log(f"  {f['name']} -> {translated_by_path[f['path']]}")

        return [
            {**f, "translated_name": translated_by_path.get(f["path"], f["name"])}
            for f in files
        ]

    def apply_renames(self, renames: list[tuple[str, str]]) -> dict:
        """
        renames: [(old_path, new_name), ...] — solo los que el usuario dejo
        confirmados (checkbox tildado) en la vista previa.

        Se procesan del path mas profundo al menos profundo: si una carpeta
        y algo dentro de ella (archivo o subcarpeta) estan ambos en la
        lista, hay que renombrar los hijos antes que el padre — si se
        renombrara la carpeta primero, el old_path guardado para sus hijos
        quedaria apuntando a una ruta que ya no existe y el rename fallaria.

        Resuelve colisiones agregando " (2)", " (3)", etc. antes de escribir.
        Devuelve { renamed: [{old, new}], errors: [{path, error}] }.
        """
        ordered = sorted(renames, key=lambda r: len(Path(r[0]).parts), reverse=True)
        renamed, errors = [], []
        for old_path_str, new_name in ordered:
            old_path = Path(old_path_str)
            try:
                new_path = self._unique_path(old_path.parent / new_name)
                old_path.rename(new_path)
                renamed.append({"old": str(old_path), "new": str(new_path)})
            except Exception as exc:
                errors.append({"path": str(old_path), "error": str(exc)})
        return {"renamed": renamed, "errors": errors}

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize(name: str) -> str:
        name = _INVALID_WIN_CHARS.sub("", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name or "untitled"

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem, suffix, parent = path.stem, path.suffix, path.parent
        i = 2
        while True:
            candidate = parent / f"{stem} ({i}){suffix}"
            if not candidate.exists():
                return candidate
            i += 1