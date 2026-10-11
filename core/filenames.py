"""
core/filenames.py
-----------------
Limpieza de nombres de archivo y de carpeta para Windows. La usan todos los
lugares que fabrican nombres a partir de texto libre (títulos de capítulo,
nombres traducidos...), para que se comporten igual.

Dos piezas:
    sanitize_name   reemplaza lo que Windows no admite por un equivalente legible
    fit_title       recorta un título para que la ruta completa no pase del límite

Sin dependencias del resto del proyecto.
"""

from __future__ import annotations

import re

# Límite "seguro" de la ruta completa. El clásico de Windows es 260 (MAX_PATH);
# se deja margen para sufijos como " (2)" que agregan otras herramientas.
SAFE_PATH_LIMIT = 240

# Caracteres que Windows no admite en un nombre → su equivalente legible.
# Los signos de puntuación de ancho completo (：／？ ...) sí son válidos y no se tocan.
_REPLACEMENTS: dict[str, str] = {
    ":": " - ",   # "Parte 1: Intro"  -> "Parte 1 - Intro"
    "|": " - ",   # "A | B"           -> "A - B"
    "/": "-",     # "AC/DC"           -> "AC-DC"
    "\\": "-",
    '"': "'",
    "<": "(",
    ">": ")",
    "?": "",      # "¿Qué es?"        -> "¿Qué es"
    "*": "",
}
_INVALID = re.compile("[" + re.escape("".join(_REPLACEMENTS)) + "]")
_WHITESPACE = re.compile(r"\s+")
# Control que NO es espacio en blanco (los que sí lo son —tab, saltos de línea...— se
# convierten en un espacio al colapsar). Se quitan ANTES de colapsar para no dejar dobles espacios.
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1b\x7f]")
_DANGLING = re.compile(r"^(?:-\s+)+|(?:\s+-)+$")  # restos " -" que deja un ":" al borde


def sanitize_name(name: str) -> str:
    """
    Devuelve `name` apto para un nombre de archivo/carpeta de Windows.

    Sustituye los caracteres inválidos (ver _REPLACEMENTS), normaliza saltos de
    línea y espacios repetidos, quita caracteres de control y limpia los
    separadores que quedan sueltos al principio o al final.

    Devuelve "" si no queda nada útil; cada llamador decide qué hacer entonces
    (p. ej. "untitled", o prescindir del título).
    """
    name = _INVALID.sub(lambda m: _REPLACEMENTS[m.group()], name)
    name = _CONTROL.sub("", name)
    name = _WHITESPACE.sub(" ", name)
    return _tidy(name)


def _tidy(name: str) -> str:
    name = _DANGLING.sub("", name.strip()).strip()
    return "" if not name.strip("- ") else name


def utf16_len(text: str) -> int:
    """Largo en unidades UTF-16, que es como Windows cuenta los caracteres de una ruta."""
    return len(text.encode("utf-16-le")) // 2


def _truncate_utf16(text: str, max_units: int) -> str:
    out: list[str] = []
    used = 0
    for ch in text:
        width = 2 if ord(ch) > 0xFFFF else 1
        if used + width > max_units:
            break
        out.append(ch)
        used += width
    return "".join(out)


def fit_title(
    title: str,
    reserved: int,
    limit: int = SAFE_PATH_LIMIT,
    min_chars: int = 10,
) -> str:
    """
    Recorta `title` para que, junto con `reserved` unidades UTF-16 ya ocupadas
    por el resto de la ruta, no pase de `limit`.

    Si el título cabe, se devuelve igual. Si queda menos de `min_chars` de espacio
    se devuelve "" (un fragmento tan corto no identifica nada): el llamador
    decide cómo llamar al archivo sin título.
    """
    available = limit - reserved
    if utf16_len(title) <= available:
        return title
    if available < min_chars:
        return ""
    return _tidy(_truncate_utf16(title, available))
