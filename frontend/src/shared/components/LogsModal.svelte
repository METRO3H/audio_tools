<script>
  import Modal from '@shared/ui/Modal.svelte'
  import CopyButton from '@shared/ui/CopyButton.svelte'
  import { stickyScroll } from '@shared/ui/stickyScroll.js'

  let { logs = [], onClose } = $props()
</script>

<Modal {onClose} size="2xl" label="Logs de ffmpeg" class="gap-3">
  <div class="flex items-center justify-between">
    <span class="text-xs font-medium text-white/50">Logs de ffmpeg</span>
    <div class="flex items-center gap-2">
      <CopyButton
        text={() => logs.join('\n')}
        disabled={logs.length === 0}
        class="text-xs text-white/30 hover:text-white/70 transition-colors px-2 py-1
               border border-white/10 rounded-md disabled:cursor-not-allowed disabled:opacity-30"
      />
      <button
        class="text-xs text-white/30 hover:text-white transition-colors px-2 py-1"
        aria-label="Cerrar"
        onclick={onClose}
      >
        ✕
      </button>
    </div>
  </div>

  <div
    use:stickyScroll={logs.length}
    class="h-80 overflow-y-auto rounded-lg bg-black/40 p-3 font-mono
           text-xs text-white/50 leading-relaxed cursor-text select-text"
  >
    {#if logs.length === 0}
      <span class="text-white/20 italic">Sin logs aún...</span>
    {:else}
      {#each logs as line, i (i)}
        <div class="whitespace-pre-wrap break-all">{line}</div>
      {/each}
    {/if}
  </div>
</Modal>
