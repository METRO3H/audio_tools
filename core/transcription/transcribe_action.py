from dataclasses import dataclass
from pathlib import Path

from core.filenames import SAFE_PATH_LIMIT, utf16_len

OUTPUT_FORMATS = ["srt", "vtt", "txt"]


def seconds_to_srt_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def seconds_to_vtt_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def build_srt(segments: list) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        start = seconds_to_srt_time(seg.start)
        end   = seconds_to_srt_time(seg.end)
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def build_vtt(segments: list) -> str:
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        start = seconds_to_vtt_time(seg.start)
        end   = seconds_to_vtt_time(seg.end)
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def build_txt(segments: list) -> str:
    return "\n".join(seg.text.strip() for seg in segments)


@dataclass(frozen=True)
class TranscribeItem:
    """Un audio planificado: de dónde sale, cuánto dura y dónde quedará su transcripción."""

    index: int
    path: Path
    duration: float
    output: Path
    exists: bool  # la salida ya existe y se sobrescribirá

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class TranscribePlan:
    """Qué va a producir Transcribe. Es la ÚNICA fuente de rutas de salida y duraciones."""

    output_dir: Path
    files: list[TranscribeItem]

    @property
    def total_duration(self) -> float:
        return sum(f.duration for f in self.files)

    def to_dict(self) -> dict:
        """Forma que recibe el frontend (rutas como texto, claves snake_case)."""
        return {
            "output_dir": str(self.output_dir),
            "files": [
                {
                    "index": f.index,
                    "name": f.name,
                    "path": str(f.path),
                    "duration": f.duration,
                    "output": str(f.output),
                    "output_name": f.output.name,
                    "exists": f.exists,
                }
                for f in self.files
            ],
            "total_duration": self.total_duration,
        }


class TranscribeAction:

    def get_output_path(
        self,
        input_file: Path,
        base_folder: Path,
        subfolder: str,
        output_format: str = "srt",
    ) -> Path:
        """<base>/transcriptions/<subcarpeta>/<nombre>.<formato>. No toca el disco."""
        return base_folder / "transcriptions" / subfolder / f"{input_file.stem}.{output_format}"

    def plan(self, configs: list) -> TranscribePlan:
        """
        Dónde quedará la transcripción de cada audio y si ya existe. Sin efectos secundarios:
        no crea carpetas ni escribe nada. `configs` son las TranscribeConfig de core/models.py,
        una por archivo, todas con la misma carpeta base, subcarpeta y formato.

        Es un error que dos audios den la misma salida (a.mp3 y a.wav → a.srt) o que la ruta
        supere el límite seguro de Windows.
        """
        if not configs:
            raise ValueError("No hay nada que procesar.")

        first = configs[0]
        output_dir = first.base_folder / "transcriptions" / first.output_subfolder

        items: list[TranscribeItem] = []
        seen: dict[str, Path] = {}  # nombre de salida (sin distinguir mayúsculas) -> audio que lo produce
        for i, cfg in enumerate(configs):
            output = self.get_output_path(cfg.input_file, cfg.base_folder, cfg.output_subfolder, cfg.output_format)

            earlier = seen.get(output.name.casefold())
            if earlier is not None:
                raise ValueError(
                    f"«{earlier.name}» y «{cfg.input_file.name}» darían la misma transcripción "
                    f"(«{output.name}»). Quita uno de los dos."
                )
            seen[output.name.casefold()] = cfg.input_file

            if utf16_len(str(output)) > SAFE_PATH_LIMIT:
                raise ValueError(
                    f"La ruta de «{output.name}» es demasiado larga para Windows "
                    f"(más de {SAFE_PATH_LIMIT} caracteres). Usa una carpeta base más corta."
                )

            items.append(TranscribeItem(i, cfg.input_file, cfg.total_duration, output, output.exists()))

        return TranscribePlan(output_dir, items)

    def write_output(
        self,
        segments: list,
        output_path: Path,
        output_format: str = "srt",
    ) -> None:
        if output_format == "srt":
            content = build_srt(segments)
        elif output_format == "vtt":
            content = build_vtt(segments)
        else:
            content = build_txt(segments)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
