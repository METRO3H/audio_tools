"""
Merge con ffmpeg/ffprobe REALES: une audios de verdad, incrusta los capítulos y los lee de vuelta.

Usa el ffmpeg de config.py si existe y, si no, el del PATH. Si no hay ninguno (o no puede
generar mp3) las pruebas se saltan.
"""
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

import config
from core.actions.merge_audio import MergeAudioAction, resolve_merge
from core.ffmpeg_runner import FFmpegRunner
from core.jobs import JobEvents, run_ffmpeg_single
from core.media_info import get_chapters, get_duration
from core.models import MergeOptions
from core.process import NO_WINDOW


def _find(configured, name):
    configured = Path(str(configured))
    if configured.exists():
        return configured
    found = shutil.which(name)
    return Path(found) if found else None


FFMPEG = _find(config.FFMPEG_BIN, "ffmpeg")
FFPROBE = _find(config.FFPROBE_BIN, "ffprobe")

pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe no disponibles")


def make_tone(path: Path, seconds: float, freq: int = 440) -> Path:
    result = subprocess.run(
        [str(FFMPEG), "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
         "-c:a", "libmp3lame", str(path)],
        capture_output=True, creationflags=NO_WINDOW,
    )
    if result.returncode != 0:
        pytest.skip("este ffmpeg no puede generar mp3 (libmp3lame)")
    return path


def run_merge_job(tmp_path, file_paths, output_name="Proj", durations=None):
    """Hace lo mismo que api.run_merge, con las piezas reales."""
    options = {"file_paths": [str(p) for p in file_paths], "output_name": output_name, "output_format": "mp3"}
    if durations is not None:
        options["durations"] = durations
    opts = MergeOptions.from_dict(options)
    inputs = resolve_merge(opts, lambda p: get_duration(FFPROBE, p))
    action = MergeAudioAction()
    plan = action.plan(inputs.config, inputs.durations)

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    command = action.build_command(plan, workdir)

    log, finished = [], threading.Event()

    def emit(name, detail):
        log.append((name, detail))
        if name == "audiotools:done":
            finished.set()

    run_ffmpeg_single(
        FFmpegRunner(str(FFMPEG)), command, JobEvents(emit, "merge", "job-1"),
        item_durations=[f.duration for f in plan.files],
        finalize=lambda ok: action.finalize(
            plan, ok, FFMPEG, workdir, probe_duration=lambda p: get_duration(FFPROBE, p)
        ),
    )
    assert finished.wait(60), "el merge no terminó"
    return plan, workdir, log


def approx(value, expected, tol=0.2):
    return abs(value - expected) <= tol


def test_merging_two_files_produces_the_audio_and_one_chapter_per_file(tmp_path, monkeypatch):
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    folder = tmp_path / "audios"
    folder.mkdir()
    a, b = make_tone(folder / "a.mp3", 2.0), make_tone(folder / "b.mp3", 1.0, 660)

    plan, workdir, log = run_merge_job(tmp_path, [a, b])

    done = log[-1][1]
    assert done["success"] is True and done["cancelled"] is False and "warning" not in done
    out = folder / "Proj.mp3"
    assert out.exists()
    assert approx(get_duration(FFPROBE, out), 3.0)

    chapters = get_chapters(FFPROBE, out)
    assert [c["title"] for c in chapters] == ["a", "b"]
    assert approx(chapters[0]["start"], 0.0) and approx(chapters[0]["end"], 2.0)
    assert approx(chapters[1]["start"], 2.0) and approx(chapters[1]["end"], 3.0)

    progress = [d["value"] for n, d in log if n == "audiotools:progress"]
    assert progress and progress[-1] == 1.0 and all(0 <= v <= 1 for v in progress)
    assert not workdir.exists()             # carpeta temporal eliminada
    assert list(elsewhere.iterdir()) == []  # y nada escrito en el directorio de trabajo


def test_regression_a_previous_merge_among_the_inputs_does_not_corrupt_chapters_or_duration(tmp_path):
    """El defecto real: 3 capítulos (el último llegaba hasta 115 s) para un audio de 15 s."""
    folder = tmp_path / "audios"
    folder.mkdir()
    a, b = make_tone(folder / "a.mp3", 2.0), make_tone(folder / "b.mp3", 1.0, 660)
    previous = make_tone(folder / "Proj.mp3", 6.0, 880)   # el merge anterior, MUY distinto en duración

    plan, workdir, log = run_merge_job(tmp_path, [a, b, previous], durations=[2.0, 1.0, 6.0])

    assert [p.name for p in plan.excluded] == ["Proj.mp3"]
    assert log[-1][1]["success"] is True
    out = folder / "Proj.mp3"
    assert approx(get_duration(FFPROBE, out), 3.0)          # NO 9 s
    chapters = get_chapters(FFPROBE, out)
    assert [c["title"] for c in chapters] == ["a", "b"]     # NO ["a", "b", "Proj"]
    assert approx(chapters[-1]["end"], 3.0)

    progress = [d for n, d in log if n == "audiotools:progress"]
    assert max(p["total"] for p in progress) == 2           # 2 archivos efectivos, no 3
    assert not workdir.exists()


def test_an_unreadable_input_is_reported_instead_of_a_silent_truncated_success(tmp_path):
    """
    ffmpeg termina con código 0 aunque no pueda leer un archivo y produce una salida con solo el
    audio anterior. Antes eso daba "Completado"; ahora el job termina con un aviso.
    """
    folder = tmp_path / "audios"
    folder.mkdir()
    a = make_tone(folder / "a.mp3", 2.0)
    missing = folder / "desaparecido.mp3"   # existía al listar, ya no está al ejecutar

    plan, workdir, log = run_merge_job(tmp_path, [a, missing], durations=[2.0, 2.0])

    done = log[-1][1]
    assert done["success"] is True                           # así lo ve ffmpeg
    assert "es posible que falte audio" in done["warning"]   # pero el usuario lo sabe
    assert approx(get_duration(FFPROBE, folder / "Proj.mp3"), 2.0)
    assert not workdir.exists()


def test_a_healthy_merge_carries_no_warning(tmp_path):
    folder = tmp_path / "audios"
    folder.mkdir()
    a, b = make_tone(folder / "a.mp3", 2.0), make_tone(folder / "b.mp3", 2.0, 660)
    _, _, log = run_merge_job(tmp_path, [a, b])
    assert "warning" not in log[-1][1]
