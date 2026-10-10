"""
Flujo de reintentos de ModelManager.translate_block / translate_texts con un
backend falso y guionado. Fija la lógica que más conviene no romper al partir
model_manager.py.
"""
import pytest

import config
from core.translation import fallback_translator
from core.translation.model_manager import ModelManager


class FakeBackend:
    """Implementa TranslationBackend. `responses` se consume en orden, una por llamada."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # [{"messages":..., "temperature":...}]

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
        self.calls.append({"messages": messages, "temperature": temperature})
        text = self.responses.pop(0)
        mid = len(text) // 2
        return iter(
            [{"choices": [{"delta": {"content": text[:mid]}}]}, {"choices": [{"delta": {"content": text[mid:]}}]}]
        )


LINES = [{"id": 1, "text": "あ"}, {"id": 2, "text": "い"}, {"id": 3, "text": "う"}]
GOOD = "1: Good morning to you all\n2: Hello my dear friends\n3: Thank you very much indeed"


@pytest.fixture(autouse=True)
def offline_fallback_disabled(monkeypatch):
    monkeypatch.setattr(fallback_translator, "unavailable_reason", lambda lang: "deshabilitado en tests")


def manager(responses):
    backend = FakeBackend(responses)
    return ModelManager(backend=backend), backend


def texts(result):
    return {r["id"]: r["text"] for r in result}


def test_all_good_needs_a_single_call():
    mgr, backend = manager([GOOD])
    result, stats = mgr.translate_block(LINES, "", "SYS", temperature=0.3, source_language="japanese")
    assert texts(result)[2] == "Hello my dear friends"
    assert stats == {
        "model_calls": 1, "tokens_generated": 2,
        "lines_needed_retry": 0, "lines_never_translated": 0, "full_block_retried": False,
    }
    # el mensaje de usuario siempre lleva /no_think; el system va tal cual
    assert backend.calls[0]["messages"][0] == {"role": "system", "content": "SYS"}
    assert backend.calls[0]["messages"][1]["content"].endswith("\n\n/no_think")


def test_one_bad_line_retries_only_that_run_with_context_and_higher_temperature():
    first = "1: Good morning to you all\n2: Konnichiwa minna\n3: Thank you very much indeed"
    mgr, backend = manager([first, "2: Good day everyone"])
    result, stats = mgr.translate_block(LINES, "", "SYS", temperature=0.3, source_language="japanese")

    assert texts(result) == {1: "Good morning to you all", 2: "Good day everyone", 3: "Thank you very much indeed"}
    assert stats["model_calls"] == 2
    assert stats["lines_needed_retry"] == 1
    assert stats["lines_never_translated"] == 0
    assert stats["full_block_retried"] is False

    retry = backend.calls[1]
    assert retry["temperature"] == pytest.approx(0.3 + config.TRANSLATION_RETRY_TEMPERATURE_BUMP)
    user_msg = retry["messages"][1]["content"]
    assert "[Previous translated context]" in user_msg and "1: Good morning to you all" in user_msg
    assert ModelManager._RETRY_LANGUAGE_REMINDER.strip() in user_msg
    assert "2: " in user_msg and "3: " not in user_msg.split("[Block to translate]:")[1]


def test_majority_bad_retries_full_block_but_keeps_lines_that_were_already_good():
    first = "1: Konnichiwa minna\n2: Arigatou gozaimasu\n3: Fine thanks a lot"
    retry = "1: Good day everyone\n2: Thank you very much\n3: A completely different text here"
    mgr, backend = manager([first, retry])
    result, stats = mgr.translate_block(LINES, "", "SYS", temperature=0.3, source_language="japanese")

    assert stats["full_block_retried"] is True and stats["model_calls"] == 2
    assert texts(result) == {1: "Good day everyone", 2: "Thank you very much", 3: "Fine thanks a lot"}


def test_unrecoverable_line_keeps_last_llm_result_when_fallback_unavailable():
    bad = "1: Good morning to you all\n2: Konnichiwa minna\n3: Thank you very much indeed"
    mgr, _ = manager([bad, "2: Konnichiwa minna"])
    result, stats = mgr.translate_block(LINES, "", "SYS", temperature=0.3, source_language="japanese")
    assert texts(result)[2] == "Konnichiwa minna"
    assert stats["lines_never_translated"] == 1 and stats["lines_needed_retry"] == 1


def test_offline_fallback_is_used_for_lines_that_survive_retries(monkeypatch):
    monkeypatch.setattr(fallback_translator, "unavailable_reason", lambda lang: None)
    monkeypatch.setattr(fallback_translator, "translate_line", lambda text, lang: "Good day everyone")
    bad = "1: Good morning to you all\n2: Konnichiwa minna\n3: Thank you very much indeed"
    mgr, _ = manager([bad, "2: Konnichiwa minna"])
    result, stats = mgr.translate_block(LINES, "", "SYS", temperature=0.3, source_language="japanese")
    assert texts(result)[2] == "Good day everyone"
    assert stats["lines_never_translated"] == 0


def test_translate_block_empty_input():
    mgr, backend = manager([])
    result, stats = mgr.translate_block([], "", "SYS")
    assert result == [] and stats["model_calls"] == 0 and backend.calls == []


def test_translate_texts_retries_only_failed_items():
    mgr, backend = manager(["0: Hello\n1: Konnichiwa minna", "1: Good day"])
    assert mgr.translate_texts(["あ", "い"], "SYS") == ["Hello", "Good day"]
    assert len(backend.calls) == 2


def test_translate_texts_leaves_original_when_nothing_works():
    mgr, backend = manager(["0: Konnichiwa minna", "0: Konnichiwa minna", "0: Konnichiwa minna"])
    # El texto original se conserva solo si el LLM no devuelve nada mejor; aquí
    # devuelve su último intento (también sin traducir): se fija ese comportamiento.
    out = mgr.translate_texts(["あ"], "SYS")
    assert len(backend.calls) == 3
    assert out == ["Konnichiwa minna"]


def test_generate_text_returns_stripped_text_and_streams_full_text():
    mgr, _ = manager(["  Work info here  "])
    seen = []
    out = mgr.generate_text("SYS", "user", on_stream=lambda tokens, text: seen.append(text))
    assert out == "Work info here"
    assert seen[-1] == "  Work info here  "
