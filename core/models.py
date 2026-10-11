import math
from dataclasses import dataclass, field, fields
from pathlib import Path

from core.jobs import job_id_from


@dataclass
class MergeAudioConfig:
    input_files: list[Path]
    output_file: Path
    base_folder: Path


@dataclass
class DivergeAudioConfig:
    input_file: Path
    base_folder: Path        # carpeta base del proyecto (naming en modo audio)
    output_folder: Path      # carpeta real donde se escriben los segmentos
    interval_seconds: int
    output_format: str
    media_type: str = "audio"     # "audio" | "video"
    use_subfolder: bool = True


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _require_text(raw: dict, key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"La opción «{key}» debe ser un texto no vacío.")
    return value


def _optional_text(raw: dict, key: str) -> str | None:
    if raw.get(key) is None:
        return None
    return _require_text(raw, key)


@dataclass
class DivergeOptions:
    """
    Opciones de api.run_diverge / api.plan_diverge tal como llegan del frontend
    (claves snake_case). `from_dict` valida claves y tipos y levanta ValueError
    con un mensaje legible; `to_config` resuelve el DivergeAudioConfig que usa
    la action.

    file_path         archivo fuente
    base_folder       carpeta base del proyecto (nombre de los segmentos en modo audio)
    segment_mode      "interval" (intervalo fijo) | "chapters" (los lee del archivo)
    interval_seconds  obligatorio en modo "interval"; debe ser None en modo "chapters"
    output_folder     SOLO con use_subfolder=False: carpeta donde se escribe
    output_format     por defecto, la extensión del archivo (stream copy)
    media_type        "audio" | "video"
    use_subfolder     True: la carpeta de salida se deduce (audio: base_folder; video:
                      la carpeta del archivo) y se escribe en audios|videos/parts
    duration_seconds  duración ya conocida; evita releerla con ffprobe (la usa el
                      preview; el run la omite y la lee del archivo)
    job_id            lo genera el frontend (ver core/jobs.py)
    """

    file_path: str
    base_folder: str
    segment_mode: str = "interval"
    interval_seconds: float | None = None
    output_folder: str | None = None
    output_format: str | None = None
    media_type: str = "audio"
    use_subfolder: bool = True
    duration_seconds: float | None = None
    job_id: str | None = None

    _REQUIRED = ("file_path", "base_folder")

    @classmethod
    def from_dict(cls, raw) -> "DivergeOptions":
        if not isinstance(raw, dict):
            raise ValueError("Las opciones deben ser un objeto.")

        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError("Opciones desconocidas: " + ", ".join(unknown))
        missing = [k for k in cls._REQUIRED if k not in raw]
        if missing:
            raise ValueError("Faltan opciones: " + ", ".join(missing))

        segment_mode = raw.get("segment_mode", "interval")
        if segment_mode not in ("interval", "chapters"):
            raise ValueError("La opción «segment_mode» debe ser «interval» o «chapters».")

        interval = raw.get("interval_seconds")
        if segment_mode == "interval":
            if not _is_number(interval) or interval <= 0:
                raise ValueError("La opción «interval_seconds» debe ser un número mayor que 0.")
        elif interval is not None:
            raise ValueError("«interval_seconds» no se usa en modo «chapters»; envía null.")

        media_type = raw.get("media_type", "audio")
        if media_type not in ("audio", "video"):
            raise ValueError("La opción «media_type» debe ser «audio» o «video».")

        use_subfolder = raw.get("use_subfolder", True)
        if not isinstance(use_subfolder, bool):
            raise ValueError("La opción «use_subfolder» debe ser verdadero o falso.")

        output_folder = _optional_text(raw, "output_folder")
        if use_subfolder and output_folder is not None:
            raise ValueError("«output_folder» solo se usa con use_subfolder=false; envía null.")
        if not use_subfolder and output_folder is None:
            raise ValueError("Falta «output_folder»: es obligatoria con use_subfolder=false.")

        duration = raw.get("duration_seconds")
        if duration is not None and (not _is_number(duration) or duration <= 0):
            raise ValueError("La opción «duration_seconds» debe ser un número mayor que 0.")

        if raw.get("job_id") is not None and job_id_from(raw) is None:
            raise ValueError("La opción «job_id» no es válida.")

        return cls(
            file_path=_require_text(raw, "file_path"),
            base_folder=_require_text(raw, "base_folder"),
            segment_mode=segment_mode,
            interval_seconds=interval,
            output_folder=output_folder,
            output_format=_optional_text(raw, "output_format"),
            media_type=media_type,
            use_subfolder=use_subfolder,
            duration_seconds=duration,
            job_id=job_id_from(raw),
        )

    def to_config(self) -> DivergeAudioConfig:
        input_file = Path(self.file_path)

        # Carpeta de salida "efectiva": con subcarpeta se deduce sola; sin ella, la elegida.
        if self.use_subfolder:
            output_folder = Path(self.base_folder) if self.media_type == "audio" else input_file.parent
        else:
            output_folder = Path(self.output_folder)

        output_format = self.output_format or input_file.suffix.lstrip(".").lower()
        if not output_format:
            raise ValueError("El archivo no tiene extensión: indica «output_format».")

        return DivergeAudioConfig(
            input_file=input_file,
            base_folder=Path(self.base_folder),
            output_folder=output_folder,
            interval_seconds=self.interval_seconds or 0,
            output_format=output_format,
            media_type=self.media_type,
            use_subfolder=self.use_subfolder,
        )


@dataclass
class AudioToVideoConfig:
    input_files:      list[Path]
    base_folder:      Path
    background_image: Path | None
    encoder:          str   = "cpu"       # cpu | nvidia | amd | intel
    fps:              int   = 1
    crf:              int   = 23
    preset:           str   = "medium"
    resolution:       str   = "1280x720"  # usado solo si no hay imagen
    copy_audio:       bool  = True



@dataclass
class TranscribeConfig:
    input_file:               Path
    base_folder:              Path
    total_duration:           float
    model_size:               str
    device:                   str
    compute_type:             str
    output_subfolder:         str
    beam_size:                int   = 5
    language:                 str   = "ja"
    vad_filter:               bool  = True
    condition_on_previous_text: bool = False
    word_timestamps:          bool  = True
    initial_prompt:           str   = ""
    output_format:            str   = "srt"
