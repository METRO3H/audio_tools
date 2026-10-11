/**
 * useToolRun.svelte.js
 * ─────────────────────
 * Ciclo de ejecución de una tool que corre en un hilo de fondo del backend y
 * reporta por eventos (contrato de core/jobs.py).
 *
 * Reemplaza el bloque que cada vista repetía:
 *   progress.reset(); processing = true; progress.running = true;
 *   await bridge.run_x(...);  function cancel(){...}  function goBack(){...}
 *
 * Uso:
 *   const job = useToolRun("run_diverge");
 *   await job.start({ file_path, ... });  // start() agrega el job_id a las opciones
 *   job.processing                        // true mientras se muestra ProcessingView
 *   job.cancel()                          // pide cancelar al backend
 *   job.back()                            // sale de ProcessingView y limpia el estado
 *
 * Los fallos del job NO llegan como excepción de la llamada: el backend los
 * reporta con audiotools:done { success:false, error } y el store `progress`
 * los expone en progress.error. El try/catch de start() cubre solo fallos de
 * transporte (puente no disponible, etc.) y los deja en el mismo lugar.
 */

import { bridge } from "@shared/services/bridge.svelte.js";
import { progress } from "@shared/state/progress.svelte.js";

function newJobId() {
   return (
      globalThis.crypto?.randomUUID?.() ??
      `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
   );
}

/**
 * @param {string} method  nombre del método del bridge que recibe un objeto de opciones
 */
export function useToolRun(method) {
   let processing = $state(false);

   /** @param {Record<string, unknown>} options */
   async function start(options) {
      progress.reset();
      progress.jobId = newJobId();
      progress.running = true;
      processing = true;

      try {
         await bridge[method]({ ...options, job_id: progress.jobId });
      } catch (err) {
         progress.running = false;
         progress.success = false;
         progress.error = err instanceof Error ? err.message : String(err);
      }
   }

   function cancel() {
      bridge.cancel();
   }

   function back() {
      processing = false;
      progress.reset();
   }

   return {
      get processing() {
         return processing;
      },
      start,
      cancel,
      back,
   };
}
