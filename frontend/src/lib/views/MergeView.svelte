<script>
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";

   import ProcessingView from "$lib/views/shared/ProcessingView.svelte";
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";

   let { goHome } = $props();

   const AUDIO_FORMATS = ["mp3", "wav", "aac", "m4a", "ogg", "flac", "opus"];
   const VIDEO_FORMATS = ["mp4", "mkv", "avi", "mov", "webm"];
   const AUDIO_EXTS = ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg", "*.flac", "*.opus"];
   const VIDEO_EXTS = ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm"];

   // ── Estado ──────────────────────────────────────────────────────────────────

   let mediaType = $state("audio");
   let outputFormat = $state("mp3");
   let processing = $state(false);
   let fileInfos = $state([]);
   let outputName = $state("");
   let autoHint = $state("");

   // ── Derivados ────────────────────────────────────────────────────────────────

   const formats = $derived(mediaType === "audio" ? AUDIO_FORMATS : VIDEO_FORMATS);
   const exts = $derived(mediaType === "audio" ? AUDIO_EXTS : VIDEO_EXTS);

   // Al cambiar tipo, resetea formato y archivos
   $effect(() => {
      outputFormat = mediaType === "audio" ? "mp3" : "mp4";
      fileInfos = [];
      autoHint = "";
   });

   // ── Helpers ──────────────────────────────────────────────────────────────────

   function basename(path) {
      return path?.split(/[\\/]/).pop() ?? "";
   }

   function folderName(path) {
      return path?.split(/[\\/]/).pop() ?? "";
   }

   // ── Carga de archivos ────────────────────────────────────────────────────────

   async function loadMedia(folder) {
      const result = await bridge.scan_media_folder(folder, mediaType);
      if (result.error) {
         fileInfos = [];
         autoHint = `⚠ ${result.error}`;
         return;
      }
      if (!result.files.length) {
         fileInfos = [];
         autoHint = `⚠ No se encontraron archivos en ./${mediaType === "audio" ? "audios" : "videos"}`;
         return;
      }
      const infos = await Promise.all(result.files.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: result.files[i] }));
      autoHint = `✓ ${infos.length} archivo(s) detectados`;
      if (!outputName) outputName = folderName(folder);
   }

   // ── Selección manual ─────────────────────────────────────────────────────────

   async function pickFiles() {
      const paths = await bridge.pick_files(exts, appConfig.baseFolder, mediaType);
      if (!paths.length) return;
      const infos = await Promise.all(paths.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: paths[i] }));
      autoHint = "";
      if (!outputName) outputName = folderName(appConfig.baseFolder);
   }

   async function pickBaseFolder() {
      const folder = await bridge.pick_folder();
      if (!folder) return;
      appConfig.setBaseFolder(folder);
      outputName = "";
      await loadMedia(folder);
   }

   function removeFile(path) {
      fileInfos = fileInfos.filter((f) => f.path !== path);
   }

   // ── Output ───────────────────────────────────────────────────────────────────

   function getOutputPath() {
      if (!fileInfos.length) return "";
      const name = outputName || folderName(appConfig.baseFolder);
      const mediaDir = fileInfos[0].path.substring(0, fileInfos[0].path.lastIndexOf("\\") + 1);
      return `${mediaDir}${name}.${outputFormat}`;
   }

   // ── Validación ───────────────────────────────────────────────────────────────

   const canRun = $derived(fileInfos.length >= 2 && !!appConfig.baseFolder && !progress.running);

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      progress.reset();
      processing = true;
      progress.running = true;

      const outPath = getOutputPath();
      const durations = fileInfos.map((f) => f.duration_seconds);
      const paths = fileInfos.map((f) => f.path);

      await bridge.run_merge(paths, outPath, appConfig.baseFolder, durations);
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
   <ProcessingView title="Merge" {goHome} {fileInfos} outputPath={getOutputPath()} onCancel={cancel} onBack={goBack} />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title="Merge" {goHome} />

      <main class="flex flex-1 flex-col items-center justify-center px-8 py-10 overflow-y-auto">
         <div class="flex w-full max-w-md flex-col gap-5">
            <!-- Toggle Audio / Video -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">Tipo</span>
               <div class="flex gap-2">
                  {#each ["audio", "video"] as type (type)}
                     <button
                        class="flex-1 rounded-lg py-2 text-xs font-medium transition-colors
                       {mediaType === type
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => (mediaType = type)}
                     >
                        {type === "audio" ? "🎵 Audio" : "🎬 Video"}
                     </button>
                  {/each}
               </div>
            </div>

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

            <!-- Archivos -->
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
                  <ul class="flex flex-col gap-1 max-h-40 overflow-y-auto ">
                     {#each fileInfos as file (file.path)}
                        <li
                           class="flex items-center justify-between rounded-lg
                           bg-white/5 px-3 py-1.5 text-xs text-white/60"
                        >
                           <span class="truncate">{file.name}</span>
                           <div class="flex shrink-0 items-center gap-2 ml-2">
                              <span class="text-white/30">{file.size_mb} MB</span>
                              <button
                                 class="text-white/20 hover:text-red-400 transition-colors"
                                 onclick={() => removeFile(file.path)}
                              >
                                 ✕
                              </button>
                           </div>
                        </li>
                     {/each}
                  </ul>
               {:else}
                  <div
                     class="rounded-lg border border-dashed border-white/10 p-4
                        text-center text-xs text-white/20"
                  >
                     {appConfig.baseFolder
                        ? `No se encontraron ${mediaType === "audio" ? "audios en ./audios" : "videos en ./videos"}`
                        : "Selecciona una carpeta base primero"}
                  </div>
               {/if}
            </div>

            <!-- Nombre y formato -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">Nombre de salida</span>
               <div class="flex gap-2">
                  <input
                     type="text"
                     bind:value={outputName}
                     placeholder={folderName(appConfig.baseFolder) || "nombre"}
                     class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-sm text-white placeholder-white/20 outline-none
                     focus:border-indigo-500/50 transition-colors"
                  />
                  <select
                     bind:value={outputFormat}
                     class="rounded-lg border border-white/10 bg-zinc-900 px-2 py-2
                     text-xs text-white/70 outline-none focus:border-indigo-500/50"
                  >
                     {#each formats as fmt (fmt)}
                        <option value={fmt}>{fmt}</option>
                     {/each}
                  </select>
               </div>
               {#if fileInfos.length && appConfig.baseFolder}
                  <span class="text-xs text-white/20 truncate">
                     → {basename(getOutputPath())}
                  </span>
               {/if}
            </div>

            <!-- Botón -->
            <button
               class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium
                 text-white transition-colors hover:bg-indigo-500
                 disabled:opacity-30 disabled:cursor-not-allowed"
               onclick={run}
               disabled={!canRun}
            >
               Ejecutar merge
            </button>
         </div>
      </main>
   </div>
{/if}
