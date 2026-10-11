"""Contrato de eventos y errores de core/jobs.py."""
import threading

import pytest

from core.ffmpeg_runner import FFmpegRunner
from core.jobs import (
    FfmpegCommand,
    JobEvents,
    describe_error,
    job_cancelled,
    job_errors,
    job_id_from,
    run_ffmpeg_commands,
)


def recorder():
    log = []
    return log, lambda name, detail: log.append((name, detail))


def names(log):
    return [name for name, _ in log]


# ── JobEvents ────────────────────────────────────────────────────────────


def test_events_payloads_carry_job_id_and_tool():
    log, emit = recorder()
    ev = JobEvents(emit, tool="diverge", job_id="j1")
    ev.start(3)
    ev.log("hola")
    ev.progress(0.5, 1, 0.5, 1, 3)
    ev.done(True)
    assert log == [
        ("audiotools:start", {"job_id": "j1", "tool": "diverge", "total": 3}),
        ("audiotools:log", {"job_id": "j1", "message": "hola"}),
        ("audiotools:progress", {
            "job_id": "j1", "value": 0.5, "file_index": 1,
            "file_progress": 0.5, "completed": 1, "total": 3,
        }),
        ("audiotools:done", {"job_id": "j1", "tool": "diverge", "success": True, "cancelled": False}),
    ]


def test_done_includes_error_only_when_given():
    log, emit = recorder()
    ev = JobEvents(emit, tool="diverge")
    ev.done(False)
    ev.done(False, "se rompió")
    assert "error" not in log[0][1]
    assert log[1][1]["error"] == "se rompió"
    assert log[0][1]["job_id"] is None


@pytest.mark.parametrize(
    "options, expected",
    [
        ({"job_id": "abc"}, "abc"),
        ({"job_id": ""}, None),
        ({"job_id": "x" * 65}, None),
        ({"job_id": 123}, None),
        ({}, None),
        (None, None),
        ("no soy dict", None),
    ],
)
def test_job_id_from(options, expected):
    assert job_id_from(options) == expected


def test_describe_error_value_error_is_plain_other_errors_show_type():
    assert describe_error(ValueError("mensaje listo")) == "mensaje listo"
    assert describe_error(RuntimeError("boom")) == "RuntimeError: boom"


# ── job_errors ───────────────────────────────────────────────────────────


def test_job_errors_is_silent_when_nothing_fails():
    log, emit = recorder()
    with job_errors(JobEvents(emit, "diverge", "j1")):
        pass
    assert log == []


@pytest.mark.parametrize(
    "exc, expected",
    [(ValueError("opción inválida"), "opción inválida"), (RuntimeError("boom"), "RuntimeError: boom")],
)
def test_job_errors_reports_and_does_not_propagate(exc, expected):
    log, emit = recorder()
    with job_errors(JobEvents(emit, "diverge", "j1")):
        raise exc
    assert names(log) == ["audiotools:log", "audiotools:done"]
    assert log[0][1]["message"] == f"[error] {expected}"
    assert log[1][1] == {
        "job_id": "j1", "tool": "diverge", "success": False, "cancelled": False, "error": expected,
    }


# ── run_ffmpeg_commands ──────────────────────────────────────────────────


def commands():
    return [
        FfmpegCommand(args=["-i", "a", "out1.mp3"], duration=30.0, label="out1.mp3"),
        FfmpegCommand(args=["-i", "a", "out2.mp3"], duration=20.0, label="out2.mp3"),
    ]


def run_with_real_runner(monkeypatch, cmds, outcomes, job_id="job-1"):
    """FFmpegRunner real (hilo incluido); solo se sustituye el lanzamiento de ffmpeg."""
    runner = FFmpegRunner("ffmpeg")
    results = iter(outcomes)
    seen_durations = []

    def fake_run_single(args, on_log, on_progress=None, duration=None):
        seen_durations.append(duration)
        on_log(f"ffmpeg -> {args[-1]}")
        if on_progress and duration:
            on_progress(0.5)
        return next(results)

    monkeypatch.setattr(runner, "_run_single", fake_run_single)

    log = []
    finished = threading.Event()

    def emit(name, detail):
        log.append((name, detail))
        if name == "audiotools:done":
            finished.set()

    run_ffmpeg_commands(runner, cmds, JobEvents(emit, "diverge", job_id))
    assert finished.wait(5), "el job no terminó"
    return log, seen_durations


def test_successful_run_event_sequence(monkeypatch):
    log, seen_durations = run_with_real_runner(monkeypatch, commands(), [True, True])

    assert log[0] == ("audiotools:start", {"job_id": "job-1", "tool": "diverge", "total": 2})
    assert all(detail["job_id"] == "job-1" for _, detail in log)
    assert log[-1] == (
        "audiotools:done",
        {"job_id": "job-1", "tool": "diverge", "success": True, "cancelled": False},
    )

    # cada comando usa SU duración (no una común)
    assert seen_durations == [30.0, 20.0]

    values = [d["value"] for n, d in log if n == "audiotools:progress"]
    assert values == sorted(values) and values[-1] == 1.0
    last = [d for n, d in log if n == "audiotools:progress"][-1]
    assert (last["completed"], last["total"], last["file_progress"]) == (2, 2, 1)


def test_failed_run_reports_done_false_without_error_and_stops(monkeypatch):
    log, seen_durations = run_with_real_runner(monkeypatch, commands(), [True, False])
    assert log[-1][1]["success"] is False and "error" not in log[-1][1]
    assert log[-1][1]["cancelled"] is False  # fallar no es cancelar
    progress = [d for n, d in log if n == "audiotools:progress"]
    assert max(d["completed"] for d in progress) == 1  # el 2º archivo nunca se completó


def test_no_commands_is_an_error_not_a_silent_success():
    log, emit = recorder()
    events = JobEvents(emit, "diverge", "j1")
    with job_errors(events):
        run_ffmpeg_commands(object(), [], events)
    assert names(log) == ["audiotools:log", "audiotools:done"]
    assert log[1][1]["error"] == "No hay nada que procesar."
    assert "audiotools:start" not in names(log)


def test_runner_failure_after_start_still_ends_with_done_error():
    class ExplodingRunner:
        def run_sequential(self, **kwargs):
            raise RuntimeError("boom")

    log, emit = recorder()
    events = JobEvents(emit, "diverge", "j1")
    with job_errors(events):
        run_ffmpeg_commands(ExplodingRunner(), commands(), events)
    assert names(log) == ["audiotools:start", "audiotools:log", "audiotools:done"]
    assert log[-1][1]["error"] == "RuntimeError: boom"


# ── Cancelación (no es un error) ─────────────────────────────────────────


def test_done_cancelled_has_no_error_and_only_counts_when_not_successful():
    log, emit = recorder()
    ev = JobEvents(emit, tool="diverge", job_id="j1")
    ev.done(False, cancelled=True)
    ev.done(True, cancelled=True)  # imposible por contrato: éxito nunca es "cancelado"
    assert log[0][1] == {"job_id": "j1", "tool": "diverge", "success": False, "cancelled": True}
    assert log[1][1]["success"] is True and log[1][1]["cancelled"] is False


class _Runner:
    def __init__(self, was_cancelled):
        self.was_cancelled = was_cancelled


@pytest.mark.parametrize(
    "success, was_cancelled, expected",
    [
        (False, True, True),    # cancelado por el usuario
        (False, False, False),  # falló por sí solo
        (True, True, False),    # cancelar llegó tarde: el job ya había terminado bien
        (True, False, False),
    ],
)
def test_job_cancelled_truth_table(success, was_cancelled, expected):
    assert job_cancelled(_Runner(was_cancelled), success) is expected


def test_job_cancelled_tolerates_runners_without_the_attribute():
    assert job_cancelled(object(), False) is False


def test_ffmpeg_runner_was_cancelled_lifecycle():
    runner = FFmpegRunner("ffmpeg")
    assert runner.was_cancelled is False
    runner.cancel()
    assert runner.was_cancelled is True

    finished = threading.Event()
    runner.run_sequential([], lambda m: None, lambda ok: finished.set())  # una corrida nueva lo reinicia
    assert finished.wait(5)
    assert runner.was_cancelled is False


def run_and_cancel_during(monkeypatch, cancel_on_call, outcomes):
    """Corre 2 comandos con el FFmpegRunner real; llama a runner.cancel() durante el comando N."""
    runner = FFmpegRunner("ffmpeg")
    results = iter(outcomes)
    started = []

    def fake_run_single(args, on_log, on_progress=None, duration=None):
        started.append(args[-1])
        if len(started) == cancel_on_call:
            runner.cancel()
        return next(results)

    monkeypatch.setattr(runner, "_run_single", fake_run_single)
    log = []
    finished = threading.Event()

    def emit(name, detail):
        log.append((name, detail))
        if name == "audiotools:done":
            finished.set()

    run_ffmpeg_commands(runner, commands(), JobEvents(emit, "diverge", "job-1"))
    assert finished.wait(5)
    return log, started


def test_cancel_mid_run_reports_cancelled_not_error_and_stops(monkeypatch):
    log, started = run_and_cancel_during(monkeypatch, cancel_on_call=1, outcomes=[False])
    assert log[-1] == (
        "audiotools:done",
        {"job_id": "job-1", "tool": "diverge", "success": False, "cancelled": True},
    )
    assert started == ["out1.mp3"]  # el segundo comando nunca arrancó
    assert not any("error" in d for n, d in log if n == "audiotools:done")


def test_cancel_between_files_is_also_cancelled(monkeypatch):
    # el 1er comando termina bien y se cancela justo después: el worker lo ve al empezar el 2º
    log, started = run_and_cancel_during(monkeypatch, cancel_on_call=1, outcomes=[True])
    assert log[-1][1]["success"] is False and log[-1][1]["cancelled"] is True
    assert started == ["out1.mp3"]


def test_cancel_arriving_after_the_last_command_is_still_a_success(monkeypatch):
    log, _ = run_and_cancel_during(monkeypatch, cancel_on_call=2, outcomes=[True, True])
    assert log[-1][1]["success"] is True and log[-1][1]["cancelled"] is False
