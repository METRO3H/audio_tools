import subprocess
import threading
from typing import Callable


class FFmpegRunner:
    """
    Ejecuta comandos ffmpeg en un thread separado para no bloquear la UI.

    Uso:
        runner = FFmpegRunner(ffmpeg_path)
        runner.run(args=["-i", "in.mp3", "out.mp3"], on_log=..., on_done=...)
    """

    def __init__(self, ffmpeg_path: str):
        self._ffmpeg_path = str(ffmpeg_path)
        self._process: subprocess.Popen | None = None

    # ── API pública ───────────────────────────────────────────────────────────

    def run(
        self,
        args: list[str],
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
    ) -> None:
        """
        Lanza ffmpeg con los argumentos dados.
        Llama on_log(line) por cada línea de salida.
        Llama on_done(success) al terminar.

        Los callbacks se invocan desde el worker thread —
        la UI debe usar .after() para actualizarse de forma segura.
        """
        thread = threading.Thread(
            target=self._worker,
            args=(args, on_log, on_done),
            daemon=True,
        )
        thread.start()

    def cancel(self) -> None:
        """Termina el proceso ffmpeg si está corriendo."""
        if self._process and self._process.poll() is None:
            self._process.terminate()

    # ── Internals ─────────────────────────────────────────────────────────────

    # Construye el comando y lanza ffmpeg como subproceso
    # Lee la salida línea por línea mientras ffmpeg corre y avisa vía on_log
    # Cuando termina, revisa el código de retorno y avisa vía on_done
    def _worker(
        self,
        args: list[str],
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
    ) -> None:
        cmd = [self._ffmpeg_path] + args
        success = False

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # ffmpeg mezcla todo en stderr; lo unificamos
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,  # no abre ventana negra en Windows
            )

            for line in self._process.stdout:
                on_log(line.rstrip())

            self._process.wait()
            success = self._process.returncode == 0

        except Exception as e:
            on_log(f"[error] {e}")

        finally:
            self._process = None
            on_done(success)