
<script>
  /**
   * HoverCard.svelte
   * ─────────────────
   * Tooltip tipo card que aparece al hacer hover sobre un ícono ?.
   * Reutilizable en cualquier vista.
   *
   * Props:
   *   text    string  — descripción a mostrar
   *   position string — 'top' | 'bottom' (default 'top')
   */

  let { text, position = 'top' } = $props()

  let visible = $state(false)
</script>

<span class="relative inline-flex items-center">
  <button
    class="inline-flex h-4 w-4 items-center justify-center rounded-full
           border border-white/20 bg-white/5 text-white/30
           hover:border-white/40 hover:text-white/60 transition-colors
           text-[10px] font-medium cursor-default"
    onmouseenter={() => visible = true}
    onmouseleave={() => visible = false}
    tabindex="-1"
  >
    ?
  </button>

  {#if visible}
    <div
      class="absolute left-1/2 z-50 w-56 -translate-x-1/2 rounded-lg
             border border-white/10 bg-zinc-800 p-3 shadow-xl
             text-xs text-white/60 leading-relaxed pointer-events-none
             {position === 'top' ? 'bottom-6' : 'top-6'}"
    >
      {text}
      <!-- Flecha -->
      <div
        class="absolute left-1/2 -translate-x-1/2 border-4 border-transparent
               {position === 'top'
                 ? 'top-full border-t-zinc-800'
                 : 'bottom-full border-b-zinc-800'}"
      ></div>
    </div>
  {/if}
</span>

