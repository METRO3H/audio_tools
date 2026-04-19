from pathlib import Path

# ── Rutas base ────────────────────────────────────────────────────────────────

# Raíz del proyecto: la carpeta donde vive este config.py
ROOT_DIR = Path(__file__).parent.resolve()

# Binario de ffmpeg dentro del proyecto
FFMPEG_BIN = ROOT_DIR / "ffmpeg" / "ffmpeg.exe"

# ── Preferencias de usuario ───────────────────────────────────────────────────

# Carpeta por defecto que se abre al pedirle al usuario que elija archivos.
# Parte en el home del usuario; él la cambia desde la UI y se persiste aquí.
DEFAULT_BASE_FOLDER = Path("E:\\Downloads\\le\\japanese_audios")

# ── UI ────────────────────────────────────────────────────────────────────────

APP_TITLE   = "Audio Tools"
APP_WIDTH   = 900
APP_HEIGHT  = 620
APPEARANCE  = "dark"   # "dark" | "light" | "system"
COLOR_THEME = "blue"   # tema de CustomTkinter