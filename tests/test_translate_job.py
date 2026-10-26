"""
Translate SRT: resolve, plan y ejecución del job, con el TranslateRunner real pero un
TranslationBackend simulado (igual que tests/test_translate_retries.py).
"""
import threading

import pytest

from core.jobs import JobEvents
from core.models import TranslateOptions
from core.translation.job import resolve_translate, run_translate_job
from core.translation.runner import TranslateRunner
from core.translation.translate_action import TranslateAction


def make_srt(tmp_path, *names, lines=1):
    folder = tmp_path / "subs"
    folder.mkdir(exist_ok=True)
    body = "\n\n".join(
        f"{i + 1}\n00:00:0{i},000 --> 00:00:0{i + 1},000\nlinea {i + 1}" for i in range(lines)
    )
    paths = []
    for name in names:
        (folder / name).write_text(body + "\n", encoding="utf-8")
        paths.append(folder / name)
    return paths


def options(tmp_path, names=("a.srt",), **overrides):
    raw = {
        "file_paths": [str(tmp_path / "subs" / n) for n in names],
        "base_folder": str(tmp_path),
        "model": "fake.gguf",
    }
    raw.update(overrides)
    return TranslateOptions.from_dict(raw)


# ── resolve_translate ────────────────────────────────────────────────────


def test_a_missing_base_folder_is_an_error_and_is_not_created(tmp_path):
    make_srt(tmp_path, "a.srt")
    ghost = tmp_path / "no_existe"
    with pytest.raises(ValueError, match="La carpeta base no existe"):
        resolve_translate(options(tmp_path, base_folder=str(ghost)))
    assert not ghost.exists()


def test_a_missing_srt_is_an_error_naming_it(tmp_path):
    with pytest.raises(ValueError, match="No se encontró el archivo «a.srt»"):
        resolve_translate(options(tmp_path))


def test_resolve_delegates_the_actual_plan_to_translate_action(tmp_path):
    make_srt(tmp_path, "a.srt", "b.srt")
    plan = resolve_translate(options(tmp_path, ("a.srt", "b.srt"), output_subfolder="mi serie"))
    assert plan.output_dir == tmp_path / "transcriptions" / "mi serie"
    assert [f.output for f in plan.files] == [plan.output_dir / "a.srt", plan.output_dir / "b.srt"]


def test_planning_has_no_side_effects(tmp_path):
    make_srt(tmp_path, "a.srt")
    resolve_translate(options(tmp_path))
    assert not (tmp_path / "transcriptions").exists()


# ── TranslateAction.plan() ───────────────────────────────────────────────


def test_two_srt_that_give_the_same_translation_are_an_error_naming_both(tmp_path):
    with pytest.raises(ValueError, match="«a.srt» y «a.srt» darían la misma traducción"):
        TranslateAction().plan(
            [tmp_path / "x" / "a.srt", tmp_path / "y" / "a.srt"], tmp_path, "english"
        )


def test_the_collision_check_ignores_case_like_windows_does(tmp_path):
    with pytest.raises(ValueError, match="darían la misma traducción"):
        TranslateAction().plan([tmp_path / "Ep.srt", tmp_path / "ep.SRT"], tmp_path, "english")


def test_a_too_long_output_path_is_an_error(tmp_path):
    long_name = ("x" * 250) + ".srt"
    with pytest.raises(ValueError, match="demasiado larga para Windows"):
        TranslateAction().plan([tmp_path / long_name], tmp_path, "english")


def test_an_empty_batch_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="nada que procesar"):
        TranslateAction().plan([], tmp_path, "english")


def test_the_plan_marks_outputs_that_already_exist(tmp_path):
    out = tmp_path / "transcriptions" / "english"
    out.mkdir(parents=True)
    (out / "b.srt").write_text("viejo")
    plan = TranslateAction().plan([tmp_path / "a.srt", tmp_path / "b.srt"], tmp_path, "english")
    assert [f.exists for f in plan.files] == [False, True]


def test_plan_to_dict_shape(tmp_path):
    plan = TranslateAction().plan([tmp_path / "a.srt"], tmp_path, "english")
    out = tmp_path / "transcriptions" / "english"
    assert plan.to_dict() == {
        "output_dir": str(out),
        "files": [{"index": 0, "name": "a.srt", "path": str(tmp_path / "a.srt"),
                   "output": str(out / "a.srt"), "output_name": "a.srt", "exists": False}],
    }


# ── run_translate_job, con el TranslateRunner real y un backend simulado ─


class FakeBackend:
    """
    Implementa TranslationBackend. `respond(n)` arma la respuesta de la n-ésima llamada (0-based)
    — por defecto, siempre "1: Hello N" (válido para translate_block: una línea con id 1, que es
    lo único que generan los .srt de una sola entrada que arma make_srt()). Pasar `respond` a
    mano para escenarios de varias líneas o varios bloques.
    """

    def __init__(self, respond=None):
        self._respond = respond or (lambda n: f"1: Hello {n}")
        self.calls = 0

    def list_models(self):
        return ["fake.gguf"]

    def load(self, model, n_gpu_layers, n_ctx):
        pass

    def unload(self):
        pass

    def is_loaded(self):
        return True

    def get_vram_snapshot(self):
        return None

    def create_chat_completion(self, messages, temperature, max_tokens=-1, stream=True):
        text = self._respond(self.calls)
        self.calls += 1
        mid = len(text) // 2
        return iter([{"choices": [{"delta": {"content": text[:mid]}}]},
                     {"choices": [{"delta": {"content": text[mid:]}}]}])


class Capture:
    def __init__(self, job_id="job-1"):
        self.events = []
        self.finished = 0
        self.job_events = JobEvents(lambda n, d: self.events.append((n, d)), "translate", job_id)

    def emit(self, name, detail):
        self.events.append((name, detail))

    def names(self):
        return [n for n, _ in self.events]

    def of(self, name):
        return [d for n, d in self.events if n == name]


def wait_for_stats(cap):
    """
    Espera a que termine el job, sondeando (TranslateRunner no expone un Event propio). El
    último evento es `audiotools:translate:stats`, NO `audiotools:done`: TranslateRunner lo
    emite en el `finally` de _queue_worker, después de `on_queue_done` (ver core/translation/
    runner.py) — así que esperar por `done` es una carrera que casi siempre se pierde (stats
    llega una instrucción después, en el mismo hilo, sin punto de espera entre medio).
    """
    for _ in range(200):
        if cap.names() and cap.names()[-1] == "audiotools:translate:stats":
            return
        threading.Event().wait(0.05)
    pytest.fail("el job no terminó a tiempo")


def run_job(tmp_path, backend=None, names=("a.srt",), wait=True, **opt_overrides):
    make_srt(tmp_path, *names)
    opts = options(tmp_path, names, **opt_overrides)
    plan = resolve_translate(opts)
    runner = TranslateRunner(backend=backend or FakeBackend())
    cap = Capture()

    def finished():
        cap.finished += 1

    run_translate_job(runner, plan, opts, cap.job_events, cap.emit, on_finished=finished)
    if wait:
        wait_for_stats(cap)
    return runner, cap, plan


def test_start_carries_the_total_and_the_job_id(tmp_path):
    _, cap, _ = run_job(tmp_path, names=("a.srt", "b.srt"))
    assert cap.events[0] == ("audiotools:start", {"job_id": "job-1", "tool": "translate", "total": 2})


def test_a_whole_job_writes_every_file_and_reports_the_contract(tmp_path):
    runner, cap, plan = run_job(tmp_path, names=("a.srt", "b.srt"))
    assert all(f.output.exists() for f in plan.files)
    names = cap.names()
    assert names[0] == "audiotools:start" and names[-1] == "audiotools:translate:stats"
    done = cap.of("audiotools:done")[0]
    assert done["job_id"] == "job-1" and done["tool"] == "translate"
    assert done["success"] is True and done["cancelled"] is False
    assert isinstance(done["elapsed"], float) and done["elapsed"] >= 0


def test_file_events_carry_the_job_id(tmp_path):
    _, cap, _ = run_job(tmp_path)
    files = cap.of("audiotools:file")
    assert len(files) == 2  # start + done de ESE único archivo
    assert all(f["job_id"] == "job-1" for f in files)
    assert [f["done"] for f in files] == [False, True]


def test_progress_is_emitted_per_file(tmp_path):
    _, cap, _ = run_job(tmp_path, names=("a.srt", "b.srt"))
    progress = cap.of("audiotools:progress")
    assert [(p["value"], p["completed"], p["total"]) for p in progress] == [(0.5, 1, 2), (1.0, 2, 2)]
    assert all(p["job_id"] == "job-1" for p in progress)


def test_system_prompt_sections_reach_the_contract_event(tmp_path):
    _, cap, _ = run_job(tmp_path, base_prompt="Translate to English.", glossary="x -> y")
    sections = cap.of("audiotools:translate:system_prompt")[0]["sections"]
    assert sections["base_prompt"] == "Translate to English." and sections["glossary"] == "x -> y"


def test_stats_are_emitted_once_with_the_run_id(tmp_path):
    _, cap, _ = run_job(tmp_path)
    stats = cap.of("audiotools:translate:stats")
    assert len(stats) == 1
    assert stats[0]["total_files"] == 1


def test_on_finished_runs_after_done(tmp_path):
    _, cap, _ = run_job(tmp_path)
    assert cap.finished == 1


def test_cancelling_is_reported_as_cancelled_not_as_an_error(tmp_path):
    """
    Cancela DURANTE la traducción del primer archivo (no antes de arrancar: run_queue() resetea
    _cancelled al arrancar, así que cancelar antes no tendría efecto) — con dos archivos de un
    solo bloque cada uno, el primero llega a escribirse (el corte se chequea entre archivos, no a
    mitad de uno) y el segundo no.
    """
    holder = {}

    def respond(n):
        if n == 1:  # la llamada del archivo 1: cancelar acá deja al archivo 0 ya escrito
            holder["runner"].cancel()
        return "1: Hello"

    runner = TranslateRunner(backend=FakeBackend(respond=respond))
    holder["runner"] = runner

    make_srt(tmp_path, "a.srt", "b.srt")
    opts = options(tmp_path, ("a.srt", "b.srt"))
    plan = resolve_translate(opts)
    cap = Capture()

    run_translate_job(runner, plan, opts, cap.job_events, cap.emit)
    wait_for_stats(cap)

    done = cap.of("audiotools:done")[0]
    assert done["success"] is False and done["cancelled"] is True
    assert "error" not in done
    assert plan.files[0].output.exists() and not plan.files[1].output.exists()
