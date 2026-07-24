from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MergeAudioConfig:
    input_files: list[Path]
    output_file: Path
    base_folder: Path


@dataclass
class DivergeAudioConfig:
    input_file: Path
    base_folder: Path
    interval_seconds: int
    output_format: str


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