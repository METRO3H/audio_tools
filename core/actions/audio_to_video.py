from pathlib import Path
from core.models import AudioToVideoConfig


# Encoders soportados con sus nombres ffmpeg
ENCODERS = {
    "cpu":    "libx264",
    "nvidia": "h264_nvenc",
    "amd":    "h264_amf",
    "intel":  "h264_qsv",
}


class AudioToVideoAction:

    def build_args_list(self, config: AudioToVideoConfig) -> list[list[str]]:
        output_dir = config.base_folder / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)
        return [
            self._build_args(f, config, output_dir)
            for f in config.input_files
        ]

    def get_output_files(self, config: AudioToVideoConfig) -> list[Path]:
        output_dir = config.base_folder / "videos"
        return [output_dir / f"{f.stem}.mp4" for f in config.input_files]

    def _build_args(
        self,
        audio: Path,
        config: AudioToVideoConfig,
        output_dir: Path,
    ) -> list[str]:
        output     = output_dir / f"{audio.stem}.mp4"
        encoder    = ENCODERS.get(config.encoder, "libx264")
        resolution = config.resolution or "1280x720"

        if config.background_image:
            video_input = [
                "-framerate", str(config.fps),
                "-loop", "1",
                "-i", str(config.background_image),
            ]
        else:
            video_input = [
                "-f", "lavfi",
                "-i", f"color=c=black:s={resolution}:r={config.fps}",
            ]

        if config.encoder == "nvidia":
            quality_args = ["-cq", str(config.crf), "-tune", "hq"]
        elif config.encoder in ("amd", "intel"):
            quality_args = ["-qp", str(config.crf)]
        else:
            tune         = ["-tune", "stillimage"] if config.background_image else []
            quality_args = ["-crf", str(config.crf), *tune]

        preset_args = ["-preset", config.preset] if config.preset else []
        audio_args  = ["-c:a", "copy"] if config.copy_audio else ["-c:a", "aac", "-b:a", "192k"]

        return [
            "-y",
            *video_input,
            "-i", str(audio),
            "-c:v", encoder,
            "-r", str(config.fps),
            *quality_args,
            *preset_args,
            *audio_args,
            "-shortest",
            str(output),
        ]