
from pathlib import Path


OUTPUT_FORMATS = ["srt", "vtt", "txt"]


def seconds_to_srt_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def seconds_to_vtt_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def build_srt(segments: list) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        start = seconds_to_srt_time(seg.start)
        end   = seconds_to_srt_time(seg.end)
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def build_vtt(segments: list) -> str:
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        start = seconds_to_vtt_time(seg.start)
        end   = seconds_to_vtt_time(seg.end)
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def build_txt(segments: list) -> str:
    return "\n".join(seg.text.strip() for seg in segments)


class TranscribeAction:

    def get_output_path(
        self,
        input_file: Path,
        base_folder: Path,
        subfolder: str,
        output_format: str = "srt",
    ) -> Path:
        out_dir = base_folder / "transcriptions" / subfolder
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{input_file.stem}.{output_format}"

    def write_output(
        self,
        segments: list,
        output_path: Path,
        output_format: str = "srt",
    ) -> None:
        if output_format == "srt":
            content = build_srt(segments)
        elif output_format == "vtt":
            content = build_vtt(segments)
        else:
            content = build_txt(segments)
        output_path.write_text(content, encoding="utf-8")

