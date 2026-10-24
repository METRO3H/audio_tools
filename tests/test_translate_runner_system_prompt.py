"""
Regresión del bug del Glossary (ver HANDOFF, sección 7, frontend): el
frontend parseaba el system prompt final con una regex que buscaba
literalmente "[Work info]", pero build_system_prompt escribe
"[Work info — persistent context for this work]", así que el lookahead
nunca coincidía y la sección Glossary se tragaba work info y título.

La corrección es que el backend entregue las secciones ya separadas (no que
el frontend intente reconstruirlas reparseando el texto final). Este test
fija ese contrato: on_system_prompt(text, sections) con sections conteniendo
base_prompt/glossary/work_info/title tal cual se usaron para construir el
prompt, independientemente de qué separadores textuales use
build_system_prompt internamente.
"""
import threading

from core.translation.runner import TranslateRunner


class FakeBackend:
    """
    Implementa TranslationBackend. `responses`, si se da, se consume en orden, una por
    llamada a create_chat_completion (work_info, luego título, en ese orden — ver
    TranslateRunner._queue_worker). Sin `responses`, cualquier llamada falla: con
    raw_title/raw_publisher_info vacíos y files=[] el pipeline no debería necesitar el
    modelo para nada más que cargarlo.
    """

    def __init__(self, responses=None):
        self.responses = list(responses) if responses else None

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
        if not self.responses:
            raise AssertionError("no debería llamarse: no hay título, work_info ni archivos")
        text = self.responses.pop(0)
        mid = len(text) // 2
        return iter(
            [{"choices": [{"delta": {"content": text[:mid]}}]}, {"choices": [{"delta": {"content": text[mid:]}}]}]
        )


def test_on_system_prompt_recibe_las_secciones_separadas_del_texto_final():
    runner = TranslateRunner(backend=FakeBackend())

    captured = {}
    done = threading.Event()

    def on_system_prompt(text, sections):
        captured["text"] = text
        captured["sections"] = sections

    def on_queue_done(succeeded, total, cancelled):
        done.set()

    runner.run_queue(
        files=[],
        base_prompt="Translate everything to English.",
        glossary="Sensei -> Teacher",
        model="fake.gguf",
        on_system_prompt=on_system_prompt,
        on_queue_done=on_queue_done,
    )

    assert done.wait(timeout=5), "run_queue no terminó a tiempo"

    assert captured["sections"] == {
        "base_prompt": "Translate everything to English.",
        "glossary": "Sensei -> Teacher",
        "work_info": "",
        "title": "",
    }
    # El texto completo sigue disponible tal cual (lo usa la vista "raw" del modal).
    assert "Translate everything to English." in captured["text"]
    assert "Sensei -> Teacher" in captured["text"]


def test_on_system_prompt_separa_work_info_y_title_aunque_el_texto_final_los_contenga():
    # work_info se genera primero (a partir de raw_publisher_info), título después (a
    # partir de raw_title) — ver el orden del pipeline en TranslateRunner._queue_worker.
    runner = TranslateRunner(backend=FakeBackend(responses=[
        "This is a slice-of-life anime.",
        "My Dear Teacher",
    ]))

    captured = {}
    done = threading.Event()

    def on_system_prompt(text, sections):
        captured["text"] = text
        captured["sections"] = sections

    def on_queue_done(succeeded, total, cancelled):
        done.set()

    runner.run_queue(
        files=[],
        raw_title="わが親愛なる先生",
        raw_publisher_info="Studio XYZ, slice-of-life genre.",
        base_prompt="Translate everything to English.",
        glossary="Sensei -> Teacher",
        model="fake.gguf",
        on_system_prompt=on_system_prompt,
        on_queue_done=on_queue_done,
    )

    assert done.wait(timeout=5), "run_queue no terminó a tiempo"
    assert captured["sections"] == {
        "base_prompt": "Translate everything to English.",
        "glossary": "Sensei -> Teacher",
        "work_info": "This is a slice-of-life anime.",
        "title": "My Dear Teacher",
    }
    # El texto final sigue incluyendo todo (lo usa la vista "raw"), pero ya no hace falta
    # reparsearlo: por eso este test no le aplica ninguna regex, solo confirma que están.
    for fragment in ("Translate everything to English.", "Sensei -> Teacher",
                     "This is a slice-of-life anime.", "My Dear Teacher"):
        assert fragment in captured["text"]
