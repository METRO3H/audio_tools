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
TRANSLATION_N_GPU_LAYERS  = 20     # default conservador para 4GB VRAM (GTX 1650) -
                                    # ajustable desde la UI por corrida; si tu modelo
                                    # no entra completo en VRAM, baja este numero
TRANSLATION_N_CTX         = 4096
TRANSLATION_TEMPERATURE   = 0.3
TRANSLATION_BLOCK_SIZE    = 15
TRANSLATION_CONTEXT_LINES = 4
