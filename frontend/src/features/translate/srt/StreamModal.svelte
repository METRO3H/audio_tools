<script>
   /**
    * StreamModal.svelte
    * ───────────────────
    * Salida cruda del modelo (Output) o lo que se le mandó (Input) durante una corrida de
    * Translate SRT, partida por bloques o en bruto. Un solo componente para dos usos:
    *
    *   all = false   un archivo (el que eligió `viewer.openFileStream`)
    *   all = true    todos los archivos, con una lista para elegir el archivo
    *
    * La pestaña Input/Output, la vista (bloques/raw) y el bloque elegido son del `viewer`
    * compartido (ver streamViewer.svelte.js), no de este componente.
    */
   import Modal from "@shared/ui/Modal.svelte";
   import { copyText } from "@shared/utils.js";
   import { parseBlocks } from "@translate/srt/srtStreamParsing.js";

   let { viewer, fileInfos = [], streamLogs, inputLogs, all = false, onClose } = $props();

   const fileIndex = $derived(all ? viewer.selectedFileIndexAll : viewer.openFileStream);
   const rawText = $derived(viewer.currentLog(fileIndex, inputLogs, streamLogs));
   const blocks = $derived(parseBlocks(rawText));
   // El bloque elegido puede quedar fuera de rango por un instante (si el log cambia, el efecto de
   // abajo recién corrige el índice después de renderizar): mientras tanto se muestra el primero.
   const selectedBlock = $derived(blocks[viewer.selectedBlockIndex] ?? blocks[0]);

   const title = $derived(
      all ? "Stream — todos los archivos" : `Stream — ${fileInfos[fileIndex]?.name ?? `archivo ${fileIndex + 1}`}`,
   );
   const noBlocksText = $derived(all ? "Este archivo no tiene bloques." : "Todavía no hay nada para este archivo.");

   // Si el contenido cambia y el bloque elegido ya no existe, vuelve al primero.
   $effect(() => {
      if (blocks.length > 0 && viewer.selectedBlockIndex >= blocks.length) {
         viewer.selectedBlockIndex = 0;
      }
   });

   function pickStreamTab(tab) {
      viewer.streamTab = tab;
      viewer.selectedBlockIndex = 0;
      if (all) viewer.selectedFileIndexAll = 0;
   }

   const PRE_STYLE = "scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;";
   const TAB_STYLE = "scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;";
   const verticalTab = (active) =>
      `px-2 py-1.5 text-xs text-left rounded-md transition-colors ${active ? "bg-indigo-500/20 text-white" : "text-white/40 hover:text-white/70 hover:bg-white/5"}`;
   const streamTabClass = (active) =>
      `px-3 py-1.5 text-xs transition-colors ${active ? "text-white border-b-2 border-indigo-500" : "text-white/40 hover:text-white/70"}`;
</script>

{#snippet pre(text)}
   <pre
      class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
      style={PRE_STYLE}>{text}</pre>
{/snippet}

<Modal {onClose} size="4xl" height="fixed-85" labelledby="srt-stream-modal-title" class="gap-3">
   <div class="flex items-center justify-between shrink-0">
      <h2 id="srt-stream-modal-title" class="text-sm font-semibold text-white truncate">{title}</h2>
      <div class="flex items-center gap-2">
         <button
            class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
            onclick={() => copyText(rawText)}
         >
            Copiar todo
         </button>
         <button
            class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
            onclick={() => (viewer.viewMode = viewer.viewMode === "blocks" ? "raw" : "blocks")}
         >
            {viewer.viewMode === "blocks" ? "Ver raw" : "Ver por bloques"}
         </button>
         <button class="text-white/30 hover:text-white transition-colors" onclick={onClose}>✕</button>
      </div>
   </div>

   <!-- Tabs Input / Output -->
   <div class="flex gap-1 shrink-0 border-b border-white/5">
      <button class={streamTabClass(viewer.streamTab === "input")} onclick={() => pickStreamTab("input")}>Input</button>
      <button class={streamTabClass(viewer.streamTab === "output")} onclick={() => pickStreamTab("output")}>Output</button>
   </div>

   <div class="flex flex-1 min-h-0 gap-3">
      {#if all}
         <!-- Tabs verticales (archivos) -->
         <div class="flex flex-col gap-1 overflow-y-auto shrink-0 w-24" style={TAB_STYLE}>
            {#each fileInfos as file, idx (file.path)}
               <button
                  class="{verticalTab(viewer.selectedFileIndexAll === idx)} truncate"
                  onclick={() => {
                     viewer.selectedFileIndexAll = idx;
                     viewer.selectedBlockIndex = 0;
                  }}
                  title={file.name}
               >
                  {file.name}
               </button>
            {:else}
               <span class="text-xs text-white/25">Sin archivos</span>
            {/each}
         </div>
      {/if}

      <div class="flex-1 flex flex-col min-h-0">
         {#if all && fileInfos.length === 0}
            <div class="flex-1 flex items-center justify-center text-xs text-white/25">No hay archivos.</div>
         {:else if viewer.viewMode === "blocks"}
            <div class="flex flex-1 gap-3 min-h-0">
               <!-- Tabs verticales (bloques) -->
               <div class="flex flex-col gap-1 overflow-y-auto shrink-0 w-20" style={TAB_STYLE}>
                  {#each blocks as _block, idx (idx)}
                     <button class={verticalTab(viewer.selectedBlockIndex === idx)} onclick={() => (viewer.selectedBlockIndex = idx)}>
                        Bloque {idx + 1}
                     </button>
                  {:else}
                     <span class="text-xs text-white/25">Sin bloques</span>
                  {/each}
               </div>

               <div class="flex-1 flex flex-col min-h-0">
                  {#if blocks.length > 0}
                     <div class="flex items-center justify-end shrink-0 mb-1">
                        <button
                           class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                           onclick={() => copyText(selectedBlock.content)}
                        >
                           Copiar
                        </button>
                     </div>
                     {@render pre(selectedBlock.content)}
                  {:else}
                     <div class="flex-1 flex items-center justify-center text-xs text-white/25">{noBlocksText}</div>
                  {/if}
               </div>
            </div>
         {:else}
            {@render pre(rawText)}
         {/if}
      </div>
   </div>
</Modal>
