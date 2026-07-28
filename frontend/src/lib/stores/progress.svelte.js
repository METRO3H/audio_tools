/**
 * progress.svelte.js
 * ───────────────────
 * Estado global de progreso para cualquier operación en curso.
 *
 * Escucha los CustomEvents que api.py emite via evaluate_js():
 *   audiotools:progress  { value: float 0..1 }
 *   audiotools:log       { message: string }
 *   audiotools:file      { index: int, done: bool }
 *   audiotools:done      { success: bool }
 *
 * Uso:
 *   import { progress } from '$lib/stores/progress.svelte.js'
 *
 *   progress.value      // 0..1
 *   progress.running    // bool
 *   progress.logs       // string[]
 *   progress.success    // bool | null (null = en curso)
 *   progress.files      // { index: int, done: bool }[]
 *   progress.reset()    // limpia para una nueva operación
 */

// ── Estado ─────────────────────────────────────────────────────────────────────

export const progress = $state({
   value: 0,
   running: false,
   logs: [],
   success: null,
   files: [],
   fileIndex: 0,
   fileProgress: 0,
   completed: 0,
   total: 0,
   startTime: null,
   elapsed: 0,

   reset() {
      this.value = 0;
      this.running = false;
      this.logs = [];
      this.success = null;
      this.files = [];
      this.fileIndex = 0;
      this.fileProgress = 0;
      this.completed = 0;
      this.total = 0;
      this.startTime = null;
      this.elapsed = 0;
   },
});

// ── Listeners ──────────────────────────────────────────────────────────────────

if (typeof window !== "undefined") {
   window.addEventListener("audiotools:progress", (/** @type {CustomEvent} */ e) => {
      if (!progress.running) return;
      if (!progress.startTime) progress.startTime = Date.now();
      progress.value = e.detail.value;
      progress.fileIndex = e.detail.file_index ?? progress.fileIndex;
      progress.fileProgress = e.detail.file_progress ?? progress.fileProgress;
      progress.completed = e.detail.completed ?? progress.completed;
      progress.total = e.detail.total ?? progress.total;
   });

   window.addEventListener("audiotools:log", (/** @type {CustomEvent} */ e) => {
      progress.logs = [...progress.logs, e.detail.message];
   });

   window.addEventListener("audiotools:file", (/** @type {CustomEvent} */ e) => {
      if (!progress.running) return;
      const { index, done } = e.detail;
      const updated = [...progress.files];
      updated[index] = { index, done };
      progress.files = updated;
   });

   window.addEventListener("audiotools:done", (e) => {
      progress.running = false;
      progress.success = e.detail.success;
      progress.value = e.detail.success ? 1 : progress.value;
      if (progress.startTime) {
         progress.elapsed = Math.round((Date.now() - progress.startTime) / 1000);
      }
   });
}
