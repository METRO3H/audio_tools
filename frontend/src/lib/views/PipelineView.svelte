<script>
  /**
   * PipelineView.svelte
   * ────────────────────
   * Encadena herramientas en secuencia con drag & drop.
   *
   * Nota: el pipeline en la versión tkinter dependía del core/pipeline/
   * que a su vez usaba ctk para los modales de configuración.
   * En esta versión, cada paso tiene su configuración inline,
   * sin modales. El executor del core se mantiene intacto.
   *
   * Props:
   *   goHome  function — vuelve a la pantalla de inicio
   */

  import { progress }  from '$lib/stores/progress.svelte.js'
  import { appConfig } from '$lib/stores/config.svelte.js'
  import { bridge }    from '$lib/stores/bridge.svelte.js'

  import ProgressBar from '$lib/components/ProgressBar.svelte'
  import LogPanel    from '$lib/components/LogPanel.svelte'

  let { goHome } = $props()

  // ── Definición de pasos disponibles ────────────────────────────────────────

  const AVAILABLE_STEPS = [
    { id: 'merge',         label: 'Merge',         icon: '🔗' },
    { id: 'diverge',       label: 'Diverge',        icon: '✂️' },
    { id: 'audio_to_video',label: 'Audio → Video',  icon: '🎬' },
    { id: 'transcribe',    label: 'Transcribe',     icon: '📝' },
  ]

  // ── Estado del pipeline ─────────────────────────────────────────────────────

  /** @type {{ id: string, label: string, icon: string, key: number }[]} */
  let steps = $state([])

  let nextKey = 0

  function addStep(step) {
    steps = [...steps, { ...step, key: nextKey++ }]
  }

  function removeStep(key) {
    steps = steps.filter(s => s.key !== key)
  }

  // ── Drag & drop de pasos ────────────────────────────────────────────────────

  let dragIndex = $state(null)

  function onDragStart(index) {
    dragIndex = index
  }

  function onDragOver(e, index) {
    e.preventDefault()
    if (dragIndex === null || dragIndex === index) return
    const reordered = [...steps]
    const [moved] = reordered.splice(dragIndex, 1)
    reordered.splice(index, 0, moved)
    steps = reordered
    dragIndex = index
  }

  function onDragEnd() {
    dragIndex = null
  }

  // ── Ejecución ───────────────────────────────────────────────────────────────

  const canRun = $derived(
    steps.length >= 2 &&
    appConfig.baseFolder &&
    !progress.running
  )

  async function run() {
    if (!canRun) return
    progress.reset()

    // Envía la lista de step ids al backend
    // El pipeline executor del core se encarga del resto
    await bridge.run_pipeline(
      steps.map(s => s.id),
      appConfig.baseFolder,
    )
  }

  function cancel() {
    bridge.cancel()
  }

  // ── Estado por paso en ejecución ────────────────────────────────────────────

  const stepStatus = $derived(
    steps.map((_, i) => {
      const file = progress.files.find(f => f.index === i)
      if (!file)             return 'pending'
      if (file.done)         return 'done'
      return 'running'
    })
  )
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
    <h1 class="text-sm font-semibold">Pipeline</h1>
  </header>

  <!-- Contenido -->
  <main class="flex flex-1 gap-6 overflow-hidden px-8 py-6">

    <!-- Panel izquierdo: constructor del pipeline -->
    <section class="flex w-80 shrink-0 flex-col gap-5">

      <!-- Pasos disponibles -->
      <div class="flex flex-col gap-2">
        <span class="text-xs text-white/40">Agregar paso</span>
        <div class="flex flex-wrap gap-2">
          {#each AVAILABLE_STEPS as step (step.id)}
            <button
              class="flex items-center gap-1.5 rounded-lg border border-white/10
                     bg-white/5 px-3 py-1.5 text-xs text-white/60
                     hover:border-white/20 hover:text-white transition-all
                     disabled:opacity-30 disabled:cursor-not-allowed"
              onclick={() => addStep(step)}
              disabled={progress.running}
            >
              <span>{step.icon}</span>
              <span>{step.label}</span>
            </button>
          {/each}
        </div>
      </div>

      <!-- Lista de pasos configurados -->
      <div class="flex flex-col gap-2">
        <span class="text-xs text-white/40">
          Secuencia
          {#if steps.length > 0}
            <span class="text-white/20">({steps.length} pasos)</span>
          {/if}
        </span>

        {#if steps.length === 0}
          <div class="rounded-xl border border-dashed border-white/10 p-6
                      text-center text-xs text-white/20">
            Agrega al menos 2 pasos para armar el pipeline
          </div>
        {:else}
          <ol class="flex flex-col gap-1.5">
            {#each steps as step, i (step.key)}
              <li
                class="flex items-center gap-2 rounded-lg border px-3 py-2
                       cursor-grab active:cursor-grabbing transition-all
                       {dragIndex === i
                         ? 'border-indigo-500/50 bg-indigo-500/10 scale-[1.02]'
                         : 'border-white/10 bg-white/5'}
                       {stepStatus[i] === 'done'    ? 'border-emerald-500/30' : ''}
                       {stepStatus[i] === 'running' ? 'border-indigo-500/50'  : ''}"
                draggable="true"
                ondragstart={() => onDragStart(i)}
                ondragover={(e) => onDragOver(e, i)}
                ondragend={onDragEnd}
              >
                <!-- Número -->
                <span class="text-xs text-white/20 w-4 shrink-0">{i + 1}</span>

                <!-- Ícono y nombre -->
                <span class="text-sm">{step.icon}</span>
                <span class="flex-1 text-xs text-white/70">{step.label}</span>

                <!-- Indicador de estado -->
                {#if stepStatus[i] === 'done'}
                  <span class="text-emerald-400 text-xs">✓</span>
                {:else if stepStatus[i] === 'running'}
                  <span class="text-indigo-400 text-xs animate-pulse">●</span>
                {:else}
                  <!-- Botón eliminar -->
                  <button
                    class="text-white/20 hover:text-red-400 transition-colors text-xs"
                    onclick={() => removeStep(step.key)}
                    disabled={progress.running}
                  >
                    ✕
                  </button>
                {/if}
              </li>
            {/each}
          </ol>
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
            Ejecutar pipeline
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