from __future__ import annotations

import re

import langid


def detect_language(text: str) -> str | None:
    """
    Detecta el idioma de un texto sin usar ningun LLM — util para decisiones
    rapidas (¿este nombre de archivo ya esta en ingles o hace falta traducirlo?)
    sin gastar una llamada al modelo.

    Usa `langid` (puro Python, modelo embebido en el propio paquete, sin
    descargas ni compilacion nativa — a diferencia de fasttext/cld3, que
    necesitan un modelo aparte o bindings en C).

    Limitacion real: en strings muy cortos (2-3 palabras, como suelen ser
    nombres de archivo o titulos de capitulo) ningun detector es 100%
    confiable. Pensado para servir de filtro/sugerencia, no como verdad
    absoluta — cualquier flujo que lo use deberia dejar al usuario
    confirmar/descartar el resultado antes de aplicar cambios definitivos.

    Devuelve el codigo ISO 639-1 detectado (ej. 'ja', 'zh', 'en'), o None
    si el texto esta vacio.
    """
    text = text.strip()
    if not text:
        return None
    lang, _confidence = langid.classify(text)
    return lang


# Hiragana, katakana (incl. medio ancho), CJK unificado (kanji/hanzi).
# Cubre japones y chino por igual — el chino no usa hiragana/katakana pero
# si el mismo rango de ideogramas.
_CJK_SCRIPT_RE = re.compile(
    r"[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9F\u4E00-\u9FFF]"
)


def looks_untranslated(text: str) -> bool:
    """
    Para validar SALIDAS de traduccion (no para clasificar idioma de
    origen, como detect_language) — ¿este texto que deberia ser ingles
    todavia parece estar en japones/chino?

    Dos chequeos, en orden de confiabilidad:
    1. Determinista: ¿tiene kanji/hiragana/katakana/hanzi? Si es asi, es
       100% seguro que no se tradujo — no hace falta langid para esto.
    2. langid como respaldo, solo para el caso de texto romanizado (ej.
       "Kimochii yo~" en vez de traducido) — mismo alfabeto latino que el
       ingles, este chequeo SI puede dar falsos positivos en frases
       cortas (ver limitacion de detect_language). Por eso quien use esto
       para reintentar una traduccion debe acotar los reintentos: en el
       peor caso se reintenta una linea que ya estaba bien, nunca se
       queda colgado.
    """
    text = text.strip()
    if not text:
        return False
    if _CJK_SCRIPT_RE.search(text):
        return True
    # langid solo es razonablemente confiable con mas texto — en frases
    # cortas (nombres de archivo, titulos, interjecciones de una sola
    # linea) da demasiados falsos positivos medidos en la practica (ej.
    # "1_Prologue" -> estonio, "Hidden Cam Video" -> aleman). Por debajo
    # de este umbral, solo se confia en el chequeo de arriba.
    if len(text.split()) < 4:
        return False
    lang = detect_language(text)
    return lang is not None and lang != "en"
