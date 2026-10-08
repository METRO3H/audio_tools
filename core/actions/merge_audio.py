
from pathlib import Path
from typing import Callable
import subprocess

from core.models import MergeAudioConfig


class MergeAudioAction:

    _CONCAT_LIST = Path("_concat_list.txt")
    _METADATA_FILE = Path("_merge_metadata.txt")

    # ── build_args: IDÉNTICO AL ORIGINAL ────────────────────────────────────
    # No se toca el comando ffmpeg del merge para no afectar el progress tracking.

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
        for path in (self._CONCAT_LIST, self._METADATA_FILE):
            if path.exists():
                path.unlink()

    # ── add_chapters: segundo paso rápido con -c copy ─────────────────────────
    # Se llama DESPUÉS de que el merge terminó. No re-encodea: solo incrusta
    # los chapter markers. Tarda < 1 segundo para cualquier archivo de audio.

    def add_chapters(
        self,
        output_file: Path,
        input_files: list[Path],
        durations: list[float],
        ffmpeg_bin: Path,
    ) -> bool:
        """
        Incrusta chapter markers en el archivo ya generado.
        Cada capítulo recibe el stem del archivo de origen como título.

        Flujo:
          1. Escribe _merge_metadata.txt con los [CHAPTER] bloques
          2. ffmpeg -i output -i metadata -map_metadata 1 -c copy temp
          3. Renombra temp → output

        Devuelve True si tuvo éxito, False si falló (el archivo original se conserva).
        """
        self._write_metadata(input_files, durations)

        temp = output_file.with_suffix(".chapters_tmp" + output_file.suffix)
        try:
            result = subprocess.run(
                [
                    str(ffmpeg_bin), "-y",
                    "-i", str(output_file),
                    "-i", str(self._METADATA_FILE),
                    "-map_metadata", "1",
                    "-c", "copy",
                    str(temp),
                ],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0 and temp.exists():
                temp.replace(output_file)
                return True
            return False
        finally:
            if temp.exists():
                temp.unlink()
            if self._METADATA_FILE.exists():
                self._METADATA_FILE.unlink()

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

    def _write_metadata(self, input_files: list[Path], durations: list[float]) -> None:
        lines = [";FFMETADATA1", ""]
        cursor = 0.0
        for f, dur in zip(input_files, durations):
            start_ms = int(cursor * 1000)
            end_ms = int((cursor + dur) * 1000)
            lines += [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={f.stem}",
                "",
            ]
            cursor += dur
        self._METADATA_FILE.write_text("\n".join(lines), encoding="utf-8")

