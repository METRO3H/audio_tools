import re
import subprocess
import threading
from typing import Callable


class FFmpegRunner:

    _TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

    def __init__(self, ffmpeg_path: str):
        self._ffmpeg_path = str(ffmpeg_path)
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    def run(
        self,
        args: list[str],
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
        on_progress: Callable[[float], None] | None = None,
        duration: float | None = None,
    ) -> None:
        self._cancelled = False
        thread = threading.Thread(
            target=self._worker,
            args=(args, on_log, on_done, on_progress, duration),
            daemon=True,
        )
        thread.start()

    def run_sequential(
        self,
        args_list: list[list[str]],
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
        on_progress: Callable[[float], None] | None = None,
        on_file_start: Callable[[int], None] | None = None,
        on_file_done: Callable[[int], None] | None = None,
        durations: list[float] | None = None,
    ) -> None:
        self._cancelled = False
        thread = threading.Thread(
            target=self._sequential_worker,
            args=(args_list, on_log, on_done, on_progress,
                  on_file_start, on_file_done, durations),
            daemon=True,
        )
        thread.start()

    def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def _run_single(
        self,
        args: list[str],
        on_log: Callable[[str], None],
        on_progress: Callable[[float], None] | None = None,
        duration: float | None = None,
    ) -> bool:
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
                line = line.rstrip()
                on_log(line)
                if on_progress and duration:
                    self._parse_progress(line, duration, on_progress)
            self._process.wait()
            return self._process.returncode == 0 and not self._cancelled
        except Exception as e:
            on_log(f"[error] {e}")
            return False
        finally:
            self._process = None

    def _worker(self, args, on_log, on_done, on_progress, duration):
        success = self._run_single(args, on_log, on_progress, duration)
        if on_progress and success:  # ← solo si completó con éxito
            on_progress(1.0)
        on_done(success)

    def _sequential_worker(self, args_list, on_log, on_done, on_progress, on_file_start, on_file_done, durations):
        for i, args in enumerate(args_list):
            if self._cancelled:
                on_done(False)
                return
            on_log(f"--- Parte {i + 1}/{len(args_list)} ---")
            if on_file_start:
                on_file_start(i)
            duration = durations[i] if durations else None
            if not self._run_single(args, on_log, on_progress, duration):
                on_done(False)
                return
            if on_progress:  # ← aquí también, solo si no fue cancelado
                on_progress(1.0)
            if on_file_done:
                on_file_done(i)
        on_done(True)

    def _parse_progress(
        self,
        line: str,
        duration: float,
        on_progress: Callable[[float], None],
    ) -> None:
        match = self._TIME_RE.search(line)
        if match:
            h, m, s = match.groups()
            elapsed = int(h) * 3600 + int(m) * 60 + float(s)
            on_progress(min(elapsed / duration, 1.0))