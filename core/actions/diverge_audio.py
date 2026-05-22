from pathlib import Path

from core.models import DivergeAudioConfig

# Mapeo de extensión de salida a codec ffmpeg
_FORMAT_CODEC: dict[str, str] = {
    "mp3":  "libmp3lame",
    "wav":  "pcm_s16le",
    "aac":  "aac",
    "m4a":  "aac",
    "ogg":  "libvorbis",
    "flac": "flac",
}


class DivergeAudioAction:

    def build_args_list(self, config: DivergeAudioConfig, duration: float) -> list[list[str]]:
        segments = self._calculate_segments(duration, config.interval_seconds)
        output_dir = config.base_folder / "parts"
        output_dir.mkdir(parents=True, exist_ok=True)
        folder_name = config.base_folder.name

        input_ext = config.input_file.suffix.lstrip(".").lower()
        output_ext = config.output_format.lower()
        same_format = input_ext == output_ext

        if same_format:
            # Mismo formato: stream copy directo, solo descartamos cover art
            audio_args = ["-vn", "-c", "copy"]
        else:
            # Formato distinto: re-encodear al codec correspondiente
            codec = _FORMAT_CODEC.get(output_ext, "copy")
            audio_args = ["-vn", "-c:a", codec]

        return [
            [
                "-y",
                "-i", str(config.input_file),
                "-ss", str(start),
                "-to", str(end),
                *audio_args,
                str(output_dir /
                    f"[{i}] {folder_name}.{config.output_format}"),
            ]
            for i, (start, end) in enumerate(segments, 1)
        ]

    def _calculate_segments(self, duration: float, interval: int) -> list[tuple[float, float]]:
        n_full = int(duration // interval)
        remainder = duration % interval

        if n_full == 0:
            return [(0, duration)]

        if remainder == 0:
            return [(i * interval, (i + 1) * interval) for i in range(n_full)]

        segments = [(i * interval, (i + 1) * interval)
                    for i in range(n_full - 1)]

        if remainder < interval / 2:
            split_point = (n_full - 1) * interval + (interval + remainder) / 2
            segments.append(((n_full - 1) * interval, split_point))
            segments.append((split_point, duration))
        else:
            segments.append(((n_full - 1) * interval, n_full * interval))
            segments.append((n_full * interval, duration))

        return segments

    def get_output_files(self, config: DivergeAudioConfig, duration: float) -> list[Path]:
        segments = self._calculate_segments(duration, config.interval_seconds)
        output_dir = config.base_folder / "parts"
        folder_name = config.base_folder.name
        return [
            output_dir / f"[{i}] {folder_name}.{config.output_format}"
            for i, _ in enumerate(segments, 1)
        ]
