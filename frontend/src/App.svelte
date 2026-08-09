<script>
   import { bridgeReady } from "$lib/stores/bridge.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { bridge } from "$lib/stores/bridge.svelte.js";

   import HomeView from "$lib/views/HomeView.svelte";
   import MergeView from "$lib/views/MergeView.svelte";
   import DivergeView from "$lib/views/DivergeView.svelte";
   import AudioToVideoView from "$lib/views/AudioToVideoView.svelte";
   import TranscribeView from "$lib/views/TranscribeView.svelte";
   import PipelineView from "$lib/views/PipelineView.svelte";
   import ConfirmModal from "$lib/components/ConfirmModal.svelte";
   import TranslateView from "$lib/views/TranslateView.svelte";

   let currentView = $state("home");
   let viewKey = $state(0);
   let showExitWarn = $state(false);
   let showCloseWarn = $state(false);

   // ── Inicialización ──────────────────────────────────────────────────────────

   $effect(() => {
      if (bridgeReady.value && !appConfig.loaded) {
         appConfig.init();
      }
   });

   $effect(() => {
      if (!bridgeReady.value) return;

      const onCloseWarning = () => {
         showCloseWarn = true;
      };
      const onKeydown = (e) => {
         if (e.altKey && e.key === "F4" && progress.running) {
            e.preventDefault();
            showCloseWarn = true;
         }
      };

      window.addEventListener("audiotools:closewarning", onCloseWarning);
      window.addEventListener("keydown", onKeydown);

      return () => {
         window.removeEventListener("audiotools:closewarning", onCloseWarning);
         window.removeEventListener("keydown", onKeydown);
      };
   });

   // ── Navegación ──────────────────────────────────────────────────────────────

   function navigate(view) {
      currentView = view;
      viewKey++;
   }

   function goHome() {
      if (progress.running) {
         showExitWarn = true;
         return;
      }
      _doGoHome();
   }

   function _doGoHome() {
      progress.reset();
      appConfig.resetBaseFolder();
      currentView = "home";
      viewKey++;
      showExitWarn = false;
   }

   async function confirmExit() {
      await bridge.cancel();
      _doGoHome();
   }

   async function confirmClose() {
      await bridge.cancel();
      showCloseWarn = false;
   }
</script>

<!-- Modal: salir al inicio con proceso en curso -->
{#if showExitWarn}
   <ConfirmModal
      title="Proceso en curso"
      message="Hay un proceso en ejecución. Si vuelves al inicio, el proceso se cancelará. ¿Deseas continuar?"
      confirmLabel="Cancelar proceso y salir"
      cancelLabel="Seguir aquí"
      danger={true}
      onConfirm={confirmExit}
      onCancel={() => (showExitWarn = false)}
   />
{/if}

<!-- Modal: cerrar la app con proceso en curso -->
{#if showCloseWarn}
   <ConfirmModal
      title="Proceso en curso"
      message="Hay un proceso en ejecución. Si cierras la app, el proceso se cancelará. ¿Deseas cerrar?"
      confirmLabel="Cancelar proceso y cerrar"
      cancelLabel="Seguir aquí"
      danger={true}
      onConfirm={confirmClose}
      onCancel={() => (showCloseWarn = false)}
   />
{/if}

<div class="h-screen w-screen overflow-hidden bg-zinc-950 text-white select-none">
   {#if !bridgeReady.value}
      <div class="flex h-full items-center justify-center">
         <span class="text-white/20 text-sm tracking-widest uppercase">Cargando...</span>
      </div>
   {:else if currentView === "home"}
      <HomeView {navigate} />
   {:else if currentView === "merge"}
      {#key viewKey}
         <MergeView {goHome} />
      {/key}
   {:else if currentView === "diverge"}
      {#key viewKey}
         <DivergeView {goHome} />
      {/key}
   {:else if currentView === "audio_to_video"}
      {#key viewKey}
         <AudioToVideoView {goHome} />
      {/key}
   {:else if currentView === "transcribe"}
      {#key viewKey}
         <TranscribeView {goHome} />
      {/key}
   {:else if currentView === "pipeline"}
      {#key viewKey}
         <PipelineView {goHome} />
      {/key}
   {:else if currentView === "translate"}
      {#key viewKey}
         <TranslateView {goHome} />
      {/key}
   {/if}
</div>
