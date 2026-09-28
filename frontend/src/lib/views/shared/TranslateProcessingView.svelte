<script>
   import { onDestroy } from "svelte";
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { formatDuration } from "$lib/utils.js";

   import FileInfoRow from "$lib/components/FileInfoRow.svelte";
   import ProgressBar from "$lib/components/ProgressBar.svelte";
   import LogsModal from "$lib/components/LogsModal.svelte";
   import Spinner from "$lib/components/Spinner.svelte";

   let { goHome, fileInfos = [], outputPath = "", onCancel, onBack } = $props();

   // – Checklist de fases / tabs
   let steps = $state([
      { key: "work_info", label: "Work info", status: "pending" },
      { key: "title", label: "Título", status: "pending" },
      { key: "blocks", label: "Traducción", status: "pending" },
   ]);

   let activeTab = $state("work_info");
   let userPickedTab = false;

   function onStepEvent(e) {
      const { step, status } = e.detail;
      steps = steps.map((s) => (s.key === step ? { ...s, status } : s));
      if (status === "active" && !userPickedTab) {
         activeTab = step;
      }
   }

   function selectTab(key) {
      activeTab = key;
      userPickedTab = true;
   }

   function stepStatus(key) {
      return steps.find((s) => s.key === key)?.status ?? "pending";
   }

   // Texto en vivo
   let workInfoText = $state("");
   let titleText = $state("");

   function onWorkInfoStream(e) {
      workInfoText = e.detail.text;
   }
   function onTitleStream(e) {
      titleText = e.detail.text;
   }
   function onWorkInfoFinal(e) {
      workInfoText = e.detail.work_info;
   }
   function onTitleFinal(e) {
      titleText = e.detail.title;
   }

   // Progreso por líneas
   let currentFileIndex = $state(0);
   let currentFileLinesDone = $state(0);
   let currentFileLinesTotal = $state(0);
   let linesGlobalDone = $state(0);
   let linesGlobalTotal = $state(0);

   function onLinesProgress(e) {
      const d = e.detail;
      currentFileIndex = d.file_index;
      currentFileLinesDone = d.lines_done_file;
      currentFileLinesTotal = d.lines_total_file;
      linesGlobalDone = d.lines_done_global;
      linesGlobalTotal = d.lines_total_global;
   }

   const globalPercent = $derived(
      linesGlobalTotal > 0 ? Math.round((linesGlobalDone / linesGlobalTotal) * 100) : 0,
   );

   function isFileDone(i) {
      if (progress.success === true) return true;
      return i < currentFileIndex;
   }
   function isFileActive(i) {
      return progress.running && i === currentFileIndex && stepStatus("blocks") === "active";
   }
   function fileProgress(i) {
      if (i < currentFileIndex) return 1;
      if (i === currentFileIndex && currentFileLinesTotal > 0) {
         return currentFileLinesDone / currentFileLinesTotal;
      }
      return null;
   }

   // Timing
   let queueStartedAt = $state(null);
   let fileTimings = $state({});
   let nowTick = $state(Date.now());

   function onQueueStarted(e) {
      queueStartedAt = e.detail.started_at;
   }

   function onFileTiming(e) {
      const { index, done, started_at, elapsed } = e.detail;
      const prev = fileTimings[index] ?? {};
      fileTimings = {
         ...fileTimings,
         [index]: done ? { ...prev, elapsedFinal: elapsed } : { ...prev, startedAt: started_at },
      };
   }

   function fileElapsed(i) {
      const t = fileTimings[i];
      if (!t) return null;
      if (t.elapsedFinal != null) return t.elapsedFinal;
      if (t.startedAt != null) return Math.max(0, nowTick / 1000 - t.startedAt);
      return null;
   }

   const queueElapsedLive = $derived(
      queueStartedAt != null ? Math.max(0, nowTick / 1000 - queueStartedAt) : 0,
   );
   const queueElapsedDisplay = $derived(
      !progress.running && progress.success !== null ? progress.elapsed : queueElapsedLive,
   );

   $effect(() => {
      if (!progress.running) return;
      const interval = setInterval(() => {
         nowTick = Date.now();
      }, 1000);
      return () => clearInterval(interval);
   });

   // Streaming crudo del modelo, por archivo
   let fileStreamLogs = $state({});
   let fileInputLogs = $state({});
   let openFileStream = $state(null);
   let showAllStreamsModal = $state(false);
   let streamTab = $state("output");

   function onBlockStream(e) {
      const { file_index, text } = e.detail;
      fileStreamLogs = { ...fileStreamLogs, [file_index]: text };
   }

   function onBlockInput(e) {
      const { file_index, text } = e.detail;
      fileInputLogs = { ...fileInputLogs, [file_index]: text };
   }

   // System prompt (para el modal de prompt completo)
   let systemPrompt = $state("");

   function onSystemPrompt(e) {
      systemPrompt = e.detail.text;
   }

   // Cancelación
   let cancelling = $state(false);

   function handleCancel() {
      cancelling = true;
      onCancel?.();
   }

   $effect(() => {
      if (!progress.running) {
         if (steps.some((s) => s.status === "active")) {
            steps = steps.map((s) =>
               s.status === "active"
                  ? { ...s, status: progress.success === false ? "cancelled" : "done" }
                  : s,
            );
         }
         cancelling = false;
      }
   });

   // --- Vista de bloques en el modal ---
   let viewMode = $state('blocks');     // 'blocks' | 'raw'
   let selectedBlockIndex = $state(0);
   let selectedFileIndexAll = $state(0); // para el modal de todos los archivos

   // Modal de prompt completo
   let showPromptModal = $state(false);
   let promptViewMode = $state('formatted'); // 'formatted' | 'raw'
   let promptTab = $state('instructions'); // tabs verticales: instructions, glossary, workInfo, title, context, block

   // Funciones para parsear el system prompt
   function parseSystemPrompt(text) {
      if (!text) return { base: '', glossary: '', workInfo: '', title: '' };

      let base = text;
      let glossary = '';
      let workInfo = '';
      let title = '';

      // Extraer [Glossary]
      const glossaryMatch = text.match(/\[Glossary\s*[-–—]?\s*use these renderings when the term appears\]:\s*([\s\S]*?)(?=\n\n\[Work info\]|$)/i);
      if (glossaryMatch) {
         glossary = glossaryMatch[1].trim();
         base = base.replace(glossaryMatch[0], '');
      }

      // Extraer [Work info]
      const workInfoMatch = text.match(/\[Work info\s*[-–—]?\s*persistent context for this work\]:\s*([\s\S]*?)(?=\n\n\[Translated title\]|$)/i);
      if (workInfoMatch) {
         workInfo = workInfoMatch[1].trim();
         base = base.replace(workInfoMatch[0], '');
      }

      // Extraer [Translated title]
      const titleMatch = text.match(/\[Translated title\]:\s*([\s\S]*?)(?=\n\n|$)/i);
      if (titleMatch) {
         title = titleMatch[1].trim();
         base = base.replace(titleMatch[0], '');
      }

      // Limpiar el base de saltos de línea extra y espacios
      base = base.replace(/\n{3,}/g, '\n\n').trim();

      return { base, glossary, workInfo, title };
   }

   const parsedSystem = $derived(parseSystemPrompt(systemPrompt));

   // Funciones para extraer contexto y bloque del user message
   function extractContext(userMessage) {
      if (!userMessage) return '';
      const match = userMessage.match(/\[Previous translated context\]:\s*([\s\S]*?)(?=\n\n\[Block to translate\]|$)/);
      return match ? match[1].trim() : '';
   }

   function extractBlock(userMessage) {
      if (!userMessage) return '';
      const match = userMessage.match(/\[Block to translate\]:\s*([\s\S]*)/);
      return match ? match[1].trim() : userMessage;
   }

   function parseBlocks(text) {
      if (!text) return [];
      const lines = text.split('\n');
      const blocks = [];
      let currentHeader = '';
      let currentContent = [];
      let inBlock = false;

      for (let line of lines) {
         if (line.match(/^═══* Bloque/)) {
            if (inBlock && currentContent.length > 0) {
               blocks.push({
                  header: currentHeader,
                  content: currentContent.join('\n').trim()
               });
            }
            currentHeader = line.trim();
            currentContent = [];
            inBlock = true;
         } else if (inBlock) {
            currentContent.push(line);
         }
      }
      if (inBlock && currentContent.length > 0) {
         blocks.push({
            header: currentHeader,
            content: currentContent.join('\n').trim()
         });
      }
      return blocks;
   }

   // Para el modal individual
   const rawText = $derived(
      streamTab === 'input' ? fileInputLogs[openFileStream] ?? '' : fileStreamLogs[openFileStream] ?? ''
   );
   const blocks = $derived(parseBlocks(rawText));

   // BUG FIX 1: Condicionar reset de selectedBlockIndex al modal individual
   $effect(() => {
      if (openFileStream === null) return;
      if (blocks.length > 0 && selectedBlockIndex >= blocks.length) {
         selectedBlockIndex = 0;
      }
   });

   // Para el modal de todos los archivos
   const allFileRawText = $derived(
      streamTab === 'input' ? fileInputLogs[selectedFileIndexAll] ?? '' : fileStreamLogs[selectedFileIndexAll] ?? ''
   );
   const allFileBlocks = $derived(parseBlocks(allFileRawText));

   // BUG FIX 1: Condicionar reset de selectedBlockIndex al modal "todos los archivos"
   $effect(() => {
      if (!showAllStreamsModal) return;
      if (allFileBlocks.length > 0 && selectedBlockIndex >= allFileBlocks.length) {
         selectedBlockIndex = 0;
      }
   });

   // Mensaje del usuario para el bloque actual (usado solo en modales de archivo individual)
   const currentUserMessage = $derived(
      streamTab === 'input' ? fileInputLogs[openFileStream] ?? '' : fileStreamLogs[openFileStream] ?? ''
   );
   // Mensaje del usuario para la vista general (usado por modal "Prompt completo" y "todos los archivos")
   const currentUserMessageAll = $derived(
      streamTab === 'input' ? fileInputLogs[selectedFileIndexAll] ?? '' : fileStreamLogs[selectedFileIndexAll] ?? ''
   );

   // Helper para copiar con fallback
   async function copyText(text) {
      if (!text) return;
      try {
         await navigator.clipboard.writeText(text);
      } catch {
         const ta = document.createElement('textarea');
         ta.value = text;
         document.body.appendChild(ta);
         ta.select();
         document.execCommand('copy');
         document.body.removeChild(ta);
      }
   }

   // --- Listeners ---
   window.addEventListener("audiotools:translate:step", onStepEvent);
   window.addEventListener("audiotools:translate:work_info_stream", onWorkInfoStream);
   window.addEventListener("audiotools:translate:title_stream", onTitleStream);
   window.addEventListener("audiotools:translate:work_info", onWorkInfoFinal);
   window.addEventListener("audiotools:translate:title", onTitleFinal);
   window.addEventListener("audiotools:translate:lines", onLinesProgress);
   window.addEventListener("audiotools:translate:queue_started", onQueueStarted);
   window.addEventListener("audiotools:file", onFileTiming);
   window.addEventListener("audiotools:translate:block_stream", onBlockStream);
   window.addEventListener("audiotools:translate:block_input", onBlockInput);
   window.addEventListener("audiotools:translate:system_prompt", onSystemPrompt);

   onDestroy(() => {
      window.removeEventListener("audiotools:translate:step", onStepEvent);
      window.removeEventListener("audiotools:translate:work_info_stream", onWorkInfoStream);
      window.removeEventListener("audiotools:translate:title_stream", onTitleStream);
      window.removeEventListener("audiotools:translate:work_info", onWorkInfoFinal);
      window.removeEventListener("audiotools:translate:title", onTitleFinal);
      window.removeEventListener("audiotools:translate:lines", onLinesProgress);
      window.removeEventListener("audiotools:translate:queue_started", onQueueStarted);
      window.removeEventListener("audiotools:file", onFileTiming);
      window.removeEventListener("audiotools:translate:block_stream", onBlockStream);
      window.removeEventListener("audiotools:translate:block_input", onBlockInput);
      window.removeEventListener("audiotools:translate:system_prompt", onSystemPrompt);
   });

   const finished = $derived(!progress.running && progress.success !== null);
   let showLogs = $state(false);
</script>

{#if showLogs}
   <LogsModal logs={progress.logs} onClose={() => (showLogs = false)} />
{/if}

<!-- BUG FIX 2: Modal de prompt completo simplificada (siempre usa vista general) -->
{#if showPromptModal}
   <div class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" role="presentation" onclick={() => (showPromptModal = false)}></div>
   <div class="fixed inset-0 z-50 flex items-center justify-center p-6 pointer-events-none">
      <div class="w-full max-w-4xl h-[85vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-3 pointer-events-auto">
         <div class="flex items-center justify-between shrink-0">
            <h2 class="text-sm font-semibold text-white truncate">
               Prompt completo — {fileInfos[selectedFileIndexAll]?.name ?? 'archivo'} · Bloque {selectedBlockIndex + 1}
            </h2>
            <div class="flex items-center gap-2">
               <button
                  class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
                  onclick={() => {
                     const text = systemPrompt + '\n\n' + currentUserMessageAll;
                     copyText(text);
                  }}
               >
                  Copiar todo
               </button>
               <button
                  class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
                  onclick={() => promptViewMode = promptViewMode === 'formatted' ? 'raw' : 'formatted'}
               >
                  {promptViewMode === 'formatted' ? 'Ver raw' : 'Ver formateado'}
               </button>
               <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showPromptModal = false)}>✕</button>
            </div>
         </div>

         <!-- Contenido: tabs verticales a la izquierda, contenido a la derecha -->
         <div class="flex flex-1 min-h-0 gap-3">
            {#if promptViewMode === 'formatted'}
               <!-- Tabs verticales -->
               <div class="flex flex-col gap-1 overflow-y-auto shrink-0 w-24" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
                  <button
                     class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                        {promptTab === 'instructions' ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                     onclick={() => promptTab = 'instructions'}
                  >
                     Instrucciones
                  </button>
                  <button
                     class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                        {promptTab === 'glossary' ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                     onclick={() => promptTab = 'glossary'}
                  >
                     Glossary
                  </button>
                  <button
                     class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                        {promptTab === 'workInfo' ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                     onclick={() => promptTab = 'workInfo'}
                  >
                     Work info
                  </button>
                  <button
                     class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                        {promptTab === 'title' ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                     onclick={() => promptTab = 'title'}
                  >
                     Título
                  </button>
                  <button
                     class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                        {promptTab === 'context' ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                     onclick={() => promptTab = 'context'}
                  >
                     Contexto
                  </button>
                  <button
                     class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                        {promptTab === 'block' ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                     onclick={() => promptTab = 'block'}
                  >
                     Bloque
                  </button>
               </div>

               <!-- Contenido del tab seleccionado -->
               <div class="flex-1 flex flex-col min-h-0">
                  {#if promptTab === 'instructions'}
                     <div class="flex flex-col h-full">
                        <div class="flex items-center justify-between shrink-0 mb-1">
                           <span class="text-[10px] text-indigo-400 font-medium">Instrucciones del sistema (srt_translation.txt)</span>
                           <button
                              class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                              onclick={() => copyText(parsedSystem.base)}
                           >
                              Copiar
                           </button>
                        </div>
                        <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                           style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                        >{parsedSystem.base || '(No hay instrucciones)'}</pre>
                     </div>
                  {:else if promptTab === 'glossary'}
                     <div class="flex flex-col h-full">
                        <div class="flex items-center justify-between shrink-0 mb-1">
                           <span class="text-[10px] text-emerald-400 font-medium">Glossary (términos fijos)</span>
                           <button
                              class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                              onclick={() => copyText(parsedSystem.glossary)}
                           >
                              Copiar
                           </button>
                        </div>
                        <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                           style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                        >{parsedSystem.glossary || '(No hay glossary)'}</pre>
                     </div>
                  {:else if promptTab === 'workInfo'}
                     <div class="flex flex-col h-full">
                        <div class="flex items-center justify-between shrink-0 mb-1">
                           <span class="text-[10px] text-yellow-400 font-medium">Work info (información del publisher)</span>
                           <button
                              class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                              onclick={() => copyText(parsedSystem.workInfo)}
                           >
                              Copiar
                           </button>
                        </div>
                        <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                           style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                        >{parsedSystem.workInfo || '(No hay work info)'}</pre>
                     </div>
                  {:else if promptTab === 'title'}
                     <div class="flex flex-col h-full">
                        <div class="flex items-center justify-between shrink-0 mb-1">
                           <span class="text-[10px] text-purple-400 font-medium">Título traducido</span>
                           <button
                              class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                              onclick={() => copyText(parsedSystem.title)}
                           >
                              Copiar
                           </button>
                        </div>
                        <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                           style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                        >{parsedSystem.title || '(No hay título)'}</pre>
                     </div>
                  {:else if promptTab === 'context'}
                     <div class="flex flex-col h-full">
                        <div class="flex items-center justify-between shrink-0 mb-1">
                           <span class="text-[10px] text-emerald-400 font-medium">Contexto (líneas anteriores traducidas)</span>
                           <button
                              class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                              onclick={() => copyText(extractContext(currentUserMessageAll))}
                           >
                              Copiar
                           </button>
                        </div>
                        <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                           style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                        >{extractContext(currentUserMessageAll) || '(No hay contexto)'}</pre>
                     </div>
                  {:else if promptTab === 'block'}
                     <div class="flex flex-col h-full">
                        <div class="flex items-center justify-between shrink-0 mb-1">
                           <span class="text-[10px] text-emerald-400 font-medium">Bloque a traducir</span>
                           <button
                              class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                              onclick={() => copyText(extractBlock(currentUserMessageAll))}
                           >
                              Copiar
                           </button>
                        </div>
                        <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                           style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                        >{extractBlock(currentUserMessageAll) || '(No hay bloque)'}</pre>
                     </div>
                  {/if}
               </div>
            {:else}
               <!-- Vista raw: todo concatenado -->
               <div class="flex-1 flex flex-col min-h-0">
                  <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                     style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                  >{systemPrompt}\n\n{currentUserMessageAll}</pre>
               </div>
            {/if}
         </div>
      </div>
   </div>
{/if}

<!-- Modal de archivo individual -->
{#if openFileStream !== null}
   <div class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" role="presentation" onclick={() => (openFileStream = null)}></div>
   <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div class="w-full max-w-4xl h-[85vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-3">
         <div class="flex items-center justify-between shrink-0">
            <h2 class="text-sm font-semibold text-white truncate">
               Stream — {fileInfos[openFileStream]?.name ?? `archivo ${openFileStream + 1}`}
            </h2>
            <div class="flex items-center gap-2">
               <button
                  class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
                  onclick={() => copyText(rawText)}
               >
                  Copiar todo
               </button>
               <button
                  class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
                  onclick={() => viewMode = viewMode === 'blocks' ? 'raw' : 'blocks'}
               >
                  {viewMode === 'blocks' ? 'Ver raw' : 'Ver por bloques'}
               </button>
               <button class="text-white/30 hover:text-white transition-colors" onclick={() => (openFileStream = null)}>✕</button>
            </div>
         </div>

         <!-- Tabs Input / Output -->
         <div class="flex gap-1 shrink-0 border-b border-white/5">
            <button
               class="px-3 py-1.5 text-xs transition-colors {streamTab === 'input' ? 'text-white border-b-2 border-indigo-500' : 'text-white/40 hover:text-white/70'}"
               onclick={() => { streamTab = 'input'; selectedBlockIndex = 0; }}
            >
               Input
            </button>
            <button
               class="px-3 py-1.5 text-xs transition-colors {streamTab === 'output' ? 'text-white border-b-2 border-indigo-500' : 'text-white/40 hover:text-white/70'}"
               onclick={() => { streamTab = 'output'; selectedBlockIndex = 0; }}
            >
               Output
            </button>
         </div>

         <!-- Contenido principal -->
         <div class="flex flex-1 min-h-0 gap-3">
            {#if viewMode === 'blocks'}
               <!-- Tabs verticales (bloques) -->
               <div class="flex flex-col gap-1 overflow-y-auto shrink-0 w-20" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
                  {#each blocks as block, idx (idx)}
                     <button
                        class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                           {selectedBlockIndex === idx ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                        onclick={() => selectedBlockIndex = idx}
                     >
                        Bloque {idx + 1}
                     </button>
                  {:else}
                     <span class="text-xs text-white/25">Sin bloques</span>
                  {/each}
               </div>

               <!-- Contenido del bloque -->
               <div class="flex-1 flex flex-col min-h-0">
                  {#if blocks.length > 0}
                     <div class="flex items-center justify-end shrink-0 mb-1">
                        <button
                           class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                           onclick={() => copyText(blocks[selectedBlockIndex].content)}
                        >
                           Copiar
                        </button>
                     </div>
                     <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                        style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                     >{blocks[selectedBlockIndex].content}</pre>
                  {:else}
                     <div class="flex-1 flex items-center justify-center text-xs text-white/25">
                        Todavía no hay nada para este archivo.
                     </div>
                  {/if}
               </div>
            {:else}
               <!-- Raw view -->
               <div class="flex-1 flex flex-col min-h-0">
                  <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                     style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                  >{rawText}</pre>
               </div>
            {/if}
         </div>
      </div>
   </div>
{/if}

<!-- Modal de todos los archivos -->
{#if showAllStreamsModal}
   <div class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" role="presentation" onclick={() => (showAllStreamsModal = false)}></div>
   <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div class="w-full max-w-4xl h-[85vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-3">
         <div class="flex items-center justify-between shrink-0">
            <h2 class="text-sm font-semibold text-white">Stream — todos los archivos</h2>
            <div class="flex items-center gap-2">
               <button
                  class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
                  onclick={() => copyText(allFileRawText)}
               >
                  Copiar todo
               </button>
               <button
                  class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
                  onclick={() => viewMode = viewMode === 'blocks' ? 'raw' : 'blocks'}
               >
                  {viewMode === 'blocks' ? 'Ver raw' : 'Ver por bloques'}
               </button>
               <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showAllStreamsModal = false)}>✕</button>
            </div>
         </div>

         <!-- Tabs Input / Output -->
         <div class="flex gap-1 shrink-0 border-b border-white/5">
            <button
               class="px-3 py-1.5 text-xs transition-colors {streamTab === 'input' ? 'text-white border-b-2 border-indigo-500' : 'text-white/40 hover:text-white/70'}"
               onclick={() => { streamTab = 'input'; selectedFileIndexAll = 0; selectedBlockIndex = 0; }}
            >
               Input
            </button>
            <button
               class="px-3 py-1.5 text-xs transition-colors {streamTab === 'output' ? 'text-white border-b-2 border-indigo-500' : 'text-white/40 hover:text-white/70'}"
               onclick={() => { streamTab = 'output'; selectedFileIndexAll = 0; selectedBlockIndex = 0; }}
            >
               Output
            </button>
         </div>

         <!-- Contenido principal -->
         <div class="flex flex-1 min-h-0 gap-3">
            <!-- Tabs verticales (archivos) -->
            <div class="flex flex-col gap-1 overflow-y-auto shrink-0 w-24" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
               {#each fileInfos as file, idx (file.path)}
                  <button
                     class="px-2 py-1.5 text-xs text-left rounded-md transition-colors truncate
                        {selectedFileIndexAll === idx ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                     onclick={() => { selectedFileIndexAll = idx; selectedBlockIndex = 0; }}
                     title={file.name}
                  >
                     {file.name}
                  </button>
               {:else}
                  <span class="text-xs text-white/25">Sin archivos</span>
               {/each}
            </div>

            <!-- Contenido del archivo seleccionado -->
            <div class="flex-1 flex flex-col min-h-0">
               {#if fileInfos.length > 0}
                  {#if viewMode === 'blocks'}
                     <!-- Tabs verticales de bloques dentro del archivo -->
                     <div class="flex flex-1 gap-3 min-h-0">
                        <div class="flex flex-col gap-1 overflow-y-auto shrink-0 w-20" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
                           {#each allFileBlocks as block, bidx (bidx)}
                              <button
                                 class="px-2 py-1.5 text-xs text-left rounded-md transition-colors
                                    {selectedBlockIndex === bidx ? 'bg-indigo-500/20 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}"
                                 onclick={() => selectedBlockIndex = bidx}
                              >
                                 Bloque {bidx + 1}
                              </button>
                           {:else}
                              <span class="text-xs text-white/25">Sin bloques</span>
                           {/each}
                        </div>

                        <div class="flex-1 flex flex-col min-h-0">
                           {#if allFileBlocks.length > 0}
                              <div class="flex items-center justify-end shrink-0 mb-1">
                                 <button
                                    class="text-[10px] text-white/30 hover:text-white/70 transition-colors"
                                    onclick={() => copyText(allFileBlocks[selectedBlockIndex].content)}
                                 >
                                    Copiar
                                 </button>
                              </div>
                              <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                                 style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                              >{allFileBlocks[selectedBlockIndex].content}</pre>
                           {:else}
                              <div class="flex-1 flex items-center justify-center text-xs text-white/25">
                                 Este archivo no tiene bloques.
                              </div>
                           {/if}
                        </div>
                     </div>
                  {:else}
                     <!-- Raw view -->
                     <div class="flex-1 flex flex-col min-h-0">
                        <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60 cursor-text"
                           style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
                        >{allFileRawText}</pre>
                     </div>
                  {/if}
               {:else}
                  <div class="flex-1 flex items-center justify-center text-xs text-white/25">
                     No hay archivos.
                  </div>
               {/if}
            </div>
         </div>
      </div>
   </div>
{/if}

<div class="flex h-full flex-col">
   <!-- Header -->
   <header class="flex items-center border-b border-white/5 px-8 py-5 shrink-0">
      <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={goHome}> ← Inicio </button>
      <span class="text-white/10 mx-3">/</span>
      <h1 class="text-sm font-semibold flex-1">Translate</h1>

      <div class="flex items-center gap-2">
         {#if progress.running}
            <Spinner size={14} duration="1.5s" />
            <button
               class="rounded-md border border-red-500/20 bg-red-500/10 px-2.5 py-1
                 text-xs text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-40"
               onclick={handleCancel}
               disabled={cancelling}
            >
               {cancelling ? "Deteniendo..." : "Cancelar"}
            </button>
         {/if}
         <!-- BUG FIX 2: Botón "Prompt completo" en el header -->
         <button
            class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1
               text-xs text-white/40 hover:text-white/70 transition-colors"
            onclick={() => (showPromptModal = true)}
            title="Ver el prompt completo"
         >
            Prompt
         </button>
         <button
            class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1
               text-xs text-white/40 hover:text-white/70 transition-colors"
            onclick={() => (showLogs = !showLogs)}
         >
            Logs
         </button>
      </div>
   </header>

   <main class="flex flex-1 flex-col gap-5 overflow-hidden px-8 py-6">
      <!-- Checklist de fases -->
      <div class="flex items-center justify-center gap-2 shrink-0">
         {#each steps as s (s.key)}
            <button
               onclick={() => selectTab(s.key)}
               class="flex items-center gap-2 rounded-lg border px-4 py-2 transition-all duration-200
                  {activeTab === s.key ? 'opacity-100 scale-[1.04]' : 'opacity-45 hover:opacity-75'}
                  {s.status === 'done'
                  ? 'border-emerald-500/20 bg-emerald-500/5'
                  : s.status === 'active'
                    ? 'border-indigo-500/30 bg-indigo-500/5'
                    : s.status === 'skipped'
                      ? 'border-white/5 bg-white/3'
                      : s.status === 'cancelled'
                        ? 'border-red-500/20 bg-red-500/5'
                        : 'border-white/5 bg-white/3'}"
               style={activeTab === s.key ? "box-shadow: 0 0 0 1.5px rgba(129,140,248,0.55);" : ""}
            >
               <span class="flex w-4 items-center justify-center">
                  {#if s.status === "done"}
                     <span class="text-emerald-400 text-xs">✓</span>
                  {:else if s.status === "active"}
                     <Spinner size={12} duration="1.5s" />
                  {:else if s.status === "skipped"}
                     <span class="text-white/20 text-xs">—</span>
                  {:else if s.status === "cancelled"}
                     <span class="text-red-400 text-xs">✕</span>
                  {:else}
                     <span class="text-white/15 text-xs">○</span>
                  {/if}
               </span>
               <span class="text-xs {s.status === 'pending' ? 'text-white/30' : 'text-white/70'}">{s.label}</span>
            </button>
         {/each}
      </div>

      <!-- Contenido del tab activo -->
      <div class="flex flex-1 flex-col min-h-0">
         {#if activeTab === "work_info"}
            {#if stepStatus("work_info") === "skipped"}
               <div class="flex flex-1 items-center justify-center text-xs text-white/25">
                  No se dio info del publisher — paso omitido
               </div>
            {:else}
               <textarea
                  readonly
                  value={workInfoText}
                  placeholder="Esperando al modelo..."
                  class="flex-1 resize-none rounded-lg border border-white/10 bg-white/5 p-3
                     text-xs text-white/70 font-mono outline-none"
                  style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
               ></textarea>
            {/if}
         {:else if activeTab === "title"}
            {#if stepStatus("title") === "skipped"}
               <div class="flex flex-1 items-center justify-center text-xs text-white/25">
                  No se dio título original — paso omitido
               </div>
            {:else}
               <textarea
                  readonly
                  value={titleText}
                  placeholder="Esperando al modelo..."
                  class="flex-1 resize-none rounded-lg border border-white/10 bg-white/5 p-3
                     text-xs text-white/70 font-mono outline-none"
                  style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
               ></textarea>
            {/if}
         {:else if activeTab === "blocks"}
            <div class="flex flex-1 flex-col gap-4 min-h-0">
               <!-- Progreso global -->
               <div class="flex flex-col gap-2 shrink-0">
                  <button
                     class="flex items-center justify-between text-left rounded-lg -mx-2 px-2 py-1 transition-colors hover:bg-white/5"
                     onclick={() => (showAllStreamsModal = true)}
                     title="Ver el stream del modelo para todos los archivos"
                  >
                     <span class="text-3xl font-semibold tabular-nums text-white">
                        {globalPercent}<span class="text-lg text-white/30">%</span>
                     </span>
                     <span class="text-xs text-white/40 tabular-nums">
                        {linesGlobalDone}/{linesGlobalTotal} líneas
                        {#if queueElapsedDisplay > 0}
                           <span class="ml-2 text-white/25">· {formatDuration(queueElapsedDisplay)}</span>
                        {/if}
                        {#if cancelling}<span class="text-red-400/70 ml-2">deteniendo...</span>{/if}
                     </span>
                  </button>
                  <ProgressBar
                     value={linesGlobalTotal > 0 ? linesGlobalDone / linesGlobalTotal : 0}
                     running={progress.running}
                     success={progress.success}
                  />
               </div>

               <!-- Lista de archivos -->
               <div
                  class="flex-1 overflow-y-auto min-h-0"
                  style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
               >
                  <div class="flex flex-col gap-2 pr-1">
                     {#each fileInfos as file, i (file.path)}
                        <FileInfoRow
                           name={file.name}
                           sizeMb={file.size_mb}
                           duration={file.duration_seconds}
                           progress={fileProgress(i)}
                           active={isFileActive(i)}
                           done={isFileDone(i)}
                           elapsedSeconds={fileElapsed(i)}
                           onRowClick={() => (openFileStream = i)}
                        />
                     {/each}
                  </div>
               </div>
            </div>
         {/if}
      </div>

      <!-- Botones resultado -->
      {#if finished}
         <div class="shrink-0 flex items-center justify-center gap-2 pt-3 border-t border-white/5">
            {#if progress.success === true}
               <button
                  class="rounded-lg border border-white/10 bg-white/5 px-4 py-2
                   text-xs text-white/60 hover:text-white transition-colors"
                  onclick={() => bridge.open_folder(outputPath)}
               >
                  Abrir carpeta
               </button>
            {/if}
            <button
               class="rounded-lg border border-white/10 bg-white/5 px-4 py-2
                 text-xs text-white/60 hover:text-white transition-colors"
               onclick={onBack}
            >
               Volver
            </button>
         </div>
      {/if}
   </main>
</div>