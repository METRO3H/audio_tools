from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.filenames import SAFE_PATH_LIMIT, utf16_len
from core.jobs import FfmpegCommand
from core.models import AudioToVideoConfig, AudioToVideoOptions
from core.video_encoding import ENCODERS  # noqa: F401 - se re-exporta: api.py y los tests lo importan de aquí

OUTPUT_SUBFOLDER = "videos"
OUTPUT_EXTENSION = ".mp4"


@dataclass(frozen=True)
class AudioToVideoItem:
    """Un audio planificado: de dónde sale, cuánto dura y dónde quedará su video."""

    index: int
    path: Path
    duration: float
    output: Path
    exists: bool  # la salida ya existe y se sobrescribirá

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class AudioToVideoPlan:
    """Qué va a producir Audio→Video. Es la ÚNICA fuente de rutas de salida y duraciones."""

    output_dir: Path
    files: list[AudioToVideoItem]

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


@dataclass(frozen=True)
class AudioToVideoInputs:
    """Todo lo que la action necesita, ya resuelto a partir de unas AudioToVideoOptions."""

    config: AudioToVideoConfig
    durations: list[float]  # una por config.input_files, en el mismo orden


def resolve_audio_to_video(
    opts: AudioToVideoOptions, get_duration: Callable[[Path], float]
) -> AudioToVideoInputs:
    """
    Resuelve las opciones a la entrada de la action y comprueba lo que ffmpeg
    solo diría tarde y mal: que existan la carpeta base, la imagen y los audios.
    La sonda de duración (ffprobe) llega inyectada para probar esto sin ffprobe.

    Se usan las duraciones que ya trae el frontend; solo se consulta ffprobe para
    las que faltan o son 0.
    """
    config = opts.to_config()

    if not config.base_folder.is_dir():
        raise ValueError(f"La carpeta base no existe: {config.base_folder}")
    if config.background_image is not None and not config.background_image.is_file():
        raise ValueError(f"No se encontró la imagen de fondo: {config.background_image}")
    for path in config.input_files:
        if not path.is_file():
            raise ValueError(f"No se encontró el archivo «{path.name}».")

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
    return AudioToVideoInputs(config, durations)


class AudioToVideoAction:

    def plan(self, config: AudioToVideoConfig, durations: list[float]) -> AudioToVideoPlan:
        """
        Dónde quedará el video de cada audio (<base>/videos/<nombre>.mp4) y si ya existe.
        Sin efectos secundarios: no crea carpetas ni escribe nada.

        Es un error que dos audios den el mismo video (a.mp3 y a.wav → a.mp4) o que la
        ruta de salida supere el límite seguro de Windows.
        """
        output_dir = config.base_folder / OUTPUT_SUBFOLDER

        items: list[AudioToVideoItem] = []
        seen: dict[str, Path] = {}  # nombre de salida (sin distinguir mayúsculas) -> audio que lo produce
        for i, (path, duration) in enumerate(zip(config.input_files, durations)):
            output = output_dir / f"{path.stem}{OUTPUT_EXTENSION}"

            earlier = seen.get(output.name.casefold())
            if earlier is not None:
                raise ValueError(
                    f"«{earlier.name}» y «{path.name}» darían el mismo video («{output.name}»). "
                    "Quita uno de los dos."
                )
            seen[output.name.casefold()] = path

            if utf16_len(str(output)) > SAFE_PATH_LIMIT:
                raise ValueError(
                    f"La ruta de «{output.name}» es demasiado larga para Windows "
                    f"(más de {SAFE_PATH_LIMIT} caracteres). Usa una carpeta base más corta."
                )

            items.append(AudioToVideoItem(i, path, duration, output, output.exists()))

        return AudioToVideoPlan(output_dir, items)

    def build_commands(self, config: AudioToVideoConfig, plan: AudioToVideoPlan) -> list[FfmpegCommand]:
        """Un comando por audio. No toca el disco: quien ejecuta crea la carpeta de salida."""
        return [
            FfmpegCommand(
                args=self._build_args(item.path, config, item.output),
                duration=item.duration,
                output=item.output,
                label=item.name,
            )
            for item in plan.files
        ]

    def _build_args(self, audio: Path, config: AudioToVideoConfig, output: Path) -> list[str]:
        encoder    = ENCODERS.get(config.encoder, "libx264")
        resolution = config.resolution or "1280x720"

        if config.background_image:
            video_input = [
                "-framerate", str(config.fps),
                "-loop", "1",
                "-i", str(config.background_image),
            ]
            # Los codecs H.264 exigen ancho y alto pares: una imagen de 101x101 no codificaría
            # (o, con 4:4:4, saldría un video que casi ningún reproductor abre).
            video_filter = ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        else:
            video_input = [
                "-f", "lavfi",
                "-i", f"color=c=black:s={resolution}:r={config.fps}",
            ]
            video_filter = []

        if config.encoder == "nvidia":
            quality_args = ["-cq", str(config.crf), "-tune", "hq"]
        elif config.encoder in ("amd", "intel"):
            quality_args = ["-qp", str(config.crf)]
        else:
            tune         = ["-tune", "stillimage"] if config.background_image else []
            quality_args = ["-crf", str(config.crf), *tune]

        # libx264 conserva el formato de píxel de la imagen (un PNG sale en 4:4:4, un perfil poco
        # compatible): se fuerza 4:2:0. Los encoders por hardware ya negocian su propio formato.
        pix_fmt_args = ["-pix_fmt", "yuv420p"] if config.encoder == "cpu" else []

        preset_args = ["-preset", config.preset] if config.preset else []
        audio_args  = ["-c:a", "copy"] if config.copy_audio else ["-c:a", "aac", "-b:a", "192k"]

        return [
            "-y",
            *video_input,
            "-i", str(audio),
            "-c:v", encoder,
            *video_filter,
            *pix_fmt_args,
            "-r", str(config.fps),
            *quality_args,
            *preset_args,
            *audio_args,
            "-shortest",
            str(output),
        ]
