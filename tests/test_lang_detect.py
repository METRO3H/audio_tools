import pytest

from core.lang_detect import detect_language, untranslated_reason


def test_detect_language_basic():
    assert detect_language("") is None
    assert detect_language("   ") is None
    assert detect_language("こんにちは、元気ですか") == "ja"


@pytest.mark.parametrize(
    "text",
    [
        "",                                                    # vacío: se considera ok
        "Hello there, how are you doing today my friend?",     # inglés normal
        "Stop it.",                                            # corto en inglés: no debe marcarse
        "Hurry",                                               # una sola palabra: ambigua, pasa
    ],
)
def test_untranslated_reason_accepts(text):
    assert untranslated_reason(text) is None


def test_cjk_is_always_untranslated():
    assert "kanji" in untranslated_reason("こんにちは")
    assert "kanji" in untranslated_reason("Hello 你好")


def test_short_romaji_is_flagged_by_phonetic_heuristic():
    assert "romaji" in untranslated_reason("Konnichiwa minna")


def test_long_romaji_is_flagged_by_low_english_confidence():
    reason = untranslated_reason("Watashi wa gakusei desu kara kyou mo benkyou shimasu yo")
    assert reason is not None and "ingles" in reason


@pytest.mark.xfail(
    strict=True,
    reason="Falso positivo conocido: la heurística de romaji marca frases cortas en inglés "
           "cuyas palabras terminan todas en vocal o 'n' (p. ej. 'Hello everyone'). "
           "Al refinar la heurística, este test pasará y xfail estricto avisará.",
)
def test_short_english_ending_in_vowels_is_not_flagged():
    assert untranslated_reason("Hello everyone") is None
