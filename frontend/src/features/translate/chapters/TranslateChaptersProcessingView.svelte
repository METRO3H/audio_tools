<script>
   /**
    * TranslateChaptersProcessingView.svelte
    * ────────────────────────────────────────
    * Progreso en vivo mientras se traducen los títulos de capítulos de la cola. NO escribe nada
    * en disco (a diferencia de TranslateProcessingView, de SRT): cuando termina bien, el padre
    * (TranslateChaptersView) pasa a la vista previa — esta vista no sabe nada de eso, solo
    * muestra qué está pasando y deja cancelar.
    */

   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import FileInfoRow from "@shared/components/FileInfoRow.svelte";
   import ProgressBar from "@shared/ui/ProgressBar.svelte";
   import LogsModal from "@shared/components/LogsModal.svelte";
   import Spinner from "@shared/ui/Spinner.svelte";
   import ConfirmModal from "@shared/ui/ConfirmModal.svelte";

   let { goHome, fileInfos = [], onCancel } = $props();

   let phaseText = $state("Iniciando...");
   let workInfoText = $state("");
   // file_index -> [{index, start, end, original_title, translated_title}], a medida que cada
   // archivo termina (ver audiotools:translation:file_titles) — se muestran apenas llegan, no hay
   // que esperar a la vista previa para ver algo.
   let fileTitles = $state({});

   function onPhase(e) {
      phaseText = e.detail.phase;
   }
   function onWorkInfoStream(e) {
      workInfoText = e.detail.text;
   }
   // El stream trae el texto crudo del modelo (con <think> y espacios); el final es el que el
   // runner realmente usa en el prompt, ya limpio. Igual que SRT, el final reemplaza al stream.
   function onWorkInfoFinal(e) {
      workInfoText = e.detail.work_info;
   }
   function onFileTitles(e) {
      fileTitles = { ...fileTitles, [e.detail.file_index]: e.detail.chapters };
   }

   window.addEventListener("audiotools:translation:phase", onPhase);
   window.addEventListener("audiotools:translation:work_info_stream", onWorkInfoStream);
   window.addEventListener("audiotools:translation:work_info", onWorkInfoFinal);
   window.addEventListener("audiotools:translation:file_titles", onFileTitles);
   $effect(() => () => {
      window.removeEventListener("audiotools:translation:phase", onPhase);
      window.removeEventListener("audiotools:translation:work_info_stream", onWorkInfoStream);
      window.removeEventListener("audiotools:translation:work_info", onWorkInfoFinal);
      window.removeEventListener("audiotools:translation:file_titles", onFileTitles);
   });

   // Igual que TranslateProcessingView (SRT), pero más simple: acá no hay progreso fino por
   // línea dentro de un archivo, solo archivo completo sí/no (progress.files, ver
   // progress.svelte.js) — el "activo" es el primero que todavía no figura como terminado.
   const doneCount = $derived(progress.files.filter((f) => f?.done).length);
   const isFileDone = (i) => !!progress.files[i]?.done;
   const isFileActive = (i) => progress.running && i === doneCount;

   let showLogs = $state(false);

   // "← Inicio" con la cola corriendo: mismo criterio que TranslateProcessingView (SRT) — avisa
   // antes de cancelar y salir, en vez de abandonar el job corriendo sin que nadie lo vea.
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

<div class="flex h-full flex-col">
   <div class="flex items-center justify-between px-6 py-4 shrink-0">
      <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={requestGoHome}> ← Inicio </button>
      <span class="text-xs text-white/30">Translate — Chapters</span>
   </div>

   <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-6">
      <div class="flex w-full max-w-lg flex-col gap-4">
         <div class="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3">
            {#if progress.running}<Spinner size={14} duration="1.5s" />{/if}
            <span class="text-sm text-white/80">{phaseText}</span>
         </div>

         {#if progress.total > 1}
            <ProgressBar value={progress.value} />
         {/if}

         {#if workInfoText}
            <div class="flex flex-col gap-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
               <span class="text-[11px] text-white/30">Work info</span>
               <p class="text-xs text-white/50 whitespace-pre-wrap max-h-32 overflow-y-auto">{workInfoText}</p>
            </div>
         {/if}

         <ul class="flex flex-col gap-2 overflow-y-auto max-h-64 pr-1">
            {#each fileInfos as file, i (file.path)}
               <li class="flex flex-col gap-1.5">
                  <FileInfoRow name={file.name} sizeMb={file.size_mb} active={isFileActive(i)} done={isFileDone(i)} />
                  {#if fileTitles[i]}
                     <ul class="flex flex-col gap-0.5 pl-1 text-[11px] text-white/40">
                        {#each fileTitles[i] as ch (ch.index)}
                           <li class="truncate">
                              [{ch.index}] {ch.original_title} → <span class="text-emerald-400/80">{ch.translated_title}</span>
                           </li>
                        {/each}
                     </ul>
                  {/if}
               </li>
            {/each}
         </ul>

         <div class="flex gap-2">
            {#if progress.running}
               <button
                  class="flex-1 rounded-lg border border-red-500/30 py-2 text-xs text-red-400 hover:bg-red-500/10 transition-colors"
                  onclick={onCancel}
               >
                  Detener
               </button>
            {/if}
            <button
               class="flex-1 rounded-lg border border-white/10 py-2 text-xs text-white/60 hover:text-white transition-colors"
               onclick={() => (showLogs = true)}
            >
               Ver logs
            </button>
         </div>
      </div>
   </main>
</div>
