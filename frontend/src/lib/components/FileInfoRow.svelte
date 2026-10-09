<script>
  /**
   * FileInfoRow.svelte
   * ───────────────────
   * Fila de archivo en la vista de procesamiento.
   * Muestra nombre, peso (si existe), duración y barra de progreso individual.
   * ...
   */

  import Spinner from "$lib/components/Spinner.svelte"

  let {
    name,
    sizeMb = 0,
    duration,
    progress = null,
    active = false,
    done = false,
    elapsedSeconds = null,
    onRowClick = null,
  } = $props()

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

<div
  class="flex flex-col gap-1.5 rounded-lg border px-4 py-3 transition-all duration-300 {rowColor}
    {onRowClick ? 'cursor-pointer hover:border-white/20' : ''}"
  role={onRowClick ? 'button' : undefined}
  tabindex={onRowClick ? 0 : undefined}
  onclick={onRowClick}
  onkeydown={onRowClick ? (e) => (e.key === 'Enter' || e.key === ' ') && onRowClick(e) : undefined}
>

  <!-- Fila superior: nombre, peso (opcional), duración -->
  <div class="flex items-center justify-between gap-4">
    <div class="flex min-w-0 items-center gap-2">
      {#if active && !done}
        <Spinner size={12} duration="1.25s" />
      {/if}
      <span class="truncate text-xs font-medium text-white/80">{name}</span>
    </div>
    <div class="flex shrink-0 items-center gap-3 text-xs text-white/30">
      {#if sizeMb > 0}
        <span>{sizeMb} MB</span>
      {/if}
      {#if duration}
        <span>{formatDuration(duration)}</span>
      {/if}
      {#if done}
        <span class="text-emerald-400">✓</span>
        {#if elapsedSeconds != null}
          <span class="text-white/25 tabular-nums">{formatDuration(elapsedSeconds)}</span>
        {/if}
      {:else if active && percent !== null}
        <span class="text-indigo-400">{percent}%</span>
        {#if elapsedSeconds != null}
          <span class="text-white/25 tabular-nums">{formatDuration(elapsedSeconds)}</span>
        {/if}
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