<script>
  /**
   * ViewHeader.svelte
   * ──────────────────
   * Header reutilizable para todas las tools.
   *
   * Props:
   *   title   string    — nombre de la herramienta
   *   goHome  function  — vuelve a la pantalla de inicio
   */

  let { title, goHome } = $props()
</script>

<header class="flex items-center gap-3 border-b border-white/5 px-8 py-5 shrink-0">
  <button
    class="text-white/30 hover:text-white transition-colors text-sm"
    onclick={goHome}
  >
    ← Inicio
  </button>
  <span class="text-white/10">/</span>
  <h1 class="text-sm font-semibold">{title}</h1>
</header>