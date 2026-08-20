import json
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
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return float(result.stdout.strip())


def get_chapters(ffprobe_path: Path, file: Path) -> list[dict]:
    """
    Retorna los chapters del archivo como lista de dicts:
        [{ "index": int, "title": str, "start": float, "end": float }]
    Retorna [] si el archivo no tiene chapters.
    """
    result = subprocess.run(
        [
            str(ffprobe_path),
            "-v", "error",
            "-print_format", "json",
            "-show_chapters",
            str(file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        data = json.loads(result.stdout)
        chapters = data.get("chapters", [])
        return [
            {
                "index": i + 1,
                "title": ch.get("tags", {}).get("title", f"Chapter {i + 1}"),
                "start": float(ch["start_time"]),
                "end":   float(ch["end_time"]),
            }
            for i, ch in enumerate(chapters)
        ]
    except (json.JSONDecodeError, KeyError, ValueError):
        return []
