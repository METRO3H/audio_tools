from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.chapters_metadata import embed_chapters
from core.jobs import FfmpegCommand
from core.models import MergeAudioConfig, MergeOptions


@dataclass(frozen=True)
class MergeFile:
    """Un archivo que SÍ entra en el merge, con el tramo que ocupará en la salida."""

    index: int
    path: Path
    duration: float
    start: float
    end: float

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class MergePlan:
    """
    Qué va a producir un merge. Es la ÚNICA fuente de la lista efectiva de archivos,
    sus duraciones y los capítulos: el progreso, los capítulos y la vista previa se
    calculan todos desde aquí, así no pueden desalinearse.
    """

    output_path: Path
    files: list[MergeFile]
    excluded: list[Path]  # entradas descartadas por ser el propio archivo de salida

    @property
    def total_duration(self) -> float:
        return sum(f.duration for f in self.files)

    @property
    def chapters(self) -> list[dict]:
        return [
            {"index": f.index, "title": f.path.stem, "start": f.start, "end": f.end}
            for f in self.files
        ]

    def to_dict(self) -> dict:
        """Forma que recibe el frontend (rutas como texto, claves snake_case)."""
        return {
            "output_path": str(self.output_path),
            "output_name": self.output_path.name,
            "files": [
                {
                    "index": f.index,
                    "name": f.name,
                    "path": str(f.path),
                    "duration": f.duration,
                    "start": f.start,
                    "end": f.end,
                }
                for f in self.files
            ],
            "excluded": [str(p) for p in self.excluded],
            "total_duration": self.total_duration,
            "chapters": self.chapters,
        }


@dataclass(frozen=True)
class MergeInputs:
    """Todo lo que la action necesita, ya resuelto a partir de unas MergeOptions."""

    config: MergeAudioConfig
    durations: list[float]  # una por config.input_files, en el mismo orden


def resolve_merge(opts: MergeOptions, get_duration: Callable[[Path], float]) -> MergeInputs:
    """
    Resuelve las opciones a la entrada de la action. La sonda de duración (ffprobe)
    llega inyectada para poder probar esta lógica sin ffprobe.

    Se usan las duraciones que ya trae el frontend; solo se consulta ffprobe para
    las que faltan o son 0.
    """
    config = opts.to_config()
    known = opts.durations or [None] * len(config.input_files)

    durations: list[float] = []
    for path, duration in zip(config.input_files, known):
        if duration is not None and duration > 0:
            durations.append(float(duration))
            continue
        try:
            durations.append(float(get_duration(path)))
        except ValueError as exc:
            raise ValueError(
                f"No se pudo leer la duración de «{path.name}». "
                "¿El archivo está dañado o su formato no es compatible?"
            ) from exc
    return MergeInputs(config, durations)


class MergeAudioAction:

    def plan(self, config: MergeAudioConfig, durations: list[float]) -> MergePlan:
        """
        Calcula la lista efectiva de archivos. Si entre las entradas está el propio
        archivo de salida (un merge anterior en la misma carpeta) se descarta JUNTO
        con su duración, para que capítulos y progreso sigan alineados con el audio.
        Sin efectos secundarios.
        """
        output = config.output_file.resolve()

        kept: list[tuple[Path, float]] = []
        excluded: list[Path] = []
        for path, duration in zip(config.input_files, durations):
            if path.resolve() == output:
                excluded.append(path)
            else:
                kept.append((path, duration))

        if len(kept) < 2:
            raise ValueError(
                "Se necesitan al menos 2 archivos para hacer un merge. "
                "Verifica que no estés incluyendo el archivo resultado como input."
            )

        files: list[MergeFile] = []
        cursor = 0.0
        for index, (path, duration) in enumerate(kept, 1):
            files.append(MergeFile(index, path, duration, cursor, cursor + duration))
            cursor += duration
        return MergePlan(config.output_file, files, excluded)

    def build_command(self, plan: MergePlan, workdir: Path) -> FfmpegCommand:
        """
        El comando de concatenación. La lista de archivos se escribe en `workdir`
        (una carpeta temporal del job), no en el directorio de trabajo del proceso.
        Los argumentos son los de siempre: no se tocan para no afectar el progreso.
        """
        concat_list = workdir / "concat_list.txt"
        concat_list.write_text(
            "\n".join(f"file '{_escape(f.path)}'" for f in plan.files),
            encoding="utf-8",
        )
        return FfmpegCommand(
            args=["-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), str(plan.output_path)],
            duration=plan.total_duration,
            output=plan.output_path,
            label=plan.output_path.name,
        )

    def finalize(
        self,
        plan: MergePlan,
        success: bool,
        ffmpeg_bin: Path | str,
        workdir: Path,
        probe_duration: Callable[[Path], float] | None = None,
    ) -> str | None:
        """
        Paso final del job (se ejecuta en su hilo, antes de emitir `done`):
          - éxito: comprueba que la salida dura lo esperado e incrusta los capítulos.
            Devuelve un aviso si algo no cuadra (el audio ya está unido)
          - fallo o cancelación: borra la salida incompleta
        Siempre elimina la carpeta temporal.

        La comprobación de duración existe porque ffmpeg termina con código 0 aunque no
        pueda leer uno de los archivos (imprime el error, pero produce una salida con
        solo el audio anterior): sin ella, un archivo dañado daría "Completado".
        """
        try:
            if success:
                warnings = []
                if probe_duration is not None:
                    warnings += self._check_duration(plan, probe_duration)
                reason = embed_chapters(ffmpeg_bin, plan.output_path, plan.chapters, workdir)
                if reason is not None:
                    warnings.append(f"No se pudieron incrustar los capítulos: {reason}")
                return " ".join(warnings) or None

            try:
                plan.output_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    @staticmethod
    def _check_duration(plan: MergePlan, probe_duration: Callable[[Path], float]) -> list[str]:
        """Avisos si la salida dura bastante menos que la suma de las entradas."""
        expected = plan.total_duration
        try:
            actual = probe_duration(plan.output_path)
        except Exception:  # noqa: BLE001 - cualquier fallo al medirla es, en sí, un aviso
            return ["No se pudo verificar la duración del archivo resultante."]

        # El recodificado añade unas décimas de segundo de relleno por archivo.
        tolerance = 1.0 + 0.1 * len(plan.files)
        if actual < expected - tolerance:
            return [
                f"El archivo resultante dura {_clock(actual)} y se esperaban {_clock(expected)}: "
                "es posible que falte audio (¿algún archivo de entrada está dañado o no se pudo leer?)."
            ]
        return []


def _clock(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _escape(path: Path) -> str:
    return path.as_posix().replace("'", "'\\''")
