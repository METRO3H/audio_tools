from pathlib import Path

from PIL import Image

MAX_BYTES = 200 * 1024  # 200 kb


def needs_optimization(image_path: Path) -> bool:
    return image_path.stat().st_size > MAX_BYTES


def optimize_image(image_path: Path) -> Path:
    """
    Si image_path supera los 200 kb, genera un archivo optimizado junto al
    original con el sufijo '_opt.jpg' y lo devuelve.
    Si no supera el límite, devuelve image_path sin modificar.

    Estrategia:
      1. Convertir a JPEG (si no lo es ya) y reducir calidad en pasos de 10.
      2. Si con calidad mínima sigue siendo grande, reducir dimensiones al 80 %
         de forma iterativa hasta alcanzar el objetivo.
    """
    if not needs_optimization(image_path):
        return image_path

    opt_path = image_path.parent / f"{image_path.stem}_opt.jpg"
    img = Image.open(image_path).convert("RGB")

    # ── Paso 1: reducir calidad ───────────────────────────────────────
    for quality in range(85, 5, -10):
        img.save(opt_path, "JPEG", quality=quality, optimize=True)
        if opt_path.stat().st_size <= MAX_BYTES:
            return opt_path

    # ── Paso 2: reducir dimensiones ──────────────────────────────────
    w, h = img.size
    while w > 50:
        w = int(w * 0.8)
        h = int(h * 0.8)
        resized = img.resize((max(w, 1), max(h, 1)), Image.LANCZOS)
        resized.save(opt_path, "JPEG", quality=60, optimize=True)
        if opt_path.stat().st_size <= MAX_BYTES:
            return opt_path

    # En el caso extremo devolvemos lo último que se generó
    return opt_path