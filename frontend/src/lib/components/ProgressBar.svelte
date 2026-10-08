
<script>
  /**
   * ProgressBar.svelte
   * ───────────────────
   * Barra de progreso animada con transición CSS suave.
   *
   * Props:
   *   value    number  — 0..1
   *   running  boolean — si está en curso (activa animación de pulso)
   *   success  boolean | null — null = en curso, true = ok, false = error
   */

  let { value = 0, running = false, success = null } = $props()

  const percent = $derived(Math.round(value * 100))

  const trackColor = $derived(
    success === null ? 'bg-white/10' :
    success          ? 'bg-white/10' :
                       'bg-red-500/20'
  )

  const fillColor = $derived(
    success === null ? 'bg-indigo-500' :
    success          ? 'bg-emerald-500' :
                       'bg-red-500'
  )
</script>

<div class="flex flex-col gap-1.5 w-full">
  <!-- Track -->
  <div class="relative h-1.5 w-full rounded-full overflow-hidden {trackColor}">
    <!-- Fill -->
    <div
      class="absolute inset-y-0 left-0 rounded-full transition-all duration-300 ease-out {fillColor}
             {running && value > 0 && value < 1 ? 'animate-pulse' : ''}"
      style="width: {percent}%"
    ></div>
  </div>

  <!-- Label -->
  <div class="flex justify-between text-xs text-white/40">
    <span>
      {#if running}
        Procesando...
      {:else if success === true}
        Completado
      {:else if success === false}
        Error
      {:else}
        Listo
      {/if}
    </span>
    <span>{percent}%</span>
  </div>
</div>

