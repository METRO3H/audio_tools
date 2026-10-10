<script>
  import { bridge } from '@shared/services/bridge.svelte.js'
  import { appConfig } from '@shared/state/config.svelte.js'

  let { onPick = null, disabled = false } = $props()

  async function pick() {
    if (disabled) return
    const folder = await bridge.pick_folder()
    if (!folder) return
    appConfig.setBaseFolder(folder)
    onPick?.(folder)
  }

  function openFolder() {
    if (!appConfig.baseFolder) return
    bridge.open_directory(appConfig.baseFolder)
  }
</script>

<div class="flex flex-col gap-1.5">
  <span class="text-xs text-white/40">Carpeta base</span>
  <div class="flex items-center gap-2">
    <button
      class="flex-1 flex items-center gap-2 rounded-lg border border-white/10
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
    {#if appConfig.baseFolder}
      <button
        class="shrink-0 rounded-lg border border-white/10 bg-white/5 px-2 py-2
               text-xs text-white/40 hover:text-white/70 transition-colors
               disabled:opacity-40"
        onclick={openFolder}
        title="Abrir carpeta"
        {disabled}
      >
        📂
      </button>
    {/if}
  </div>
</div>
