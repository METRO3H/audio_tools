<script>
   import { tick } from "svelte";

   let { name, logs = [], status = "En espera", onClose } = $props();

   let container = $state(null);
   let copied = $state(false);

   const statusColor = $derived(
      status === "Completado"
         ? "text-emerald-400"
         : status === "Finalizado con error"
           ? "text-red-400"
           : status === "Procesando"
             ? "text-indigo-300"
             : "text-white/40",
   );

   $effect(() => {
      if (container && logs.length) {
         tick().then(() => {
            if (container) container.scrollTop = container.scrollHeight;
         });
      }
   });

   function isSegment(line) {
      return /^\[\d+(?:\.\d+)?s\s*->\s*\d+(?:\.\d+)?s\]/.test(line);
   }

   async function copyLogs() {
      if (!logs.length) return;

      const text = logs.join("\n");
      try {
         await navigator.clipboard.writeText(text);
      } catch {
         const textarea = document.createElement("textarea");
         textarea.value = text;
         document.body.appendChild(textarea);
         textarea.select();
         document.execCommand("copy");
         document.body.removeChild(textarea);
      }

      copied = true;
      setTimeout(() => (copied = false), 2000);
   }
</script>

<div
   class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
   role="presentation"
   onclick={onClose}
></div>

<div class="fixed inset-0 z-50 flex items-center justify-center p-6">
   <section
      class="flex h-[85vh] w-full max-w-4xl flex-col gap-3 rounded-2xl border border-white/10 bg-zinc-900 p-5 shadow-2xl"
      role="dialog"
      aria-modal="true"
      aria-label="Procesamiento de {name}"
   >
      <header class="flex shrink-0 items-center justify-between gap-4">
         <div class="min-w-0">
            <h2 class="truncate text-sm font-semibold text-white">{name}</h2>
            <p class="mt-1 text-xs text-white/35">Procesamiento en vivo de la transcripción</p>
         </div>
         <div class="flex shrink-0 items-center gap-2">
            <span class="text-xs font-medium {statusColor}">{status}</span>
            <button
               class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/45 transition-colors hover:text-white/80 disabled:cursor-not-allowed disabled:opacity-30"
               onclick={copyLogs}
               disabled={logs.length === 0}
            >
               {copied ? "✓ Copiado" : "Copiar todo"}
            </button>
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
         bind:this={container}
         class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-white/5 bg-black/35 p-3 font-mono text-xs leading-relaxed"
         style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; user-select: text; -webkit-user-select: text;"
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
   </section>
</div>
