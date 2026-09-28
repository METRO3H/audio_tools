from __future__ import annotations

import re

import langid
from lingua import Language, LanguageDetectorBuilder

import config


def detect_language(text: str) -> str | None:
    """
    Detecta el idioma de un texto sin usar ningun LLM — util para
    decisiones rapidas (¿este nombre de archivo ya esta en ingles o hace
    falta traducirlo?) sin gastar una llamada al modelo.

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

    NOTA: esto es independiente de `untranslated_reason()` de mas abajo.
    Este detecta el idioma de ORIGEN de un texto corto (nombres de
    archivo). El otro valida SALIDAS de traduccion (¿esto que deberia ser
    ingles, lo es de verdad?) y usa `lingua`, no `langid` — son
    necesidades distintas, con textos de naturaleza distinta (nombres de
    archivo cortos y limpios vs. dialogo largo y con ruido).
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

# Detector de idioma para validar SALIDAS de traduccion (ver
# untranslated_reason). A diferencia de detect_language() de arriba, este
# SI necesita andar bien con texto corto y con ruido (dialogo fragmentado,
# onomatopeyas) — por eso lingua en vez de langid, que ya demostro no ser
# confiable ahi (por eso antes se evitaba usar langid en textos de menos
# de 5 palabras, dejando pasar romaji sin chequear en absoluto).
#
# Se construye con TODOS los idiomas que soporta lingua (no solo
# ingles/japones/chino) a proposito: si se limitara el detector solo a
# esos tres, un texto en romaji (alfabeto latino, sin ningun caracter
# japones) terminaria compitiendo unicamente contra dos modelos basados
# en script japones/chino que jamas van a matchear texto en alfabeto
# latino — el ingles ganaria por descarte, no porque el texto realmente
# se parezca a ingles. Con todos los idiomas activos, el romaji tiene que
# competir tambien contra otros idiomas de alfabeto latino (italiano,
# indonesio, etc.), lo que da una confianza de "es ingles" mucho mas
# realista. El costo es mas memoria/tiempo de carga al importar este
# modulo (una sola vez por proceso, no por linea).
_LINGUA_DETECTOR = LanguageDetectorBuilder.from_all_languages().build()

# Palabras/token de al menos esta cantidad para confiar en la confianza
# probabilistica de lingua. Probado empiricamente (ver historial): por
# debajo de esto, CUALQUIER detector estadistico (lingua, langid, etc.)
# es practicamente ruido — frases en ingles perfectamente correctas como
# "Stop it." o "No way." dieron confianzas de ingles mas bajas (0.045,
# 0.06) que texto en romaji (0.003-0.02), y lingua.detect_language_of()
# llego a elegir esloveno/somali para esas mismas frases cortas en
# ingles. No es una falla de lingua: con tan pocos caracteres no hay
# señal estadistica suficiente para ningun idioma.
_MIN_WORDS_FOR_LINGUA = 4

# Debajo de _MIN_WORDS_FOR_LINGUA se usa esto en su lugar: el romaji
# (japones en alfabeto latino) practicamente siempre termina cada mora en
# vocal o en "n" (a diferencia del ingles, que termina libremente en
# cualquier consonante: "up", "it", "way", "out"...). Probado contra
# ejemplos reales: frases cortas en ingles dieron ratios de 0.0 a 0.67,
# romaji corto dio siempre 1.0 exacto — separacion limpia. Requiere al
# menos 2 tokens porque una sola palabra (un nombre propio, un "Hurry"
# suelto) es ambigua en cualquier direccion y mejor dejarla pasar.
_WORD_RE = re.compile(r"[a-zA-Z']+")
_VOWEL_OR_N = set("aeioun")


def _looks_like_short_romaji(text: str) -> bool:
    tokens = _WORD_RE.findall(text)
    if len(tokens) < 2:
        return False
    return all(t[-1].lower() in _VOWEL_OR_N for t in tokens)


def untranslated_reason(text: str) -> str | None:
    """
    Para validar SALIDAS de traduccion (no para clasificar idioma de
    origen, como detect_language) — ¿este texto que deberia ser ingles
    todavia parece estar en japones/chino, o es una transliteracion
    (romaji) en vez de una traduccion real?

    Devuelve None si el texto pasa el chequeo (se considera traducido), o
    un string explicando el motivo puntual si no — pensado para loguear
    el motivo real de cada reintento (ver core/translation/model_manager.py),
    no solo "no se tradujo".

    Tres chequeos, en orden:
    1. Determinista: ¿tiene kanji/hiragana/katakana/hanzi? Si es asi, es
       100% seguro que no se tradujo — no hace falta nada mas para esto.
    2. Texto CORTO (menos de _MIN_WORDS_FOR_LINGUA palabras): heuristica
       fonetica (ver _looks_like_short_romaji) — lingua/langid no son
       confiables aca en ninguna direccion (ver comentario arriba).
    3. Texto largo: confianza de lingua de que el texto sea ingles (ver
       _LINGUA_DETECTOR), con un umbral BAJO (config.TRANSLATION_MIN_ENGLISH_CONFIDENCE),
       no uno alto — probado contra ejemplos reales: oraciones en ingles
       correctas con nombres/honorificos japoneses (comunes en este tipo
       de contenido, ej. "Kumada-sensei", "Norio-sama") dan confianzas de
       apenas 0.1-0.25 pese a estar 100% bien traducidas, mientras que el
       romaji da 0.003-0.02. Un umbral alto tipo 0.5 hubiera marcado como
       "mal" a la mayoria de las traducciones buenas.
    """
    text = text.strip()
    if not text:
        return None

    if _CJK_SCRIPT_RE.search(text):
        return "contiene kanji/hiragana/katakana/hanzi"

    words = text.split()
    if len(words) < _MIN_WORDS_FOR_LINGUA:
        if _looks_like_short_romaji(text):
            return "texto corto con terminaciones tipicas de romaji (vocal/n)"
        return None

    confidence = _LINGUA_DETECTOR.compute_language_confidence(text, Language.ENGLISH)
    if confidence < config.TRANSLATION_MIN_ENGLISH_CONFIDENCE:
        return (
            f"confianza de que sea ingles: {confidence:.0%} "
            f"(minimo {config.TRANSLATION_MIN_ENGLISH_CONFIDENCE:.0%})"
        )

    return None


def looks_untranslated(text: str) -> bool:
    """Wrapper booleano de `untranslated_reason` para callers que no
    necesitan el motivo puntual."""
    return untranslated_reason(text) is not None