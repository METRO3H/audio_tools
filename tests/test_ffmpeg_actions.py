"""Construcción de comandos de ffmpeg (audio→video) y lógica pura del FFmpegRunner."""
from pathlib import Path

import pytest

from core.actions.audio_to_video import AudioToVideoAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import AudioToVideoConfig


# ── Audio → Video ────────────────────────────────────────────────────────


def a2v_config(tmp_path, **overrides):
    values = dict(input_files=[tmp_path / "ep1.mp3"], base_folder=tmp_path, background_image=None)
    values.update(overrides)
    return AudioToVideoConfig(**values)


def test_a2v_default_cpu_black_background(tmp_path):
    cfg = a2v_config(tmp_path)
    args = AudioToVideoAction().build_args_list(cfg)[0]
    assert (tmp_path / "videos").is_dir()
    assert args == [
        "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=1",
        "-i", str(tmp_path / "ep1.mp3"),
        "-c:v", "libx264", "-r", "1", "-crf", "23", "-preset", "medium",
        "-c:a", "copy", "-shortest",
        str(tmp_path / "videos" / "ep1.mp4"),
    ]


def test_a2v_with_image_uses_loop_and_stillimage_tune(tmp_path):
    img = tmp_path / "bg.jpg"
    args = AudioToVideoAction().build_args_list(a2v_config(tmp_path, background_image=img))[0]
    assert args[1:6] == ["-framerate", "1", "-loop", "1", "-i"] and args[6] == str(img)
    assert args[args.index("-tune") + 1] == "stillimage"


@pytest.mark.parametrize(
    "encoder, codec, quality",
    [
        ("nvidia", "h264_nvenc", ["-cq", "23", "-tune", "hq"]),
        ("amd", "h264_amf", ["-qp", "23"]),
        ("intel", "h264_qsv", ["-qp", "23"]),
    ],
)
def test_a2v_hardware_encoders(tmp_path, encoder, codec, quality):
    args = AudioToVideoAction().build_args_list(a2v_config(tmp_path, encoder=encoder))[0]
    assert args[args.index("-c:v") + 1] == codec
    i = args.index(quality[0])
    assert args[i:i + len(quality)] == quality


def test_a2v_reencode_audio_and_empty_preset(tmp_path):
    args = AudioToVideoAction().build_args_list(a2v_config(tmp_path, copy_audio=False, preset=""))[0]
    assert "-preset" not in args
    assert args[args.index("-c:a"):args.index("-c:a") + 4] == ["-c:a", "aac", "-b:a", "192k"]


def test_a2v_output_files(tmp_path):
    cfg = a2v_config(tmp_path, input_files=[tmp_path / "a.mp3", tmp_path / "b.wav"])
    assert AudioToVideoAction().get_output_files(cfg) == [tmp_path / "videos" / "a.mp4", tmp_path / "videos" / "b.mp4"]


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
