<script>
  /**
   * MergeView.svelte
   * ─────────────────
   * Fusiona varios archivos de audio en uno solo con capítulos.
   *
   * Props:
   *   goHome  function — vuelve a la pantalla de inicio
   */

  import { bridge }    from '$lib/stores/bridge.svelte.js'
  import { progress }  from '$lib/stores/progress.svelte.js'
  import { appConfig } from '$lib/stores/config.svelte.js'

  import FileDropZone from '$lib/components/FileDropZone.svelte'
  import ProgressBar  from '$lib/components/ProgressBar.svelte'
  import LogPanel     from '$lib/components/LogPanel.svelte'

  let { goHome } = $props()

  // ── Estado local ────────────────────────────────────────────────────────────

  let files      = $state([])
  let outputName = $state('merged.opus')

  const canRun = $derived(
    files.length >= 2 &&
    outputName.trim() &&
    appConfig.baseFolder &&
    !progress.running
  )

  // ── Acciones ────────────────────────────────────────────────────────────────

  async function run() {
    if (!canRun) return
    progress.reset()

    const outputPath = `${appConfig.baseFolder}\\${outputName}`
    await bridge.run_merge(files, outputPath, appConfig.baseFolder)
  }

  function cancel() {
    bridge.cancel()
  }
</script>

<div class="flex h-full flex-col">

  <!-- Header -->
  <header class="flex items-center gap-3 border-b border-white/5 px-8 py-5">
    <button
      class="text-white/30 hover:text-white transition-colors text-sm"
      onclick={goHome}
    >
      ← Inicio
    </button>
    <span class="text-white/10">/</span>
    <h1 class="text-sm font-semibold">Merge</h1>
  </header>

  <!-- Contenido -->
  <main class="flex flex-1 gap-6 overflow-hidden px-8 py-6">

    <!-- Panel izquierdo: configuración -->
    <section class="flex w-80 shrink-0 flex-col gap-5">

      <FileDropZone
        bind:files
        accept={['*.mp3', '*.opus', '*.m4a', '*.wav', '*.flac', '*.ogg']}
        disabled={progress.running}
      />

      <!-- Nombre del archivo de salida -->
      <div class="flex flex-col gap-1.5">
        <label class="text-xs text-white/40" for="output-name">
          Nombre de salida
        </label>
        <input
          id="output-name"
          type="text"
          bind:value={outputName}
          disabled={progress.running}
          placeholder="merged.opus"
          class="rounded-lg border border-white/10 bg-white/5 px-3 py-2
                 text-sm text-white placeholder-white/20 outline-none
                 focus:border-indigo-500/50 transition-colors
                 disabled:opacity-40"
        />
      </div>

      <!-- Botones -->
      <div class="flex gap-2 mt-auto">
        {#if progress.running}
          <button
            class="flex-1 rounded-lg bg-red-500/20 px-4 py-2 text-sm
                   text-red-400 hover:bg-red-500/30 transition-colors"
            onclick={cancel}
          >
            Cancelar
          </button>
        {:else}
          <button
            class="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm
                   font-medium text-white transition-colors
                   hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed"
            onclick={run}
            disabled={!canRun}
          >
            Fusionar
          </button>
        {/if}
      </div>

    </section>

    <!-- Panel derecho: progreso -->
    <section class="flex flex-1 flex-col gap-4">
      <ProgressBar
        value={progress.value}
        running={progress.running}
        success={progress.success}
      />
      <LogPanel logs={progress.logs} />
    </section>

  </main>

</div>