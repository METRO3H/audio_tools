from __future__ import annotations

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
