<script>
   import { bridgeReady } from "$lib/stores/bridge.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";

   import HomeView from "$lib/views/HomeView.svelte";
   import MergeView from "$lib/views/MergeView.svelte";
   import DivergeView from "$lib/views/DivergeView.svelte";
   import AudioToVideoView from "$lib/views/AudioToVideoView.svelte";
   import TranscribeView from "$lib/views/TranscribeView.svelte";
   import PipelineView from "$lib/views/PipelineView.svelte";

   let currentView = $state("home");
   let viewKey = $state(0);

   function navigate(view) {
      currentView = view;
      viewKey++;
   }

   function goHome() {
      progress.reset();
      appConfig.resetBaseFolder();
      currentView = "home";
      viewKey++;
   }

   $effect(() => {
      if (bridgeReady.value && !appConfig.loaded) {
         appConfig.init();
      }
   });
</script>

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
      {#key currentView}
         <DivergeView {goHome} />
      {/key}
   {:else if currentView === "audio_to_video"}
      {#key currentView}
         <AudioToVideoView {goHome} />
      {/key}
   {:else if currentView === "transcribe"}
      {#key currentView}
         <TranscribeView {goHome} />
      {/key}
   {:else if currentView === "pipeline"}
      {#key currentView}
         <PipelineView {goHome} />
      {/key}
   {/if}
</div>
