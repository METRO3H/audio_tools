from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineContext:
    base_folder: Path
    current_files: list[Path]
    # Último set de archivos de audio del pipeline.
    # AudioToVideoStep actualiza current_files con los videos pero deja
    # audio_files intacto para que TranscribeStep siempre opere sobre audios.
    audio_files: list[Path] = field(default_factory=list)