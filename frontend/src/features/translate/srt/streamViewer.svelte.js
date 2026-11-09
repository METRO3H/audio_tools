/**
 * streamViewer.svelte.js
 * ───────────────────────
 * Estado COMPARTIDO de los tres modales de la vista de progreso de Translate SRT (stream de un
 * archivo, stream de todos los archivos y prompt completo). Es compartido a propósito: así
 * funciona desde antes de partir la vista, y el modal de prompt depende de ello — su título
 * "Bloque N" y sus pestañas Contexto/Bloque leen el archivo, el bloque y la pestaña
 * Input/Output que se dejaron elegidos en los modales de stream.
 *
 * Es una clase con campos $state (y no un objeto $state) para que los modales hijos puedan
 * asignar sus campos sin disparar el aviso de Svelte por mutar estado de otro componente.
 */
export class StreamViewer {
   // Qué modal está abierto
   openFileStream = $state(null); // índice de archivo del modal individual, o null
   showAllStreamsModal = $state(false);
   showPromptModal = $state(false);

   // Compartido por los dos modales de stream y leído por el de prompt
   streamTab = $state("output"); // "input" | "output"
   viewMode = $state("blocks"); // "blocks" | "raw"
   selectedBlockIndex = $state(0);
   selectedFileIndexAll = $state(0);

   // Del modal de prompt; viven acá para que sobrevivan a cerrarlo y abrirlo de nuevo
   promptViewMode = $state("formatted"); // "formatted" | "raw"
   promptTab = $state("instructions"); // instructions | glossary | workInfo | title | context | block

   /** Log del archivo `fileIndex` según la pestaña Input/Output elegida. */
   currentLog(fileIndex, inputLogs, streamLogs) {
      return (this.streamTab === "input" ? inputLogs[fileIndex] : streamLogs[fileIndex]) ?? "";
   }
}
