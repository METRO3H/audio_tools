<script>
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";

   import ProcessingView from "$lib/views/shared/ProcessingView.svelte";
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
   import HoverCard from "$lib/components/HoverCard.svelte";
   import BaseFolderPicker from "$lib/components/BaseFolderPicker.svelte";
   import Spinner from "$lib/components/Spinner.svelte";
   import { basename, folderName } from "$lib/utils.js";
   import { persistentConfig } from "$lib/stores/persistentConfig.js";

   let { goHome } = $props();

   // ── Selección local / remoto ─────────────────────────────────────────────────
   // mode: null (todavía sin elegir) | "local" | "remote"
   let mode = $state(null);
   let checkingRemote = $state(false);
   let remoteError = $state("");
   let remoteInfo = $state(null); // { host, port, models } una vez encontrado

   // ── Constantes ───────────────────────────────────────────────────────────────

   const MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"];
   const DEVICES = ["cuda", "cpu"];
   const COMPUTE_BY_DEVICE = {
      cuda: ["float16", "int8_float16", "int8"],
      cpu: ["float32", "int8"],
   };
   const LANGUAGES = [
      { code: "auto", label: "Auto-detectar" },
      { code: "ja", label: "Japonés" },
      { code: "zh", label: "Chino" },
      { code: "ko", label: "Coreano" },
      { code: "es", label: "Español" },
      { code: "en", label: "Inglés" },
   ];

   const LANGUAGE_FOLDERS = {
      auto: "auto",
      ja: "japanese",
      zh: "chinese",
      ko: "korean",
      es: "spanish",
      en: "english",
   };

   const OUTPUT_FORMATS = ["srt", "vtt", "txt"];
   const AUDIO_EXTS = ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg", "*.flac", "*.opus"];

   // ── Estado ───────────────────────────────────────────────────────────────────

   let processing = $state(false);
   let fileInfos = $state([]);
   let autoHint = $state("");

   // Parámetros del modelo
   let modelSize = $state("medium");
   let device = $state("cuda");
   let computeType = $state("int8_float16");
   let beamSize = $state(5);

   // Parámetros de transcripción
   let language = $state("ja");
   let vadFilter = $state(true);
   let conditionOnPrev = $state(false);
   let wordTimestamps = $state(true);
   let initialPrompt = $state("");
   let outputFormat = $state("srt");
   let outputSubfolder = $state("ja");

   // ── Cargar configuración guardada ────────────────────────────────────────────

   $effect(() => {
      const saved = persistentConfig.get("transcribe_config");
      if (saved) {
         modelSize = saved.modelSize ?? "medium";
         device = saved.device ?? "cuda";
         computeType = saved.computeType ?? "int8_float16";
         beamSize = saved.beamSize ?? 5;
         language = saved.language ?? "ja";
         vadFilter = saved.vadFilter ?? true;
         conditionOnPrev = saved.conditionOnPrev ?? false;
         wordTimestamps = saved.wordTimestamps ?? true;
         initialPrompt = saved.initialPrompt ?? "";
         outputFormat = saved.outputFormat ?? "srt";
         outputSubfolder = saved.outputSubfolder ?? "ja";
      }
      // Inicializar desde config.py si no hay guardado
      if (!saved && appConfig.loaded) {
         initialPrompt = appConfig.transcribeInitialPrompt ?? "";
      }
   });

   // ── Guardar configuración al cambiar ────────────────────────────────────────

   $effect(() => {
      persistentConfig.set("transcribe_config", {
         modelSize,
         device,
         computeType,
         beamSize,
         language,
         vadFilter,
         conditionOnPrev,
         wordTimestamps,
         initialPrompt,
         outputFormat,
         outputSubfolder,
      });
   });

   // ── Derivados ────────────────────────────────────────────────────────────────

   const outputPath = $derived(
      appConfig.baseFolder ? `${appConfig.baseFolder}\\transcriptions\\${outputSubfolder}` : "",
   );

   const canRun = $derived(fileInfos.length >= 1 && !!appConfig.baseFolder && !progress.running);

   const modelSizesToShow = $derived(
      mode === "remote" && remoteInfo ? remoteInfo.models : MODEL_SIZES,
   );

   // ── Carga ────────────────────────────────────────────────────────────────────

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
      autoHint = `✓ ${infos.length} archivo(s) detectados desde ${result.source}`;
      if (!outputSubfolder || outputSubfolder === "default") {
         outputSubfolder = folderName(folder);
      }
   }

   async function pickFiles() {
      const paths = await bridge.pick_files(AUDIO_EXTS, appConfig.baseFolder, "audio");
      if (!paths.length) return;
      const infos = await Promise.all(paths.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: paths[i] }));
      autoHint = "";
   }

   function removeFile(path) {
      fileInfos = fileInfos.filter((f) => f.path !== path);
   }

   // ── Selección local / remoto ─────────────────────────────────────────────────

   function selectLocal() {
      mode = "local";
   }

   async function selectRemote() {
      checkingRemote = true;
      remoteError = "";
      const result = await bridge.check_remote_server();
      checkingRemote = false;

      if (!result.found) {
         remoteError = "No se encontró el server mediador en la red. ¿Está prendido?";
         return;
      }
      if (result.state === "busy" || result.state === "loading") {
         remoteError = `El mediador está ocupado en este momento (modelo: ${
            result.busy_model ?? "desconocido"
         }). Probá de nuevo en un rato.`;
         return;
      }

      remoteInfo = result;
      // Si el modelo que tenías elegido no está disponible en este
      // mediador en particular, caemos al primero que sí lo esté.
      if (result.models.length && !result.models.includes(modelSize)) {
         modelSize = result.models[0];
      }
      mode = "remote";
   }

   function changeMode() {
      mode = null;
      remoteError = "";
   }

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      progress.reset();
      processing = true;
      progress.running = true;

      await bridge.run_transcribe(
         fileInfos.map((f) => f.path),
         appConfig.baseFolder,
         modelSize,
         device,
         computeType,
         outputSubfolder,
         beamSize,
         language,
         vadFilter,
         conditionOnPrev,
         wordTimestamps,
         initialPrompt,
         outputFormat,
         mode === "remote" ? remoteInfo.host : null,
         mode === "remote" ? remoteInfo.port : null,
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

{#if mode === null}
   <div class="flex h-full flex-col">
      <ViewHeader title="Transcribe" {goHome} />

      <main class="flex flex-1 items-center justify-center px-8">
         <div class="flex w-full max-w-2xl items-stretch gap-6">
            <!-- Remoto -->
            <div class="flex flex-1 flex-col gap-2">
               <button
                  class="group flex flex-1 flex-col items-center justify-center gap-3
                     rounded-2xl border border-white/10 bg-white/5 p-8 text-center
                     transition-all duration-200 hover:border-white/20 hover:bg-white/10
                     hover:scale-[1.02] active:scale-[0.98] cursor-pointer
                     disabled:cursor-wait disabled:opacity-60 disabled:hover:scale-100"
                  onclick={selectRemote}
                  disabled={checkingRemote}
               >
                  {#if checkingRemote}
                     <Spinner size={28} />
                     <span class="text-xs text-white/40">Buscando mediador en la red...</span>
                  {:else}
                     <span class="text-3xl">🌐</span>
                     <span class="text-sm font-semibold text-white tracking-wide">
                        Transcribir en remoto
                     </span>
                     <span class="text-xs text-white/50 leading-relaxed">
                        Usa el server mediador de la red para transcribir sin cargar
                        el modelo en esta PC.
                     </span>
                  {/if}
               </button>
               {#if remoteError}
                  <span class="text-xs text-yellow-400 text-center">{remoteError}</span>
               {/if}
            </div>

            <!-- Separador vertical -->
            <div class="w-px self-stretch bg-white/10"></div>

            <!-- Local -->
            <button
               class="group flex flex-1 flex-col items-center justify-center gap-3
                  rounded-2xl border border-white/10 bg-white/5 p-8 text-center
                  transition-all duration-200 hover:border-white/20 hover:bg-white/10
                  hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
               onclick={selectLocal}
            >
               <span class="text-3xl">💻</span>
               <span class="text-sm font-semibold text-white tracking-wide">
                  Transcribir en esta PC
               </span>
               <span class="text-xs text-white/50 leading-relaxed">
                  Carga el modelo localmente, como siempre.
               </span>
            </button>
         </div>
      </main>
   </div>
{:else if processing}
   <ProcessingView
      title="Transcribe"
      {goHome}
      {fileInfos}
      {outputPath}
      showOpenFile={false}
      onCancel={cancel}
      onBack={goBack}
   />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={mode === "remote" ? "Transcribe (remoto)" : "Transcribe"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <button
               class="self-start text-xs text-white/30 hover:text-white transition-colors"
               onclick={changeMode}
            >
               ← Cambiar modo (local/remoto)
            </button>

            <!-- Carpeta base con botón abrir -->
            <BaseFolderPicker onPick={loadAudios} />

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

            <!-- Idioma -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Idioma</span>
                  <HoverCard
                     text="Especificar el idioma mejora la precisión y velocidad. Auto-detectar analiza los primeros segundos del audio para determinarlo."
                  />
               </div>
               <div class="flex flex-wrap gap-1.5">
                  {#each LANGUAGES as lang (lang.code)}
                     <button
                        class="rounded-md px-3 py-1.5 text-xs transition-colors
                       {language === lang.code
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => (language = lang.code)}
                     >
                        {lang.label}
                     </button>
                  {/each}
               </div>
            </div>

            <!-- Modelo -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Modelo</span>
                  <HoverCard
                     text="Modelos más grandes son más precisos pero más lentos y consumen más memoria. 'medium' es un buen balance para la mayoría de casos."
                  />
               </div>
               <div class="flex flex-wrap gap-1.5">
                  {#each modelSizesToShow as size (size)}
                     <button
                        class="rounded-md px-3 py-1.5 text-xs transition-colors
                       {modelSize === size
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => (modelSize = size)}
                     >
                        {size}
                     </button>
                  {/each}
               </div>
               {#if mode === "remote" && modelSizesToShow.length === 0}
                  <span class="text-xs text-yellow-400">
                     Este mediador no tiene ningún modelo copiado en whisper_models/ todavía.
                  </span>
               {/if}
            </div>

            <!-- Device -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Device</span>
                  <HoverCard
                     text="CUDA usa la GPU NVIDIA para acelerar la transcripción. CPU es más lento pero funciona en cualquier máquina."
                  />
               </div>
               <div class="flex gap-2">
                  {#each DEVICES as d (d)}
                     <button
                        class="flex-1 rounded-md py-1.5 text-xs transition-colors
                       {device === d
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => (device = d)}
                     >
                        {d.toUpperCase()}
                     </button>
                  {/each}
               </div>
            </div>

            <!-- Compute type -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Compute type</span>
                  <HoverCard
                     text="Controla la precisión numérica del modelo. int8 es más rápido y usa menos memoria. float16 es más preciso. int8_float16 es un balance entre ambos."
                  />
               </div>
               <div class="flex flex-wrap gap-1.5">
                  {#each COMPUTE_BY_DEVICE[device] as ct (ct)}
                     <button
                        class="rounded-md px-3 py-1.5 text-xs transition-colors
                       {computeType === ct
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => (computeType = ct)}
                     >
                        {ct}
                     </button>
                  {/each}
               </div>
            </div>

            <!-- Beam size -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <label class="text-xs text-white/40" for="beam-size">Beam size</label>
                  <HoverCard
                     text="Número de hipótesis que el modelo evalúa en paralelo. Valores más altos dan mejor resultado pero son más lentos. 5 es el valor estándar."
                  />
               </div>
               <input
                  id="beam-size"
                  type="number"
                  bind:value={beamSize}
                  min="1"
                  max="10"
                  class="w-20 rounded-lg border border-white/10 bg-white/5 px-3 py-2
                   text-sm text-white outline-none focus:border-indigo-500/50
                   transition-colors text-center"
               />
            </div>

            <!-- VAD filter -->
            <div class="flex items-center justify-between">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">VAD filter</span>
                  <HoverCard
                     text="Detecta y omite los silencios del audio antes de transcribir. Mejora la precisión y velocidad, especialmente en audios con pausas largas como el ASMR."
                  />
               </div>
               <button
                  class="relative h-5 w-9 rounded-full transition-colors
                   {vadFilter ? 'bg-indigo-600' : 'bg-white/10'}"
                  onclick={() => (vadFilter = !vadFilter)}
               >
                  <span
                     class="absolute top-0.5 h-4 w-4 rounded-full bg-white shadow
                     transition-transform
                     {vadFilter ? 'translate-x-4' : 'translate-x-0.5'}"
                  ></span>
               </button>
            </div>

            <!-- Condition on previous text -->
            <div class="flex items-center justify-between">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Condition on previous text</span>
                  <HoverCard
                     text="Usa el texto transcrito anteriormente como contexto para el siguiente segmento. Puede mejorar la coherencia pero también causar alucinaciones en audios largos."
                  />
               </div>
               <button
                  class="relative h-5 w-9 rounded-full transition-colors
                   {conditionOnPrev ? 'bg-indigo-600' : 'bg-white/10'}"
                  onclick={() => (conditionOnPrev = !conditionOnPrev)}
               >
                  <span
                     class="absolute top-0.5 h-4 w-4 rounded-full bg-white shadow
                     transition-transform
                     {conditionOnPrev ? 'translate-x-4' : 'translate-x-0.5'}"
                  ></span>
               </button>
            </div>

            <!-- Word timestamps -->
            <div class="flex items-center justify-between">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Word timestamps</span>
                  <HoverCard
                     text="Calcula timestamps más precisos a nivel de palabra. El SRT mantiene el formato por segmento pero con mayor precisión en los tiempos de inicio y fin."
                  />
               </div>
               <button
                  class="relative h-5 w-9 rounded-full transition-colors
                   {wordTimestamps ? 'bg-indigo-600' : 'bg-white/10'}"
                  onclick={() => (wordTimestamps = !wordTimestamps)}
               >
                  <span
                     class="absolute top-0.5 h-4 w-4 rounded-full bg-white shadow
                     transition-transform
                     {wordTimestamps ? 'translate-x-4' : 'translate-x-0.5'}"
                  ></span>
               </button>
            </div>

            <!-- Formato de salida -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Formato de salida</span>
                  <HoverCard
                     text="SRT es el formato estándar para subtítulos. VTT es similar pero compatible con HTML5. TXT exporta solo el texto sin timestamps."
                  />
               </div>
               <div class="flex gap-2">
                  {#each OUTPUT_FORMATS as fmt (fmt)}
                     <button
                        class="rounded-md px-4 py-1.5 text-xs transition-colors
                       {outputFormat === fmt
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => (outputFormat = fmt)}
                     >
                        .{fmt}
                     </button>
                  {/each}
               </div>
            </div>

            <!-- Initial prompt -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <label class="text-xs text-white/40" for="prompt">Initial prompt</label>
                  <HoverCard
                     text="Texto inicial que guía el estilo de transcripción. Puede influir en el idioma, puntuación y formato. El valor por defecto se configura en config.py."
                     position="top"
                  />
               </div>
               <textarea
                  id="prompt"
                  bind:value={initialPrompt}
                  rows="2"
                  placeholder="Sin prompt..."
                  class="rounded-lg border border-white/10 bg-white/5 px-3 py-2
                   text-xs text-white placeholder-white/20 outline-none
                   focus:border-indigo-500/50 transition-colors resize-none"
               ></textarea>
            </div>

            <!-- Subcarpeta de salida -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <label class="text-xs text-white/40" for="subfolder">Subcarpeta de salida</label>
                  <HoverCard
                     text="Los archivos se guardan en ./transcriptions/[idioma]/. Puedes editarlo manualmente si necesitas una subcarpeta distinta."
                  />
               </div>
               <input
                  id="subfolder"
                  type="text"
                  bind:value={outputSubfolder}
                  placeholder="default"
                  class="rounded-lg border border-white/10 bg-white/5 px-3 py-2
                   text-sm text-white placeholder-white/20 outline-none
                   focus:border-indigo-500/50 transition-colors"
               />
               {#if appConfig.baseFolder}
                  <span class="text-xs text-white/20">
                     → transcriptions/{outputSubfolder}/
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
               Ejecutar transcripción
            </button>
         </div>
      </main>
   </div>
{/if}
