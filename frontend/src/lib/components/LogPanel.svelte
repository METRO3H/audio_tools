<script>
  /**
   * LogPanel.svelte
   * ────────────────
   * Panel de logs en tiempo real con auto-scroll al fondo.
   *
   * Props:
   *   logs     string[]  — líneas de log
   *   maxLines number    — máximo de líneas a mostrar (default 200)
   */

  import { tick } from 'svelte'

  let { logs = [], maxLines = 200 } = $props()

  let container = $state(null)

  const visibleLogs = $derived(logs.slice(-maxLines))

  // Auto-scroll al fondo cada vez que llegan nuevos logs
  $effect(() => {
    if (logs.length && container) {
      tick().then(() => {
        container.scrollTop = container.scrollHeight
      })
    }
  })
</script>

<div
  bind:this={container}
  class="h-40 overflow-y-auto rounded-xl bg-black/30 border border-white/5
         p-3 font-mono text-xs text-white/50 leading-relaxed
         scrollbar-thin scrollbar-thumb-white/10"
>
  {#if visibleLogs.length === 0}
    <span class="text-white/20 italic">Sin logs aún...</span>
  {:else}
    {#each visibleLogs as line (line)}
      <div class="whitespace-pre-wrap break-all">{line}</div>
    {/each}
  {/if}
</div>