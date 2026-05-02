import subprocess
import threading
from typing import Callable


class FFmpegRunner:

    def __init__(self, ffmpeg_path: str):
        self._ffmpeg_path = str(ffmpeg_path)
        self._process: subprocess.Popen | None = None

    def run(
        self,
        args: list[str],
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
    ) -> None:
        thread = threading.Thread(
            target=self._worker,
            args=(args, on_log, on_done),
            daemon=True,
        )
        thread.start()

    def run_sequential(
        self,
        args_list: list[list[str]],
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
    ) -> None:
        thread = threading.Thread(
            target=self._sequential_worker,
            args=(args_list, on_log, on_done),
            daemon=True,
        )
        thread.start()

    def cancel(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def _run_single(self, args: list[str], on_log: Callable[[str], None]) -> bool:
        cmd = [self._ffmpeg_path] + args
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in self._process.stdout:
                on_log(line.rstrip())
            self._process.wait()
            return self._process.returncode == 0
        except Exception as e:
            on_log(f"[error] {e}")
            return False
        finally:
            self._process = None

    def _worker(self, args, on_log, on_done):
        on_done(self._run_single(args, on_log))

    def _sequential_worker(self, args_list, on_log, on_done):
        for i, args in enumerate(args_list, 1):
            on_log(f"--- Parte {i}/{len(args_list)} ---")
            if not self._run_single(args, on_log):
                on_done(False)
                return
        on_done(True)