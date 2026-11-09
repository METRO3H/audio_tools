"""
Guarda de sincronía emisor/listener de los eventos de traducción.

Cambiar el nombre de un evento en core/translation/job.py sin tocar el listener del frontend
(o al revés) no rompe ningún test ni el build: la vista simplemente deja de recibirlo. Este
test cruza los dos lados leyendo los fuentes:

  - emisores:  cada emit("audiotools:...") literal en core/translation/job.py
  - listeners: cada addEventListener con un literal "audiotools:..." en frontend/src
               (removeEventListener no cuenta: un add renombrado debe fallar aunque el remove no)

Un evento emitido sin listener falla, salvo que figure en EMITTED_WITHOUT_LISTENER (con el
porqué). Un listener sin emisor también falla: es un evento muerto.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOB_PY = ROOT / "core" / "translation" / "job.py"
FRONTEND_SRC = ROOT / "frontend" / "src"

EVENT_NAME = r'"(audiotools:[a-z_]+(?::[a-z_]+)?)"'

# Emitidos hoy sin que ninguna vista los escuche. Cada entrada es deuda a resolver (borrar el
# emit o agregar el listener); el test falla si una entrada deja de ser cierta.
#
# Límite: el cruce es por NOMBRE, no por vista. Con el nombre compartido, que una vista escuche
# `translation:phase` (Chapters) alcanza para que el test lo dé por escuchado, aunque SRT emita
# ese mismo evento y su vista no lo use (muestra pasos con :step; el texto de fase está
# duplicado en el log). Ese caso no lo puede detectar este test.
EMITTED_WITHOUT_LISTENER: dict[str, str] = {
    "audiotools:translation:stats": "SRT: se emite al final, ninguna vista lo consume todavía",
}

# Eventos genéricos del contrato (core/jobs.py), emitidos por JobEvents y no por job.py.
GENERIC = {"audiotools:start", "audiotools:log", "audiotools:progress",
           "audiotools:done", "audiotools:file"}


def _emitted() -> set[str]:
    src = JOB_PY.read_text(encoding="utf-8")
    return set(re.findall(r'emit\(\s*' + EVENT_NAME, src)) - GENERIC


def _listened() -> set[str]:
    found: set[str] = set()
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".svelte", ".js"} or ".test." in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        found |= set(re.findall(r'addEventListener\(\s*' + EVENT_NAME, text))
    return found - GENERIC


def test_every_emitted_translation_event_has_a_listener():
    missing = _emitted() - _listened() - set(EMITTED_WITHOUT_LISTENER)
    assert not missing, f"emitidos sin listener en el frontend: {sorted(missing)}"


def test_every_translation_listener_has_an_emitter():
    orphans = {e for e in _listened() if e.startswith("audiotools:translation:")} - _emitted()
    assert not orphans, f"listeners sin emisor en job.py: {sorted(orphans)}"


def test_exemptions_are_still_true():
    stale = {e for e in EMITTED_WITHOUT_LISTENER if e not in _emitted() or e in _listened()}
    assert not stale, f"exenciones obsoletas, borrarlas: {sorted(stale)}"
