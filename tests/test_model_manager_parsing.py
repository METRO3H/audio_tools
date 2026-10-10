"""Parsing de respuestas y consumo de streams de ModelManager (sin modelo real)."""
from core.translation.model_manager import ModelManager


def chunk(text):
    return {"choices": [{"delta": {"content": text}}]}


# ── _parse_block ─────────────────────────────────────────────────────────


def test_parse_block_by_id_including_multiline():
    out = ModelManager._parse_block("1: Hello\n2: World\n3: Multi\nline", {1: "a", 2: "b", 3: "c"})
    assert out == [
        {"id": 1, "text": "Hello"},
        {"id": 2, "text": "World"},
        {"id": 3, "text": "Multi\nline"},
    ]


def test_parse_block_reassigns_by_order_when_ids_mismatch_but_count_matches():
    out = ModelManager._parse_block("5: Hello\n7: World", {5: "a", 6: "b"})
    assert out == [{"id": 5, "text": "Hello"}, {"id": 6, "text": "World"}]


def test_parse_block_falls_back_to_original_for_missing_ids():
    out = ModelManager._parse_block("5: Hello", {5: "a", 6: "b"})
    assert out == [{"id": 5, "text": "Hello"}, {"id": 6, "text": "b"}]


def test_parse_block_without_ids_returns_originals():
    out = ModelManager._parse_block("Hello\nWorld", {5: "a", 6: "b"})
    assert out == [{"id": 5, "text": "a"}, {"id": 6, "text": "b"}]


# ── _strip_thinking ──────────────────────────────────────────────────────


def test_strip_thinking_removes_closed_block():
    assert ModelManager._strip_thinking("<think>razonando</think>1: Hi") == "1: Hi"


def test_strip_thinking_cuts_unclosed_block():
    assert ModelManager._strip_thinking("1: Hi\n<think>me quedé pensando") == "1: Hi\n"


# ── _consume_stream ──────────────────────────────────────────────────────


def test_consume_stream_counts_tokens_and_ignores_empty_deltas():
    stream = [chunk("1: a"), chunk(""), {"choices": [{"delta": {}}]}, chunk("\n2: b")]
    text, tokens = ModelManager._consume_stream(iter(stream))
    assert text == "1: a\n2: b"
    assert tokens == 2


def test_consume_stream_reports_completed_lines_progressively():
    seen = []
    stream = [chunk("1: a\n"), chunk("2: b\n"), chunk("3: c")]
    ModelManager._consume_stream(iter(stream), on_line_progress=seen.append)
    # una línea se considera completa cuando aparece el marcador de la siguiente
    assert seen == [1, 2]


def test_consume_stream_emits_full_text_to_on_stream_at_the_end_and_keeps_think_for_display():
    emitted = []
    stream = [chunk("<think>x</think>"), chunk("1: ok")]
    text, _ = ModelManager._consume_stream(iter(stream), on_stream=lambda tokens, t: emitted.append(t))
    assert text == "1: ok"                              # lo parseable va sin <think>
    assert emitted[-1] == "<think>x</think>1: ok"      # lo mostrado en vivo no se filtra
