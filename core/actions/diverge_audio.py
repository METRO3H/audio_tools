
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

    def build_args_list(
        self,
        config: DivergeAudioConfig,
        duration: float,
        chapters: list[dict] | None = None,
    ) -> list[list[str]]:
        folder_name, output_dir = self._resolve_naming_and_dir(config)
        output_dir.mkdir(parents=True, exist_ok=True)

        input_ext = config.input_file.suffix.lstrip(".").lower()
        output_ext = config.output_format.lower()
        same_format = input_ext == output_ext

        if same_format:
            audio_args = ["-vn", "-c", "copy"]
        else:
            codec = _FORMAT_CODEC.get(output_ext, "copy")
            audio_args = ["-vn", "-c:a", codec]

        if chapters:
            segments = [(ch["start"], ch["end"], ch["title"])
                        for ch in chapters]
        else:
            segs = self._calculate_segments(duration, config.interval_seconds)
            segments = [(start, end, None) for start, end in segs]

        args_list = []
        for i, (start, end, title) in enumerate(segments, 1):
            if title:
                filename = f"[{i}] {folder_name} - {title}.{config.output_format}"
            else:
                filename = f"[{i}] {folder_name}.{config.output_format}"

            args_list.append([
                "-y",
                "-i", str(config.input_file),
                "-ss", str(start),
                "-to", str(end),
                *audio_args,
                str(output_dir / filename),
            ])

        return args_list

    def get_segment_names(
        self,
        config: DivergeAudioConfig,
        duration: float,
        chapters: list[dict] | None = None,
    ) -> list[str]:
        folder_name, _ = self._resolve_naming_and_dir(config)
        if chapters:
            return [
                f"[{i}] {folder_name} - {ch['title']}.{config.output_format}"
                for i, ch in enumerate(chapters, 1)
            ]
        segs = self._calculate_segments(duration, config.interval_seconds)
        return [
            f"[{i}] {folder_name}.{config.output_format}"
            for i, _ in enumerate(segs, 1)
        ]

    def _resolve_naming_and_dir(self, config: DivergeAudioConfig) -> tuple[str, Path]:
        folder_name = (
            config.input_file.stem if config.media_type == "video" else config.base_folder.name
        )
        if config.use_subfolder:
            subfolder = "videos" if config.media_type == "video" else "audios"
            output_dir = config.output_folder / subfolder / "parts"
        else:
            output_dir = config.output_folder
        return folder_name, output_dir

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

