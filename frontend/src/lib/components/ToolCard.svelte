
<script>
  /**
   * ToolCard.svelte
   * ────────────────
   * Card clickeable de la pantalla de inicio.
   *
   * Props:
   *   title       string   — nombre de la herramienta
   *   description string   — descripción corta
   *   icon        string   — emoji o SVG string
   *   onclick     function — callback al hacer click
   */

  let { title, description, icon, onclick } = $props()
</script>

<button
  class="group flex flex-col gap-3 rounded-2xl border border-white/10
         bg-white/5 p-6 text-left transition-all duration-200
         hover:border-white/20 hover:bg-white/10 hover:scale-[1.02]
         active:scale-[0.98] cursor-pointer w-full"
  onclick={onclick}
>
  <span class="text-3xl">{icon}</span>

  <div class="flex flex-col gap-1">
    <span class="text-sm font-semibold text-white tracking-wide">
      {title}
    </span>
    <span class="text-xs text-white/50 leading-relaxed">
      {description}
    </span>
  </div>
</button>

