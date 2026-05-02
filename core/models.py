from dataclasses import dataclass
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
    input_files: list[Path]
    base_folder: Path
    background_image: Path | None