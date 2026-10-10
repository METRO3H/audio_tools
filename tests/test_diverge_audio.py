"""
Tests de caracterización de DivergeAudioAction: fijan el comportamiento
ACTUAL (segmentación, nombres de salida, args de ffmpeg) para detectar
cambios no intencionales al refactorizar.
"""
from pathlib import Path

import pytest

from core.actions.diverge_audio import DivergeAudioAction
from core.models import DivergeAudioConfig


@pytest.fixture
def action():
    return DivergeAudioAction()


# ── _calculate_segments ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "duration, interval, expected",
    [
        # menos que un intervalo: un solo segmento
        (20, 30, [(0, 20)]),
        # múltiplo exacto
        (90, 30, [(0, 30), (30, 60), (60, 90)]),
        # resto < interval/2: el último intervalo completo se reparte con el resto
        (100, 30, [(0, 30), (30, 60), (60, 80.0), (80.0, 100)]),
        (95, 30, [(0, 30), (30, 60), (60, 77.5), (77.5, 95)]),
        # justo debajo de la mitad (12 < 15): se reparte
        (102, 30, [(0, 30), (30, 60), (60, 81.0), (81.0, 102)]),
        # resto >= interval/2: el resto queda como segmento propio
        (110, 30, [(0, 30), (30, 60), (60, 90), (90, 110)]),
        # justo en la mitad (15 == 15): NO se reparte
        (105, 30, [(0, 30), (30, 60), (60, 90), (90, 105)]),
        # duración 0 (comportamiento actual: un segmento vacío)
        (0, 30, [(0, 0)]),
    ],
)
def test_calculate_segments(action, duration, interval, expected):
    assert action._calculate_segments(duration, interval) == expected


@pytest.mark.parametrize("duration, interval", [(20, 30), (90, 30), (100, 30), (95, 30), (102, 30), (105, 30), (110, 30), (7261, 600)])
def test_segments_are_contiguous_and_cover_duration(action, duration, interval):
    segs = action._calculate_segments(duration, interval)
    assert segs[0][0] == 0
    assert segs[-1][1] == duration
    for (_, end), (start, _) in zip(segs, segs[1:]):
        assert end == start


def test_segment_count_equals_ceil_of_duration_over_interval(action):
    # El preview del frontend usa Math.ceil(total / interval): el CONTEO
    # coincide con el backend (las duraciones de los dos últimos no).
    import math
    for duration, interval in [(100, 30), (95, 30), (110, 30), (90, 30), (20, 30)]:
        assert len(action._calculate_segments(duration, interval)) == math.ceil(duration / interval)


# ── build_args_list / nombres ────────────────────────────────────────────


def _config(tmp_path, **overrides):
    base = tmp_path / "Proj"
    base.mkdir(exist_ok=True)
    values = dict(
        input_file=tmp_path / "show.mp3",
        base_folder=base,
        output_folder=tmp_path / "out",
        interval_seconds=30,
        output_format="mp3",
        media_type="audio",
        use_subfolder=True,
    )
    values.update(overrides)
    return DivergeAudioConfig(**values)


def test_args_same_format_uses_stream_copy(action, tmp_path):
    cfg = _config(tmp_path)
    args_list = action.build_args_list(cfg, duration=100)
    out_dir = tmp_path / "out" / "audios" / "parts"
    assert out_dir.is_dir()
    assert args_list[0] == [
        "-y", "-i", str(cfg.input_file),
        "-ss", "0", "-to", "30",
        "-vn", "-c", "copy",
        str(out_dir / "[1] Proj.mp3"),
    ]
    assert len(args_list) == 4
    assert args_list[2][3:7] == ["-ss", "60", "-to", "80.0"]


def test_args_different_format_picks_codec(action, tmp_path):
    cfg = _config(tmp_path, output_format="wav")
    args = action.build_args_list(cfg, duration=60)[0]
    assert args[args.index("-vn"):args.index("-vn") + 3] == ["-vn", "-c:a", "pcm_s16le"]
    assert args[-1].endswith("[1] Proj.wav")


def test_args_with_chapters_use_titles_and_chapter_times(action, tmp_path):
    cfg = _config(tmp_path)
    chapters = [
        {"index": 1, "title": "Intro", "start": 0.0, "end": 12.5},
        {"index": 2, "title": "Main", "start": 12.5, "end": 99.0},
    ]
    args_list = action.build_args_list(cfg, duration=99, chapters=chapters)
    assert [Path(a[-1]).name for a in args_list] == ["[1] Proj - Intro.mp3", "[2] Proj - Main.mp3"]
    assert args_list[1][3:7] == ["-ss", "12.5", "-to", "99.0"]


def test_video_mode_names_after_input_stem_and_uses_videos_subfolder(action, tmp_path):
    cfg = _config(tmp_path, input_file=tmp_path / "clip.mp4", output_format="mp4", media_type="video")
    args_list = action.build_args_list(cfg, duration=40)
    assert Path(args_list[0][-1]).parent == tmp_path / "out" / "videos" / "parts"
    assert Path(args_list[0][-1]).name == "[1] clip.mp4"


def test_without_subfolder_writes_directly_to_output_folder(action, tmp_path):
    cfg = _config(tmp_path, use_subfolder=False)
    args_list = action.build_args_list(cfg, duration=30)
    assert Path(args_list[0][-1]).parent == tmp_path / "out"


def test_segment_names_match_actual_output_filenames(action, tmp_path):
    cfg = _config(tmp_path)
    chapters = [{"index": 1, "title": "A", "start": 0, "end": 5}, {"index": 2, "title": "B", "start": 5, "end": 9}]
    for chs in (None, chapters):
        args_list = action.build_args_list(cfg, duration=100, chapters=chs)
        assert [Path(a[-1]).name for a in args_list] == action.get_segment_names(cfg, 100, chs)
