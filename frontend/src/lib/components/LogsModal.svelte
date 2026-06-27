<script>
   import { tick } from "svelte";

   let { logs = [], onClose } = $props();

   let container = $state(null);

   $effect(() => {
      if (logs.length && container) {
         tick().then(() => {
            container.scrollTop = container.scrollHeight;
         });
      }
   });
</script>

<!-- Modal -->
<div class="fixed inset-0 z-50 flex items-center justify-center p-6">
  <div class="w-full max-w-2xl rounded-2xl border border-white/10
              bg-zinc-900 p-5 shadow-2xl">
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs font-medium text-white/50">Logs de ffmpeg</span>
      <button
        class="text-xs text-white/30 hover:text-white transition-colors px-2 py-1"
        onclick={onClose}
      >
        ✕
      </button>
    </div>
    <div
      bind:this={container}
      class="h-80 overflow-y-auto rounded-lg bg-black/40 p-3 font-mono
             text-xs text-white/50 leading-relaxed"
      style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
    >
      {#if logs.length === 0}
        <span class="text-white/20 italic">Sin logs aún...</span>
      {:else}
        {#each logs.slice(-300) as line, i (i)}
          <div class="whitespace-pre-wrap break-all">{line}</div>
        {/each}
      {/if}
    </div>
  </div>
</div>
