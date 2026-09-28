"""
Traductor de respaldo, offline y liviano, para las pocas lineas que
sobreviven a los reintentos del LLM principal sin traducirse de verdad
(ver core/translation/model_manager.py:translate_block). No reemplaza al
LLM como traductor principal — es solo la ultima red de contencion para
lineas puntuales, para cuando ya no vale la pena insistirle al mismo
modelo con el mismo tipo de contenido que ya esquivo dos veces (a la
misma temperatura, un LLM tiende a reproducir una respuesta muy similar
frente al mismo prompt).

Usa ctranslate2 (inferencia rapida en CPU/GPU) sobre un checkpoint de
NLLB-200 convertido, con el tokenizer de HuggingFace/`transformers` para
el pre/post-procesado (SentencePiece + los tags de idioma que NLLB
necesita).

SETUP REQUERIDO (manual, una sola vez — este modulo no lo hace solo):

    pip install ctranslate2 transformers sentencepiece --break-system-packages

    Convertir un checkpoint de NLLB-200 a formato ctranslate2. El
    "distilled-600M" alcanza para esto (es una red de contencion, no el
    traductor principal — no hace falta el de 3.3B):

        ct2-transformers-converter \
            --model facebook/nllb-200-distilled-600M \
            --output_dir models/nllb-200-distilled-600M-ct2 \
            --quantization int8

    config.FALLBACK_TRANSLATION_MODEL_DIR ya apunta a esa carpeta de
    salida por default. El tokenizer (config.FALLBACK_TRANSLATION_TOKENIZER)
    se descarga aparte, una sola vez, via `transformers.AutoTokenizer`
    (se cachea localmente despues de la primera vez).

Si el modelo o el tokenizer no estan disponibles, `is_available()`
devuelve False y `unavailable_reason()` explica por que — el caller
(translate_block) debe loguearlo y seguir sin este respaldo, nunca dejar
que esto rompa una corrida completa.

AVISO: el patron de tokenizacion/traduccion de mas abajo sigue la forma
estandar documentada de usar ctranslate2 con un tokenizer de NLLB, pero
no se pudo probar en este entorno (sin acceso a Hugging Face ni a los
pesos del modelo desde este sandbox). Probalo con un par de lineas de
prueba antes de confiar en el en una corrida real.
"""

from __future__ import annotations

import threading

import config

# Codigo NLLB por carpeta de idioma de origen del proyecto (ver
# core/translation/prompts/<idioma>/). Si agregan una carpeta de idioma
# nueva sin entrada aca, el respaldo offline simplemente no esta
# disponible para ese idioma (se loguea y se sigue solo con el LLM) —
# no hace falta que este modulo sepa de todos los idiomas del proyecto.
_NLLB_LANG_CODES: dict[str, str] = {
    "japanese": "jpn_Jpan",
    "chinese": "zho_Hans",
}
_NLLB_TARGET_LANG = "eng_Latn"

_lock = threading.RLock()
_translator = None
_tokenizer = None
_load_error: str | None = None
_load_attempted = False


def _ensure_loaded() -> None:
    global _translator, _tokenizer, _load_error, _load_attempted
    with _lock:
        if _load_attempted:
            return
        _load_attempted = True
        try:
            import ctranslate2
            from transformers import AutoTokenizer

            model_dir = config.FALLBACK_TRANSLATION_MODEL_DIR
            if not model_dir.exists():
                _load_error = f"no se encontro el modelo convertido en {model_dir}"
                return

            _translator = ctranslate2.Translator(str(model_dir), device="auto")
            _tokenizer = AutoTokenizer.from_pretrained(config.FALLBACK_TRANSLATION_TOKENIZER)
        except Exception as exc:
            _load_error = f"{type(exc).__name__}: {exc}"


def is_available(source_language: str) -> bool:
    """True si el respaldo offline puede traducir desde este idioma."""
    return unavailable_reason(source_language) is None


def unavailable_reason(source_language: str) -> str | None:
    """Motivo por el que el respaldo no esta disponible, o None si si lo esta."""
    if source_language not in _NLLB_LANG_CODES:
        return f"'{source_language}' no tiene codigo NLLB configurado en fallback_translator.py"
    _ensure_loaded()
    if _load_error:
        return _load_error
    return None


def translate_line(text: str, source_language: str) -> str:
    """
    Traduce una sola linea con NLLB-200 via ctranslate2. Pensado para
    llamarse pocas veces por corrida (una por linea que sobrevivio a los
    reintentos del LLM) — no esta optimizado para lotes grandes.

    Lanza RuntimeError si el respaldo no esta disponible para
    source_language (el caller debe manejarlo con unavailable_reason()
    antes de llamar, o capturar la excepcion — nunca dejar que reviente
    el bloque completo).
    """
    with _lock:
        reason = unavailable_reason(source_language)
        if reason:
            raise RuntimeError(reason)

        src_code = _NLLB_LANG_CODES[source_language]
        _tokenizer.src_lang = src_code
        tokens = _tokenizer.convert_ids_to_tokens(_tokenizer.encode(text))

        results = _translator.translate_batch(
            [tokens],
            target_prefix=[[_NLLB_TARGET_LANG]],
        )
        output_tokens = results[0].hypotheses[0][1:]  # saca el tag de idioma del prefix
        translated_ids = _tokenizer.convert_tokens_to_ids(output_tokens)
        return _tokenizer.decode(translated_ids, skip_special_tokens=True).strip()