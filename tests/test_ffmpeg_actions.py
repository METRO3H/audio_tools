"""Construcción de comandos y metadatos de ffmpeg (merge, audio→video, chapters)."""
from pathlib import Path

import pytest

from core.actions.audio_to_video import AudioToVideoAction
from core.actions.merge_audio import MergeAudioAction
from core.ffmpeg_runner import FFmpegRunner
from core.models import AudioToVideoConfig, MergeAudioConfig
from core.translation.chapters_runner import ChaptersTranslateRunner


# ── Merge ────────────────────────────────────────────────────────────────


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    # Merge y chapters escriben archivos temporales relativos al CWD.
    monkeypatch.chdir(tmp_path)
    return tmp_path


def merge_config(tmp_path, names=("a.mp3", "b.mp3", "c.mp3"), output="merged.mp3"):
    return MergeAudioConfig(
        input_files=[tmp_path / n for n in names],
        output_file=tmp_path / output,
        base_folder=tmp_path,
    )


def test_merge_build_args_and_concat_list(in_tmp):
    cfg = merge_config(in_tmp)
    args = MergeAudioAction().build_args(cfg)
    assert args == ["-y", "-f", "concat", "-safe", "0", "-i", "_concat_list.txt", str(cfg.output_file)]
    lines = (in_tmp / "_concat_list.txt").read_text(encoding="utf-8").splitlines()
    assert lines == [f"file '{(in_tmp / n).as_posix()}'" for n in ("a.mp3", "b.mp3", "c.mp3")]


def test_merge_concat_list_escapes_single_quotes(in_tmp):
    cfg = merge_config(in_tmp, names=("it's.mp3", "b.mp3"))
    MergeAudioAction().build_args(cfg)
    first = (in_tmp / "_concat_list.txt").read_text(encoding="utf-8").splitlines()[0]
    assert first == f"file '{(in_tmp / 'it').as_posix()}'\\''s.mp3'"


def test_merge_excludes_previous_output_from_inputs_and_logs_it(in_tmp):
    cfg = merge_config(in_tmp, names=("a.mp3", "b.mp3", "merged.mp3"))
    logs = []
    MergeAudioAction().build_args(cfg, on_log=logs.append)
    content = (in_tmp / "_concat_list.txt").read_text(encoding="utf-8")
    assert "merged.mp3" not in content
    assert logs and "excluyó" in logs[0]


def test_merge_requires_at_least_two_inputs(in_tmp):
    cfg = merge_config(in_tmp, names=("a.mp3", "merged.mp3"))
    with pytest.raises(ValueError):
        MergeAudioAction().build_args(cfg)


def test_merge_cleanup_removes_temp_files(in_tmp):
    action = MergeAudioAction()
    action.build_args(merge_config(in_tmp))
    action._write_metadata([in_tmp / "a.mp3"], [1.0])
    action.cleanup()
    assert not (in_tmp / "_concat_list.txt").exists()
    assert not (in_tmp / "_merge_metadata.txt").exists()


EXPECTED_METADATA = (
    ";FFMETADATA1\n\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=10500\ntitle=a\n\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=10500\nEND=15500\ntitle=b\n"
)


def test_merge_metadata_format(in_tmp):
    MergeAudioAction()._write_metadata([in_tmp / "a.mp3", in_tmp / "b.mp3"], [10.5, 5.0])
    assert (in_tmp / "_merge_metadata.txt").read_text(encoding="utf-8") == EXPECTED_METADATA


def test_chapters_translate_metadata_has_same_format_as_merge(in_tmp):
    """
    Hoy son dos implementaciones separadas del mismo formato FFMETADATA1.
    Este test fija que producen el mismo texto, para poder unificarlas sin
    cambiar el resultado.
    """
    chapters = [
        {"index": 1, "title": "a", "start": 0.0, "end": 10.5},
        {"index": 2, "title": "b", "start": 10.5, "end": 15.5},
    ]
    runner = ChaptersTranslateRunner()
    runner._write_metadata(chapters, ["a", "b"])
    assert (in_tmp / "_chapters_translate_metadata.txt").read_text(encoding="utf-8") == EXPECTED_METADATA


def test_chapters_translate_metadata_flattens_newlines_in_titles(in_tmp):
    runner = ChaptersTranslateRunner()
    runner._write_metadata([{"index": 1, "title": "x", "start": 0, "end": 1}], ["  two\nlines  "])
    assert "title=two lines\n" in (in_tmp / "_chapters_translate_metadata.txt").read_text(encoding="utf-8")


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
