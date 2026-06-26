<script>
  /**
   * AudioToVideoView.svelte
   * ────────────────────────
   * Convierte archivos de audio a video con imagen de fondo estática.
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

  let files           = $state([])
  let backgroundImage = $state(null)

  const canRun = $derived(
    files.length >= 1 &&
    appConfig.baseFolder &&
    !progress.running
  )

  // ── Acciones ────────────────────────────────────────────────────────────────

  async function pickImage() {
    const path = await bridge.pick_image()
    if (path) backgroundImage = path
  }

  function clearImage() {
    backgroundImage = null
  }

  function basename(path) {
    return path?.split(/[\\/]/).pop() ?? ''
  }

  async function run() {
    if (!canRun) return
    progress.reset()

    await bridge.run_audio_to_video(
      files,
      appConfig.baseFolder,
      backgroundImage,
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
    <h1 class="text-sm font-semibold">Audio → Video</h1>
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

      <!-- Imagen de fondo -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs text-white/40">Imagen de fondo</span>

        {#if backgroundImage}
          <div class="flex items-center justify-between rounded-lg
                      border border-white/10 bg-white/5 px-3 py-2">
            <span class="truncate text-xs text-white/60">
              {basename(backgroundImage)}
            </span>
            <button
              class="ml-2 shrink-0 text-white/30 hover:text-red-400 transition-colors text-xs"
              onclick={clearImage}
              disabled={progress.running}
            >
              ✕
            </button>
          </div>
        {:else}
          <button
            class="rounded-lg border border-dashed border-white/10 px-4 py-3
                   text-xs text-white/30 hover:border-white/20 hover:text-white/50
                   transition-colors disabled:opacity-40"
            onclick={pickImage}
            disabled={progress.running}
          >
            + Seleccionar imagen (opcional)
          </button>
          <span class="text-xs text-white/20">
            Sin imagen se usa fondo negro 1280×720
          </span>
        {/if}
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
            Convertir
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