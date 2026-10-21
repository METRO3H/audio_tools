"""
Audio→Video con ffmpeg/ffprobe REALES: genera videos de verdad y lee de vuelta su formato.

Usa el ffmpeg de config.py si existe y, si no, el del PATH. Si no hay ninguno las pruebas
se saltan. Los encoders por hardware no se prueban (dependen de la máquina).
"""
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

import config
from core.actions.audio_to_video import AudioToVideoAction, resolve_audio_to_video
from core.ffmpeg_runner import FFmpegRunner
from core.jobs import JobEvents, run_ffmpeg_commands
from core.media_info import get_duration
from core.models import AudioToVideoOptions
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


def _ffmpeg(*args):
    return subprocess.run([str(FFMPEG), "-v", "error", "-y", *args], capture_output=True, creationflags=NO_WINDOW)


def make_audio(path: Path, seconds: float, codec: str = "libmp3lame") -> Path:
    if _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", codec, str(path)).returncode != 0:
        pytest.skip(f"este ffmpeg no puede generar audio con {codec}")
    return path


def make_image(path: Path, size: str) -> Path:
    assert _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={size}:rate=1", "-frames:v", "1", str(path)).returncode == 0
    return path


def video_stream(path: Path) -> dict:
    out = subprocess.run(
        [str(FFPROBE), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=pix_fmt,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    ).stdout
    return json.loads(out)["streams"][0]


def run_job(tmp_path, names, **overrides):
    """Hace lo mismo que api.run_audio_to_video, con las piezas reales."""
    raw = {"file_paths": [str(tmp_path / "audios" / n) for n in names], "base_folder": str(tmp_path)}
    raw.update(overrides)
    opts = AudioToVideoOptions.from_dict(raw)
    inputs = resolve_audio_to_video(opts, lambda p: get_duration(FFPROBE, p))
    action = AudioToVideoAction()
    plan = action.plan(inputs.config, inputs.durations)
    commands = action.build_commands(inputs.config, plan)
    plan.output_dir.mkdir(parents=True, exist_ok=True)

    log, finished = [], threading.Event()

    def emit(name, detail):
        log.append((name, detail))
        if name == "audiotools:done":
            finished.set()

    run_ffmpeg_commands(FFmpegRunner(str(FFMPEG)), commands, JobEvents(emit, "audio_to_video", "job-1"))
    assert finished.wait(120), "el job no terminó"
    return plan, log


def audios(tmp_path, *specs):
    folder = tmp_path / "audios"
    folder.mkdir(exist_ok=True)
    return [make_audio(folder / name, seconds) for name, seconds in specs]


def test_a_black_background_gives_a_420_video_of_the_audio_duration_with_its_audio(tmp_path):
    audios(tmp_path, ("ep1.mp3", 2.0))
    plan, log = run_job(tmp_path, ["ep1.mp3"])

    assert log[-1][1]["success"] is True and log[-1][1]["cancelled"] is False
    out = tmp_path / "videos" / "ep1.mp4"
    assert video_stream(out) == {"width": 1280, "height": 720, "pix_fmt": "yuv420p"}
    assert abs(get_duration(FFPROBE, out) - 2.0) < 0.5


def test_regression_a_png_with_odd_dimensions_gives_even_dimensions_and_420(tmp_path):
    """Antes: salía 101x101 en yuv444p (perfil «High 4:4:4 Predictive», que casi nada reproduce)."""
    audios(tmp_path, ("ep1.mp3", 2.0))
    image = make_image(tmp_path / "bg.png", "101x101")
    plan, log = run_job(tmp_path, ["ep1.mp3"], background_image=str(image))

    assert log[-1][1]["success"] is True
    assert video_stream(tmp_path / "videos" / "ep1.mp4") == {"width": 100, "height": 100, "pix_fmt": "yuv420p"}


def test_an_image_with_even_dimensions_keeps_its_size_and_becomes_420(tmp_path):
    audios(tmp_path, ("ep1.mp3", 2.0))
    image = make_image(tmp_path / "bg.png", "640x360")
    run_job(tmp_path, ["ep1.mp3"], background_image=str(image))
    assert video_stream(tmp_path / "videos" / "ep1.mp4") == {"width": 640, "height": 360, "pix_fmt": "yuv420p"}


def test_several_audios_run_in_order_with_the_contract_events(tmp_path):
    audios(tmp_path, ("a.mp3", 1.0), ("b.mp3", 2.0))
    plan, log = run_job(tmp_path, ["a.mp3", "b.mp3"])

    names = [n for n, _ in log]
    assert names[0] == "audiotools:start" and names[-1] == "audiotools:done"
    assert log[0][1] == {"job_id": "job-1", "tool": "audio_to_video", "total": 2}
    assert all(d["job_id"] == "job-1" for _, d in log)
    assert [f.output.name for f in plan.files] == ["a.mp4", "b.mp4"]
    assert all(f.output.exists() for f in plan.files)

    progress = [d for n, d in log if n == "audiotools:progress"]
    assert progress[-1]["value"] == 1.0 and progress[-1]["completed"] == 2
    assert all(0 <= p["value"] <= 1 for p in progress)
    assert {p["file_index"] for p in progress} == {0, 1}


@pytest.mark.parametrize("codec, ext", [("pcm_s16le", "wav"), ("flac", "flac")])
def test_copying_the_audio_works_for_the_other_input_formats(tmp_path, codec, ext):
    folder = tmp_path / "audios"
    folder.mkdir()
    make_audio(folder / f"ep1.{ext}", 1.0, codec)
    plan, log = run_job(tmp_path, [f"ep1.{ext}"], copy_audio=True)
    assert log[-1][1]["success"] is True
    assert (tmp_path / "videos" / "ep1.mp4").stat().st_size > 0


def test_re_encoding_the_audio_also_works(tmp_path):
    audios(tmp_path, ("ep1.mp3", 1.0))
    plan, log = run_job(tmp_path, ["ep1.mp3"], copy_audio=False)
    assert log[-1][1]["success"] is True
