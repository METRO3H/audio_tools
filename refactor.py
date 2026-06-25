"""
cleanup_for_refactor.py
-----------------------
Limpia el proyecto audio_tools eliminando todo lo relacionado con
CustomTkinter/tkinter para dejar el repo listo para el refactor
a pywebview + Svelte 5.

Uso:
    python cleanup_for_refactor.py          # dry-run (muestra qué haría)
    python cleanup_for_refactor.py --apply  # ejecuta los cambios

Lo que elimina:
    - ui/                    carpeta entera (views, components, app.py)
    - main.py                entrypoint tkinter (se reescribirá)
    - audio_tools.spec       spec de PyInstaller para la build tkinter

Lo que parchea (no elimina):
    - config.py              elimina las vars de UI (APP_WIDTH, APP_HEIGHT,
                             APPEARANCE, COLOR_THEME) que ya no aplican

Lo que NO toca:
    - core/                  lógica pura, sin cambios
    - util/                  sin cambios
    - ffmpeg/                binarios, sin cambios
    - .gitignore             sin cambios
    - dist/                  ni se acerca (tampoco debería estar en git)
"""

import re
import shutil
import sys
from pathlib import Path

DRY_RUN = "--apply" not in sys.argv

ROOT = Path(__file__).parent.resolve()

# ── Colores para la terminal ───────────────────────────────────────────────────

def red(s):    return f"\033[91m{s}\033[0m"
def green(s):  return f"\033[92m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def cyan(s):   return f"\033[96m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"


# ── Helpers ────────────────────────────────────────────────────────────────────

def log_action(verb: str, path: Path, color_fn=red):
    label = f"[{'DRY-RUN' if DRY_RUN else 'APPLY'}]"
    print(f"  {yellow(label)} {color_fn(verb):30s} {path.relative_to(ROOT)}")


def remove_dir(path: Path):
    if not path.exists():
        print(f"  {cyan('[SKIP]'):30s} {path.relative_to(ROOT)} (no existe)")
        return
    log_action("ELIMINAR CARPETA", path)
    if not DRY_RUN:
        shutil.rmtree(path)


def remove_file(path: Path):
    if not path.exists():
        print(f"  {cyan('[SKIP]'):30s} {path.relative_to(ROOT)} (no existe)")
        return
    log_action("ELIMINAR ARCHIVO", path)
    if not DRY_RUN:
        path.unlink()


def patch_config(path: Path):
    """
    Elimina de config.py las variables exclusivas de la UI tkinter:
        APP_TITLE, APP_WIDTH, APP_HEIGHT, APPEARANCE, COLOR_THEME
    y el bloque de comentario '# ── UI ──' que las agrupa.
    Deja intactas ROOT_DIR, FFMPEG_BIN, FFPROBE_BIN, DEFAULT_BASE_FOLDER.
    """
    if not path.exists():
        print(f"  {cyan('[SKIP]'):30s} {path.relative_to(ROOT)} (no existe)")
        return

    original = path.read_text(encoding="utf-8")

    # Patrón: bloque de comentario UI + las 5 variables que le siguen
    pattern = re.compile(
        r"\n# ── UI [─]+\n"          # línea de comentario del bloque UI
        r"(?:\n?(?:APP_TITLE|APP_WIDTH|APP_HEIGHT|APPEARANCE|COLOR_THEME)"
        r"\s*=\s*.*\n)+",
        re.MULTILINE,
    )

    patched = pattern.sub("\n", original)

    if patched == original:
        print(f"  {cyan('[SKIP]'):30s} config.py (bloque UI no encontrado o ya limpio)")
        return

    removed_lines = [
        ln for ln in original.splitlines()
        if ln not in patched.splitlines()
        and ln.strip()
    ]

    log_action("PARCHEAR ARCHIVO", path, color_fn=yellow)
    for ln in removed_lines:
        print(f"         {red('-')} {ln}")

    if not DRY_RUN:
        path.write_text(patched, encoding="utf-8")


def check_dist_git_status(dist_path: Path):
    """
    Avisa si dist/ tiene archivos trackeados por git.
    No elimina nada — solo informa.
    """
    if not dist_path.exists():
        return
    import subprocess
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(dist_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print()
        print(yellow("  ⚠  AVISO: dist/ tiene archivos trackeados por git."))
        print(yellow("     Agrega 'dist/' a tu .gitignore antes de continuar."))
    else:
        print(f"  {green('[OK]'):30s} dist/ no está trackeada por git")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print()
    print(bold("=" * 60))
    mode = "DRY-RUN — nada será modificado" if DRY_RUN else "APLICANDO CAMBIOS"
    print(bold(f"  cleanup_for_refactor  [{mode}]"))
    print(bold("=" * 60))
    print()

    print(bold("── Verificando dist/ ─────────────────────────────────────"))
    check_dist_git_status(ROOT / "dist")
    print()

    print(bold("── Eliminando carpetas ───────────────────────────────────"))
    remove_dir(ROOT / "ui")
    print()

    print(bold("── Eliminando archivos ───────────────────────────────────"))
    remove_file(ROOT / "main.py")
    remove_file(ROOT / "audio_tools.spec")
    print()

    print(bold("── Parcheando config.py ──────────────────────────────────"))
    patch_config(ROOT / "config.py")
    print()

    print(bold("── Estado final del proyecto ─────────────────────────────"))
    preserved = ["core/", "util/", "ffmpeg/", "config.py", ".gitignore"]
    for item in preserved:
        p = ROOT / item.rstrip("/")
        exists = p.exists()
        status = green("✓ existe") if exists else red("✗ no encontrado")
        print(f"  {status}  {item}")
    print()

    if DRY_RUN:
        print(yellow("  Nada fue modificado. Ejecuta con --apply para aplicar."))
        print(yellow("  Ejemplo: python cleanup_for_refactor.py --apply"))
    else:
        print(green("  Limpieza completada. El repo está listo para el refactor."))
    print()


if __name__ == "__main__":
    main()