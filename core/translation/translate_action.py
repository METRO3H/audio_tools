"""
core/translation/translate_action.py
-------------------------------------
Qué va a producir la traducción de una cola de .srt, sin ejecutar nada: mismo
rol que core/transcription/transcribe_action.py::TranscribeAction, pero más
simple — la salida conserva el nombre del archivo de entrada (no cambia de
extensión ni de formato), solo cambia de carpeta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.filenames import SAFE_PATH_LIMIT, utf16_len


@dataclass(frozen=True)
class TranslateItem:
    """Un .srt planificado: de dónde sale y dónde quedará su traducción."""

    index: int
    path: Path
    output: Path
    exists: bool  # la salida ya existe y se sobrescribirá

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class TranslatePlan:
    """Qué va a producir Translate (SRT). Es la ÚNICA fuente de rutas de salida."""

    output_dir: Path
    files: list[TranslateItem]

    def to_dict(self) -> dict:
        """Forma que recibe el frontend (rutas como texto, claves snake_case)."""
        return {
            "output_dir": str(self.output_dir),
            "files": [
                {
                    "index": f.index,
                    "name": f.name,
                    "path": str(f.path),
                    "output": str(f.output),
                    "output_name": f.output.name,
                    "exists": f.exists,
                }
                for f in self.files
            ],
        }


class TranslateAction:

    def get_output_path(self, input_file: Path, base_folder: Path, subfolder: str) -> Path:
        """<base>/transcriptions/<subcarpeta>/<mismo nombre>. No toca el disco."""
        return base_folder / "transcriptions" / subfolder / input_file.name

    def plan(self, file_paths: list[Path], base_folder: Path, subfolder: str) -> TranslatePlan:
        """
        Dónde quedará la traducción de cada .srt y si ya existe. Sin efectos secundarios: no
        crea carpetas ni escribe nada.

        Es un error que dos entradas den la misma salida (mismo nombre de archivo elegido desde
        carpetas distintas) o que la ruta supere el límite seguro de Windows.
        """
        if not file_paths:
            raise ValueError("No hay nada que procesar.")

        output_dir = base_folder / "transcriptions" / subfolder

        items: list[TranslateItem] = []
        seen: dict[str, Path] = {}  # nombre de salida (sin distinguir mayúsculas) -> entrada que lo produce
        for i, path in enumerate(file_paths):
            output = self.get_output_path(path, base_folder, subfolder)

            earlier = seen.get(output.name.casefold())
            if earlier is not None:
                raise ValueError(
                    f"«{earlier.name}» y «{path.name}» darían la misma traducción "
                    f"(«{output.name}»). Quita uno de los dos."
                )
            seen[output.name.casefold()] = path

            if utf16_len(str(output)) > SAFE_PATH_LIMIT:
                raise ValueError(
                    f"La ruta de «{output.name}» es demasiado larga para Windows "
                    f"(más de {SAFE_PATH_LIMIT} caracteres). Usa una carpeta base más corta."
                )

            items.append(TranslateItem(i, path, output, output.exists()))

        return TranslatePlan(output_dir, items)
