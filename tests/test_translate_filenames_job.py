"""
Translate Filenames: ejecución del job. Igual que Chapters, NO escribe nada en disco — termina
en audiotools:filenames:preview_ready. apply_filename_renames (el que sí escribe) ya tenía sus
propios tests de antes (no los toqué: su firma no cambió).
"""
import threading

import pytest

from core.jobs import JobEvents
from core.models import FilenamesOptions
from core.translation.filenames_runner import FilenameTranslateRunner
from core.translation.job import run_translate_filenames_job


FILES = [
    {"path": "/x/a", "relative_path": "a", "name": "a", "is_dir": False,
     "detected_lang": "ja", "needs_translation": True},
    {"path": "/x/b", "relative_path": "b", "name": "b.mp4", "is_dir": False,
     "detected_lang": None, "needs_translation": False},
]


class FakeBackend:
    def __init__(self, respond=None):
        self._respond = respond or (lambda n: "0: Translated")
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
        self.job_events = JobEvents(lambda n, d: self.events.append((n, d)), "translate_filenames", job_id)

    def emit(self, name, detail):
        self.events.append((name, detail))

    def names(self):
        return [n for n, _ in self.events]

    def of(self, name):
        return [d for n, d in self.events if n == name]


def wait_for_done(cap):
    for _ in range(200):
        if "audiotools:done" in cap.names():
            return
        threading.Event().wait(0.05)
    pytest.fail("el job no terminó a tiempo")


def run_job(backend=None, **opt_overrides):
    raw = {"files": FILES, "model": "fake.gguf"}
    raw.update(opt_overrides)
    opts = FilenamesOptions.from_dict(raw)
    runner = FilenameTranslateRunner(backend=backend or FakeBackend())
    cap = Capture()

    def finished():
        cap.finished += 1

    run_translate_filenames_job(runner, opts, cap.job_events, cap.emit, on_finished=finished)
    wait_for_done(cap)
    return runner, cap


def test_start_carries_the_total_and_the_job_id():
    _, cap = run_job()
    assert cap.events[0] == ("audiotools:start", {"job_id": "job-1", "tool": "translate_filenames", "total": 2})


def test_preview_ready_has_the_translated_name_and_leaves_what_did_not_need_it_untouched():
    _, cap = run_job()
    preview = cap.of("audiotools:filenames:preview_ready")
    assert len(preview) == 1 and preview[0]["job_id"] == "job-1"
    rows = {f["name"]: f for f in preview[0]["files"]}
    assert rows["a"]["translated_name"] == "Translated"
    assert rows["b.mp4"]["translated_name"] == "b.mp4"  # no necesitaba traducción, intacto


def test_preview_ready_fires_before_done():
    _, cap = run_job()
    names = cap.names()
    assert names.index("audiotools:filenames:preview_ready") < names.index("audiotools:done")


def test_done_reports_success():
    _, cap = run_job()
    done = cap.of("audiotools:done")[0]
    assert done["success"] is True and done["cancelled"] is False


def test_on_finished_runs_after_done():
    _, cap = run_job()
    assert cap.finished == 1


def test_cancelling_is_reported_as_cancelled_with_no_preview():
    """
    Regresión del bug real que motivó runner.cancelled (ver su docstring): translate_preview()
    retorna la MISMA forma (lista con translated_name) tanto si se cancela como si nada
    necesitaba traducción — sin chequear runner.cancelled, esto se vería como un éxito vacío en
    vez de una cancelación.
    """
    holder = {}

    def respond(n):
        holder["runner"].cancel()
        return "0: Translated"

    runner = FilenameTranslateRunner(backend=FakeBackend(respond=respond))
    holder["runner"] = runner
    opts = FilenamesOptions.from_dict({"files": FILES, "model": "fake.gguf"})
    cap = Capture()

    run_translate_filenames_job(runner, opts, cap.job_events, cap.emit)
    wait_for_done(cap)

    done = cap.of("audiotools:done")[0]
    assert done["success"] is False and done["cancelled"] is True
    assert cap.of("audiotools:filenames:preview_ready") == []


def test_a_backend_failure_is_reported_as_an_error_not_an_exception():
    class BrokenBackend(FakeBackend):
        def load(self, model, n_gpu_layers, n_ctx):
            raise RuntimeError("no VRAM")

    _, cap = run_job(backend=BrokenBackend())
    done = cap.of("audiotools:done")[0]
    assert done["success"] is False and "no VRAM" in done["error"]
    assert cap.of("audiotools:filenames:preview_ready") == []
