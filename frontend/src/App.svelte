<script>
  /**
   * App.svelte
   * ───────────
   * Raíz de la aplicación. Responsabilidades:
   *   1. Esperar a que pywebview esté listo
   *   2. Inicializar appConfig desde el backend
   *   3. Manejar qué vista está activa
   *
   * No contiene lógica de negocio ni UI de herramientas.
   */

  import { bridgeReady } from '$lib/stores/bridge.svelte.js'
  import { appConfig }   from '$lib/stores/config.svelte.js'

  import HomeView          from '$lib/views/HomeView.svelte'
  import MergeView         from '$lib/views/MergeView.svelte'
  import DivergeView       from '$lib/views/DivergeView.svelte'
  import AudioToVideoView  from '$lib/views/AudioToVideoView.svelte'
  import TranscribeView    from '$lib/views/TranscribeView.svelte'
  import PipelineView      from '$lib/views/PipelineView.svelte'

  // ── Navegación ──────────────────────────────────────────────────────────────

  /** @type {'home' | 'merge' | 'diverge' | 'audio_to_video' | 'transcribe' | 'pipeline'} */
  let currentView = $state('home')

  function navigate(view) {
    currentView = view
  }

  function goHome() {
    currentView = 'home'
  }

  // ── Inicialización ──────────────────────────────────────────────────────────

  $effect(() => {
    if (bridgeReady.value && !appConfig.loaded) {
      appConfig.init()
    }
  })
</script>

<div class="h-screen w-screen overflow-hidden bg-zinc-950 text-white select-none">

  {#if !bridgeReady.value}
    <!-- Splash mientras pywebview carga -->
    <div class="flex h-full items-center justify-center">
      <span class="text-white/20 text-sm tracking-widest uppercase">
        Cargando...
      </span>
    </div>

  {:else if currentView === 'home'}
    <HomeView {navigate} />

  {:else if currentView === 'merge'}
    <MergeView {goHome} />

  {:else if currentView === 'diverge'}
    <DivergeView {goHome} />

  {:else if currentView === 'audio_to_video'}
    <AudioToVideoView {goHome} />

  {:else if currentView === 'transcribe'}
    <TranscribeView {goHome} />

  {:else if currentView === 'pipeline'}
    <PipelineView {goHome} />

  {/if}

</div>