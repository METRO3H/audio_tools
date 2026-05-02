import subprocess
from pathlib import Path


def get_duration(ffprobe_path: Path, file: Path) -> float:
    result = subprocess.run(
        [
            str(ffprobe_path),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file),
        ],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return float(result.stdout.strip())