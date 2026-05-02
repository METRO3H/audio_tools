from pathlib import Path

from core.models import DivergeAudioConfig


class DivergeAudioAction:

    def build_args_list(self, config: DivergeAudioConfig, duration: float) -> list[list[str]]:
        segments = self._calculate_segments(duration, config.interval_seconds)
        output_dir = config.base_folder / "parts"
        output_dir.mkdir(parents=True, exist_ok=True)
        folder_name = config.base_folder.name

        return [
            [
                "-y",
                "-i", str(config.input_file),
                "-ss", str(start),
                "-to", str(end),
                "-c", "copy",
                str(output_dir / f"[{i}] {folder_name}.{config.output_format}"),
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

        segments = [(i * interval, (i + 1) * interval) for i in range(n_full - 1)]

        if remainder < interval / 2:
            split_point = (n_full - 1) * interval + (interval + remainder) / 2
            segments.append(((n_full - 1) * interval, split_point))
            segments.append((split_point, duration))
        else:
            segments.append(((n_full - 1) * interval, n_full * interval))
            segments.append((n_full * interval, duration))

        return segments