"""
core/process.py
---------------
Opciones comunes para lanzar subprocesos (ffmpeg, ffprobe...).
"""

import subprocess

# En Windows evita que aparezca una ventana de consola por cada subproceso.
# En otros sistemas la constante no existe: 0 = sin flags.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
