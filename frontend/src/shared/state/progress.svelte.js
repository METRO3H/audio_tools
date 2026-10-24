/**
 * progress.svelte.js
 * ───────────────────
 * Estado global de progreso para cualquier operación en curso.
 *
 * Escucha los CustomEvents que api.py emite via evaluate_js():
 *   audiotools:start     { job_id, tool, total }                (tools con contrato core/jobs.py)
 *   audiotools:progress  { value: float 0..1, ... }
 *   audiotools:log       { message: string }
 *   audiotools:file      { index: int, done: bool, started_at?: float, elapsed?: float }
 *   audiotools:done      { success: bool, cancelled?: bool, elapsed?: float, error?: string, warning?: string }
 *   audiotools:transcribe:file_log  { job_id, file_index: int, message: string }  (los mensajes de cada archivo)
 *
 * Las tools migradas al contrato agregan `job_id` a cada evento. Si el evento
 * trae job_id y no coincide con `progress.jobId` (p. ej. el `done` rezagado de
 * un job cancelado) se descarta. Los eventos sin job_id (tools aun sin migrar)
 * se procesan como siempre.
 *
 * Uso:
 *   import { progress } from '@shared/state/progress.svelte.js'
 *
 *   progress.value      // 0..1
 *   progress.running    // bool
 *   progress.logs       // string[]
 *   progress.success    // bool | null (null = en curso)
 *   progress.error      // string | null (mensaje cuando el job falla)
 *   progress.cancelled  // bool (true = terminó porque el usuario lo canceló; no es un error)
 *   progress.warning    // string | null (el job terminó bien, pero con algo que el usuario debe saber)
 *   progress.jobId      // string | null (lo asigna useToolRun)
 *   progress.files      // { index: int, done: bool }[]
 *   progress.fileLogs   { [file_index]: string[] }  (logs por archivo; los lee ProcessingView con enableFileLogs)
 *   progress.reset()    // limpia para una nueva operación
 */

// ── Estado ─────────────────────────────────────────────────────────────────────

export const progress = $state({
   value: 0,
   running: false,
   logs: [],
   success: null,
   files: [],
   fileLogs: {},
   fileIndex: 0,
   fileProgress: 0,
   completed: 0,
   total: 0,
   startTime: null,
   elapsed: 0,
   jobId: null,
   error: null,
   cancelled: false,
   warning: null,

   reset() {
      this.value = 0;
      this.running = false;
      this.logs = [];
      this.success = null;
      this.files = [];
      this.fileLogs = {};
      this.fileIndex = 0;
      this.fileProgress = 0;
      this.completed = 0;
      this.total = 0;
      this.startTime = null;
      this.elapsed = 0;
      this.jobId = null;
      this.error = null;
      this.cancelled = false;
      this.warning = null;
   },
});

/**
 * ¿El evento pertenece a otro job distinto del actual?
 * Sin job_id (tools sin migrar) nunca se considera rezagado.
 * @param {{ job_id?: string | null }} detail
 */
function isStale(detail) {
   return detail.job_id != null && detail.job_id !== progress.jobId;
}

// ── Listeners ──────────────────────────────────────────────────────────────────

if (typeof window !== "undefined") {
   window.addEventListener("audiotools:start", (/** @type {CustomEvent} */ e) => {
      if (isStale(e.detail)) return;
      progress.total = e.detail.total ?? progress.total;
      if (!progress.startTime) progress.startTime = Date.now();
   });

   window.addEventListener("audiotools:progress", (/** @type {CustomEvent} */ e) => {
      if (isStale(e.detail)) return;
      if (!progress.running) return;
      if (!progress.startTime) progress.startTime = Date.now();
      progress.value = e.detail.value;
      progress.fileIndex = e.detail.file_index ?? progress.fileIndex;
      progress.fileProgress = e.detail.file_progress ?? progress.fileProgress;
      progress.completed = e.detail.completed ?? progress.completed;
      progress.total = e.detail.total ?? progress.total;
   });

   window.addEventListener("audiotools:log", (/** @type {CustomEvent} */ e) => {
      if (isStale(e.detail)) return;
      progress.logs = [...progress.logs, e.detail.message];
   });

   window.addEventListener("audiotools:transcribe:file_log", (/** @type {CustomEvent} */ e) => {
      if (isStale(e.detail)) return;
      const { file_index, message } = e.detail;
      if (!Number.isInteger(file_index) || file_index < 0) return;
      progress.fileLogs = {
         ...progress.fileLogs,
         [file_index]: [...(progress.fileLogs[file_index] ?? []), String(message ?? "")],
      };
   });

   window.addEventListener("audiotools:file", (/** @type {CustomEvent} */ e) => {
      if (isStale(e.detail)) return;
      if (!progress.running) return;
      const { index, done } = e.detail;
      const updated = [...progress.files];
      updated[index] = { index, done };
      progress.files = updated;
   });

   window.addEventListener("audiotools:done", (/** @type {CustomEvent} */ e) => {
      if (isStale(e.detail)) return;
      progress.running = false;
      progress.success = e.detail.success;
      progress.error = e.detail.error ?? null;
      progress.cancelled = e.detail.cancelled === true;
      progress.warning = e.detail.warning ?? null;
      progress.value = e.detail.success ? 1 : progress.value;
      // Si el backend manda su propio elapsed (medido con su propio reloj,
      // mas preciso), se usa ese en vez de aproximarlo con Date.now() del
      // navegador. Hoy solo run_translate() (.srt) lo manda; el resto de
      // las tools sigue cayendo al calculo anterior, sin cambios.
      if (e.detail.elapsed != null) {
         progress.elapsed = Math.round(e.detail.elapsed);
      } else if (progress.startTime) {
         progress.elapsed = Math.round((Date.now() - progress.startTime) / 1000);
      }
   });
}
