<script>
  /**
   * BaseFolderPicker.svelte
   * ────────────────────────
   * Selector de carpeta base reutilizable.
   *
   * Props:
   *   onPick  function(folder) — callback cuando se selecciona una carpeta
   *   disabled boolean
   */

  import { bridge }    from '$lib/stores/bridge.svelte.js'
  import { appConfig } from '$lib/stores/config.svelte.js'

  let { onPick = null, disabled = false } = $props()

  async function pick() {
    if (disabled) return
    const folder = await bridge.pick_folder()
    if (!folder) return
    appConfig.setBaseFolder(folder)
    onPick?.(folder)
  }
</script>

<div class="flex flex-col gap-1.5">
  <span class="text-xs text-white/40">Carpeta base</span>
  <button
    class="flex items-center gap-2 rounded-lg border border-white/10
           bg-white/5 px-3 py-2 text-xs text-left transition-all
           hover:border-white/20 disabled:opacity-40"
    onclick={pick}
    {disabled}
  >
    <span>📁</span>
    <span class="truncate text-white/60">
      {appConfig.baseFolder || 'Sin seleccionar'}
    </span>
  </button>
</div>