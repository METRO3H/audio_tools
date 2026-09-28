<script>
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";
import { persistentConfig } from "$lib/stores/persistentConfig.js";
   import ProcessingView from "$lib/views/shared/ProcessingView.svelte";
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
   import { basename, folderName } from "$lib/utils.js";
   let { goHome } = $props();

   const VIDEO_EXTS = ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm"];

   // ── Estado ───────────────────────────────────────────────────────────────────

   let mediaType = $state("audio");
   let processing = $state(false);
   let fileInfo = $state(null);
   let chapters = $state([]);
   let hasChapters = $state(false);
   let segmentMode = $state("chapters");
   let intervalMins = $state(20);
   let outputFolder = $state("");
   let useSubfolder = $state(true);
   let autoHint = $state("");


   // ── Cargar configuración guardada ────────────────────────────────────────────
$effect(() => {
  const saved = persistentConfig.get('diverge_config');
  if (saved) {
    mediaType = saved.mediaType ?? "audio";
    segmentMode = saved.segmentMode ?? "chapters";
    intervalMins = saved.intervalMins ?? 20;
    useSubfolder = saved.useSubfolder ?? true;
  }
});

// ── Guardar configuración al cambiar ────────────────────────────────────────
$effect(() => {
  persistentConfig.set('diverge_config', {
    mediaType,
    segmentMode,
    intervalMins,
    useSubfolder,
  });
});

   // ── Derivados ────────────────────────────────────────────────────────────────

   const intervalSeconds = $derived(intervalMins * 60);

   const outputFormat = $derived(fileInfo ? fileInfo.name.split(".").pop().toLowerCase() : "mp3");

   // Fuente del nombre usado para los segmentos: en audio es la carpeta base
   // (nombre del proyecto), en video es el nombre del propio archivo (sin extensión),
   // ya que en modo video no existe un concepto de "carpeta base".
   const namingSource = $derived(
      mediaType === "video"
         ? fileInfo
            ? fileInfo.name.replace(/\.[^.]+$/, "")
            : ""
         : folderName(appConfig.baseFolder),
   );

   const estimatedSegments = $derived(() => {
      if (!fileInfo || segmentMode === "chapters") return [];
      const total = fileInfo.duration_seconds;
      const interval = intervalSeconds;
      if (!total || !interval) return [];
      const count = Math.ceil(total / interval);
      return Array.from({ length: count }, (_, i) => ({
         name: `[${i + 1}] ${namingSource}.${outputFormat}`,
         size_mb: 0,
         duration_seconds: Math.min(interval, total - i * interval),
         path: "",
      }));
   });

   const fileInfos = $derived(
      segmentMode === "chapters"
         ? chapters.map((ch, i) => ({
              name: `[${i + 1}] ${namingSource} - ${ch.title}.${outputFormat}`,
              size_mb: 0,
              duration_seconds: ch.end - ch.start,
              path: "",
           }))
         : estimatedSegments(),
   );

   const outputSubfolder = $derived(mediaType === "video" ? "videos" : "audios");

   // Carpeta efectiva donde se va a guardar:
   //  - toggle ON  → se infiere sola (carpeta base en audio, carpeta del archivo en video)
   //  - toggle OFF → la que el usuario eligió manualmente
   const effectiveOutputFolder = $derived.by(() => {
      if (!useSubfolder) return outputFolder;
      if (mediaType === "audio") return appConfig.baseFolder;
      if (!fileInfo?.path) return "";
      const idx = Math.max(fileInfo.path.lastIndexOf("\\"), fileInfo.path.lastIndexOf("/"));
      return idx >= 0 ? fileInfo.path.slice(0, idx) : "";
   });

   const outputPath = $derived.by(() => {
      if (!effectiveOutputFolder) return "";
      if (!useSubfolder) return effectiveOutputFolder;
      return `${effectiveOutputFolder}\\${outputSubfolder}\\parts`;
   });

   const canRun = $derived(!!fileInfo && !!effectiveOutputFolder && intervalMins > 0 && !progress.running);

   function formatDuration(seconds) {
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = Math.floor(seconds % 60);
      if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
      return `${m}:${String(s).padStart(2, "0")}`;
   }

   // ── Reset al cambiar tipo ────────────────────────────────────────────────────

   $effect(() => {
      mediaType;
      fileInfo = null;
      chapters = [];
      hasChapters = false;
      segmentMode = "chapters";
      outputFolder = "";
      autoHint = "";
   });

   // ── Carga ────────────────────────────────────────────────────────────────────

   async function pickBaseFolder() {
      const folder = await bridge.pick_folder();
      if (!folder) return;
      appConfig.setBaseFolder(folder);
      if (!outputFolder) outputFolder = folder;
      await autoLoadAudio(folder);
   }

   async function autoLoadAudio(folder) {
      const info = await bridge.get_file_for_diverge(folder);
      if (!info) {
         fileInfo = null;
         autoHint = "⚠ No se encontró archivo de audio en ./audios";
         return;
      }
      fileInfo = info;
      autoHint = `✓ Auto-detectado: ${info.name}`;
      await loadChapters(info.path);
   }

   async function loadChapters(path) {
      const chs = await bridge.get_chapters_for_file(path);
      chapters = chs;
      hasChapters = chs.length > 0;
      segmentMode = hasChapters ? "chapters" : "interval";
   }

   async function pickFile() {
      const exts =
         mediaType === "audio" ? ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg", "*.flac", "*.opus"] : VIDEO_EXTS;
      const paths = await bridge.pick_files(exts, appConfig.baseFolder, mediaType);
      if (!paths.length) return;

      const info = await bridge.get_file_info(paths[0]);
      fileInfo = { ...info, path: paths[0] };
      autoHint = "";

      if (mediaType === "audio") {
         await loadChapters(paths[0]);
      } else {
         hasChapters = false;
         segmentMode = "interval";
      }
   }

   async function pickOutputFolder() {
      const folder = await bridge.pick_folder();
      if (folder) outputFolder = folder;
   }

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      progress.reset();
      processing = true;
      progress.running = true;

      await bridge.run_diverge(
         fileInfo.path,
         appConfig.baseFolder,
         effectiveOutputFolder,
         intervalSeconds,
         outputFormat,
         segmentMode === "chapters" ? chapters : null,
         mediaType,
         useSubfolder,
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
      title="Diverge"
      {goHome}
      {fileInfos}
      {outputPath}
      showOpenFile={false}
      onCancel={cancel}
      onBack={goBack}
   />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title="Diverge" {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
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

            <!-- Carpeta base (solo audio) -->
            {#if mediaType === "audio"}
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
            {/if}

            <!-- Archivo -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center justify-between">
                  <span class="text-xs text-white/40">Archivo</span>
                  <button class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors" onclick={pickFile}>
                     {mediaType === "audio" ? "Seleccionar manualmente" : "Seleccionar archivo"}
                  </button>
               </div>

               {#if autoHint}
                  <span class="text-xs {autoHint.startsWith('⚠') ? 'text-yellow-400' : 'text-emerald-400'}">
                     {autoHint}
                  </span>
               {/if}

               {#if fileInfo}
                  <div
                     class="flex items-center justify-between rounded-lg
                        border border-white/10 bg-white/5 px-3 py-2"
                  >
                     <span class="truncate text-xs text-white/70">{fileInfo.name}</span>
                     <div class="flex shrink-0 items-center gap-3 ml-3 text-xs text-white/30">
                        <span>{fileInfo.size_mb} MB</span>
                        <span>{formatDuration(fileInfo.duration_seconds)}</span>
                     </div>
                  </div>
               {:else}
                  <div
                     class="rounded-lg border border-dashed border-white/10 p-4
                        text-center text-xs text-white/20"
                  >
                     {mediaType === "audio"
                        ? "Selecciona una carpeta base o elige manualmente"
                        : "Selecciona un archivo de video"}
                  </div>
               {/if}
            </div>

            <!-- Modo de segmentación — horizontal -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">Modo de segmentación</span>
               <div class="flex gap-5">
                  <label
                     class="flex items-center gap-2
                          {hasChapters ? 'cursor-pointer' : 'cursor-not-allowed opacity-40'}"
                  >
                     <input
                        type="radio"
                        name="segmentMode"
                        value="chapters"
                        bind:group={segmentMode}
                        disabled={!hasChapters}
                        class="accent-indigo-500"
                     />
                     <span class="text-xs text-white/70">
                        Chapters
                        {#if fileInfo && !hasChapters}
                           <span class="text-white/25">(sin chapters)</span>
                        {:else if hasChapters}
                           <span class="text-white/25">({chapters.length})</span>
                        {/if}
                     </span>
                  </label>

                  <label class="flex items-center gap-2 cursor-pointer">
                     <input
                        type="radio"
                        name="segmentMode"
                        value="interval"
                        bind:group={segmentMode}
                        class="accent-indigo-500"
                     />
                     <span class="text-xs text-white/70">Intervalo fijo</span>
                  </label>
               </div>
            </div>

            <!-- Intervalo — input pequeño -->
            {#if segmentMode === "interval"}
               <div class="flex flex-col gap-1.5">
                  <label class="text-xs text-white/40" for="interval"> Intervalo (minutos) </label>
                  <div class="flex items-center gap-3">
                     <input
                        id="interval"
                        type="number"
                        bind:value={intervalMins}
                        min="1"
                        max="999"
                        class="w-20 rounded-lg border border-white/10 bg-white/5 px-3 py-2
                       text-sm text-white outline-none focus:border-indigo-500/50
                       transition-colors text-center"
                     />
                     {#if fileInfo}
                        <span class="text-xs text-white/30">
                           ≈ {estimatedSegments().length} segmentos
                        </span>
                     {/if}
                  </div>
               </div>
            {/if}

            <!-- Toggle subcarpeta audios/parts o videos/parts -->
            <div class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2.5">
               <div class="flex flex-col gap-0.5">
                  <span class="text-xs text-white/70">
                     Guardar en subcarpeta <code class="text-white/40">{outputSubfolder}/parts</code>
                  </span>
                  {#if outputPath}
                     <span class="truncate text-[11px] text-white/30">{outputPath}</span>
                  {/if}
               </div>
               <button
                  type="button"
                  role="switch"
                  aria-checked={useSubfolder}
                  onclick={() => (useSubfolder = !useSubfolder)}
                  class="relative h-5 w-9 shrink-0 rounded-full border-none p-0 transition-colors
                     {useSubfolder ? 'bg-indigo-600' : 'bg-white/15'}"
               >
                  <span
                     class="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform
                        {useSubfolder ? 'translate-x-4' : 'translate-x-0'}"
                  ></span>
               </button>
            </div>

            <!-- Carpeta de salida (solo si se desactiva la subcarpeta automática) -->
            {#if !useSubfolder}
               <div class="flex flex-col gap-1.5">
                  <span class="text-xs text-white/40">Carpeta de salida</span>
                  <button
                     class="flex items-center gap-2 rounded-lg border border-white/10
                     bg-white/5 px-3 py-2 text-xs text-left transition-all
                     hover:border-white/20"
                     onclick={pickOutputFolder}
                  >
                     <span>📁</span>
                     <span class="truncate text-white/60">
                        {outputFolder || "Sin seleccionar"}
                     </span>
                  </button>
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
               Ejecutar diverge
            </button>
         </div>
      </main>
   </div>
{/if}