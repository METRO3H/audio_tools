from dataclasses import dataclass
from pathlib import Path


@dataclass
class MergeAudioConfig:
    input_files: list[Path]
    output_file: Path
    base_folder: Path