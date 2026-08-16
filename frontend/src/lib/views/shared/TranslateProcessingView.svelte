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

   // ── Checklist de fases / tabs ────────────────────────────────────────────

   let steps = $state([
      { key: "work_info", label: "Work info", status: "pending" },
      { key: "title", label: "Título", status: "pending" },
      { key: "blocks", label: "Traducción", status: "pending" },
   ]);

   let activeTab = $state("work_info");
   let userPickedTab = false; // si el usuario clickeó un tab a mano, no lo pisamos con el auto-avance

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

   // ── Texto en vivo de work_info / título ──────────────────────────────────

   let workInfoText = $state("");
   let titleText = $state("");

   function onWorkInfoStream(e) {
      workInfoText = e.detail.text;
   }
   function onTitleStream(e) {
      titleText = e.detail.text;
   }
   // valor final autoritativo (por si el último tick de streaming no alcanzó a mandarse)
   function onWorkInfoFinal(e) {
      workInfoText = e.detail.work_info;
   }
   function onTitleFinal(e) {
      titleText = e.detail.title;
   }

   // ── Progreso por líneas (tab Traducción) ─────────────────────────────────

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

   // ── Timing ───────────────────────────────────────────────────────────────
   // queueStartedAt / fileTimings llegan del backend (timestamps epoch, mas
   // precisos que medir con Date.now() del navegador). nowTick solo sirve
   // para que el conteo en vivo se re-dibuje cada 1s mientras corre — el
   // numero final (una vez que un archivo o la cola terminan) siempre sale
   // del backend, no de este tick.

   let queueStartedAt = $state(null); // epoch segundos — incluye carga del modelo
   let fileTimings = $state({}); // { [idx]: { startedAt: epoch|null, elapsedFinal: seg|null } }
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
   // Una vez terminado, el total autoritativo es progress.elapsed (lo manda
   // el backend en audiotools:done — ver progress.svelte.js). No uso la
   // const `finished` de mas abajo porque en el orden del archivo todavia
   // no esta declarada en este punto.
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

   // ── Cancelación: feedback inmediato aunque el modelo tarde en soltar ───────

   let cancelling = $state(false);

   function handleCancel() {
      cancelling = true;
      onCancel?.();
   }

   // ── Reacciona a que la corrida terminó, sin loop infinito ──────────────────
   // (la condición extra evita reasignar `steps` si ya no queda nada "active"
   //  que resolver — sin eso, el efecto se re-dispara a sí mismo sin parar)

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

   // ── Listeners ────────────────────────────────────────────────────────────
   // Mismo patrón que progress.svelte.js: window.addEventListener directo
   // sobre los CustomEvent que api.py dispara via evaluate_js().

   window.addEventListener("audiotools:translate:step", onStepEvent);
   window.addEventListener("audiotools:translate:work_info_stream", onWorkInfoStream);
   window.addEventListener("audiotools:translate:title_stream", onTitleStream);
   window.addEventListener("audiotools:translate:work_info", onWorkInfoFinal);
   window.addEventListener("audiotools:translate:title", onTitleFinal);
   window.addEventListener("audiotools:translate:lines", onLinesProgress);
   window.addEventListener("audiotools:translate:queue_started", onQueueStarted);
   window.addEventListener("audiotools:file", onFileTiming);

   onDestroy(() => {
      window.removeEventListener("audiotools:translate:step", onStepEvent);
      window.removeEventListener("audiotools:translate:work_info_stream", onWorkInfoStream);
      window.removeEventListener("audiotools:translate:title_stream", onTitleStream);
      window.removeEventListener("audiotools:translate:work_info", onWorkInfoFinal);
      window.removeEventListener("audiotools:translate:title", onTitleFinal);
      window.removeEventListener("audiotools:translate:lines", onLinesProgress);
      window.removeEventListener("audiotools:translate:queue_started", onQueueStarted);
      window.removeEventListener("audiotools:file", onFileTiming);
   });

   const finished = $derived(!progress.running && progress.success !== null);
   let showLogs = $state(false);
</script>

{#if showLogs}
   <LogsModal logs={progress.logs} onClose={() => (showLogs = false)} />
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
      <!-- Checklist de fases, en una fila, hace también de selector de tab -->
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
                  <div class="flex items-center justify-between">
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
                  </div>
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