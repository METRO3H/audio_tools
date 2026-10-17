"""Escritura e incrustación de capítulos (core/chapters_metadata.py)."""
import re
from pathlib import Path

import pytest

from core import chapters_metadata
from core.chapters_metadata import embed_chapters, write_ffmetadata
from core.translation.chapters_runner import ChaptersTranslateRunner

CHAPTERS = [
    {"title": "a", "start": 0.0, "end": 10.5},
    {"title": "b", "start": 10.5, "end": 15.5},
]

EXPECTED = (
    ";FFMETADATA1\n\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=10500\ntitle=a\n\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=10500\nEND=15500\ntitle=b\n"
)


def test_metadata_format(tmp_path):
    out = tmp_path / "meta.txt"
    write_ffmetadata(out, CHAPTERS)
    assert out.read_text(encoding="utf-8") == EXPECTED


def test_no_chapters_writes_only_the_header(tmp_path):
    out = tmp_path / "meta.txt"
    write_ffmetadata(out, [])
    assert out.read_text(encoding="utf-8") == ";FFMETADATA1\n"


def test_titles_are_flattened_to_a_single_line(tmp_path):
    out = tmp_path / "meta.txt"
    write_ffmetadata(out, [{"title": "  two\nlines\t here  ", "start": 0, "end": 1}])
    assert "title=two lines here\n" in out.read_text(encoding="utf-8")


def test_unicode_titles_survive(tmp_path):
    out = tmp_path / "meta.txt"
    write_ffmetadata(out, [{"title": "第１章：はじめに", "start": 0, "end": 1}])
    assert "title=第１章：はじめに" in out.read_text(encoding="utf-8")


def test_milliseconds_are_rounded_not_truncated(tmp_path):
    # 1.001 * 1000 == 1000.9999999999999 en coma flotante: truncar daría 1000 (1 ms de menos)
    out = tmp_path / "meta.txt"
    write_ffmetadata(out, [{"title": "x", "start": 1.001, "end": 2.002}])
    text = out.read_text(encoding="utf-8")
    assert "START=1001" in text and "END=2002" in text


def test_consecutive_chapters_have_no_gap_or_overlap(tmp_path):
    out = tmp_path / "meta.txt"
    durations = [3.3, 0.1, 7.7, 2.2]
    cursor, chapters = 0.0, []
    for i, d in enumerate(durations):
        chapters.append({"title": str(i), "start": cursor, "end": cursor + d})
        cursor += d
    write_ffmetadata(out, chapters)
    text = out.read_text(encoding="utf-8")
    starts = [int(s) for s in re.findall(r"START=(\d+)", text)]
    ends = [int(e) for e in re.findall(r"END=(\d+)", text)]
    assert starts[1:] == ends[:-1]


def test_same_format_as_the_chapters_translator(tmp_path, monkeypatch):
    """
    El traductor de capítulos tiene hoy su propia copia de este formato y pasará a usar este
    módulo. Este test fija que ambos producen el mismo texto, para poder unificarlos sin cambios.
    """
    monkeypatch.chdir(tmp_path)
    translator_chapters = [
        {"index": 1, "title": "x", "start": 0.0, "end": 10.5},
        {"index": 2, "title": "x", "start": 10.5, "end": 15.5},
    ]
    ChaptersTranslateRunner()._write_metadata(translator_chapters, ["a", "b"])
    theirs = (tmp_path / "_chapters_translate_metadata.txt").read_text(encoding="utf-8")

    out = tmp_path / "meta.txt"
    write_ffmetadata(out, CHAPTERS)
    assert out.read_text(encoding="utf-8") == theirs


# ── embed_chapters (subprocess simulado) ─────────────────────────────────


class FakeRun:
    """Sustituye subprocess.run: registra la llamada y simula lo que haría ffmpeg."""

    def __init__(self, returncode=0, stderr=b"", write_temp=True, content=b"CON CAPITULOS"):
        self.returncode, self.stderr, self.write_temp, self.content = returncode, stderr, write_temp, content
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.write_temp:
            Path(args[-1]).write_bytes(self.content)
        return type("Result", (), {"returncode": self.returncode, "stderr": self.stderr})()


def media(tmp_path):
    f = tmp_path / "Proj.mp3"
    f.write_bytes(b"ORIGINAL")
    return f


def test_embed_runs_ffmpeg_with_the_expected_arguments_and_replaces_the_file(tmp_path, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(chapters_metadata.subprocess, "run", fake)
    work = tmp_path / "work"
    work.mkdir()
    f = media(tmp_path)

    assert embed_chapters("ffmpeg", f, CHAPTERS, work) is None

    args, kwargs = fake.calls[0]
    temp = tmp_path / "Proj.chapters_tmp.mp3"
    assert args == ["ffmpeg", "-y", "-i", str(f), "-i", str(work / "chapters_metadata.txt"),
                    "-map_metadata", "1", "-c", "copy", str(temp)]
    assert kwargs["capture_output"] is True
    assert (work / "chapters_metadata.txt").read_text(encoding="utf-8") == EXPECTED
    assert f.read_bytes() == b"CON CAPITULOS"       # reemplazado
    assert not temp.exists()                          # sin restos


def test_embed_failure_returns_the_reason_and_keeps_the_original(tmp_path, monkeypatch):
    fake = FakeRun(returncode=1, stderr=b"\nuna linea\nError: algo salio mal\n\n")
    monkeypatch.setattr(chapters_metadata.subprocess, "run", fake)
    work = tmp_path / "work"
    work.mkdir()
    f = media(tmp_path)

    assert embed_chapters("ffmpeg", f, CHAPTERS, work) == "Error: algo salio mal"
    assert f.read_bytes() == b"ORIGINAL"
    assert not (tmp_path / "Proj.chapters_tmp.mp3").exists()


def test_embed_failure_without_stderr_still_explains(tmp_path, monkeypatch):
    monkeypatch.setattr(chapters_metadata.subprocess, "run", FakeRun(returncode=3, stderr=b"", write_temp=False))
    work = tmp_path / "work"
    work.mkdir()
    assert "código 3" in embed_chapters("ffmpeg", media(tmp_path), CHAPTERS, work)


def test_embed_with_ok_exit_code_but_no_output_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(chapters_metadata.subprocess, "run", FakeRun(returncode=0, write_temp=False))
    work = tmp_path / "work"
    work.mkdir()
    f = media(tmp_path)
    assert embed_chapters("ffmpeg", f, CHAPTERS, work) is not None
    assert f.read_bytes() == b"ORIGINAL"


def test_embed_propagates_when_ffmpeg_cannot_run_and_leaves_no_temp(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("ffmpeg no encontrado")

    monkeypatch.setattr(chapters_metadata.subprocess, "run", boom)
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(FileNotFoundError):
        embed_chapters("ffmpeg", media(tmp_path), CHAPTERS, work)
    assert not (tmp_path / "Proj.chapters_tmp.mp3").exists()
