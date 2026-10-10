from types import SimpleNamespace

import pytest

from core.transcription.transcribe_action import (
    TranscribeAction,
    build_srt,
    build_txt,
    build_vtt,
    seconds_to_srt_time,
    seconds_to_vtt_time,
)


def seg(start, end, text):
    return SimpleNamespace(start=start, end=end, text=text)


SEGMENTS = [seg(0.0, 1.5, " Hello "), seg(3661.5, 3662.25, "World")]


def test_time_formats():
    assert seconds_to_srt_time(3661.5) == "01:01:01,500"
    assert seconds_to_vtt_time(3661.5) == "01:01:01.500"
    assert seconds_to_srt_time(0) == "00:00:00,000"


@pytest.mark.xfail(
    strict=True,
    reason="BUG conocido: round() de los ms puede dar 1000 -> '00:00:00,1000' (timestamp inválido). "
           "Al corregirlo, este test pasará y xfail estricto avisará para quitar el marcador.",
)
def test_time_rounding_never_produces_1000_ms():
    assert seconds_to_srt_time(0.9996) == "00:00:01,000"


def test_build_srt():
    assert build_srt(SEGMENTS) == (
        "1\n00:00:00,000 --> 00:00:01,500\nHello\n\n"
        "2\n01:01:01,500 --> 01:01:02,250\nWorld\n"
    )


def test_build_vtt():
    out = build_vtt(SEGMENTS)
    assert out.startswith("WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.500\nHello")
    assert "01:01:01.500 --> 01:01:02.250" in out


def test_build_txt():
    assert build_txt(SEGMENTS) == "Hello\nWorld"


def test_output_path_creates_folder_and_uses_stem(tmp_path):
    action = TranscribeAction()
    out = action.get_output_path(tmp_path / "audios" / "ep1.mp3", tmp_path, "japanese", "vtt")
    assert out == tmp_path / "transcriptions" / "japanese" / "ep1.vtt"
    assert out.parent.is_dir()


@pytest.mark.parametrize("fmt, expected_start", [("srt", "1\n00:00:00,000"), ("vtt", "WEBVTT"), ("txt", "Hello")])
def test_write_output_dispatches_by_format(tmp_path, fmt, expected_start):
    action = TranscribeAction()
    path = tmp_path / f"out.{fmt}"
    action.write_output(SEGMENTS, path, fmt)
    assert path.read_text(encoding="utf-8").startswith(expected_start)
