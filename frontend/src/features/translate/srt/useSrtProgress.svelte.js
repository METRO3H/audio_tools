/**
 * useSrtProgress.svelte.js
 * ─────────────────────────
 * Estado en vivo de una corrida de Translate SRT, alimentado por los eventos
 * `audiotools:translation:*` (ver core/translation/job.py::run_translate_job) y por
 * `audiotools:file`. Es lo que TranslateProcessingView mostraba directo en su <script>:
 * pasos y pestañas, texto de work info y título, progreso por líneas, tiempos y los logs de
 * stream/input por archivo.
 *
 * Se llama durante la inicialización del componente: los listeners se registran en el momento
 * (no en un $effect, para no perder eventos que lleguen antes de montar) y se quitan al destruirlo.
 *
 *   const run = useSrtProgress({ onCancel: () => onCancel?.() });
 *   run.steps, run.activeTab, run.workInfoText, run.globalPercent, run.fileStreamLogs, ...
 */

import { onDestroy } from "svelte";
import { progress } from "@shared/state/progress.svelte.js";

export function useSrtProgress({ onCancel } = {}) {
   // ── Checklist de pasos / pestañas ──────────────────────────────────────────
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
      if (status === "active" && !userPickedTab) activeTab = step;
   }

   function selectTab(key) {
      activeTab = key;
      userPickedTab = true;
   }

   function stepStatus(key) {
      return steps.find((s) => s.key === key)?.status ?? "pending";
   }

   // ── Texto en vivo ──────────────────────────────────────────────────────────
   // El stream trae el texto crudo del modelo; el evento final trae el ya limpio y lo reemplaza.
   let workInfoText = $state("");
   let titleText = $state("");

   const onWorkInfoStream = (e) => (workInfoText = e.detail.text);
   const onTitleStream = (e) => (titleText = e.detail.text);
   const onWorkInfoFinal = (e) => (workInfoText = e.detail.work_info);
   const onTitleFinal = (e) => (titleText = e.detail.title);

   // ── Progreso por líneas ────────────────────────────────────────────────────
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

   // ── Tiempos ────────────────────────────────────────────────────────────────
   let queueStartedAt = $state(null);
   let fileTimings = $state({});
   let nowTick = $state(Date.now());

   const onQueueStarted = (e) => (queueStartedAt = e.detail.started_at);

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

   const queueElapsedLive = $derived(queueStartedAt != null ? Math.max(0, nowTick / 1000 - queueStartedAt) : 0);
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

   // ── Salida cruda del modelo y mensajes enviados, por archivo ───────────────
   let fileStreamLogs = $state({});
   let fileInputLogs = $state({});

   function onBlockStream(e) {
      const { file_index, text } = e.detail;
      fileStreamLogs = { ...fileStreamLogs, [file_index]: text };
   }
   function onBlockInput(e) {
      const { file_index, text } = e.detail;
      fileInputLogs = { ...fileInputLogs, [file_index]: text };
   }

   // ── Prompt del sistema ─────────────────────────────────────────────────────
   // El backend manda el texto final completo (vista "raw") y sus secciones ya separadas (vista
   // "formateada"): no se reparsea del lado del frontend porque los separadores textuales de
   // build_system_prompt no son estables.
   let systemPrompt = $state("");
   let systemPromptSections = $state({ base_prompt: "", glossary: "", work_info: "", title: "" });

   function onSystemPrompt(e) {
      systemPrompt = e.detail.text;
      systemPromptSections = e.detail.sections ?? systemPromptSections;
   }

   // ── Cancelación ────────────────────────────────────────────────────────────
   let cancelling = $state(false);

   function cancel() {
      cancelling = true;
      onCancel?.();
   }

   // Al terminar el job, un paso que quedó "activo" pasa a done (o cancelled si falló/canceló).
   $effect(() => {
      if (!progress.running) {
         if (steps.some((s) => s.status === "active")) {
            steps = steps.map((s) =>
               s.status === "active" ? { ...s, status: progress.success === false ? "cancelled" : "done" } : s,
            );
         }
         cancelling = false;
      }
   });

   // ── Listeners ──────────────────────────────────────────────────────────────
   // Una llamada por evento, con el nombre como literal: tests/test_translation_event_sync.py
   // busca `addEventListener("audiotools:...")` para cruzar emisores y listeners.
   window.addEventListener("audiotools:translation:step", onStepEvent);
   window.addEventListener("audiotools:translation:work_info_stream", onWorkInfoStream);
   window.addEventListener("audiotools:translation:title_stream", onTitleStream);
   window.addEventListener("audiotools:translation:work_info", onWorkInfoFinal);
   window.addEventListener("audiotools:translation:title", onTitleFinal);
   window.addEventListener("audiotools:translation:lines", onLinesProgress);
   window.addEventListener("audiotools:translation:queue_started", onQueueStarted);
   window.addEventListener("audiotools:file", onFileTiming);
   window.addEventListener("audiotools:translation:block_stream", onBlockStream);
   window.addEventListener("audiotools:translation:block_input", onBlockInput);
   window.addEventListener("audiotools:translation:system_prompt", onSystemPrompt);

   onDestroy(() => {
      window.removeEventListener("audiotools:translation:step", onStepEvent);
      window.removeEventListener("audiotools:translation:work_info_stream", onWorkInfoStream);
      window.removeEventListener("audiotools:translation:title_stream", onTitleStream);
      window.removeEventListener("audiotools:translation:work_info", onWorkInfoFinal);
      window.removeEventListener("audiotools:translation:title", onTitleFinal);
      window.removeEventListener("audiotools:translation:lines", onLinesProgress);
      window.removeEventListener("audiotools:translation:queue_started", onQueueStarted);
      window.removeEventListener("audiotools:file", onFileTiming);
      window.removeEventListener("audiotools:translation:block_stream", onBlockStream);
      window.removeEventListener("audiotools:translation:block_input", onBlockInput);
      window.removeEventListener("audiotools:translation:system_prompt", onSystemPrompt);
   });

   return {
      get steps() { return steps; },
      get activeTab() { return activeTab; },
      selectTab,
      stepStatus,
      get workInfoText() { return workInfoText; },
      get titleText() { return titleText; },
      get linesGlobalDone() { return linesGlobalDone; },
      get linesGlobalTotal() { return linesGlobalTotal; },
      get globalPercent() { return globalPercent; },
      isFileDone,
      isFileActive,
      fileProgress,
      fileElapsed,
      get queueElapsedDisplay() { return queueElapsedDisplay; },
      get fileStreamLogs() { return fileStreamLogs; },
      get fileInputLogs() { return fileInputLogs; },
      get systemPrompt() { return systemPrompt; },
      get systemPromptSections() { return systemPromptSections; },
      get cancelling() { return cancelling; },
      cancel,
   };
}
