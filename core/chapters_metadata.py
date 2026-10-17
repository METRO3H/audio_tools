"""
core/chapters_metadata.py
-------------------------
Capítulos de un archivo multimedia: escritura del archivo de metadatos
(formato FFMETADATA1 de ffmpeg) e incrustación en un archivo ya generado.

Lo usa Merge. El traductor de capítulos tiene hoy su propia copia de esta lógica
y pasará a usar este módulo (hay un test que fija que ambos formatos coinciden).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from core.process import NO_WINDOW


def write_ffmetadata(path: Path, chapters: Iterable[dict]) -> None:
    """
    Escribe `path` con un bloque [CHAPTER] por capítulo.

    chapters: [{"title": str, "start": segundos, "end": segundos}, ...]
    El título se aplana a una sola línea (un salto de línea rompería el formato).
    """
    lines = [";FFMETADATA1", ""]
    for chapter in chapters:
        title = " ".join(str(chapter["title"]).split())
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={round(chapter['start'] * 1000)}",
            f"END={round(chapter['end'] * 1000)}",
            f"title={title}",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def embed_chapters(
    ffmpeg_bin: Path | str,
    media_file: Path,
    chapters: Iterable[dict],
    workdir: Path,
) -> str | None:
    """
    Incrusta `chapters` en `media_file` (sin recodificar: -c copy, tarda menos de un segundo).

    Devuelve None si salió bien, o un mensaje con el motivo si ffmpeg falló.
    En ese caso `media_file` queda intacto. Si no se puede ejecutar ffmpeg, la
    excepción se propaga.
    """
    metadata = workdir / "chapters_metadata.txt"
    write_ffmetadata(metadata, chapters)

    temp = media_file.with_suffix(".chapters_tmp" + media_file.suffix)
    try:
        result = subprocess.run(
            [
                str(ffmpeg_bin), "-y",
                "-i", str(media_file),
                "-i", str(metadata),
                "-map_metadata", "1",
                "-c", "copy",
                str(temp),
            ],
            capture_output=True,
            creationflags=NO_WINDOW,
        )
        if result.returncode == 0 and temp.exists():
            temp.replace(media_file)
            return None
        return _last_line(result.stderr) or f"ffmpeg terminó con código {result.returncode}"
    finally:
        if temp.exists():
            temp.unlink()


def _last_line(stderr: bytes | None) -> str:
    lines = [ln.strip() for ln in (stderr or b"").decode("utf-8", errors="replace").splitlines() if ln.strip()]
    return lines[-1] if lines else ""
