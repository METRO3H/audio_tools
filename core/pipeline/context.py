from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineContext:
    base_folder: Path
    current_files: list[Path] = field(default_factory=list)