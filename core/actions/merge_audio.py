from pathlib import Path

from config import FFPROBE_BIN
from core.media_info import get_duration
from core.models import MergeAudioConfig


class MergeAudioAction:

    _CONCAT_LIST = Path("_concat_list.txt")
    _METADATA_FILE = Path("_metadata.txt")

    def build_args(self, config: MergeAudioConfig) -> list[str]:
        self._write_concat_list(config.input_files)
        self._write_metadata(config.input_files)
        return [
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(self._CONCAT_LIST),
            "-i", str(self._METADATA_FILE),
            "-map", "0:a",
            "-map_metadata", "1",
            str(config.output_file),
        ]

    def get_output_files(self, config: MergeAudioConfig) -> list[Path]:
        return [config.output_file]

    def cleanup(self) -> None:
        for f in [self._CONCAT_LIST, self._METADATA_FILE]:
            if f.exists():
                f.unlink()

    def _write_concat_list(self, files: list[Path]) -> None:
        def escape(path: Path) -> str:
            return path.as_posix().replace("'", "'\\''")
        lines = [f"file '{escape(f)}'" for f in files]
        self._CONCAT_LIST.write_text("\n".join(lines), encoding="utf-8")

    def _write_metadata(self, files: list[Path]) -> None:
        lines = [";FFMETADATA1"]
        cursor = 0
        for f in files:
            duration_secs = get_duration(FFPROBE_BIN, f)
            duration_ms = int(duration_secs * 1000)
            lines += [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={cursor}",
                f"END={cursor + duration_ms}",
                f"title={f.stem}",
            ]
            cursor += duration_ms
        self._METADATA_FILE.write_text("\n".join(lines), encoding="utf-8")