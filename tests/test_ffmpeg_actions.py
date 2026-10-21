"""Lógica pura del FFmpegRunner (los comandos de Audio→Video están en test_audio_to_video.py)."""
from pathlib import Path

import pytest

from core.ffmpeg_runner import FFmpegRunner


# ── FFmpegRunner (lógica pura, sin lanzar ffmpeg) ─────────────────────────


def test_ffmpeg_progress_parsing():
    runner = FFmpegRunner("ffmpeg")
    seen = []
    runner._parse_progress("size=1kB time=00:01:30.50 bitrate=1", 180.0, seen.append)
    runner._parse_progress("time=01:00:00.00", 180.0, seen.append)  # se limita a 1.0
    runner._parse_progress("sin tiempo", 180.0, seen.append)         # sin match: no emite
    assert seen == [pytest.approx(90.5 / 180.0), 1.0]


def test_ffmpeg_sequential_worker_stops_at_first_failure(monkeypatch):
    runner = FFmpegRunner("ffmpeg")
    results = iter([True, False, True])
    ran = []
    monkeypatch.setattr(runner, "_run_single", lambda args, *a, **k: (ran.append(args), next(results))[1])

    events = {"start": [], "done": [], "progress": [], "finished": []}
    runner._sequential_worker(
        [["a"], ["b"], ["c"]],
        on_log=lambda m: None,
        on_done=events["finished"].append,
        on_progress=events["progress"].append,
        on_file_start=events["start"].append,
        on_file_done=events["done"].append,
        durations=None,
    )
    assert ran == [["a"], ["b"]]
    assert events["start"] == [0, 1]
    assert events["done"] == [0]
    assert events["progress"] == [1.0]
    assert events["finished"] == [False]


def test_ffmpeg_sequential_worker_success(monkeypatch):
    runner = FFmpegRunner("ffmpeg")
    monkeypatch.setattr(runner, "_run_single", lambda *a, **k: True)
    finished = []
    runner._sequential_worker([["a"], ["b"]], lambda m: None, finished.append, None, None, None, None)
    assert finished == [True]
