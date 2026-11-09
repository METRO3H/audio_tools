"""
core/translation/chapters_action.py
-------------------------------------
Qué va a traducir Chapters, sin ejecutar nada: lee los capítulos ya existentes de cada archivo
(ffprobe — de solo lectura, no escribe nada) para armar la cola a traducir. A diferencia de
Translate SRT, acá no hay rutas de salida que planificar: no se crea ningún archivo nuevo. El
resultado se aplica sobre el mismo archivo (ver `ChaptersAction.apply`, más abajo) recién cuando
el usuario confirma o edita la vista previa — ver core/translation/job.py.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from typing import Callable

from core.chapters_metadata import embed_chapters
from core.jobs import describe_error


@dataclass(frozen=True)
class ChaptersFileItem:
    path: Path
    chapters: list[dict]  # [{index, title, start, end}], tal cual los devuelve get_chapters()


@dataclass(frozen=True)
class ChaptersPlan:
    files: list[ChaptersFileItem]

    def to_dict(self) -> dict:
        return {
            "files": [
                {"path": str(f.path), "name": f.path.name, "chapters": f.chapters}
                for f in self.files
            ],
        }


class ChaptersAction:

    def plan(self, get_chapters: Callable[[Path], list[dict]], file_paths: list[Path]) -> ChaptersPlan:
        """
        Lee los capítulos de cada archivo (la sonda, ffprobe, llega inyectada para poder probar
        esto sin ffprobe — mismo patrón que resolve_transcribe con get_duration). Es un error que
        un archivo no tenga ninguno: no hay nada que traducir ahí, y mejor avisar antes de cargar
        el modelo que a mitad de la cola.
        """
        if not file_paths:
            raise ValueError("No hay nada que procesar.")

        items = []
        for path in file_paths:
            chapters = get_chapters(path)
            if not chapters:
                raise ValueError(f"«{path.name}» no tiene capítulos.")
            items.append(ChaptersFileItem(path, chapters))
        return ChaptersPlan(items)

    def apply(self, ffmpeg_bin, items: list[dict]) -> dict:
        """
        Escribe los capítulos confirmados (y editados, si corresponde) de la vista previa —
        ver audiotools:translation:preview_ready. items: [{"path": str, "chapters": [{"start",
        "end", "title"}, ...]}], ya filtrados del lado del frontend a solo los capítulos que el
        usuario dejó marcados (los no marcados no entran acá, así que conservan su título
        original tal cual estaban).

        Cada archivo se escribe IN-PLACE (mismo path, sin copia ni carpeta nueva):
        embed_chapters ya usa un temporal + reemplazo, así que si ffmpeg falla a mitad de camino
        en uno, ESE archivo queda intacto — pero no hay nada que deshaga los que ya se
        escribieron bien antes en la misma llamada.

        Nunca lanza: un archivo que falla se reporta en "errors" y se sigue con el resto.
        Devuelve {"applied": [path, ...], "errors": [{"path", "error"}, ...]}.
        """
        applied: list[str] = []
        errors: list[dict] = []
        workdir = Path(tempfile.mkdtemp(prefix="audiotools_chapters_"))
        try:
            for item in items:
                path = Path(item["path"])
                try:
                    reason = embed_chapters(ffmpeg_bin, path, item["chapters"], workdir)
                    if reason is None:
                        applied.append(str(path))
                    else:
                        errors.append({"path": str(path), "error": reason})
                except Exception as exc:
                    errors.append({"path": str(path), "error": describe_error(exc)})
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        return {"applied": applied, "errors": errors}
