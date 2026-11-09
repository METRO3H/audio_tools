<script>
   /**
    * TranslateProcessingView.svelte
    * ───────────────────────────────
    * Progreso en vivo de una corrida de Translate SRT: checklist de pasos (work info, título,
    * traducción), progreso por líneas y por archivo, y tres modales de detalle (stream de un
    * archivo, stream de todos y prompt completo).
    *
    * El estado que alimentan los eventos vive en useSrtProgress; el que comparten los modales,
    * en StreamViewer; cada modal, en su componente (StreamModal, SystemPromptModal).
    */
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { formatDuration } from "@shared/utils.js";

   import FileInfoRow from "@shared/components/FileInfoRow.svelte";
   import ProgressBar from "@shared/ui/ProgressBar.svelte";
   import LogsModal from "@shared/components/LogsModal.svelte";
   import Spinner from "@shared/ui/Spinner.svelte";
   import ConfirmModal from "@shared/ui/ConfirmModal.svelte";
   import StreamModal from "@translate/srt/StreamModal.svelte";
   import SystemPromptModal from "@translate/srt/SystemPromptModal.svelte";
   import { useSrtProgress } from "@translate/srt/useSrtProgress.svelte.js";
   import { StreamViewer } from "@translate/srt/streamViewer.svelte.js";

   let { goHome, fileInfos = [], outputPath = "", onCancel, onBack } = $props();

   const run = useSrtProgress({ onCancel: () => onCancel?.() });
   const viewer = new StreamViewer();

   const finished = $derived(!progress.running && progress.success !== null);
   let showLogs = $state(false);

   // "← Inicio" con una traducción en curso: antes volvía al menú sin cancelar el job, que
   // seguía corriendo en el backend sin que nadie lo viera. Ahora avisa primero.
   let showLeaveConfirm = $state(false);

   function requestGoHome() {
      if (progress.running) {
         showLeaveConfirm = true;
      } else {
         goHome();
      }
   }

   function confirmLeave() {
      showLeaveConfirm = false;
      onCancel?.();
      goHome();
   }
</script>

{#if showLeaveConfirm}
   <ConfirmModal
      title="Hay una traducción en curso"
      message="Si vuelves al inicio ahora, se cancela. ¿Seguro que quieres salir?"
      confirmLabel="Cancelar y volver al inicio"
      cancelLabel="Seguir traduciendo"
      danger
      onConfirm={confirmLeave}
      onCancel={() => (showLeaveConfirm = false)}
   />
{/if}

{#if showLogs}
   <LogsModal logs={progress.logs} onClose={() => (showLogs = false)} />
{/if}

{#if viewer.showPromptModal}
   <SystemPromptModal
      {viewer}
      {fileInfos}
      systemPrompt={run.systemPrompt}
      sections={run.systemPromptSections}
      streamLogs={run.fileStreamLogs}
      inputLogs={run.fileInputLogs}
      onClose={() => (viewer.showPromptModal = false)}
   />
{/if}

{#if viewer.openFileStream !== null}
   <StreamModal
      {viewer}
      {fileInfos}
      streamLogs={run.fileStreamLogs}
      inputLogs={run.fileInputLogs}
      onClose={() => (viewer.openFileStream = null)}
   />
{/if}

{#if viewer.showAllStreamsModal}
   <StreamModal
      all
      {viewer}
      {fileInfos}
      streamLogs={run.fileStreamLogs}
      inputLogs={run.fileInputLogs}
      onClose={() => (viewer.showAllStreamsModal = false)}
   />
{/if}

<div class="flex h-full flex-col">
   <!-- Header -->
   <header class="flex items-center border-b border-white/5 px-8 py-5 shrink-0">
      <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={requestGoHome}> ← Inicio </button>
      <span class="text-white/10 mx-3">/</span>
      <h1 class="text-sm font-semibold flex-1">Translate</h1>

      <div class="flex items-center gap-2">
         {#if progress.running}
            <Spinner size={14} duration="1.5s" />
            <button
               class="rounded-md border border-red-500/20 bg-red-500/10 px-2.5 py-1
                 text-xs text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-40"
               onclick={run.cancel}
               disabled={run.cancelling}
            >
               {run.cancelling ? "Deteniendo..." : "Cancelar"}
            </button>
         {/if}
         <button
            class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1
               text-xs text-white/40 hover:text-white/70 transition-colors"
            onclick={() => (viewer.showPromptModal = true)}
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
         {#each run.steps as s (s.key)}
            <button
               onclick={() => run.selectTab(s.key)}
               class="flex items-center gap-2 rounded-lg border px-4 py-2 transition-all duration-200
                  {run.activeTab === s.key ? 'opacity-100 scale-[1.04]' : 'opacity-45 hover:opacity-75'}
                  {s.status === 'done'
                  ? 'border-emerald-500/20 bg-emerald-500/5'
                  : s.status === 'active'
                    ? 'border-indigo-500/30 bg-indigo-500/5'
                    : s.status === 'skipped'
                      ? 'border-white/5 bg-white/3'
                      : s.status === 'cancelled'
                        ? 'border-red-500/20 bg-red-500/5'
                        : 'border-white/5 bg-white/3'}"
               style={run.activeTab === s.key ? "box-shadow: 0 0 0 1.5px rgba(129,140,248,0.55);" : ""}
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
         {#if run.activeTab === "work_info"}
            {#if run.stepStatus("work_info") === "skipped"}
               <div class="flex flex-1 items-center justify-center text-xs text-white/25">
                  No se dio info del publisher — paso omitido
               </div>
            {:else}
               <textarea
                  readonly
                  value={run.workInfoText}
                  placeholder="Esperando al modelo..."
                  class="flex-1 resize-none rounded-lg border border-white/10 bg-white/5 p-3
                     text-xs text-white/70 font-mono outline-none"
                  style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
               ></textarea>
            {/if}
         {:else if run.activeTab === "title"}
            {#if run.stepStatus("title") === "skipped"}
               <div class="flex flex-1 items-center justify-center text-xs text-white/25">
                  No se dio título original — paso omitido
               </div>
            {:else}
               <textarea
                  readonly
                  value={run.titleText}
                  placeholder="Esperando al modelo..."
                  class="flex-1 resize-none rounded-lg border border-white/10 bg-white/5 p-3
                     text-xs text-white/70 font-mono outline-none"
                  style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
               ></textarea>
            {/if}
         {:else if run.activeTab === "blocks"}
            <div class="flex flex-1 flex-col gap-4 min-h-0">
               <!-- Progreso global -->
               <div class="flex flex-col gap-2 shrink-0">
                  <button
                     class="flex items-center justify-between text-left rounded-lg -mx-2 px-2 py-1 transition-colors hover:bg-white/5"
                     onclick={() => (viewer.showAllStreamsModal = true)}
                     title="Ver el stream del modelo para todos los archivos"
                  >
                     <span class="text-3xl font-semibold tabular-nums text-white">
                        {run.globalPercent}<span class="text-lg text-white/30">%</span>
                     </span>
                     <span class="text-xs text-white/40 tabular-nums">
                        {run.linesGlobalDone}/{run.linesGlobalTotal} líneas
                        {#if run.queueElapsedDisplay > 0}
                           <span class="ml-2 text-white/25">· {formatDuration(run.queueElapsedDisplay)}</span>
                        {/if}
                        {#if run.cancelling}<span class="text-red-400/70 ml-2">deteniendo...</span>{/if}
                     </span>
                  </button>
                  <ProgressBar
                     value={run.linesGlobalTotal > 0 ? run.linesGlobalDone / run.linesGlobalTotal : 0}
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
                           progress={run.fileProgress(i)}
                           active={run.isFileActive(i)}
                           done={run.isFileDone(i)}
                           elapsedSeconds={run.fileElapsed(i)}
                           onRowClick={() => (viewer.openFileStream = i)}
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
