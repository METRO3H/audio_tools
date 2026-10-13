<script>
   import Modal from "@shared/ui/Modal.svelte";
   import CopyButton from "@shared/ui/CopyButton.svelte";
   import { stickyScroll } from "@shared/ui/stickyScroll.js";

   let { name, logs = [], status = "En espera", onClose } = $props();

   const statusColor = $derived(
      status === "Completado"
         ? "text-emerald-400"
         : status === "Finalizado con error"
           ? "text-red-400"
           : status === "Cancelado"
             ? "text-amber-400"
             : status === "Procesando"
               ? "text-indigo-300"
               : "text-white/40",
   );

   function isSegment(line) {
      return /^\[\d+(?:\.\d+)?s\s*->\s*\d+(?:\.\d+)?s\]/.test(line);
   }
</script>

<Modal {onClose} size="4xl" height="fixed-85" label="Procesamiento de {name}" class="gap-3">
   <header class="flex shrink-0 items-center justify-between gap-4">
      <div class="min-w-0">
         <h2 class="truncate text-sm font-semibold text-white">{name}</h2>
         <p class="mt-1 text-xs text-white/35">Procesamiento en vivo de la transcripción</p>
      </div>
      <div class="flex shrink-0 items-center gap-2">
         <span class="text-xs font-medium {statusColor}">{status}</span>
         <CopyButton text={() => logs.join("\n")} disabled={logs.length === 0} />
         <button
            class="px-2 py-1 text-sm text-white/35 transition-colors hover:text-white"
            onclick={onClose}
            aria-label="Cerrar modal"
         >
            ✕
         </button>
      </div>
   </header>

   <div
      use:stickyScroll={logs.length}
      class="min-h-0 flex-1 select-text overflow-y-auto rounded-lg border border-white/5 bg-black/35 p-3 font-mono text-xs leading-relaxed"
   >
      {#if logs.length === 0}
         <p class="py-3 text-white/30 italic">
            {status === "En espera"
               ? "Este archivo todavía no ha comenzado a procesarse."
               : "Esperando los primeros mensajes del procesamiento..."}
         </p>
      {:else}
         {#each logs as line, i (i)}
            <div
               class="whitespace-pre-wrap break-words {line.toLowerCase().includes('[error]') || line.toLowerCase().includes('error:') ? 'text-red-300' : isSegment(line) ? 'text-white/85' : 'text-white/45'}"
            >{line}</div>
         {/each}
      {/if}
   </div>
   <p class="shrink-0 text-[11px] text-white/25">
      Los mensajes y segmentos reconocidos aparecen aquí a medida que se procesan. Puedes seleccionar y copiar cualquier texto.
   </p>
</Modal>
