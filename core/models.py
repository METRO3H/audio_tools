import math
from dataclasses import dataclass, field, fields
from pathlib import Path

from core.filenames import sanitize_name
from core.formats import output_formats
from core.jobs import job_id_from
from core import video_encoding
from core.network.remote_target import RemoteTarget, parse_target
from core.transcription import options as whisper_options


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
class MergeAudioConfig:
    input_files: list[Path]
    output_file: Path


@dataclass
class MergeOptions:
    """
    Opciones de api.run_merge / api.plan_merge tal como llegan del frontend
    (claves snake_case). `from_dict` valida claves y tipos y levanta ValueError
    con un mensaje legible.

    file_paths     archivos a unir, en orden (mínimo 2)
    output_name    nombre de salida SIN extensión; se limpia para Windows (core/filenames.py)
    output_format  extensión de salida; debe ser válida para media_type (core/formats.py)
    media_type     "audio" | "video"
    durations      duración conocida de cada archivo (None/0 = desconocida: se lee con ffprobe)
    job_id         lo genera el frontend (ver core/jobs.py)

    La salida se escribe junto al primer archivo: Diverge la busca ahí.
    """

    file_paths: list[str]
    output_name: str
    output_format: str
    media_type: str = "audio"
    durations: list[float | None] | None = None
    job_id: str | None = None

    _REQUIRED = ("file_paths", "output_name", "output_format")

    @classmethod
    def from_dict(cls, raw) -> "MergeOptions":
        if not isinstance(raw, dict):
            raise ValueError("Las opciones deben ser un objeto.")

        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError("Opciones desconocidas: " + ", ".join(unknown))
        missing = [k for k in cls._REQUIRED if k not in raw]
        if missing:
            raise ValueError("Faltan opciones: " + ", ".join(missing))

        paths = raw["file_paths"]
        if not isinstance(paths, list) or not all(isinstance(p, str) and p.strip() for p in paths):
            raise ValueError("La opción «file_paths» debe ser una lista de rutas.")
        if len(paths) < 2:
            raise ValueError("Se necesitan al menos 2 archivos para hacer un merge.")

        media_type = raw.get("media_type", "audio")
        if media_type not in ("audio", "video"):
            raise ValueError("La opción «media_type» debe ser «audio» o «video».")

        name = sanitize_name(_require_text(raw, "output_name"))
        if not name:
            raise ValueError("El nombre de salida no es válido: no queda nada tras quitar los caracteres no permitidos.")

        fmt = _require_text(raw, "output_format").strip().lower()
        if fmt not in output_formats(media_type):
            raise ValueError(
                f"El formato «{fmt}» no es válido para {media_type}. "
                f"Formatos admitidos: {', '.join(output_formats(media_type))}."
            )

        durations = raw.get("durations")
        if durations is not None:
            if not isinstance(durations, list) or len(durations) != len(paths):
                raise ValueError("La opción «durations» debe tener una duración por archivo.")
            if not all(d is None or (_is_number(d) and d >= 0) for d in durations):
                raise ValueError("Cada duración debe ser un número mayor o igual que 0 (o null si se desconoce).")

        if raw.get("job_id") is not None and job_id_from(raw) is None:
            raise ValueError("La opción «job_id» no es válida.")

        return cls(
            file_paths=list(paths),
            output_name=name,
            output_format=fmt,
            media_type=media_type,
            durations=list(durations) if durations is not None else None,
            job_id=job_id_from(raw),
        )

    def to_config(self) -> MergeAudioConfig:
        files = [Path(p) for p in self.file_paths]
        return MergeAudioConfig(
            input_files=files,
            output_file=files[0].parent / f"{self.output_name}.{self.output_format}",
        )


@dataclass
class DivergeAudioConfig:
    input_file: Path
    base_folder: Path        # carpeta base del proyecto (naming en modo audio)
    output_folder: Path      # carpeta real donde se escriben los segmentos
    interval_seconds: int
    output_format: str
    media_type: str = "audio"     # "audio" | "video"
    use_subfolder: bool = True


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


def _whole_number(raw: dict, key: str, default: int) -> int:
    """Entero (los números de JS llegan como int o float con valor entero)."""
    value = raw.get(key, default)
    if not _is_number(value) or not float(value).is_integer():
        raise ValueError(f"La opción «{key}» debe ser un número entero.")
    return int(value)


@dataclass
class AudioToVideoOptions:
    """
    Opciones de api.run_audio_to_video / api.plan_audio_to_video tal como llegan
    del frontend (claves snake_case). `from_dict` valida claves y valores contra
    core/video_encoding.py y levanta ValueError con un mensaje legible;
    `to_config` resuelve el AudioToVideoConfig que usa la action.

    file_paths        audios a convertir (mínimo 1); cada uno produce un video
    base_folder       carpeta base: los videos se escriben en <base_folder>/videos
    background_image  imagen de fondo; None = fondo negro con `resolution`
    encoder           cpu | nvidia | amd | intel
    fps               uno de video_encoding.FPS_OPTIONS
    crf               calidad 0-51 (menor es mejor; es el cq/qp en nvidia/amd/intel)
    preset            uno de video_encoding.PRESETS[encoder]; si falta, el de por defecto
    resolution        solo cuenta sin imagen; una de video_encoding.RESOLUTIONS
    copy_audio        True: copia el audio sin recodificar; False: AAC 192k
    durations         duración conocida de cada audio (None/0 = desconocida: se lee con ffprobe)
    job_id            lo genera el frontend (ver core/jobs.py)
    """

    file_paths: list[str]
    base_folder: str
    background_image: str | None = None
    encoder: str = "cpu"
    fps: int = 1
    crf: int = 23
    preset: str | None = None
    resolution: str = "1280x720"
    copy_audio: bool = True
    durations: list[float | None] | None = None
    job_id: str | None = None

    _REQUIRED = ("file_paths", "base_folder")

    @classmethod
    def from_dict(cls, raw) -> "AudioToVideoOptions":
        if not isinstance(raw, dict):
            raise ValueError("Las opciones deben ser un objeto.")

        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError("Opciones desconocidas: " + ", ".join(unknown))
        missing = [k for k in cls._REQUIRED if k not in raw]
        if missing:
            raise ValueError("Faltan opciones: " + ", ".join(missing))

        paths = raw["file_paths"]
        if not isinstance(paths, list) or not all(isinstance(p, str) and p.strip() for p in paths):
            raise ValueError("La opción «file_paths» debe ser una lista de rutas.")
        if not paths:
            raise ValueError("Selecciona al menos un audio.")

        encoder = raw.get("encoder", "cpu")
        if encoder not in video_encoding.ENCODERS:
            raise ValueError(
                "La opción «encoder» debe ser una de: " + ", ".join(video_encoding.ENCODERS) + "."
            )

        fps = _whole_number(raw, "fps", 1)
        if fps not in video_encoding.FPS_OPTIONS:
            raise ValueError(
                "La opción «fps» debe ser una de: " + ", ".join(map(str, video_encoding.FPS_OPTIONS)) + "."
            )

        low, high = video_encoding.QUALITY_RANGE
        crf = _whole_number(raw, "crf", 23)
        if not low <= crf <= high:
            raise ValueError(f"La opción «crf» debe estar entre {low} y {high}.")

        presets = video_encoding.PRESETS[encoder]
        preset = raw.get("preset")
        if preset is None:
            preset = video_encoding.DEFAULT_PRESETS[encoder]
        elif preset not in presets:
            raise ValueError(
                f"El preset «{preset}» no existe para el encoder «{encoder}»; usa uno de: "
                + ", ".join(presets) + "."
            )

        resolution = raw.get("resolution", "1280x720")
        if resolution not in video_encoding.RESOLUTIONS:
            raise ValueError(
                "La opción «resolution» debe ser una de: " + ", ".join(video_encoding.RESOLUTIONS) + "."
            )

        copy_audio = raw.get("copy_audio", True)
        if not isinstance(copy_audio, bool):
            raise ValueError("La opción «copy_audio» debe ser verdadero o falso.")

        durations = raw.get("durations")
        if durations is not None:
            if (
                not isinstance(durations, list)
                or len(durations) != len(paths)
                or not all(d is None or (_is_number(d) and d >= 0) for d in durations)
            ):
                raise ValueError(
                    "La opción «durations» debe ser una lista con un número (o null) por cada archivo."
                )

        if raw.get("job_id") is not None and job_id_from(raw) is None:
            raise ValueError("La opción «job_id» no es válida.")

        return cls(
            file_paths=list(paths),
            base_folder=_require_text(raw, "base_folder"),
            background_image=_optional_text(raw, "background_image"),
            encoder=encoder,
            fps=fps,
            crf=crf,
            preset=preset,
            resolution=resolution,
            copy_audio=copy_audio,
            durations=durations,
            job_id=job_id_from(raw),
        )

    def to_config(self) -> AudioToVideoConfig:
        return AudioToVideoConfig(
            input_files=[Path(p) for p in self.file_paths],
            base_folder=Path(self.base_folder),
            background_image=Path(self.background_image) if self.background_image else None,
            encoder=self.encoder,
            fps=self.fps,
            crf=self.crf,
            preset=self.preset or video_encoding.DEFAULT_PRESETS[self.encoder],
            resolution=self.resolution,
            copy_audio=self.copy_audio,
        )



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


def _choice(raw: dict, key: str, allowed, default):
    value = raw.get(key, default)
    if value not in allowed:
        raise ValueError(f"La opción «{key}» debe ser una de: " + ", ".join(map(str, allowed)) + ".")
    return value


def _flag(raw: dict, key: str, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"La opción «{key}» debe ser verdadero o falso.")
    return value


@dataclass
class TranscribeOptions:
    """
    Opciones de api.run_transcribe / api.plan_transcribe tal como llegan del frontend
    (claves snake_case). `from_dict` valida claves y valores contra
    core/transcription/options.py y levanta ValueError con un mensaje legible;
    `to_configs` produce la configuración por archivo que usan los runners.

    file_paths                  audios a transcribir (mínimo 1)
    base_folder                 carpeta base: las salidas van a <base>/transcriptions/<subcarpeta>
    model_size                  uno de MODEL_SIZES; con target remoto, el nombre de un modelo del
                                mediador (que es quien conoce su lista)
    device / compute_type       uno de DEVICES y uno de COMPUTE_TYPES[device]
    beam_size                   uno de BEAM_SIZES
    language                    uno de LANGUAGES (código: ja, zh)
    vad_filter, condition_on_previous_text, word_timestamps   interruptores de faster-whisper
    initial_prompt              texto que guía la transcripción ("" = ninguno)
    output_format               uno de OUTPUT_FORMATS
    output_subfolder            UN nombre de carpeta; vacío o ausente = la del idioma. Tras `from_dict`
                                es siempre texto ya resuelto y saneado (ver resolve_subfolder)
    target                      {"mode": "local"} | {"mode": "remote", "host", "port"} (ver
                                core/network/remote_target.py); tras `from_dict` es None (local) o un
                                RemoteTarget
    durations                   duración conocida de cada audio (None/0 = desconocida: se lee con ffprobe)
    job_id                      lo genera el frontend (ver core/jobs.py)
    """

    file_paths: list[str]
    base_folder: str
    model_size: str = whisper_options.DEFAULTS["model_size"]
    device: str = whisper_options.DEFAULTS["device"]
    compute_type: str = whisper_options.DEFAULTS["compute_type"]
    beam_size: int = whisper_options.DEFAULTS["beam_size"]
    language: str = whisper_options.DEFAULTS["language"]
    vad_filter: bool = whisper_options.DEFAULTS["vad_filter"]
    condition_on_previous_text: bool = whisper_options.DEFAULTS["condition_on_previous_text"]
    word_timestamps: bool = whisper_options.DEFAULTS["word_timestamps"]
    initial_prompt: str = ""
    output_format: str = whisper_options.DEFAULTS["output_format"]
    output_subfolder: str | None = None
    target: RemoteTarget | None = None
    durations: list[float | None] | None = None
    job_id: str | None = None

    _REQUIRED = ("file_paths", "base_folder")

    @classmethod
    def from_dict(cls, raw) -> "TranscribeOptions":
        if not isinstance(raw, dict):
            raise ValueError("Las opciones deben ser un objeto.")

        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError("Opciones desconocidas: " + ", ".join(unknown))
        missing = [k for k in cls._REQUIRED if k not in raw]
        if missing:
            raise ValueError("Faltan opciones: " + ", ".join(missing))

        paths = raw["file_paths"]
        if not isinstance(paths, list) or not all(isinstance(p, str) and p.strip() for p in paths):
            raise ValueError("La opción «file_paths» debe ser una lista de rutas.")
        if not paths:
            raise ValueError("Selecciona al menos un audio.")

        target = parse_target(raw.get("target"))

        # Con un mediador remoto, la lista de modelos es la suya (externa a este proyecto): solo se
        # exige un nombre. En local, uno de los conocidos.
        model_size = raw.get("model_size", whisper_options.DEFAULTS["model_size"])
        if target is None:
            model_size = _choice(raw, "model_size", whisper_options.MODEL_SIZES, model_size)
        elif not isinstance(model_size, str) or not model_size.strip():
            raise ValueError("La opción «model_size» debe ser el nombre de un modelo.")

        device = _choice(raw, "device", whisper_options.DEVICES, whisper_options.DEFAULTS["device"])
        compute_type = raw.get("compute_type", whisper_options.DEFAULTS["compute_type"])
        if compute_type not in whisper_options.COMPUTE_TYPES[device]:
            raise ValueError(
                f"La opción «compute_type» debe ser una de: "
                + ", ".join(whisper_options.COMPUTE_TYPES[device])
                + f" (para el dispositivo «{device}»)."
            )

        beam_size = raw.get("beam_size", whisper_options.DEFAULTS["beam_size"])
        if not _is_number(beam_size) or not float(beam_size).is_integer() or int(beam_size) not in whisper_options.BEAM_SIZES:
            raise ValueError(
                "La opción «beam_size» debe ser uno de: " + ", ".join(map(str, whisper_options.BEAM_SIZES)) + "."
            )

        language = _choice(raw, "language", whisper_options.LANGUAGES, whisper_options.DEFAULTS["language"])
        output_format = _choice(
            raw, "output_format", whisper_options.OUTPUT_FORMATS, whisper_options.DEFAULTS["output_format"]
        )

        initial_prompt = raw.get("initial_prompt", "")
        if not isinstance(initial_prompt, str):
            raise ValueError("La opción «initial_prompt» debe ser un texto.")

        subfolder = raw.get("output_subfolder")
        if subfolder is not None and not isinstance(subfolder, str):
            raise ValueError("La opción «output_subfolder» debe ser un texto.")

        durations = raw.get("durations")
        if durations is not None:
            if (
                not isinstance(durations, list)
                or len(durations) != len(paths)
                or not all(d is None or (_is_number(d) and d >= 0) for d in durations)
            ):
                raise ValueError(
                    "La opción «durations» debe ser una lista con un número (o null) por cada archivo."
                )

        if raw.get("job_id") is not None and job_id_from(raw) is None:
            raise ValueError("La opción «job_id» no es válida.")

        return cls(
            file_paths=list(paths),
            base_folder=_require_text(raw, "base_folder"),
            model_size=model_size.strip(),
            device=device,
            compute_type=compute_type,
            beam_size=int(beam_size),
            language=language,
            vad_filter=_flag(raw, "vad_filter", whisper_options.DEFAULTS["vad_filter"]),
            condition_on_previous_text=_flag(
                raw, "condition_on_previous_text", whisper_options.DEFAULTS["condition_on_previous_text"]
            ),
            word_timestamps=_flag(raw, "word_timestamps", whisper_options.DEFAULTS["word_timestamps"]),
            initial_prompt=initial_prompt,
            output_format=output_format,
            output_subfolder=whisper_options.resolve_subfolder(subfolder, language),
            target=target,
            durations=durations,
            job_id=job_id_from(raw),
        )

    def to_configs(self, durations: list[float]) -> list["TranscribeConfig"]:
        """Una configuración por archivo; `durations` (una por archivo) alimenta el progreso."""
        return [
            TranscribeConfig(
                input_file=Path(path),
                base_folder=Path(self.base_folder),
                total_duration=duration,
                model_size=self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                output_subfolder=self.output_subfolder,
                beam_size=self.beam_size,
                language=self.language,
                vad_filter=self.vad_filter,
                condition_on_previous_text=self.condition_on_previous_text,
                word_timestamps=self.word_timestamps,
                initial_prompt=self.initial_prompt,
                output_format=self.output_format,
            )
            for path, duration in zip(self.file_paths, durations)
        ]
