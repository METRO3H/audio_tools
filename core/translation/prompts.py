from __future__ import annotations

import re
from pathlib import Path

# ── Rutas ────────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_VALID_KINDS = ("srt", "chapters", "filenames")

_NAME_RE = re.compile(r"^[a-zA-Z0-9 _\-]{1,64}$")


def _sanitize_name(name: str) -> str:
    name = name.strip()
    if not name or not _NAME_RE.match(name):
        raise ValueError(f"Nombre de preset invalido: {name!r}")
    return name


def _sanitize_kind(kind: str) -> str:
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind invalido: {kind!r} (debe ser uno de {_VALID_KINDS})")
    return kind


def _presets_dir(kind: str) -> Path:
    d = _PROMPTS_DIR / _sanitize_kind(kind) / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _system_dir(kind: str) -> Path:
    d = _PROMPTS_DIR / _sanitize_kind(kind) / "system"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── System prompts (fijos por kind, sin idioma, se leen desde archivo) ────

def get_system_prompt(kind: str, name: str) -> str:
    """name sin extension, ej. 'title_translation', 'work_info_extraction'."""
    path = _system_dir(kind) / f"{name}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# ── Presets (seleccionables desde la UI, independientes por kind) ─────────

def list_presets(kind: str) -> list[str]:
    return sorted(p.stem for p in _presets_dir(kind).glob("*.txt"))


def get_preset(kind: str, name: str) -> str:
    name = _sanitize_name(name)
    path = _presets_dir(kind) / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Preset no encontrado: {kind}/{name}")
    return path.read_text(encoding="utf-8")


def save_preset(kind: str, name: str, content: str) -> None:
    name = _sanitize_name(name)
    path = _presets_dir(kind) / f"{name}.txt"
    path.write_text(content, encoding="utf-8")


def delete_preset(kind: str, name: str) -> None:
    name = _sanitize_name(name)
    path = _presets_dir(kind) / f"{name}.txt"
    if path.exists():
        path.unlink()


def default_preset_content(kind: str) -> str:
    """Contenido a mostrar cuando la UI carga por primera vez, para ese kind."""
    presets = list_presets(kind)
    if not presets:
        return ""
    preferred = "japanese" if kind == "srt" and "japanese" in presets else presets[0]
    return get_preset(kind, preferred)


# ── Construccion de prompts finales ─────────────────────────────────────

def build_system_prompt(base_prompt: str, title: str = "", work_info: str = "") -> str:
    """
    Usado por la traduccion de .srt: preset + work_info + titulo ya
    traducido, armado una sola vez por cola de archivos.
    """
    parts = [base_prompt.strip()]
    if work_info:
        parts.append(f"\n[Work info — persistent context for this work]:\n{work_info.strip()}")
    if title:
        parts.append(f"\n[Translated title]:\n{title.strip()}")
    return "\n".join(parts)


def build_short_text_prompt(kind_instructions: str, base_prompt: str, work_info: str = "") -> str:
    """
    Usado por chapters/filenames: instrucciones especificas de la tarea +
    preset (vocabulario/terminologia) + work_info opcional. No hay titulo
    aca, esos dos flujos no lo necesitan.
    """
    parts = [kind_instructions.strip()]
    if base_prompt.strip():
        parts.append(f"\n[Vocabulary / terminology reference]:\n{base_prompt.strip()}")
    if work_info:
        parts.append(f"\n[Work info — context for this work]:\n{work_info.strip()}")
    return "\n".join(parts)
