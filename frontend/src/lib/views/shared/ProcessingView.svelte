<script>
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
   import ProgressBar from "$lib/components/ProgressBar.svelte";
   import FileInfoRow from "$lib/components/FileInfoRow.svelte";
   import LogsModal from "$lib/components/LogsModal.svelte";
   import TranscribeFileLogsModal from "$lib/components/TranscribeFileLogsModal.svelte";
   import Spinner from "$lib/components/Spinner.svelte";
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { formatElapsed } from "$lib/utils.js"; 

   let {
      title,
      goHome,
      fileInfos = [],
      outputPath = null,
      onCancel,
      onBack,
      showOpenFile = true,
      enableFileLogs = false,
      fileLogsByIndex = {},
   } = $props();

   // ── Logs modals ────────────────────────────────────────────────────────────

   let showLogs = $state(false);
   let selectedFileIndex = $state(null);

   function fileStatus(index) {
      if (progress.success === true || index < progress.completed) return "Completado";
      if (index === progress.fileIndex && progress.success === false) return "Finalizado con error";
      if (progress.running && index === progress.fileIndex) return "Procesando";
      return "En espera";
   }

   // ── Progreso ────────────────────────────────────────────────────────────────

   const percent = $derived(Math.round(progress.value * 100));

   const completedCount = $derived(progress.success === true ? fileInfos.length : progress.completed);

   function isFileDone(i) {
      if (progress.success === true) return true;
      return i < progress.completed;
   }

   function isFileActive(i) {
      if (!progress.running) return false;
      return i === progress.fileIndex;
   }

   function fileProgress(i) {
      if (progress.success === false) {
         if (i < progress.completed) return 1;
         if (i === progress.fileIndex) return progress.fileProgress;
         return null;
      }
      if (progress.success === true) return 1;
      if (i < progress.completed) return 1;
      if (i === progress.fileIndex) return progress.fileProgress;
      return null;
   }

   // ── Estado final ────────────────────────────────────────────────────────────

   const finished = $derived(!progress.running && progress.success !== null);

   const statusLabel = $derived(
      progress.success === true
         ? "Completado"
         : progress.success === false
           ? "Error"
           : progress.running
             ? "Procesando..."
             : "",
   );

   const statusColor = $derived(
      progress.success === true ? "text-emerald-400" : progress.success === false ? "text-red-400" : "text-white/40",
   );
</script>

{#if showLogs}
   <LogsModal logs={progress.logs} onClose={() => (showLogs = false)} />
{/if}

{#if enableFileLogs && selectedFileIndex !== null}
   <TranscribeFileLogsModal
      name={fileInfos[selectedFileIndex]?.name ?? `Archivo ${selectedFileIndex + 1}`}
      logs={fileLogsByIndex[selectedFileIndex] ?? []}
      status={fileStatus(selectedFileIndex)}
      onClose={() => (selectedFileIndex = null)}
   />
{/if}

<div class="flex h-full flex-col">
   <!-- Header -->
   <header class="flex items-center border-b border-white/5 px-8 py-5 shrink-0">
      <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={goHome}> ← Inicio </button>
      <span class="text-white/10 mx-3">/</span>
      <h1 class="text-sm font-semibold flex-1">{title}</h1>

      <div class="flex items-center gap-2">
         {#if progress.running}
            <Spinner size={14} duration="1.5s" />
            <button
               class="rounded-md border border-red-500/20 bg-red-500/10 px-2.5 py-1
                 text-xs text-red-400 hover:bg-red-500/20 transition-colors"
               onclick={onCancel}
            >
               Cancelar
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
      <!-- Progreso global -->
      <div class="flex flex-col gap-3 shrink-0">
         <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
               <span class="text-4xl font-semibold tabular-nums text-white">
                  {percent}<span class="text-xl text-white/30">%</span>
               </span>
               {#if progress.running}
                  <Spinner size={28} duration="1.25s" />
               {/if}
            </div>
            <div class="flex items-center gap-3">
               <span class="{statusColor} text-sm font-medium">{statusLabel}</span>
               {#if progress.elapsed > 0}
                  <span class="text-xs text-white/30">{formatElapsed(progress.elapsed)}</span>
               {/if}
               <span class="text-sm text-white/40 tabular-nums">
                  {completedCount}/{fileInfos.length}
               </span>
            </div>
         </div>

         <ProgressBar value={progress.value} running={progress.running} success={progress.success} />
      </div>

      <!-- Lista de archivos -->
      <div
         class="flex-1 overflow-y-auto min-h-0"
         style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
      >
         <div class="flex flex-col gap-2 pr-1">
            {#each fileInfos as file, i (file.name)}
               <FileInfoRow
                  name={file.name}
                  sizeMb={file.size_mb}
                  duration={file.duration_seconds}
                  progress={fileProgress(i)}
                  active={isFileActive(i)}
                  done={isFileDone(i)}
                  onRowClick={enableFileLogs ? () => (selectedFileIndex = i) : null}
               />
            {/each}
         </div>
      </div>

      <!-- Botones resultado -->
      {#if finished}
         <div
            class="shrink-0 flex items-center justify-center gap-2 pt-2
                  border-t border-white/5 bg-zinc-950"
         >
            {#if progress.success === true}
               <button
                  class="rounded-lg border border-white/10 bg-white/5 px-4 py-2
                   text-xs text-white/60 hover:text-white transition-colors"
                  onclick={() => bridge.open_folder(outputPath)}
               >
                  Abrir carpeta
               </button>
               {#if showOpenFile}
                  <button
                     class="rounded-lg border border-white/10 bg-white/5 px-4 py-2
                     text-xs text-white/60 hover:text-white transition-colors"
                     onclick={() => bridge.open_file(outputPath)}
                  >
                     Abrir archivo
                  </button>
               {/if}
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
