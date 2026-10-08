
from pathlib import Path

# ── Rutas base ────────────────────────────────────────────────────────────────

# Raíz del proyecto: la carpeta donde vive este config.py
ROOT_DIR = Path(__file__).parent.resolve()

# Binario de ffmpeg dentro del proyecto
FFMPEG_BIN = ROOT_DIR / "ffmpeg" / "ffmpeg.exe"
FFPROBE_BIN = ROOT_DIR / "ffmpeg" / "ffprobe.exe"

# ── Preferencias de usuario ───────────────────────────────────────────────────

# Carpeta por defecto que se abre al pedirle al usuario que elija archivos.
# Parte en el home del usuario; él la cambia desde la UI y se persiste aquí.
DEFAULT_BASE_FOLDER = Path("E:\\Downloads\\le\\japanese_audios")


TRANSCRIBE_INITIAL_PROMPT: str = ""


# ── Traduccion (LLM local, sin server) ──────────────────────────────────
TRANSLATION_MODELS_DIR    = ROOT_DIR / "models"
TRANSLATION_N_GPU_LAYERS  = 36

TRANSLATION_N_CTX         = 14096
TRANSLATION_TEMPERATURE   = 0.3
TRANSLATION_BLOCK_SIZE    = 15
TRANSLATION_CONTEXT_LINES = 4

# Cuanto subir la temperatura en los reintentos de translate_block (bloque
# completo / tramo contiguo) respecto de TRANSLATION_TEMPERATURE — a la
# misma temperatura, reintentar el mismo prompt tiende a reproducir la
# misma salida fallida. Un solo escalon: lo que sigue mal despues de esto
# va al traductor offline de respaldo, no se le insiste una tercera vez
# al LLM. Cap absoluto de 1.0 aplicado en el codigo (model_manager.py).
TRANSLATION_RETRY_TEMPERATURE_BUMP = 0.2

# Confianza minima (0-1) de que una linea "traducida" (de 4+ palabras)
# este realmente en ingles, segun lingua (ver
# core/lang_detect.py:untranslated_reason). Probado empiricamente: un
# umbral "intuitivo" como 0.5 marca como malas a la MAYORIA de las
# traducciones buenas (una oracion en ingles perfecta con un nombre u
# honorifico japones, muy comunes en este tipo de contenido, ronda
# 0.1-0.25 de confianza) — el romaji real da 0.003-0.02. Este valor bajo
# deja margen de sobra por encima de lo malo sin castigar lo bueno.
TRANSLATION_MIN_ENGLISH_CONFIDENCE = 0.05

TRANSLATION_STATS_DB      = ROOT_DIR / "stats" / "translation_stats.db"

# ── Traductor offline de respaldo ────────────────────────────────────────
# Ultima instancia para lineas que sobreviven a los reintentos del LLM sin
# traducirse de verdad (ver core/translation/fallback_translator.py para
# el comando de conversion exacto). Si esta carpeta no existe, el
# respaldo simplemente no esta disponible — se loguea, no rompe la corrida.
FALLBACK_TRANSLATION_MODEL_DIR = ROOT_DIR / "models" / "nllb-200-distilled-600M-ct2"
FALLBACK_TRANSLATION_TOKENIZER = "facebook/nllb-200-distilled-600M"

