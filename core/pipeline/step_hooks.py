from dataclasses import dataclass
from typing import Callable


@dataclass
class StepProgressHooks:
    """
    Callbacks opcionales que un paso del pipeline invoca para reportar
    su progreso a la UI. Todos son opcionales: si son None el paso
    funciona igual que cuando se ejecuta de forma standalone.

    Flujo de llamadas por paso:
      1. on_setup(filenames, title)   → al inicio, antes de llamar al runner
      2. on_file_active(filename)     → cuando un archivo empieza a procesarse
      3. on_file_progress(fname, v)   → durante el procesamiento (0.0 – 1.0)
      4. on_file_done(filename)       → cuando un archivo termina
         (2-4 se repiten por cada archivo en pasos multi-archivo)
      5. on_pipeline_progress(v)      → progreso global del paso (0.0 – 1.0),
                                        emitido junto con on_file_progress para
                                        actualizar la barra del pipeline en tiempo real
    """

    on_setup: Callable[[list[str], str], None] | None = None
    """(filenames, title) — lista de archivos que va a procesar el paso."""

    on_file_active: Callable[[str], None] | None = None
    """(filename) — el archivo indicado acaba de comenzar a procesarse."""

    on_file_progress: Callable[[str, float], None] | None = None
    """(filename, 0-1) — progreso del archivo activo."""

    on_file_done: Callable[[str], None] | None = None
    """(filename) — el archivo indicado terminó de procesarse."""

    on_pipeline_progress: Callable[[float], None] | None = None
    """(0-1) — progreso general del paso, para la barra global del pipeline."""