"""Limpieza de nombres para Windows (core/filenames.py)."""
import random

import pytest

from core.filenames import SAFE_PATH_LIMIT, fit_title, sanitize_name, utf16_len

INVALID = set('<>:"/\\|?*')


@pytest.mark.parametrize(
    "raw, expected",
    [
        # ── caracteres inválidos → equivalente legible ───────────────────
        ("Parte 1: Intro", "Parte 1 - Intro"),
        ("Parte 1 : Intro", "Parte 1 - Intro"),
        ("12:30", "12 - 30"),
        ("A | B", "A - B"),
        ("AC/DC en vivo", "AC-DC en vivo"),
        ("ruta\\corta", "ruta-corta"),
        ('Dijo "hola"', "Dijo 'hola'"),
        ("<Intro>", "(Intro)"),
        ("¿Qué es?", "¿Qué es"),
        ("¡Wow*!", "¡Wow!"),
        # ── restos de separador al borde ─────────────────────────────────
        ("Intro:", "Intro"),
        (":Intro", "Intro"),
        ("A: ?", "A"),
        # ── espacios y caracteres de control ─────────────────────────────
        ("  espacios   internos  ", "espacios internos"),
        ("línea1\nlínea2\t3", "línea1 línea2 3"),
        ("con\x00control", "concontrol"),
        ("a \x00 b", "a b"),            # regresión: el control entre espacios no deja un doble espacio
        ("a\x1fb", "a b"),               # los separadores ASCII cuentan como espacio
        # ── lo válido no se toca ─────────────────────────────────────────
        ("Capítulo １：はじめに／終", "Capítulo １：はじめに／終"),  # signos de ancho completo
        ("-Hey", "-Hey"),
        ("COVID-", "COVID-"),
        ("ya limpio", "ya limpio"),
    ],
)
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "???", "***", ":", "|", "::", "- -", "-", "  -  "])
def test_sanitize_returns_empty_when_nothing_useful_is_left(raw):
    assert sanitize_name(raw) == ""


def test_sanitize_output_is_always_valid_and_stable():
    rng = random.Random(1234)
    alphabet = list('abcXYZ 012:|/\\"<>?*-\t\n\x00\x1f.ñé日本') + ["　"]
    for _ in range(4000):
        raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
        out = sanitize_name(raw)
        assert not (set(out) & INVALID), (raw, out)
        assert not any(ord(c) < 32 or ord(c) == 127 for c in out), (raw, out)
        assert out == out.strip() and "  " not in out, (raw, out)
        assert sanitize_name(out) == out, (raw, out)  # idempotente


# ── utf16_len / fit_title ────────────────────────────────────────────────


def test_utf16_len_counts_like_windows():
    assert utf16_len("abc") == 3
    assert utf16_len("日本") == 2
    assert utf16_len("😀") == 2  # fuera del plano básico: 2 unidades


def test_default_limit_leaves_margin_under_max_path():
    assert SAFE_PATH_LIMIT == 240


def test_title_that_fits_is_returned_unchanged():
    assert fit_title("Un título corto", reserved=100) == "Un título corto"
    assert fit_title("x" * 40, reserved=200) == "x" * 40  # justo cabe


def test_long_title_is_cut_to_exactly_the_available_space():
    out = fit_title("x" * 500, reserved=200)
    assert out == "x" * 40
    assert 200 + utf16_len(out) <= SAFE_PATH_LIMIT


def test_too_little_space_drops_the_title():
    assert fit_title("x" * 500, reserved=231) == ""           # 9 < min_chars
    assert fit_title("x" * 500, reserved=230) == "x" * 10     # justo el mínimo
    assert fit_title("x" * 500, reserved=300) == ""           # ni la base cabe


def test_cut_counts_utf16_units_and_never_splits_a_character():
    out = fit_title("😀" * 30, reserved=200)  # 2 unidades cada uno; caben 20
    assert out == "😀" * 20
    assert utf16_len(out) == 40
    odd = fit_title("😀" * 30, reserved=199)  # 41 disponibles: no se parte el 21.º
    assert odd == "😀" * 20


def test_cut_does_not_leave_a_dangling_separator():
    assert fit_title("Hola mundo - cruel", reserved=228) == "Hola mundo"  # el corte cae tras " -"
