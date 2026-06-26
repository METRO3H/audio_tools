<script>
  /**
   * DivergeView.svelte
   * ───────────────────
   * Divide un archivo de audio en segmentos de igual duración.
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

  // ── Formatos disponibles ────────────────────────────────────────────────────

  const formats = ['mp3', 'opus', 'm4a', 'wav', 'flac', 'ogg']

  // ── Estado local ────────────────────────────────────────────────────────────

  let files          = $state([])
  let intervalMins   = $state(30)
  let outputFormat   = $state('opus')

  const intervalSeconds = $derived(intervalMins * 60)

  const canRun = $derived(
    files.length === 1 &&
    intervalMins > 0 &&
    appConfig.baseFolder &&
    !progress.running
  )

  // ── Acciones ────────────────────────────────────────────────────────────────

  async function run() {
    if (!canRun) return
    progress.reset()

    await bridge.run_diverge(
      files[0],
      appConfig.baseFolder,
      intervalSeconds,
      outputFormat,
    )
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
    <h1 class="text-sm font-semibold">Diverge</h1>
  </header>

  <!-- Contenido -->
  <main class="flex flex-1 gap-6 overflow-hidden px-8 py-6">

    <!-- Panel izquierdo: configuración -->
    <section class="flex w-80 shrink-0 flex-col gap-5">

      <FileDropZone
        bind:files
        accept={['*.mp3', '*.opus', '*.m4a', '*.wav', '*.flac', '*.ogg']}
        multiple={false}
        disabled={progress.running}
      />

      <!-- Intervalo -->
      <div class="flex flex-col gap-1.5">
        <label class="text-xs text-white/40" for="interval">
          Intervalo (minutos)
        </label>
        <input
          id="interval"
          type="number"
          bind:value={intervalMins}
          min="1"
          max="180"
          disabled={progress.running}
          class="rounded-lg border border-white/10 bg-white/5 px-3 py-2
                 text-sm text-white outline-none focus:border-indigo-500/50
                 transition-colors disabled:opacity-40"
        />
        <span class="text-xs text-white/25">
          {intervalSeconds / 60} min = {intervalSeconds}s por segmento
        </span>
      </div>

      <!-- Formato de salida -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs text-white/40">Formato de salida</span>
        <div class="flex flex-wrap gap-2">
          {#each formats as fmt (fmt)}
            <button
              class="rounded-md px-3 py-1 text-xs transition-colors
                     {outputFormat === fmt
                       ? 'bg-indigo-600 text-white'
                       : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
              onclick={() => outputFormat = fmt}
              disabled={progress.running}
            >
              {fmt}
            </button>
          {/each}
        </div>
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
            Dividir
          </button>
        {/if}
      </div>

    </section>

    <!-- Panel derecho: progreso -->
    <section class="flex flex-1 flex-col gap-4">

      <!-- Progreso global -->
      <ProgressBar
        value={progress.value}
        running={progress.running}
        success={progress.success}
      />

      <!-- Progreso por segmento -->
      {#if progress.files.length > 0}
        <div class="flex flex-col gap-1">
          <span class="text-xs text-white/30">Segmentos</span>
          <div class="flex flex-wrap gap-1.5">
            {#each progress.files as file (file.index)}
              <div
                class="h-2 w-8 rounded-full transition-colors
                       {file.done ? 'bg-emerald-500' : 'bg-indigo-500 animate-pulse'}"
                title="Segmento {file.index + 1}"
              ></div>
            {/each}
          </div>
        </div>
      {/if}

      <LogPanel logs={progress.logs} />
    </section>

  </main>

</div>