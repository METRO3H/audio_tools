from pathlib import Path
from typing import Callable

from core.models import MergeAudioConfig


class MergeAudioAction:

    _CONCAT_LIST = Path("_concat_list.txt")

    def build_args(
        self,
        config: MergeAudioConfig,
        on_log: Callable[[str], None] | None = None,
    ) -> list[str]:
        files = self._filter_inputs(config, on_log)
        self._write_concat_list(files)
        return [
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(self._CONCAT_LIST),
            str(config.output_file),
        ]

    def get_output_files(self, config: MergeAudioConfig) -> list[Path]:
        return [config.output_file]

    def cleanup(self) -> None:
        if self._CONCAT_LIST.exists():
            self._CONCAT_LIST.unlink()

    # ── Internals ────────────────────────────────────────────────────────────

    def _filter_inputs(
        self,
        config: MergeAudioConfig,
        on_log: Callable[[str], None] | None,
    ) -> list[Path]:
        output = config.output_file.resolve()
        filtered = [f for f in config.input_files if f.resolve() != output]

        if len(filtered) < len(config.input_files):
            removed = len(config.input_files) - len(filtered)
            msg = f"[AVISO] Se excluyó el archivo merged anterior de los inputs ({removed} archivo(s))."
            if on_log:
                on_log(msg)

        if len(filtered) < 2:
            raise ValueError(
                "Se necesitan al menos 2 archivos para hacer un merge. "
                "Verifica que no estés incluyendo el archivo resultado como input."
            )

        return filtered

    def _write_concat_list(self, files: list[Path]) -> None:
        def escape(path: Path) -> str:
            return path.as_posix().replace("'", "'\\''")
        lines = [f"file '{escape(f)}'" for f in files]
        self._CONCAT_LIST.write_text("\n".join(lines), encoding="utf-8")