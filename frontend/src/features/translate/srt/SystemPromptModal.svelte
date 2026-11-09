<script>
   /**
    * SystemPromptModal.svelte
    * ─────────────────────────
    * Prompt completo de una corrida de Translate SRT: las instrucciones del sistema con sus
    * secciones (instrucciones, glossary, work info, título) y el mensaje del usuario de un bloque
    * (contexto previo y bloque a traducir), en pestañas, o todo junto en bruto.
    *
    * Las secciones llegan ya separadas del backend (audiotools:translation:system_prompt ·
    * sections). El mensaje del usuario sale del log que dejaron elegido los modales de stream
    * (archivo, bloque y pestaña Input/Output del `viewer` compartido — ver streamViewer.svelte.js).
    */
   import Modal from "@shared/ui/Modal.svelte";
   import { copyText } from "@shared/utils.js";
   import { extractContext, extractBlock } from "@translate/srt/srtStreamParsing.js";

   let { viewer, fileInfos = [], systemPrompt = "", sections, streamLogs, inputLogs, onClose } = $props();

   const userMessage = $derived(viewer.currentLog(viewer.selectedFileIndexAll, inputLogs, streamLogs));

   // Una definición por pestaña; `text` es lo que muestra y copia.
   const tabs = $derived([
      { key: "instructions", label: "Instrucciones", heading: "Instrucciones del sistema (srt_translation.txt)", color: "text-indigo-400", empty: "(No hay instrucciones)", text: sections.base_prompt || "" },
      { key: "glossary", label: "Glossary", heading: "Glossary (términos fijos)", color: "text-emerald-400", empty: "(No hay glossary)", text: sections.glossary || "" },
      { key: "workInfo", label: "Work info", heading: "Work info (información del publisher)", color: "text-yellow-400", empty: "(No hay work info)", text: sections.work_info || "" },
      { key: "title", label: "Título", heading: "Título traducido", color: "text-purple-400", empty: "(No hay título)", text: sections.title || "" },
      { key: "context", label: "Contexto", heading: "Contexto (líneas anteriores traducidas)", color: "text-emerald-400", empty: "(No hay contexto)", text: extractContext(userMessage) },
      { key: "block", label: "Bloque", heading: "Bloque a traducir", color: "text-emerald-400", empty: "(No hay bloque)", text: extractBlock(userMessage) },
   ]);
   const activeTab = $derived(tabs.find((t) => t.key === viewer.promptTab) ?? tabs[0]);

   const PRE_STYLE = "scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;";
   const PRE_CLASS =
      "flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text";
</script>

<Modal {onClose} size="4xl" height="fixed-85" labelledby="srt-prompt-modal-title" class="gap-3">
   <div class="flex items-center justify-between shrink-0">
      <h2 id="srt-prompt-modal-title" class="text-sm font-semibold text-white truncate">
         Prompt completo — {fileInfos[viewer.selectedFileIndexAll]?.name ?? "archivo"} · Bloque {viewer.selectedBlockIndex + 1}
      </h2>
      <div class="flex items-center gap-2">
         <button
            class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
            onclick={() => copyText(systemPrompt + "\n\n" + userMessage)}
         >
            Copiar todo
         </button>
         <button
            class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
            onclick={() => (viewer.promptViewMode = viewer.promptViewMode === "formatted" ? "raw" : "formatted")}
         >
            {viewer.promptViewMode === "formatted" ? "Ver raw" : "Ver formateado"}
         </button>
         <button class="text-white/30 hover:text-white transition-colors" onclick={onClose}>✕</button>
      </div>
   </div>

   <!-- Tabs verticales a la izquierda, contenido a la derecha -->
   <div class="flex flex-1 min-h-0 gap-3">
      {#if viewer.promptViewMode === "formatted"}
         <div class="flex flex-col gap-1 overflow-y-auto shrink-0 w-24" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
            {#each tabs as tab (tab.key)}
               <button
                  class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                     {viewer.promptTab === tab.key ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                  onclick={() => (viewer.promptTab = tab.key)}
               >
                  {tab.label}
               </button>
            {/each}
         </div>

         <div class="flex-1 flex flex-col min-h-0">
            <div class="flex flex-col h-full">
               <div class="flex items-center justify-between shrink-0 mb-1">
                  <span class="text-[10px] {activeTab.color} font-medium">{activeTab.heading}</span>
                  <button class="text-[10px] text-white/30 hover:text-white/70 transition-colors" onclick={() => copyText(activeTab.text)}>
                     Copiar
                  </button>
               </div>
               <pre class={PRE_CLASS} style={PRE_STYLE}>{activeTab.text || activeTab.empty}</pre>
            </div>
         </div>
      {:else}
         <!-- Vista raw: todo concatenado. Los "\n\n" son TEXTO LITERAL (no saltos de línea): es
              lo que hacía la vista antes de partirse, fijado por TranslateProcessingView.test.js. -->
         <div class="flex-1 flex flex-col min-h-0">
            <pre class={PRE_CLASS} style={PRE_STYLE}>{systemPrompt}\n\n{userMessage}</pre>
         </div>
      {/if}
   </div>
</Modal>
