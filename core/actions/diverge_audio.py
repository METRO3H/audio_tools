from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.filenames import fit_title, sanitize_name, utf16_len
from core.jobs import FfmpegCommand
from core.models import DivergeAudioConfig, DivergeOptions

# Mapeo de extensión de salida a codec ffmpeg
_FORMAT_CODEC: dict[str, str] = {
    "mp3":  "libmp3lame",
    "wav":  "pcm_s16le",
    "aac":  "aac",
    "m4a":  "aac",
    "ogg":  "libvorbis",
    "flac": "flac",
}


@dataclass(frozen=True)
class DivergeSegment:
    """Un segmento planificado: qué parte del origen y dónde/cómo se llama la salida."""

    index: int
    start: float
    end: float
    filename: str
    output: Path

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class DivergePlan:
    """Qué va a producir un diverge. Es la ÚNICA fuente de nombres, rutas y duraciones."""

    output_dir: Path
    segments: list[DivergeSegment]

    def to_dict(self) -> dict:
        """Forma que recibe el frontend (rutas como texto, claves snake_case)."""
        return {
            "output_dir": str(self.output_dir),
            "segments": [
                {
                    "index": s.index,
                    "name": s.filename,
                    "start": s.start,
                    "end": s.end,
                    "duration": s.duration,
                    "output": str(s.output),
                }
                for s in self.segments
            ],
        }


@dataclass(frozen=True)
class DivergeInputs:
    """Todo lo que la action necesita, ya resuelto a partir de unas DivergeOptions."""

    config: DivergeAudioConfig
    duration: float
    chapters: list[dict] | None


def resolve_diverge(
    opts: DivergeOptions,
    get_duration: Callable[[Path], float],
    get_chapters: Callable[[Path], list[dict]],
) -> DivergeInputs:
    """
    Resuelve las opciones a la entrada de la action. Las sondas (ffprobe) llegan
    inyectadas para poder probar esta lógica sin ffprobe.

    - modo "chapters": los capítulos se leen del archivo (el frontend ya no los envía)
    - modo "interval": usa duration_seconds si viene; si no, la lee con get_duration
    """
    config = opts.to_config()

    if opts.segment_mode == "chapters":
        found = get_chapters(config.input_file)
        if not found:
            raise ValueError("El archivo no tiene capítulos (o no se pudieron leer).")
        chapters = [
            {"start": ch["start"], "end": ch["end"], "title": ch.get("title") or ""}
            for ch in found
        ]
        return DivergeInputs(config, opts.duration_seconds or 0.0, chapters)

    if opts.duration_seconds is not None:
        return DivergeInputs(config, opts.duration_seconds, None)

    try:
        duration = get_duration(config.input_file)
    except ValueError as exc:
        raise ValueError(
            f"No se pudo leer la duración de «{config.input_file.name}». "
            "¿El archivo está dañado o su formato no es compatible?"
        ) from exc
    return DivergeInputs(config, duration, None)


class DivergeAudioAction:

    def plan(
        self,
        config: DivergeAudioConfig,
        duration: float,
        chapters: list[dict] | None = None,
    ) -> DivergePlan:
        """
        Qué segmentos se producirán, con su nombre y ruta de salida.
        Sin efectos secundarios: no crea carpetas ni toca el disco.
        """
        folder_name, output_dir = self._resolve_naming_and_dir(config)

        if chapters:
            raw = [(ch["start"], ch["end"], ch.get("title")) for ch in chapters]
        else:
            segs = self._calculate_segments(duration, config.interval_seconds)
            raw = [(start, end, None) for start, end in segs]

        suffix = f".{config.output_format}"
        dir_len = utf16_len(str(output_dir)) + 1  # +1: el separador antes del nombre

        segments = []
        for i, (start, end, raw_title) in enumerate(raw, 1):
            prefix = f"[{i}] {folder_name}"
            # El título viene del archivo: se limpia y se recorta para que la ruta quepa.
            # Si no queda un título utilizable, el archivo se nombra sin título.
            title = sanitize_name(raw_title) if raw_title else ""
            if title:
                title = fit_title(title, reserved=dir_len + utf16_len(prefix) + len(" - ") + utf16_len(suffix))
            filename = f"{prefix} - {title}{suffix}" if title else f"{prefix}{suffix}"
            segments.append(DivergeSegment(i, start, end, filename, output_dir / filename))

        return DivergePlan(output_dir, segments)

    def build_commands(
        self,
        config: DivergeAudioConfig,
        duration: float,
        chapters: list[dict] | None = None,
    ) -> list[FfmpegCommand]:
        """
        Un FfmpegCommand por segmento del plan. `duration` de cada comando es la
        del SEGMENTO (end - start), que es lo que necesita el progreso del runner.
        Crea la carpeta de salida.
        """
        plan = self.plan(config, duration, chapters)
        plan.output_dir.mkdir(parents=True, exist_ok=True)
        audio_args = self._audio_args(config)

        return [
            FfmpegCommand(
                args=[
                    "-y",
                    "-i", str(config.input_file),
                    "-ss", str(seg.start),
                    "-to", str(seg.end),
                    *audio_args,
                    str(seg.output),
                ],
                duration=seg.duration,
                output=seg.output,
                label=seg.filename,
            )
            for seg in plan.segments
        ]

    def build_args_list(
        self,
        config: DivergeAudioConfig,
        duration: float,
        chapters: list[dict] | None = None,
    ) -> list[list[str]]:
        return [c.args for c in self.build_commands(config, duration, chapters)]

    # — Internals ———————————————————————————————————————————————————————————

    def _audio_args(self, config: DivergeAudioConfig) -> list[str]:
        input_ext = config.input_file.suffix.lstrip(".").lower()
        output_ext = config.output_format.lower()
        if input_ext == output_ext:
            return ["-vn", "-c", "copy"]
        return ["-vn", "-c:a", _FORMAT_CODEC.get(output_ext, "copy")]

    def _resolve_naming_and_dir(self, config: DivergeAudioConfig) -> tuple[str, Path]:
        folder_name = (
            config.input_file.stem if config.media_type == "video" else config.base_folder.name
        )
        if config.use_subfolder:
            subfolder = "videos" if config.media_type == "video" else "audios"
            output_dir = config.output_folder / subfolder / "parts"
        else:
            output_dir = config.output_folder
        return folder_name, output_dir

    def _calculate_segments(self, duration: float, interval: int) -> list[tuple[float, float]]:
        n_full = int(duration // interval)
        remainder = duration % interval

        if n_full == 0:
            return [(0, duration)]

        if remainder == 0:
            return [(i * interval, (i + 1) * interval) for i in range(n_full)]

        segments = [(i * interval, (i + 1) * interval)
                    for i in range(n_full - 1)]

        if remainder < interval / 2:
            split_point = (n_full - 1) * interval + (interval + remainder) / 2
            segments.append(((n_full - 1) * interval, split_point))
            segments.append((split_point, duration))
        else:
            segments.append(((n_full - 1) * interval, n_full * interval))
            segments.append((n_full * interval, duration))

        return segments
