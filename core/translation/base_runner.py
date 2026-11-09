from __future__ import annotations

from core.translation.model_manager import ModelManager, TranslationBackend


class BaseTranslationRunner:
    """
    Lo que es 100% idéntico en los 3 runners de traducción (SRT, Chapters, Filenames): cada
    uno es dueño de su ModelManager y delega ahí listar/descargar modelos, y comparte el flag
    de cancelación.

    Deliberadamente NO incluye la lógica de cola: las 3 colas tienen formas distintas de verdad
    (SRT: pares (input, output); Chapters: (path, chapters) sin output; Filenames: lista plana
    con needs_translation) y cada runner mantiene la suya.

    `cancelled` es "se pidió cancelar" (lo que cancel() deja en True). TranslateRunner y
    ChaptersTranslateRunner además llevan `_was_cancelled`: "la cola LO OBSERVÓ y se detuvo",
    que es distinto (un cancel() tardío, después de terminar la cola, no cuenta como
    cancelación), y por eso vive en cada uno y no acá.
    """

    def __init__(self, backend: TranslationBackend | None = None) -> None:
        self._manager = ModelManager(backend=backend)
        self._cancelled = False

    def list_models(self) -> list[str]:
        return self._manager.list_models()

    def unload(self) -> None:
        self._manager.unload()

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        """
        Si cancel() se llamó desde que arrancó la última corrida. Existe porque, a diferencia
        de las colas de SRT/Chapters, translate_preview() de Filenames no tiene un callback de
        "terminó, y así terminó": al cancelarse retorna la lista con los nombres SIN traducir
        (mismo shape que un éxito real), así que sin esto el caller no distingue "nada
        necesitaba traducción" de "se canceló a mitad de camino" (bug real de 6c: cancelar
        mostraba una vista previa "exitosa" con todos los nombres iguales a los originales).
        """
        return self._cancelled
