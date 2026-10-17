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
    locate_progress,
    run_ffmpeg_commands,
    run_ffmpeg_single,
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


# ── warning ──────────────────────────────────────────────────────────────


def test_done_includes_warning_only_when_given():
    log, emit = recorder()
    ev = JobEvents(emit, tool="merge", job_id="j1")
    ev.done(True)
    ev.done(True, warning="No se pudieron incrustar los capítulos")
    assert "warning" not in log[0][1]
    assert log[1][1] == {
        "job_id": "j1", "tool": "merge", "success": True, "cancelled": False,
        "warning": "No se pudieron incrustar los capítulos",
    }


# ── locate_progress (un comando, varios elementos) ───────────────────────


@pytest.mark.parametrize(
    "durations, value, expected",
    [
        ([10, 5], 0.0, (0, 0.0, 0)),
        ([10, 5], 0.5, (0, 0.75, 0)),                 # 7.5 s: va por el 75 % del primero
        ([10, 5], 10 / 15, (1, 0.0, 1)),              # justo en la frontera: ya es el segundo
        ([10, 5], 0.8, (1, 0.4, 1)),                  # 12 s: 2 s del segundo (5 s)
        ([10, 5], 1.0, (1, 1.0, 1)),                  # al final, `completed` es el índice activo (N-1)
        ([10], 0.5, (0, 0.5, 0)),                     # un solo elemento
        ([3, 3, 3], 0.5, (1, 0.5, 1)),
        ([0, 0], 0.7, (1, 0.0, 1)),                   # duraciones desconocidas: sin dividir entre cero
    ],
)
def test_locate_progress(durations, value, expected):
    active, progress, completed = locate_progress(durations, value)
    assert active == expected[0] and completed == expected[2]
    assert progress == pytest.approx(expected[1])


def test_locate_progress_never_goes_past_the_last_element_or_100_percent():
    active, progress, _ = locate_progress([4, 6], 1.7)  # un avance mayor que 1 no debe romper nada
    assert active == 1 and progress == 1.0


# ── run_ffmpeg_single ────────────────────────────────────────────────────


def single_command():
    return FfmpegCommand(args=["-i", "x", "out.mp3"], duration=15.0, label="out.mp3")


def run_single(monkeypatch, outcome, items=(10.0, 5.0), finalize=None, cancel=False, progress=(0.5, 1.0)):
    """FFmpegRunner real (hilo incluido); solo se sustituye el lanzamiento de ffmpeg."""
    runner = FFmpegRunner("ffmpeg")
    seen = {}

    def fake_run_single(args, on_log, on_progress=None, duration=None):
        seen.update(args=args, duration=duration)
        on_log("ffmpeg -> out.mp3")
        for value in progress:
            on_progress(value)
        if cancel:
            runner.cancel()
        return outcome

    monkeypatch.setattr(runner, "_run_single", fake_run_single)
    log = []
    finished = threading.Event()

    def emit(name, detail):
        log.append((name, detail))
        if name == "audiotools:done":
            finished.set()

    run_ffmpeg_single(runner, single_command(), JobEvents(emit, "merge", "job-1"), list(items), finalize)
    assert finished.wait(5), "el job no terminó"
    return log, seen


def test_single_command_event_sequence_and_arguments(monkeypatch):
    log, seen = run_single(monkeypatch, True)
    assert seen == {"args": ["-i", "x", "out.mp3"], "duration": 15.0}
    assert log[0] == ("audiotools:start", {"job_id": "job-1", "tool": "merge", "total": 2})
    assert all(d["job_id"] == "job-1" for _, d in log)

    progress = [d for n, d in log if n == "audiotools:progress"]
    # 0.5 de 15 s = 7.5 s -> archivo 1 al 75 %; 1.0 -> archivo 2 completo. El runner añade siempre
    # un 1.0 final cuando ffmpeg termina bien, de ahí el tercer evento.
    assert [(p["file_index"], round(p["file_progress"], 2), p["completed"], p["total"]) for p in progress] == [
        (0, 0.75, 0, 2), (1, 1.0, 1, 2), (1, 1.0, 1, 2),
    ]
    assert [p["value"] for p in progress] == [0.5, 1.0, 1.0]
    assert log[-1] == ("audiotools:done", {"job_id": "job-1", "tool": "merge", "success": True, "cancelled": False})


def test_finalize_runs_before_done_and_receives_the_outcome(monkeypatch):
    order = []

    def finalize(success):
        order.append(("finalize", success))

    runner_log, _ = run_single(monkeypatch, True, finalize=finalize)
    order.append(("done", runner_log[-1][1]["success"]))
    assert order == [("finalize", True), ("done", True)]


def test_a_text_returned_by_finalize_becomes_a_warning_on_a_successful_job(monkeypatch):
    log, _ = run_single(monkeypatch, True, finalize=lambda ok: "no se pudieron incrustar los capítulos")
    done = log[-1][1]
    assert done["success"] is True and done["warning"] == "no se pudieron incrustar los capítulos"


def test_a_crashing_finalize_still_emits_done_with_a_warning(monkeypatch):
    def finalize(success):
        raise RuntimeError("boom")

    log, _ = run_single(monkeypatch, True, finalize=finalize)
    done = log[-1][1]
    assert done["success"] is True and done["warning"] == "RuntimeError: boom"


def test_failure_calls_finalize_with_false_and_reports_no_error_text(monkeypatch):
    seen = []
    log, _ = run_single(monkeypatch, False, finalize=lambda ok: seen.append(ok))
    done = log[-1][1]
    assert seen == [False]
    assert done["success"] is False and done["cancelled"] is False and "error" not in done and "warning" not in done


def test_cancellation_is_reported_as_cancelled(monkeypatch):
    seen = []
    log, _ = run_single(monkeypatch, False, finalize=lambda ok: seen.append(ok), cancel=True)
    done = log[-1][1]
    assert done["success"] is False and done["cancelled"] is True
    assert seen == [False]


def test_cancel_arriving_after_a_successful_run_is_still_a_success(monkeypatch):
    log, _ = run_single(monkeypatch, True, cancel=True)
    assert log[-1][1]["success"] is True and log[-1][1]["cancelled"] is False


def test_no_items_is_an_error_not_a_silent_success():
    log, emit = recorder()
    events = JobEvents(emit, "merge", "j1")
    with job_errors(events):
        run_ffmpeg_single(object(), single_command(), events, [])
    assert names(log) == ["audiotools:log", "audiotools:done"]
    assert log[1][1]["error"] == "No hay nada que procesar."
