from pathlib import Path

from core.models import AudioToVideoConfig


class AudioToVideoAction:

    def build_args_list(self, config: AudioToVideoConfig) -> list[list[str]]:
        output_dir = config.base_folder / "translation"
        output_dir.mkdir(parents=True, exist_ok=True)
        return [
            self._build_args(f, config.background_image, output_dir)
            for f in config.input_files
        ]

    def _build_args(self, audio: Path, image: Path | None, output_dir: Path) -> list[str]:
        output = output_dir / f"{audio.stem}.mp4"
        video_input = (
            ["-loop", "1", "-i", str(image)]
            if image
            else ["-f", "lavfi", "-i", "color=c=black:s=1280x720:r=1"]
        )
        return [
            "-y",
            *video_input,
            "-i", str(audio),
            "-c:v", "h264_nvenc",
            "-r", "1",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output),
        ]