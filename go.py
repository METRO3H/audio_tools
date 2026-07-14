"""
go.py
──────
    py go.py              # lanza la app
    py go.py --build      # compila el frontend y lanza
    py go.py --debug      # lanza con DevTools
    py go.py --build --debug  # compila y lanza con DevTools
"""

import subprocess
import sys
from pathlib import Path

ROOT     = Path(__file__).parent.resolve()
FRONTEND = ROOT / "frontend"


def build():
    print("Building frontend...")
    result = subprocess.run(
        "npm run build",
        cwd=FRONTEND,
        shell=True,
    )
    if result.returncode != 0:
        print("Build failed.")
        sys.exit(1)
    print("Build complete.")


def run():
    args = [sys.executable, str(ROOT / "main.py")]
    if "--debug" in sys.argv:
        args.append("--debug")
    subprocess.run(args, cwd=ROOT)


if __name__ == "__main__":
    if "--build" in sys.argv:
        build()
    run()