from pathlib import Path


def seconds_to_srt_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments: list) -> str:
    """Convierte una lista de segmentos faster-whisper a texto SRT."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = seconds_to_srt_time(seg.start)
        end   = seconds_to_srt_time(seg.end)
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg.text.strip())
        lines.append("")          # línea en blanco entre bloques
    return "\n".join(lines)


class TranscribeAction:

    def get_output_path(self, input_file: Path, base_folder: Path, subfolder: str) -> Path:
        out_dir = base_folder / "transcriptions" / subfolder
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{input_file.stem}.srt"

    def write_srt(self, segments: list, output_path: Path) -> None:
        output_path.write_text(build_srt(segments), encoding="utf-8")