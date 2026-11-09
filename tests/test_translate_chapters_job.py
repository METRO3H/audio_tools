"""
Translate Chapters: resolve, plan y ejecución del job. A diferencia de Translate SRT, acá NO se
escribe nada en disco — el job termina en audiotools:translation:preview_ready con los títulos
traducidos, no con archivos escritos. Eso es ChaptersAction.apply, que se prueba aparte (ver
tests/test_chapters_metadata.py para el "subprocess simulado" de embed_chapters, y el final de
este archivo para apply() en sí).
"""
import threading

import pytest

from core.jobs import JobEvents
from core.models import ChaptersOptions
from core.translation.chapters_action import ChaptersAction
from core.translation.chapters_runner import ChaptersTranslateRunner
from core.translation.job import resolve_translate_chapters, run_translate_chapters_job


CHAPTERS = [
    {"index": 1, "title": "Introducción", "start": 0.0, "end": 60.0},
    {"index": 2, "title": "Desarrollo", "start": 60.0, "end": 300.0},
]


def fake_get_chapters(chapters_by_path):
    def get(path):
        return chapters_by_path.get(str(path), [])
    return get


def make_file(tmp_path, name):
    f = tmp_path / name
    f.write_bytes(b"not a real media file")
    return f


def options(**overrides):
    raw = {"file_paths": [], "model": "fake.gguf"}
    raw.update(overrides)
    return ChaptersOptions.from_dict(raw)


# ── resolve_translate_chapters ───────────────────────────────────────────


def test_a_missing_file_is_an_error_naming_it(tmp_path):
    with pytest.raises(ValueError, match="No se encontró el archivo «a.mp4»"):
        resolve_translate_chapters(options(file_paths=[str(tmp_path / "a.mp4")]), fake_get_chapters({}))


def test_a_file_without_chapters_is_an_error_naming_it(tmp_path):
    f = make_file(tmp_path, "a.mp4")
    with pytest.raises(ValueError, match="«a.mp4» no tiene capítulos"):
        resolve_translate_chapters(options(file_paths=[str(f)]), fake_get_chapters({str(f): []}))


def test_resolve_reads_the_chapters_of_every_file(tmp_path):
    a, b = make_file(tmp_path, "a.mp4"), make_file(tmp_path, "b.mp4")
    get = fake_get_chapters({str(a): CHAPTERS, str(b): CHAPTERS[:1]})
    plan = resolve_translate_chapters(options(file_paths=[str(a), str(b)]), get)
    assert [f.path for f in plan.files] == [a, b]
    assert [len(f.chapters) for f in plan.files] == [2, 1]


def test_planning_has_no_side_effects(tmp_path):
    a = make_file(tmp_path, "a.mp4")
    original = a.read_bytes()
    resolve_translate_chapters(options(file_paths=[str(a)]), fake_get_chapters({str(a): CHAPTERS}))
    assert a.read_bytes() == original


# ── run_translate_chapters_job, con un backend simulado ──────────────────


class FakeBackend:
    """
    translate_texts traduce de a lotes (ver ModelManager): un solo create_chat_completion por
    lote, respuesta "1: x\n2: y\n...". `prefix` se antepone a cada título para distinguir
    archivos en los asserts.
    """

    def __init__(self, prefix="EN: "):
        self.prefix = prefix
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
        self.calls += 1
        user = messages[-1]["content"]
        # Formato real de _call_model: "0: texto\n1: texto..." (ids desde 0, ver
        # model_manager.py); la respuesta esperada es ese mismo formato.
        import re
        ids = re.findall(r"^(\d+): ", user, re.MULTILINE)
        text = "\n".join(f"{i}: {self.prefix}{i}" for i in ids)
        mid = len(text) // 2
        return iter([{"choices": [{"delta": {"content": text[:mid]}}]},
                     {"choices": [{"delta": {"content": text[mid:]}}]}])


class Capture:
    def __init__(self, job_id="job-1"):
        self.events = []
        self.finished = 0
        self.job_events = JobEvents(lambda n, d: self.events.append((n, d)), "translate_chapters", job_id)

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


def run_job(tmp_path, names=("a.mp4",), backend=None, **opt_overrides):
    files = [make_file(tmp_path, n) for n in names]
    opts = options(file_paths=[str(f) for f in files], **opt_overrides)
    get = fake_get_chapters({str(f): CHAPTERS for f in files})
    plan = resolve_translate_chapters(opts, get)
    runner = ChaptersTranslateRunner(backend=backend or FakeBackend())
    cap = Capture()

    def finished():
        cap.finished += 1

    run_translate_chapters_job(runner, plan, opts, cap.job_events, cap.emit, on_finished=finished)
    wait_for_done(cap)
    return runner, cap, plan, files


def test_nothing_is_written_to_disk(tmp_path):
    _, _, _, files = run_job(tmp_path)
    for f in files:
        assert f.read_bytes() == b"not a real media file"  # sin tocar


def test_start_carries_the_total_and_the_job_id(tmp_path):
    _, cap, _, _ = run_job(tmp_path, names=("a.mp4", "b.mp4"))
    assert cap.events[0] == ("audiotools:start", {"job_id": "job-1", "tool": "translate_chapters", "total": 2})


def test_preview_ready_has_every_file_with_original_and_translated_titles(tmp_path):
    _, cap, _, files = run_job(tmp_path, names=("a.mp4", "b.mp4"))
    preview = cap.of("audiotools:translation:preview_ready")
    assert len(preview) == 1
    assert preview[0]["job_id"] == "job-1"
    out_files = preview[0]["files"]
    assert [f["name"] for f in out_files] == ["a.mp4", "b.mp4"]
    rows = out_files[0]["chapters"]
    assert rows[0]["original_title"] == "Introducción" and rows[0]["translated_title"] == "EN: 0"
    assert rows[1]["original_title"] == "Desarrollo" and rows[1]["translated_title"] == "EN: 1"
    assert rows[0]["start"] == 0.0 and rows[0]["end"] == 60.0


def test_preview_ready_fires_before_done(tmp_path):
    _, cap, _, _ = run_job(tmp_path)
    names = cap.names()
    assert names.index("audiotools:translation:preview_ready") < names.index("audiotools:done")


def test_done_reports_success(tmp_path):
    _, cap, _, _ = run_job(tmp_path)
    done = cap.of("audiotools:done")[0]
    assert done["success"] is True and done["cancelled"] is False


def test_file_events_carry_the_job_id(tmp_path):
    _, cap, _, _ = run_job(tmp_path, names=("a.mp4", "b.mp4"))
    files = cap.of("audiotools:file")
    assert len(files) == 4  # start+done por archivo
    assert all(f["job_id"] == "job-1" for f in files)


def test_on_finished_runs_after_done(tmp_path):
    _, cap, _, _ = run_job(tmp_path)
    assert cap.finished == 1


def test_work_info_is_generated_once_for_the_whole_queue_not_per_file(tmp_path):
    backend = FakeBackend()
    orig_create = backend.create_chat_completion
    calls = {"n": 0}

    def counting(*a, **kw):
        calls["n"] += 1
        return orig_create(*a, **kw)

    backend.create_chat_completion = counting
    run_job(tmp_path, names=("a.mp4", "b.mp4"), backend=backend, raw_publisher_info="Un publisher cualquiera")
    # 1 llamada de work_info + 1 por archivo (translate_texts hace 1 lote por archivo acá, con
    # solo 2 títulos cada uno) = 3, no 4 (no hay una segunda de work_info para el archivo b).
    assert calls["n"] == 3


def test_no_work_info_call_when_raw_publisher_info_is_empty(tmp_path):
    backend = FakeBackend()
    run_job(tmp_path, backend=backend, raw_publisher_info="")
    assert backend.calls == 1  # solo la traducción de títulos del único archivo


def test_cancelling_mid_queue_is_reported_as_cancelled_with_no_preview(tmp_path):
    """
    Con dos archivos: cancela DURANTE la traducción del primero (no del último — el chequeo de
    cancelación está al principio de CADA vuelta del for, antes de procesar ese archivo, así que
    cancelar durante el último no alcanza a cortar nada: ya no queda ninguna vuelta más después).
    Cancelando durante el primero, ese igual se termina de traducir (el corte no es a mitad de
    archivo), pero el segundo se salta — igual que en test_translate_job.py con SRT.
    """
    holder = {}
    backend = FakeBackend()
    orig_create = backend.create_chat_completion
    calls = {"n": 0}

    def cancelling(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:  # la traducción de títulos del archivo a
            holder["runner"].cancel()
        return orig_create(*a, **kw)

    backend.create_chat_completion = cancelling

    files = [make_file(tmp_path, n) for n in ("a.mp4", "b.mp4")]
    opts = options(file_paths=[str(f) for f in files])
    get = fake_get_chapters({str(f): CHAPTERS for f in files})
    plan = resolve_translate_chapters(opts, get)
    runner = ChaptersTranslateRunner(backend=backend)
    holder["runner"] = runner
    cap = Capture()

    run_translate_chapters_job(runner, plan, opts, cap.job_events, cap.emit)
    wait_for_done(cap)

    done = cap.of("audiotools:done")[0]
    assert done["success"] is False and done["cancelled"] is True
    assert cap.of("audiotools:translation:preview_ready") == []


# ── ChaptersAction.apply ──────────────────────────────────────────────────


class FakeRun:
    """Mismo helper que tests/test_chapters_metadata.py, para no depender de ffmpeg real."""

    def __init__(self, returncode=0, stderr=b"", content=b"CON CAPITULOS TRADUCIDOS"):
        self.returncode, self.stderr, self.content = returncode, stderr, content
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        from pathlib import Path
        Path(args[-1]).write_bytes(self.content)
        return type("Result", (), {"returncode": self.returncode, "stderr": self.stderr})()


def test_apply_writes_each_confirmed_file_in_place(tmp_path, monkeypatch):
    import core.chapters_metadata as chapters_metadata
    fake = FakeRun()
    monkeypatch.setattr(chapters_metadata.subprocess, "run", fake)

    f = tmp_path / "a.mp4"
    f.write_bytes(b"ORIGINAL")
    result = ChaptersAction().apply("ffmpeg", [
        {"path": str(f), "chapters": [{"title": "Intro (EN)", "start": 0.0, "end": 60.0}]},
    ])
    assert result == {"applied": [str(f)], "errors": []}
    assert f.read_bytes() == b"CON CAPITULOS TRADUCIDOS"  # reemplazado in-place, mismo nombre


def test_apply_reports_per_file_errors_and_keeps_going(tmp_path, monkeypatch):
    import core.chapters_metadata as chapters_metadata
    monkeypatch.setattr(chapters_metadata.subprocess, "run", FakeRun(returncode=1, stderr=b"boom"))

    a = tmp_path / "a.mp4"
    a.write_bytes(b"ORIGINAL")
    b = tmp_path / "b.mp4"
    b.write_bytes(b"ORIGINAL")
    result = ChaptersAction().apply("ffmpeg", [
        {"path": str(a), "chapters": [{"title": "x", "start": 0.0, "end": 1.0}]},
        {"path": str(b), "chapters": [{"title": "y", "start": 0.0, "end": 1.0}]},
    ])
    assert result["applied"] == []
    assert len(result["errors"]) == 2
    assert a.read_bytes() == b"ORIGINAL"  # sin tocar: ffmpeg "falló"
