from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleEntry:
    index: int
    timestamp: str
    lines: list[str]


def parse_srt(path: Path) -> list[SubtitleEntry]:
    """
    Parsea un .srt en una lista de SubtitleEntry. Los bloques se separan
    por lineas en blanco. Bloques con menos de 3 filas (indice, timestamp,
    al menos una linea de texto) se descartan silenciosamente.
    """
    raw = path.read_text(encoding="utf-8-sig").strip()
    blocks = raw.split("\n\n")
    entries: list[SubtitleEntry] = []

    for block in blocks:
        rows = [r for r in block.strip().splitlines() if r.strip() != ""]
        if len(rows) < 3:
            continue
        try:
            index = int(rows[0].strip())
        except ValueError:
            continue
        timestamp = rows[1].strip()
        lines = rows[2:]
        entries.append(SubtitleEntry(index=index, timestamp=timestamp, lines=lines))

    return entries


def write_srt(path: Path, entries: list[SubtitleEntry]) -> None:
    blocks = []
    for e in entries:
        text = "\n".join(e.lines)
        blocks.append(f"{e.index}\n{e.timestamp}\n{text}")
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
