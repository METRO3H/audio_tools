from pathlib import Path
from core.models import MergeAudioConfig


class MergeAudioAction:

    _CONCAT_LIST = Path("_concat_list.txt")

    def build_args(self, config: MergeAudioConfig) -> list[str]:
        self._write_concat_list(config.input_files)
        return [
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(self._CONCAT_LIST),
            str(config.output_file),
        ]

    def cleanup(self) -> None:
        if self._CONCAT_LIST.exists():
            self._CONCAT_LIST.unlink()

    def _write_concat_list(self, files: list[Path]) -> None:
        def escape(path: Path) -> str:
            return path.as_posix().replace("'", "'\\''")
        lines = [f"file '{escape(f)}'" for f in files]
        self._CONCAT_LIST.write_text("\n".join(lines), encoding="utf-8")