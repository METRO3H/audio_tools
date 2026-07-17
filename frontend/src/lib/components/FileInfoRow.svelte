<script>
  /**
   * FileInfoRow.svelte
   * ───────────────────
   * Fila de archivo en la vista de procesamiento.
   * Muestra nombre, peso (si existe), duración y barra de progreso individual.
   *
   * Props:
   *   name      string  — nombre del archivo
   *   sizeMb    number  — peso en MB (0 o null = no mostrar)
   *   duration  number  — duración en segundos
   *   progress  number  — 0..1 (null = en cola, 1 = completado)
   *   active    boolean — si está siendo procesado ahora
   *   done      boolean — si ya terminó
   */

  let { name, sizeMb = 0, duration, progress = null, active = false, done = false } = $props()

  function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    return `${m}:${String(s).padStart(2, '0')}`
  }

  const percent = $derived(progress !== null ? Math.round(progress * 100) : null)

  const rowColor = $derived(
    done   ? 'border-emerald-500/20 bg-emerald-500/5' :
    active ? 'border-indigo-500/30 bg-indigo-500/5'  :
             'border-white/5 bg-white/3'
  )
</script>

<div class="flex flex-col gap-1.5 rounded-lg border px-4 py-3 transition-all duration-300 {rowColor}">

  <!-- Fila superior: nombre, peso (opcional), duración -->
  <div class="flex items-center justify-between gap-4">
    <span class="truncate text-xs font-medium text-white/80">{name}</span>
    <div class="flex shrink-0 items-center gap-3 text-xs text-white/30">
      {#if sizeMb > 0}
        <span>{sizeMb} MB</span>
      {/if}
      <span>{formatDuration(duration)}</span>
      {#if done}
        <span class="text-emerald-400">✓</span>
      {:else if active && percent !== null}
        <span class="text-indigo-400">{percent}%</span>
      {/if}
    </div>
  </div>

  <!-- Barra individual — solo visible cuando está activo -->
  {#if active && progress !== null && !done}
    <div class="h-0.5 w-full overflow-hidden rounded-full bg-white/10">
      <div
        class="h-full rounded-full bg-indigo-500 transition-all duration-200 ease-out"
        style="width: {percent}%"
      ></div>
    </div>
  {/if}

</div>
