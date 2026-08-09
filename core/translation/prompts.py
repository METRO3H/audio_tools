from __future__ import annotations

import re
from pathlib import Path

# ── Rutas ────────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PRESETS_DIR = _PROMPTS_DIR / "presets"
_SYSTEM_DIR = _PROMPTS_DIR / "system"

_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
_SYSTEM_DIR.mkdir(parents=True, exist_ok=True)

# Nombres de preset: letras, numeros, espacios, guiones. Nada de rutas.
_NAME_RE = re.compile(r"^[a-zA-Z0-9 _\-]{1,64}$")


def _sanitize_name(name: str) -> str:
    name = name.strip()
    if not name or not _NAME_RE.match(name):
        raise ValueError(f"Nombre de preset invalido: {name!r}")
    return name


def _read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# ── System prompts (fijos, sin idioma, se leen una vez al importar) ───────

TITLE_TRANSLATION_PROMPT = _read_text_file(_SYSTEM_DIR / "title_translation.txt")
WORK_INFO_EXTRACTION_PROMPT = _read_text_file(_SYSTEM_DIR / "work_info_extraction.txt")


# ── Presets (seleccionables desde la UI) ───────────────────────────────────

def list_presets() -> list[str]:
    return sorted(p.stem for p in _PRESETS_DIR.glob("*.txt"))


def get_preset(name: str) -> str:
    name = _sanitize_name(name)
    path = _PRESETS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Preset no encontrado: {name}")
    return path.read_text(encoding="utf-8")


def save_preset(name: str, content: str) -> None:
    name = _sanitize_name(name)
    path = _PRESETS_DIR / f"{name}.txt"
    path.write_text(content, encoding="utf-8")


def delete_preset(name: str) -> None:
    name = _sanitize_name(name)
    path = _PRESETS_DIR / f"{name}.txt"
    if path.exists():
        path.unlink()


def default_preset_content() -> str:
    """Contenido a mostrar cuando la UI carga por primera vez."""
    presets = list_presets()
    if not presets:
        return ""
    preferred = "japanese" if "japanese" in presets else presets[0]
    return get_preset(preferred)


# ── Construccion del system prompt final ───────────────────────────────────

def build_system_prompt(base_prompt: str, title: str = "", work_info: str = "") -> str:
    """
    Arma el system prompt final para traduccion de bloques, combinando
    el preset elegido (vocabulario/tono especifico del idioma origen)
    con el titulo ya traducido y el work_info generado, si existen.
    Se arma una sola vez por cola de archivos.
    """
    parts = [base_prompt.strip()]
    if work_info:
        parts.append(f"\n[Work info — persistent context for this work]:\n{work_info.strip()}")
    if title:
        parts.append(f"\n[Translated title]:\n{title.strip()}")
    return "\n".join(parts)
