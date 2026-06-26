<script>
  /**
   * TranscribeView.svelte
   * ──────────────────────
   * Transcribe archivos de audio a .srt usando faster-whisper.
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

  // ── Opciones del modelo ─────────────────────────────────────────────────────

  const modelSizes = ['tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3']
  const devices    = ['cuda', 'cpu']

  const computeTypesByDevice = {
    cuda: ['float16', 'int8_float16', 'int8'],
    cpu:  ['float32', 'int8'],
  }

  // ── Estado local ────────────────────────────────────────────────────────────

  let files           = $state([])
  let modelSize       = $state('medium')
  let device          = $state('cuda')
  let computeType     = $state('int8_float16')
  let outputSubfolder = $state('output')
  let beamSize        = $state(5)

  // Al cambiar device, ajusta compute type al primero disponible
  $effect(() => {
    const available = computeTypesByDevice[device]
    if (!available.includes(computeType)) {
      computeType = available[0]
    }
  })

  const canRun = $derived(
    files.length >= 1 &&
    outputSubfolder.trim() &&
    appConfig.baseFolder &&
    !progress.running
  )

  // ── Acciones ────────────────────────────────────────────────────────────────

  async function run() {
    if (!canRun) return
    progress.reset()

    await bridge.run_transcribe(
      files,
      appConfig.baseFolder,
      modelSize,
      device,
      computeType,
      outputSubfolder,
      beamSize,
    )
  }

  function cancel() {
    bridge.cancel()
  }

  function basename(path) {
    return path?.split(/[\\/]/).pop() ?? ''
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
    <h1 class="text-sm font-semibold">Transcribe</h1>
  </header>

  <!-- Contenido -->
  <main class="flex flex-1 gap-6 overflow-hidden px-8 py-6">

    <!-- Panel izquierdo: configuración -->
    <section class="flex w-80 shrink-0 flex-col gap-5 overflow-y-auto">

      <FileDropZone
        bind:files
        accept={['*.mp3', '*.opus', '*.m4a', '*.wav', '*.flac', '*.ogg']}
        disabled={progress.running}
      />

      <!-- Modelo -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs text-white/40">Modelo</span>
        <div class="flex flex-wrap gap-1.5">
          {#each modelSizes as size (size)}
            <button
              class="rounded-md px-3 py-1 text-xs transition-colors
                     {modelSize === size
                       ? 'bg-indigo-600 text-white'
                       : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
              onclick={() => modelSize = size}
              disabled={progress.running}
            >
              {size}
            </button>
          {/each}
        </div>
      </div>

      <!-- Device -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs text-white/40">Device</span>
        <div class="flex gap-2">
          {#each devices as d (d)}
            <button
              class="flex-1 rounded-md px-3 py-1.5 text-xs transition-colors
                     {device === d
                       ? 'bg-indigo-600 text-white'
                       : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
              onclick={() => device = d}
              disabled={progress.running}
            >
              {d.toUpperCase()}
            </button>
          {/each}
        </div>
      </div>

      <!-- Compute type -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs text-white/40">Compute type</span>
        <div class="flex flex-wrap gap-1.5">
          {#each computeTypesByDevice[device] as ct (ct)}
            <button
              class="rounded-md px-3 py-1 text-xs transition-colors
                     {computeType === ct
                       ? 'bg-indigo-600 text-white'
                       : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
              onclick={() => computeType = ct}
              disabled={progress.running}
            >
              {ct}
            </button>
          {/each}
        </div>
      </div>

      <!-- Beam size -->
      <div class="flex flex-col gap-1.5">
        <label class="text-xs text-white/40" for="beam-size">
          Beam size
        </label>
        <input
          id="beam-size"
          type="number"
          bind:value={beamSize}
          min="1"
          max="10"
          disabled={progress.running}
          class="rounded-lg border border-white/10 bg-white/5 px-3 py-2
                 text-sm text-white outline-none focus:border-indigo-500/50
                 transition-colors disabled:opacity-40"
        />
      </div>

      <!-- Subcarpeta de salida -->
      <div class="flex flex-col gap-1.5">
        <label class="text-xs text-white/40" for="subfolder">
          Subcarpeta de salida
        </label>
        <input
          id="subfolder"
          type="text"
          bind:value={outputSubfolder}
          disabled={progress.running}
          placeholder="output"
          class="rounded-lg border border-white/10 bg-white/5 px-3 py-2
                 text-sm text-white placeholder-white/20 outline-none
                 focus:border-indigo-500/50 transition-colors disabled:opacity-40"
        />
        <span class="text-xs text-white/20">
          Se guarda en: transcriptions/{outputSubfolder}/
        </span>
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
            Transcribir
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

      <!-- Progreso por archivo -->
      {#if progress.files.length > 0}
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-white/30">Archivos</span>
          {#each progress.files as file (file.index)}
            <div class="flex items-center gap-2 text-xs text-white/50">
              <div
                class="h-1.5 w-1.5 rounded-full shrink-0
                       {file.done ? 'bg-emerald-500' : 'bg-indigo-500 animate-pulse'}"
              ></div>
              <span class="truncate">
                {basename(files[file.index] ?? '')}
              </span>
            </div>
          {/each}
        </div>
      {/if}

      <LogPanel logs={progress.logs} />
    </section>

  </main>

</div>