"""
Transcribe: resolve, plan y ejecución del job con los runners reales (local y remoto), pero con
faster-whisper y el cliente del mediador simulados.
"""
import sys
import threading
import types
from types import SimpleNamespace

import pytest

if "faster_whisper" not in sys.modules:  # no se necesita el paquete real: el modelo se simula en cada prueba
    _stub = types.ModuleType("faster_whisper")
    _stub.WhisperModel = object
    sys.modules["faster_whisper"] = _stub

from core.jobs import JobEvents  # noqa: E402
from core.models import TranscribeOptions  # noqa: E402
from core.transcription import remote_whisper_runner, whisper_runner  # noqa: E402
from core.transcription.job import resolve_transcribe, run_transcription  # noqa: E402
from core.transcription.transcribe_action import TranscribeAction  # noqa: E402


def make_audio(tmp_path, *names):
    folder = tmp_path / "audios"
    folder.mkdir(exist_ok=True)
    paths = []
    for name in names:
        (folder / name).write_bytes(b"x")
        paths.append(folder / name)
    return paths


def options(tmp_path, names=("a.mp3",), **overrides):
    raw = {"file_paths": [str(tmp_path / "audios" / n) for n in names], "base_folder": str(tmp_path)}
    raw.update(overrides)
    return TranscribeOptions.from_dict(raw)


class Probe:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def __call__(self, path):
        self.calls.append(path.name)
        if self.error:
            raise self.error
        return 42.0


# ── resolve_transcribe ───────────────────────────────────────────────────


def test_known_durations_are_used_without_probing(tmp_path):
    make_audio(tmp_path, "a.mp3")
    probe = Probe()
    configs = resolve_transcribe(options(tmp_path, durations=[10.5]), probe)
    assert configs[0].total_duration == 10.5 and probe.calls == []


def test_only_missing_or_zero_durations_are_probed(tmp_path):
    names = ["a.mp3", "b.mp3", "c.mp3"]
    make_audio(tmp_path, *names)
    probe = Probe()
    configs = resolve_transcribe(options(tmp_path, names, durations=[10, None, 0]), probe)
    assert [c.total_duration for c in configs] == [10.0, 42.0, 42.0] and probe.calls == ["b.mp3", "c.mp3"]


def test_an_unreadable_file_gives_a_readable_error_naming_it(tmp_path):
    make_audio(tmp_path, "a.mp3")
    with pytest.raises(ValueError, match="No se pudo leer la duración de «a.mp3»"):
        resolve_transcribe(options(tmp_path), Probe(error=ValueError("x")))


def test_a_missing_base_folder_is_an_error_and_is_not_created(tmp_path):
    make_audio(tmp_path, "a.mp3")
    ghost = tmp_path / "no_existe"
    with pytest.raises(ValueError, match="La carpeta base no existe"):
        resolve_transcribe(options(tmp_path, base_folder=str(ghost)), Probe())
    assert not ghost.exists()


def test_a_missing_audio_is_an_error_naming_it(tmp_path):
    with pytest.raises(ValueError, match="No se encontró el archivo «a.mp3»"):
        resolve_transcribe(options(tmp_path), Probe())


# ── Plan ─────────────────────────────────────────────────────────────────


def plan_for(tmp_path, names, **overrides):
    make_audio(tmp_path, *names)
    configs = resolve_transcribe(options(tmp_path, names, durations=[10.0] * len(names), **overrides), Probe())
    return TranscribeAction().plan(configs)


def test_each_audio_gets_a_transcription_in_the_language_folder(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3", "b.wav"])
    assert plan.output_dir == tmp_path / "transcriptions" / "japanese"
    assert [f.output for f in plan.files] == [plan.output_dir / "a.srt", plan.output_dir / "b.srt"]
    assert plan.total_duration == 20.0


def test_the_plan_follows_the_format_the_subfolder_and_the_language(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3"], language="zh", output_format="vtt")
    assert plan.files[0].output == tmp_path / "transcriptions" / "chinese" / "a.vtt"
    plan = plan_for(tmp_path, ["a.mp3"], output_subfolder="serie 1")
    assert plan.files[0].output == tmp_path / "transcriptions" / "serie 1" / "a.srt"


def test_the_plan_marks_outputs_that_already_exist(tmp_path):
    out = tmp_path / "transcriptions" / "japanese"
    out.mkdir(parents=True)
    (out / "b.srt").write_text("viejo")
    assert [f.exists for f in plan_for(tmp_path, ["a.mp3", "b.mp3"]).files] == [False, True]


def test_two_audios_that_give_the_same_transcription_are_an_error_naming_both(tmp_path):
    with pytest.raises(ValueError, match="«a.mp3» y «a.wav» darían la misma transcripción"):
        plan_for(tmp_path, ["a.mp3", "a.wav"])


def test_the_collision_check_ignores_case_like_windows_does(tmp_path):
    with pytest.raises(ValueError, match="darían la misma transcripción"):
        plan_for(tmp_path, ["Ep.mp3", "ep.wav"])


def test_a_too_long_output_path_is_an_error(tmp_path):
    cfg = SimpleNamespace(input_file=tmp_path / ("x" * 250 + ".mp3"), base_folder=tmp_path,
                          output_subfolder="japanese", output_format="srt", total_duration=1.0)
    with pytest.raises(ValueError, match="demasiado larga para Windows"):
        TranscribeAction().plan([cfg])


def test_an_empty_batch_is_an_error():
    with pytest.raises(ValueError, match="nada que procesar"):
        TranscribeAction().plan([])


def test_planning_has_no_side_effects(tmp_path):
    plan_for(tmp_path, ["a.mp3"])
    assert not (tmp_path / "transcriptions").exists()


def test_plan_to_dict_shape(tmp_path):
    d = plan_for(tmp_path, ["a.mp3"]).to_dict()
    out = tmp_path / "transcriptions" / "japanese"
    assert d == {
        "output_dir": str(out),
        "files": [{"index": 0, "name": "a.mp3", "path": str(tmp_path / "audios" / "a.mp3"), "duration": 10.0,
                   "output": str(out / "a.srt"), "output_name": "a.srt", "exists": False}],
        "total_duration": 10.0,
    }


# ── run_transcription con un runner falso (se manejan los callbacks a mano) ──


class FakeRunner:
    def __init__(self):
        self.was_cancelled = False
        self.kw = None

    def run_sequential(self, **kw):
        self.kw = kw


class Capture:
    def __init__(self):
        self.events, self.file_logs, self.finished = [], [], 0
        self.job_events = JobEvents(lambda n, d: self.events.append((n, d)), "transcribe", "job-1")

    def emit_file_log(self, index, message):
        self.file_logs.append((index, message))

    def names(self):
        return [n for n, _ in self.events]


def start_fake(tmp_path, names=("a.mp3", "b.mp3"), **overrides):
    make_audio(tmp_path, *names)
    configs = resolve_transcribe(options(tmp_path, names, durations=[10.0] * len(names), **overrides), Probe())
    plan = TranscribeAction().plan(configs)
    runner, cap = FakeRunner(), Capture()

    def finished():
        cap.finished += 1

    run_transcription(runner, configs, plan, cap.job_events, cap.emit_file_log, on_finished=finished)
    return runner, cap, plan


SEGS = [SimpleNamespace(start=0.0, end=1.0, text="hola")]


def test_start_is_emitted_with_the_total_and_every_callback_reaches_the_runner(tmp_path):
    runner, cap, _ = start_fake(tmp_path)
    assert cap.events == [("audiotools:start", {"job_id": "job-1", "tool": "transcribe", "total": 2})]
    assert set(runner.kw) == {"configs", "on_log", "on_done", "on_progress", "on_file_start", "on_file_done"}
    assert len(runner.kw["configs"]) == 2


def test_progress_is_global_and_per_file(tmp_path):
    runner, cap, _ = start_fake(tmp_path)
    kw = runner.kw
    kw["on_file_start"](0)
    kw["on_progress"](0.5)
    kw["on_file_done"](0, SEGS)
    kw["on_file_start"](1)
    progress = [d for n, d in cap.events if n == "audiotools:progress"]
    assert [(p["value"], p["file_index"], p["file_progress"], p["completed"], p["total"]) for p in progress] == [
        (0.0, 0, 0, 0, 2), (0.25, 0, 0.5, 0, 2), (0.5, 0, 1, 1, 2), (0.5, 1, 0, 1, 2),
    ]
    assert all(p["job_id"] == "job-1" for p in progress)


def test_each_transcription_is_written_to_its_planned_path_when_its_file_finishes(tmp_path):
    runner, cap, plan = start_fake(tmp_path, output_format="vtt")
    runner.kw["on_file_done"](1, SEGS)
    assert not plan.files[0].output.exists()
    assert plan.files[1].output.read_text(encoding="utf-8").startswith("WEBVTT")


def test_logs_go_to_the_global_log_and_to_the_current_file(tmp_path):
    runner, cap, _ = start_fake(tmp_path)
    kw = runner.kw
    kw["on_log"]("Cargando modelo")                  # antes de file_start y sin nombre → primer archivo
    kw["on_log"]("Subiendo b.mp3...")                # antes de file_start pero nombra un archivo → ese
    kw["on_file_start"](1)
    kw["on_log"]("[0.00s -> 1.00s] hola")            # ya hay archivo en curso
    assert cap.file_logs == [(0, "Cargando modelo"), (1, "Subiendo b.mp3..."), (1, "[0.00s -> 1.00s] hola")]
    assert [d["message"] for n, d in cap.events if n == "audiotools:log"] == [m for _, m in cap.file_logs]


def test_done_success(tmp_path):
    runner, cap, _ = start_fake(tmp_path)
    runner.kw["on_done"](True, [SEGS, SEGS])
    assert cap.events[-1] == ("audiotools:done", {"job_id": "job-1", "tool": "transcribe", "success": True, "cancelled": False})
    assert cap.finished == 1


def test_done_carries_the_error_message(tmp_path):
    runner, cap, _ = start_fake(tmp_path)
    runner.kw["on_done"](False, [], "El mediador está ocupado")
    assert cap.events[-1][1] == {"job_id": "job-1", "tool": "transcribe", "success": False, "cancelled": False,
                                 "error": "El mediador está ocupado"}


def test_cancelling_is_not_an_error(tmp_path):
    runner, cap, _ = start_fake(tmp_path)
    runner.was_cancelled = True
    runner.kw["on_done"](False, [])
    detail = cap.events[-1][1]
    assert (detail["success"], detail["cancelled"]) == (False, True) and "error" not in detail


def test_a_cancel_that_arrives_after_success_still_counts_as_success(tmp_path):
    runner, cap, _ = start_fake(tmp_path)
    runner.was_cancelled = True
    runner.kw["on_done"](True, [])
    assert cap.events[-1][1]["success"] is True and cap.events[-1][1]["cancelled"] is False


# ── WhisperRunner real (modelo simulado) de punta a punta ────────────────


class FakeModel:
    def __init__(self, segments=None, fail=None, on_segment=None):
        self.segments = segments if segments is not None else [SimpleNamespace(start=0.0, end=2.0, text=" hola ")]
        self.fail, self.on_segment, self.calls = fail, on_segment, []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if self.fail:
            raise self.fail
        info = SimpleNamespace(language="ja", language_probability=0.99)

        def generate():
            for seg in self.segments:
                if self.on_segment:
                    self.on_segment()
                yield seg

        return generate(), info


def run_local(tmp_path, monkeypatch, model, names=("a.mp3", "b.mp3"), **overrides):
    """Ejecuta el job completo con el WhisperRunner real y espera al `done`."""
    created = []

    def fake_whisper_model(size, device, compute_type):
        created.append((size, device, compute_type))
        return model

    monkeypatch.setattr(whisper_runner, "WhisperModel", fake_whisper_model)
    runner = whisper_runner.WhisperRunner()
    make_audio(tmp_path, *names)
    configs = resolve_transcribe(options(tmp_path, names, durations=[2.0] * len(names), **overrides), Probe())
    plan = TranscribeAction().plan(configs)

    cap, finished = Capture(), threading.Event()
    run_transcription(runner, configs, plan, cap.job_events, cap.emit_file_log, on_finished=finished.set)
    assert finished.wait(10), "el job no terminó"
    return runner, cap, plan, created


def test_a_whole_local_job_writes_every_file_and_reports_the_contract(tmp_path, monkeypatch):
    model = FakeModel()
    runner, cap, plan, created = run_local(tmp_path, monkeypatch, model)

    assert created == [("large-v3", "cuda", "int8_float16")]  # el modelo se carga una sola vez
    assert all(f.output.read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> 00:00:02,000\nhola") for f in plan.files)
    names = cap.names()
    assert names[0] == "audiotools:start" and names[-1] == "audiotools:done"
    assert cap.events[-1][1] == {"job_id": "job-1", "tool": "transcribe", "success": True, "cancelled": False}
    last_progress = [d for n, d in cap.events if n == "audiotools:progress"][-1]
    assert last_progress["value"] == 1.0 and last_progress["completed"] == 2
    assert {i for i, _ in cap.file_logs} == {0, 1}
    assert any("hola" in m for _, m in cap.file_logs)


def test_the_language_code_reaches_whisper_and_the_prompt_too(tmp_path, monkeypatch):
    model = FakeModel()
    run_local(tmp_path, monkeypatch, model, names=("a.mp3",), language="zh", initial_prompt="glosario", beam_size=3,
              vad_filter=False)
    kwargs = model.calls[0][1]
    assert (kwargs["language"], kwargs["initial_prompt"], kwargs["beam_size"], kwargs["vad_filter"]) == ("zh", "glosario", 3, False)


def test_a_model_that_fails_to_load_reaches_the_user_as_the_error(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("CUDA no disponible")

    monkeypatch.setattr(whisper_runner, "WhisperModel", boom)
    runner = whisper_runner.WhisperRunner()
    make_audio(tmp_path, "a.mp3")
    configs = resolve_transcribe(options(tmp_path, durations=[2.0]), Probe())
    cap, finished = Capture(), threading.Event()
    run_transcription(runner, configs, TranscribeAction().plan(configs), cap.job_events, cap.emit_file_log, finished.set)
    assert finished.wait(10)
    detail = cap.events[-1][1]
    assert detail["success"] is False and detail["cancelled"] is False
    assert detail["error"] == "RuntimeError: CUDA no disponible"
    assert any("[error] CUDA no disponible" in m for _, m in cap.file_logs)  # y sigue en el log por archivo


def test_a_failure_while_transcribing_a_file_is_the_error(tmp_path, monkeypatch):
    runner, cap, plan, _ = run_local(tmp_path, monkeypatch, FakeModel(fail=ValueError("audio corrupto")))
    assert cap.events[-1][1]["error"] == "audio corrupto" and cap.events[-1][1]["success"] is False
    assert not any(f.output.exists() for f in plan.files)


def test_a_write_failure_is_the_error(tmp_path, monkeypatch):
    (tmp_path / "transcriptions").write_text("soy un archivo, no una carpeta")  # impide crear la subcarpeta
    runner, cap, plan, _ = run_local(tmp_path, monkeypatch, FakeModel(), names=("a.mp3",))
    detail = cap.events[-1][1]
    assert detail["success"] is False and detail["error"]


def test_cancelling_a_local_job_is_cancelled_not_an_error(tmp_path, monkeypatch):
    holder = {}
    model = FakeModel(on_segment=lambda: holder["runner"].cancel())
    created_runner = {}

    def fake_whisper_model(size, device, compute_type):
        return model

    monkeypatch.setattr(whisper_runner, "WhisperModel", fake_whisper_model)
    runner = whisper_runner.WhisperRunner()
    holder["runner"] = runner
    make_audio(tmp_path, "a.mp3", "b.mp3")
    configs = resolve_transcribe(options(tmp_path, ("a.mp3", "b.mp3"), durations=[2.0, 2.0]), Probe())
    plan = TranscribeAction().plan(configs)
    cap, finished = Capture(), threading.Event()
    run_transcription(runner, configs, plan, cap.job_events, cap.emit_file_log, finished.set)
    assert finished.wait(10)
    detail = cap.events[-1][1]
    assert (detail["success"], detail["cancelled"]) == (False, True) and "error" not in detail
    assert not any(f.output.exists() for f in plan.files)


# ── RemoteWhisperRunner real (cliente del mediador simulado) ─────────────


class FakeClient:
    """Sustituye a MediatorClient. `script` recibe el handler de mensajes y los emite."""

    script = staticmethod(lambda handle: None)
    create_error = None
    listen_error = None
    instances = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.cancel_requested = False
        FakeClient.instances.append(self)

    def create_job(self, job_config, files_expected):
        if FakeClient.create_error:
            raise FakeClient.create_error
        self.job_config = job_config
        return {"job_id": "j1", "job_number": 7, "ws_path": "/ws/j1"}

    def upload_file(self, job_id, path, duration, on_slow=None):
        pass

    def listen(self, ws_path, on_message):
        FakeClient.script(on_message)
        if FakeClient.listen_error:
            raise FakeClient.listen_error

    def request_cancel(self):
        self.cancel_requested = True


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(remote_whisper_runner, "MediatorClient", FakeClient)
    FakeClient.script = staticmethod(lambda handle: None)
    FakeClient.create_error = FakeClient.listen_error = None
    FakeClient.instances = []
    return FakeClient


def run_remote(tmp_path, names=("a.mp3",)):
    runner = remote_whisper_runner.RemoteWhisperRunner("10.0.0.5", 9000)
    make_audio(tmp_path, *names)
    target = {"mode": "remote", "host": "10.0.0.5", "port": 9000}
    configs = resolve_transcribe(options(tmp_path, names, durations=[2.0] * len(names), target=target), Probe())
    plan = TranscribeAction().plan(configs)
    cap, finished = Capture(), threading.Event()
    run_transcription(runner, configs, plan, cap.job_events, cap.emit_file_log, finished.set)
    assert finished.wait(10), "el job no terminó"
    return runner, cap, plan


def test_a_whole_remote_job_writes_the_files_it_receives(tmp_path, remote):
    def script(handle):
        handle({"type": "file_start", "file_index": 0})
        handle({"type": "progress", "file_progress": 0.5})
        handle({"type": "result", "file_index": 0, "segments": [{"start": 0, "end": 1.5, "text": " hola "}]})
        handle({"type": "done", "success": True})

    remote.script = staticmethod(script)
    runner, cap, plan = run_remote(tmp_path)
    assert plan.files[0].output.read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> 00:00:01,500\nhola")
    assert cap.events[-1][1] == {"job_id": "job-1", "tool": "transcribe", "success": True, "cancelled": False}
    assert remote.instances[0].job_config["model_size"] == "large-v3"


def test_a_busy_mediator_is_reported_as_the_error(tmp_path, remote):
    remote.create_error = remote_whisper_runner.MediatorBusyError("ya hay un job")
    runner, cap, _ = run_remote(tmp_path)
    detail = cap.events[-1][1]
    assert detail["success"] is False and detail["error"] == "El mediador está ocupado: ya hay un job"


def test_a_rejected_request_is_reported_as_the_error(tmp_path, remote):
    remote.create_error = remote_whisper_runner.MediatorRejectedError("modelo desconocido")
    assert run_remote(tmp_path)[1].events[-1][1]["error"] == "El mediador rechazó la solicitud: modelo desconocido"


def test_an_error_message_from_the_mediator_is_the_error(tmp_path, remote):
    def script(handle):
        handle({"type": "error", "message": "sin VRAM"})
        handle({"type": "done", "success": False})

    remote.script = staticmethod(script)
    detail = run_remote(tmp_path)[1].events[-1][1]
    assert (detail["success"], detail["error"]) == (False, "sin VRAM")


def test_a_failed_done_without_any_message_still_says_something(tmp_path, remote):
    remote.script = staticmethod(lambda handle: handle({"type": "done", "success": False}))
    assert "sin completar" in run_remote(tmp_path)[1].events[-1][1]["error"]


def test_the_mediator_reporting_a_cancel_is_cancelled_not_an_error(tmp_path, remote):
    remote.script = staticmethod(lambda handle: handle({"type": "done", "success": False, "cancelled": True}))
    detail = run_remote(tmp_path)[1].events[-1][1]
    assert (detail["success"], detail["cancelled"]) == (False, True) and "error" not in detail


def test_a_connection_failure_is_the_error(tmp_path, remote):
    remote.listen_error = remote_whisper_runner.MediatorError("se cortó la conexión")
    detail = run_remote(tmp_path)[1].events[-1][1]
    assert (detail["success"], detail["error"]) == (False, "se cortó la conexión")


def test_a_connection_that_drops_because_the_user_cancelled_is_not_an_error(tmp_path, remote):
    runner_box = {}

    def script(handle):
        runner_box["runner"].cancel()  # el usuario cancela; el mediador corta el WebSocket

    remote.script = staticmethod(script)
    remote.listen_error = remote_whisper_runner.MediatorError("conexión cerrada")

    runner = remote_whisper_runner.RemoteWhisperRunner("10.0.0.5", 9000)
    runner_box["runner"] = runner
    make_audio(tmp_path, "a.mp3")
    target = {"mode": "remote", "host": "10.0.0.5", "port": 9000}
    configs = resolve_transcribe(options(tmp_path, durations=[2.0], target=target), Probe())
    cap, finished = Capture(), threading.Event()
    run_transcription(runner, configs, TranscribeAction().plan(configs), cap.job_events, cap.emit_file_log, finished.set)
    assert finished.wait(10)
    detail = cap.events[-1][1]
    assert (detail["success"], detail["cancelled"]) == (False, True) and "error" not in detail
