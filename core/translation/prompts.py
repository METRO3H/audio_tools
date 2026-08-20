from __future__ import annotations

import re
from pathlib import Path

"""
Sistema de prompts de traduccion.

    prompts/
    ├── japanese/
    │   ├── srt_translation.txt
    │   ├── chapters_translation.txt
    │   ├── filenames_translation.txt
    │   └── glossary.txt
    ├── chinese/
    │   └── ... (misma estructura)
    └── shared/
        ├── title_translation.txt
        └── work_info_extraction.txt

Un idioma = una carpeta. Alta de un idioma nuevo = crear la carpeta con sus
4 archivos, no hace falta tocar codigo — list_languages() la descubre sola.

"{kind}_translation.txt" son las instrucciones de traduccion propiamente
dichas (editables desde la UI, un archivo por idioma+tipo). "glossary.txt"
es un diccionario de terminos fijo, tambien por idioma, pero COMPARTIDO
entre los tres tipos (srt/chapters/filenames) — se inyecta automaticamente
en el prompt final de los tres, para no repetir los mismos terminos tres
veces. Es un concepto distinto del "Glossary" que se genera dinamicamente
dentro de work_info por cada trabajo puntual (apodos/nicknames especificos
de ESA obra) — ese vive en shared/work_info_extraction.txt y no se toca aca.

"shared/" son los dos prompts de sistema que no dependen del idioma de
origen (sus instrucciones son 100% en ingles y genericas): title_translation
(solo lo usa srt) y work_info_extraction (lo usan los tres). No son
editables desde la UI de presets, son fijos.
"""

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_KINDS = ("srt", "chapters", "filenames")
_SHARED_NAMES = ("title_translation", "work_info_extraction")

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,32}$")


def _sanitize_kind(kind: str) -> str:
    if kind not in _KINDS:
        raise ValueError(f"kind invalido: {kind!r} (debe ser uno de {_KINDS})")
    return kind


def _sanitize_language(language: str) -> str:
    language = (language or "").strip()
    if not language or language == "shared" or not _SAFE_NAME_RE.match(language):
        raise ValueError(f"idioma invalido: {language!r}")
    return language


def _lang_dir(language: str, create: bool = False) -> Path:
    d = _PROMPTS_DIR / _sanitize_language(language)
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _shared_dir() -> Path:
    return _PROMPTS_DIR / "shared"


# ── Idiomas disponibles ──────────────────────────────────────────────────

def list_languages() -> list[str]:
    """
    Idiomas = subcarpetas de prompts/, excepto "shared" (esa no es un
    idioma, son los dos prompts de sistema compartidos por los tres tipos).
    """
    if not _PROMPTS_DIR.exists():
        return []
    return sorted(
        p.name for p in _PROMPTS_DIR.iterdir()
        if p.is_dir() and p.name != "shared"
    )


# ── Prompt de traduccion por idioma+tipo (editable desde la UI) ──────────

def get_translation_prompt(language: str, kind: str) -> str:
    path = _lang_dir(language) / f"{_sanitize_kind(kind)}_translation.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_translation_prompt(language: str, kind: str, content: str) -> None:
    path = _lang_dir(language, create=True) / f"{_sanitize_kind(kind)}_translation.txt"
    path.write_text(content, encoding="utf-8")


# ── Glosario por idioma (compartido entre los tres tipos) ────────────────

def get_glossary(language: str) -> str:
    path = _lang_dir(language) / "glossary.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_glossary(language: str, content: str) -> None:
    path = _lang_dir(language, create=True) / "glossary.txt"
    path.write_text(content, encoding="utf-8")


# ── System prompts compartidos (fijos, sin idioma, no editables desde UI) ─

def get_shared_prompt(name: str) -> str:
    """name sin extension: 'title_translation' o 'work_info_extraction'."""
    if name not in _SHARED_NAMES:
        raise ValueError(f"shared prompt invalido: {name!r} (debe ser uno de {_SHARED_NAMES})")
    path = _shared_dir() / f"{name}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ── Construccion de prompts finales ───────────────────────────────────────

def build_system_prompt(base_prompt: str, glossary: str = "", title: str = "", work_info: str = "") -> str:
    """
    Usado por la traduccion de .srt: prompt de traduccion (ya trae sus
    propias instrucciones de tarea y de formato de salida) + glosario del
    idioma + work_info + titulo ya traducido, armado una sola vez por cola
    de archivos.
    """
    parts = [base_prompt.strip()]
    if glossary.strip():
        parts.append(f"\n[Glossary — use these renderings when the term appears]:\n{glossary.strip()}")
    if work_info:
        parts.append(f"\n[Work info — persistent context for this work]:\n{work_info.strip()}")
    if title:
        parts.append(f"\n[Translated title]:\n{title.strip()}")
    return "\n".join(parts)


def build_short_text_prompt(base_prompt: str, glossary: str = "", work_info: str = "") -> str:
    """
    Usado por chapters/filenames: prompt de traduccion (ya trae sus propias
    instrucciones de tarea y de formato de salida) + glosario del idioma +
    work_info opcional. No hay titulo aca, esos dos flujos no lo usan.
    """
    parts = [base_prompt.strip()]
    if glossary.strip():
        parts.append(f"\n[Glossary — use these renderings when the term appears]:\n{glossary.strip()}")
    if work_info:
        parts.append(f"\n[Work info — context for this work]:\n{work_info.strip()}")
    return "\n".join(parts)
