<script>
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";
   import Spinner from "$lib/components/Spinner.svelte";
   import ProcessingView from "$lib/views/shared/ProcessingView.svelte";
   import { persistentConfig } from "$lib/stores/persistentConfig.js";
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
   import { basename, folderName } from "$lib/utils.js";
   let { goHome } = $props();

   // ── Estado ───────────────────────────────────────────────────────────────────

   let processing = $state(false);
   let fileInfos = $state([]);
   let imageInfo = $state(null); // { path, name, optimized }
   let autoHint = $state("");
   let imageHint = $state("");
   let showAdvanced = $state(false);

   // Encoders
   let availableEncoders = $state({ cpu: true, nvidia: false, amd: false, intel: false });
   let encoder = $state("cpu");
   let detectingEncoders = $state(true);

   // Opciones de encoding
   let fps = $state(1);
   let crf = $state(23);
   let preset = $state("medium");
   let resolution = $state("1280x720");
   let copyAudio = $state(true);

   const FPS_OPTIONS = [1, 24, 30, 60];
   const RESOLUTION_OPTIONS = ["1280x720", "1920x1080", "3840x2160"];
   const AUDIO_EXTS = ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg", "*.flac", "*.opus"];

   // Presets según encoder
   const presetOptions = $derived(
      encoder === "nvidia"
         ? ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
         : encoder === "cpu"
           ? ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]
           : ["fast", "medium", "slow"],
   );
// ── Cargar configuración guardada ────────────────────────────────────────────
$effect(() => {
  const saved = persistentConfig.get('audio_to_video_config');
  if (saved) {
    encoder = saved.encoder ?? "cpu";
    fps = saved.fps ?? 1;
    crf = saved.crf ?? 23;
    preset = saved.preset ?? "medium";
    resolution = saved.resolution ?? "1280x720";
    copyAudio = saved.copyAudio ?? true;
    showAdvanced = saved.showAdvanced ?? false;
  }
});

// ── Guardar configuración al cambiar ────────────────────────────────────────
$effect(() => {
  persistentConfig.set('audio_to_video_config', {
    encoder,
    fps,
    crf,
    preset,
    resolution,
    copyAudio,
    showAdvanced,
  });
});
   $effect(() => {
      // Reset preset al cambiar encoder si no es válido
      if (!presetOptions.includes(preset)) {
         preset = presetOptions[Math.floor(presetOptions.length / 2)];
      }
   });

   // fileInfos para ProcessingView
   const processingFileInfos = $derived(fileInfos);

   const outputPath = $derived(appConfig.baseFolder ? `${appConfig.baseFolder}\\videos` : "");

   const canRun = $derived(fileInfos.length >= 1 && !!appConfig.baseFolder && !progress.running);

   const encoderLabels = {
      cpu: "CPU (libx264)",
      nvidia: "NVIDIA (nvenc)",
      amd: "AMD (amf)",
      intel: "Intel (qsv)",
   };

   // ── Inicialización ────────────────────────────────────────────────────────────

   $effect(() => {
      // Detectar encoders al montar
      bridge.detect_encoders().then((result) => {
         availableEncoders = result;
         detectingEncoders = false;
         // Prioridad: nvidia > amd > intel > cpu
         if (result.nvidia) encoder = "nvidia";
         else if (result.amd) encoder = "amd";
         else if (result.intel) encoder = "intel";
         else encoder = "cpu";
      });
   });

   // ── Carga ────────────────────────────────────────────────────────────────────

   async function pickBaseFolder() {
      const folder = await bridge.pick_folder();
      if (!folder) return;
      appConfig.setBaseFolder(folder);
      await loadAll(folder);
   }

   async function loadAll(folder) {
      await Promise.all([loadAudios(folder), loadImage(folder)]);
   }

   async function loadAudios(folder) {
      const result = await bridge.scan_audio_parts_or_audios(folder);
      if (result.error) {
         fileInfos = [];
         autoHint = `⚠ ${result.error}`;
         return;
      }
      if (!result.files.length) {
         fileInfos = [];
         autoHint = "⚠ No se encontraron audios";
         return;
      }
      const infos = await Promise.all(result.files.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: result.files[i] }));
      autoHint = `✓ ${infos.length} audio(s) detectados desde ${result.source}`;
   }

   async function loadImage(folder) {
      const result = await bridge.scan_images_folder(folder);
      if (!result) {
         imageInfo = null;
         imageHint = "⚠ No se encontró imagen en ./images — se usará fondo negro";
         return;
      }
      imageInfo = result;
      imageHint = result.optimized ? `✓ Imagen optimizada: ${result.name}` : `✓ Imagen detectada: ${result.name}`;
   }

   async function pickFiles() {
      const paths = await bridge.pick_files(AUDIO_EXTS, appConfig.baseFolder, "audio");
      if (!paths.length) return;
      const infos = await Promise.all(paths.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: paths[i] }));
      autoHint = "";
   }

   async function pickImage() {
      const path = await bridge.pick_image(appConfig.baseFolder);
      if (!path) return;
      const result = await bridge.scan_images_folder(appConfig.baseFolder);
      // Si eligió manualmente, usamos esa imagen directamente optimizándola
      imageInfo = { path, name: basename(path), optimized: false };
      imageHint = `✓ Imagen seleccionada: ${basename(path)}`;
   }

   function clearImage() {
      imageInfo = null;
      imageHint = "Sin imagen — se usará fondo negro";
   }

   function removeFile(path) {
      fileInfos = fileInfos.filter((f) => f.path !== path);
   }

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      progress.reset();
      processing = true;
      progress.running = true;

      await bridge.run_audio_to_video(
         fileInfos.map((f) => f.path),
         appConfig.baseFolder,
         imageInfo?.path ?? null,
         encoder,
         fps,
         crf,
         preset,
         resolution,
         copyAudio,
      );
   }

   function cancel() {
      bridge.cancel();
   }

   function goBack() {
      processing = false;
      progress.reset();
   }
</script>

{#if processing}
   <ProcessingView
      title="Audio → Video"
      {goHome}
      fileInfos={processingFileInfos}
      {outputPath}
      showOpenFile={false}
      onCancel={cancel}
      onBack={goBack}
   />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title="Audio → Video" {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <!-- Carpeta base -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">Carpeta base</span>
               <button
                  class="flex items-center gap-2 rounded-lg border border-white/10
                   bg-white/5 px-3 py-2 text-xs text-left transition-all
                   hover:border-white/20"
                  onclick={pickBaseFolder}
               >
                  <span>📁</span>
                  <span class="truncate text-white/60">
                     {appConfig.baseFolder || "Sin seleccionar"}
                  </span>
               </button>
            </div>

            <!-- Archivos de audio -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center justify-between">
                  <span class="text-xs text-white/40">
                     Archivos
                     {#if fileInfos.length}
                        <span class="text-white/20">({fileInfos.length})</span>
                     {/if}
                  </span>
                  <button class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors" onclick={pickFiles}>
                     Seleccionar manualmente
                  </button>
               </div>

               {#if autoHint}
                  <span class="text-xs {autoHint.startsWith('⚠') ? 'text-yellow-400' : 'text-emerald-400'}">
                     {autoHint}
                  </span>
               {/if}

               {#if fileInfos.length}
                  <ul class="flex flex-col gap-1 overflow-y-auto max-h-40">
                     {#each fileInfos as file (file.path)}
                        <li
                           class="flex items-center justify-between rounded-lg
                           bg-white/5 px-3 py-1.5 text-xs text-white/60 shrink-0"
                        >
                           <span class="truncate">{file.name}</span>
                           <div class="flex shrink-0 items-center gap-2 ml-2">
                              <span class="text-white/30">{file.size_mb} MB</span>
                              <button
                                 class="text-white/20 hover:text-red-400 transition-colors"
                                 onclick={() => removeFile(file.path)}>✕</button
                              >
                           </div>
                        </li>
                     {/each}
                  </ul>
               {:else}
                  <div
                     class="rounded-lg border border-dashed border-white/10 p-4
                        text-center text-xs text-white/20"
                  >
                     {appConfig.baseFolder ? "No se encontraron audios" : "Selecciona una carpeta base primero"}
                  </div>
               {/if}
            </div>

            <!-- Imagen de fondo -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center justify-between">
                  <span class="text-xs text-white/40">Imagen de fondo</span>
                  <div class="flex gap-2">
                     <button class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors" onclick={pickImage}>
                        Cambiar
                     </button>
                     {#if imageInfo}
                        <button class="text-xs text-white/30 hover:text-red-400 transition-colors" onclick={clearImage}>
                           Quitar
                        </button>
                     {/if}
                  </div>
               </div>

               {#if imageHint}
                  <span class="text-xs {imageHint.startsWith('⚠') ? 'text-yellow-400' : 'text-emerald-400'}">
                     {imageHint}
                  </span>
               {/if}

               {#if imageInfo}
                  <div
                     class="flex items-center gap-2 rounded-lg border border-white/10
                        bg-white/5 px-3 py-2 text-xs text-white/60"
                  >
                     <span>🖼</span>
                     <span class="truncate">{imageInfo.name}</span>
                     {#if imageInfo.optimized}
                        <span class="shrink-0 text-white/30">(optimizada)</span>
                     {/if}
                  </div>
               {:else}
                  <div
                     class="rounded-lg border border-dashed border-white/10 p-3
                        text-center text-xs text-white/20"
                  >
                     Fondo negro 1280×720
                  </div>
               {/if}
            </div>

            <!-- Encoder -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-2">
                  <span class="text-xs text-white/40">Encoder</span>
                  {#if detectingEncoders}
                     <Spinner size={12} color="text-white/30" duration="1s" />
                     <span class="text-xs text-white/20">Detectando...</span>
                  {/if}
               </div>
               <div class="flex flex-wrap gap-2">
                  {#each Object.entries(encoderLabels) as [key, label] (key)}
                     <button
                        class="rounded-md px-3 py-1.5 text-xs transition-colors
                       {!availableEncoders[key]
                           ? 'opacity-30 cursor-not-allowed border border-white/10 bg-white/5 text-white/30'
                           : encoder === key
                             ? 'bg-indigo-600 text-white'
                             : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => {
                           if (availableEncoders[key]) encoder = key;
                        }}
                        disabled={!availableEncoders[key]}
                     >
                        {label}
                     </button>
                  {/each}
               </div>
            </div>

            <!-- FPS -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">FPS</span>
               <div class="flex gap-2">
                  {#each FPS_OPTIONS as f (f)}
                     <button
                        class="rounded-md px-3 py-1.5 text-xs transition-colors
                       {fps === f
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => (fps = f)}
                     >
                        {f}
                     </button>
                  {/each}
               </div>
            </div>

            <!-- Toggle opciones avanzadas -->
            <button
               class="flex items-center gap-2 text-xs text-white/30 hover:text-white/60
                 transition-colors w-fit"
               onclick={() => (showAdvanced = !showAdvanced)}
            >
               <span>{showAdvanced ? "▼" : "▶"}</span>
               <span>Opciones avanzadas</span>
            </button>

            {#if showAdvanced}
               <div class="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/3 p-4">
                  <!-- CRF -->
                  <div class="flex flex-col gap-1.5">
                     <div class="flex items-center justify-between">
                        <label class="text-xs text-white/40" for="crf"> Calidad (CRF) — menor es mejor </label>
                        <span class="text-xs text-white/50">{crf}</span>
                     </div>
                     <input
                        id="crf"
                        type="range"
                        bind:value={crf}
                        min="0"
                        max="51"
                        step="1"
                        class="accent-indigo-500 w-full"
                     />
                     <div class="flex justify-between text-xs text-white/20">
                        <span>0 (mejor)</span>
                        <span>51 (peor)</span>
                     </div>
                  </div>

                  <!-- Preset -->
                  <div class="flex flex-col gap-1.5">
                     <span class="text-xs text-white/40">Preset</span>
                     <div class="flex flex-wrap gap-1.5">
                        {#each presetOptions as p (p)}
                           <button
                              class="rounded-md px-2.5 py-1 text-xs transition-colors
                           {preset === p
                                 ? 'bg-indigo-600 text-white'
                                 : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                              onclick={() => (preset = p)}
                           >
                              {p}
                           </button>
                        {/each}
                     </div>
                  </div>

                  <!-- Resolución (solo si no hay imagen) -->
                  {#if !imageInfo}
                     <div class="flex flex-col gap-1.5">
                        <span class="text-xs text-white/40">Resolución (fondo negro)</span>
                        <div class="flex gap-2">
                           {#each RESOLUTION_OPTIONS as r (r)}
                              <button
                                 class="rounded-md px-3 py-1 text-xs transition-colors
                             {resolution === r
                                    ? 'bg-indigo-600 text-white'
                                    : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                                 onclick={() => (resolution = r)}
                              >
                                 {r}
                              </button>
                           {/each}
                        </div>
                     </div>
                  {/if}

                  <!-- Audio -->
                  <div class="flex flex-col gap-1.5">
                     <span class="text-xs text-white/40">Audio</span>
                     <div class="flex gap-2">
                        <button
                           class="rounded-md px-3 py-1.5 text-xs transition-colors
                         {copyAudio
                              ? 'bg-indigo-600 text-white'
                              : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                           onclick={() => (copyAudio = true)}
                        >
                           Copy (sin re-encodear)
                        </button>
                        <button
                           class="rounded-md px-3 py-1.5 text-xs transition-colors
                         {!copyAudio
                              ? 'bg-indigo-600 text-white'
                              : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                           onclick={() => (copyAudio = false)}
                        >
                           AAC 192k
                        </button>
                     </div>
                  </div>
               </div>
            {/if}

            <!-- Botón -->
            <button
               class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium
                 text-white transition-colors hover:bg-indigo-500
                 disabled:opacity-30 disabled:cursor-not-allowed"
               onclick={run}
               disabled={!canRun}
            >
               Ejecutar Audio → Video
            </button>
         </div>
      </main>
   </div>
{/if}
