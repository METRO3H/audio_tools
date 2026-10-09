<script>
   import { onDestroy } from "svelte";
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";

   import ProcessingView from "$lib/views/shared/ProcessingView.svelte";
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
   import HoverCard from "$lib/components/HoverCard.svelte";
   import BaseFolderPicker from "$lib/components/BaseFolderPicker.svelte";
   import Spinner from "$lib/components/Spinner.svelte";
   import { persistentConfig } from "$lib/stores/persistentConfig.js";

   let { goHome } = $props();

   // ── Selección local / remoto ─────────────────────────────────────────────────
   let mode = $state(null);
   let checkingRemote = $state(false);
   let remoteError = $state("");
   let remoteInfo = $state(null);

   // ── Constantes ───────────────────────────────────────────────────────────────

   const MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"];
   const DEVICES = ["cuda", "cpu"];
   const COMPUTE_BY_DEVICE = {
      cuda: ["float16", "int8_float16", "int8"],
      cpu: ["float32", "int8"],
   };
   const LANGUAGES = [
      { code: "ja", label: "japanese" },
      { code: "zh", label: "chinese" },
   ];

   const LANGUAGE_FOLDERS = {
      ja: "japanese",
      zh: "chinese",
   };

   const OUTPUT_FORMATS = ["srt", "vtt", "txt"];
   const AUDIO_EXTS = ["*.mp3", "*.wav", "*.m4a", "*.aac", "*.ogg", "*.flac", "*.opus"];
   const BEAM_SIZES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

   // ── Estado ───────────────────────────────────────────────────────────────────

   let processing = $state(false);
   let fileInfos = $state([]);
   let fileLogsByIndex = $state({});
   let autoHint = $state("");

   function onTranscribeFileLog(event) {
      const { file_index, message } = event.detail ?? {};
      if (!Number.isInteger(file_index) || file_index < 0) return;

      fileLogsByIndex = {
         ...fileLogsByIndex,
         [file_index]: [...(fileLogsByIndex[file_index] ?? []), String(message ?? "")],
      };
   }

   if (typeof window !== "undefined") {
      window.addEventListener("audiotools:transcribe:file_log", onTranscribeFileLog);
   }

   onDestroy(() => {
      if (typeof window !== "undefined") {
         window.removeEventListener("audiotools:transcribe:file_log", onTranscribeFileLog);
      }
   });

   // Parámetros del modelo
   let modelSize = $state("large-v3");
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
   let outputSubfolder = $state("japanese");
   let showAdditionalOptions = $state(false);
   let loadingFiles = $state(false);

   // Bandera para evitar que el efecto de guardado pise la config persistida
   // con los valores default antes de que el efecto de carga termine.
   let configLoaded = $state(false);

   // ── Cargar configuración guardada ────────────────────────────────────────────

   $effect(() => {
      const saved = persistentConfig.get("transcribe_config");
      if (saved) {
         const savedLanguage = ["ja", "zh"].includes(saved.language)
            ? saved.language
            : saved.language === "chinese"
              ? "zh"
              : "ja";

         modelSize = saved.modelSize ?? "large-v3";
         device = saved.device ?? "cuda";
         computeType = saved.computeType ?? "int8_float16";
         beamSize = saved.beamSize ?? 5;
         language = savedLanguage;
         vadFilter = saved.vadFilter ?? true;
         conditionOnPrev = saved.conditionOnPrev ?? false;
         wordTimestamps = saved.wordTimestamps ?? true;
         initialPrompt = saved.initialPrompt ?? "";
         outputFormat = saved.outputFormat ?? "srt";

         const savedSubfolder = saved.outputSubfolder;
         outputSubfolder =
            !savedSubfolder ||
            ["default", "ja", "zh", "auto", "korean", "spanish", "english", "japanese", "chinese"].includes(
               savedSubfolder,
            )
               ? LANGUAGE_FOLDERS[savedLanguage]
               : savedSubfolder;

         if (!COMPUTE_BY_DEVICE[device]?.includes(computeType)) {
            computeType = COMPUTE_BY_DEVICE[device]?.[0] ?? "int8_float16";
         }
      }

      // Inicializar desde config.py si no hay guardado.
      if (!saved && appConfig.loaded) {
         initialPrompt = appConfig.transcribeInitialPrompt ?? "";
      }

      configLoaded = true;
   });

   function changeLanguage(code) {
      language = code;
      outputSubfolder = LANGUAGE_FOLDERS[code];
   }

   function changeDevice(nextDevice) {
      device = nextDevice;
      if (!COMPUTE_BY_DEVICE[nextDevice].includes(computeType)) {
         computeType = COMPUTE_BY_DEVICE[nextDevice][0];
      }
   }

   // ── Guardar configuración al cambiar ────────────────────────────────────────
   // Solo guarda una vez que el efecto de carga ya corrió, para no pisar la
   // config persistida con los valores default en el primer mount.

   $effect(() => {
      if (!configLoaded) return;
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

   const modelSizesToShow = $derived(mode === "remote" && remoteInfo ? remoteInfo.models : MODEL_SIZES);

   // ── Carga ────────────────────────────────────────────────────────────────────

   async function loadAudios(folder) {
      loadingFiles = true;
      try {
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
      } finally {
         loadingFiles = false;
      }
   }

   async function pickFiles() {
      loadingFiles = true;
      try {
         const paths = await bridge.pick_files(AUDIO_EXTS, appConfig.baseFolder, "audio");
         if (!paths.length) return;
         const infos = await Promise.all(paths.map((p) => bridge.get_file_info(p)));
         fileInfos = infos.map((info, i) => ({ ...info, path: paths[i] }));
         autoHint = "";
      } finally {
         loadingFiles = false;
      }
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
      fileLogsByIndex = {};
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
                     <span class="text-sm font-semibold text-white tracking-wide"> Transcribir en remoto </span>
                     <span class="text-xs text-white/50 leading-relaxed">
                        Usa el server mediador de la red para transcribir sin cargar el modelo en esta PC.
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
               <span class="text-sm font-semibold text-white tracking-wide"> Transcribir en esta PC </span>
               <span class="text-xs text-white/50 leading-relaxed"> Carga el modelo localmente, como siempre. </span>
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
      enableFileLogs={true}
      {fileLogsByIndex}
      onCancel={cancel}
      onBack={goBack}
   />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={mode === "remote" ? "Transcribe (remoto)" : "Transcribe"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-lg flex-col gap-5">
            <button
               class="self-start text-xs text-white/30 hover:text-white transition-colors cursor-pointer"
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
                  <button
                     class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer"
                     onclick={pickFiles}
                  >
                     Seleccionar manualmente
                  </button>
               </div>

               {#if autoHint}
                  <span class="text-xs {autoHint.startsWith('⚠') ? 'text-yellow-400' : 'text-emerald-400'}">
                     {autoHint}
                  </span>
               {/if}

               <!-- Contenedor con altura reservada (≈5 filas) para evitar layout shift -->
               <div
                  class="h-44 overflow-y-auto rounded-lg border border-white/5 bg-black/10 p-1.5"
                  style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
               >
                  {#if loadingFiles}
                     <div class="flex h-full items-center justify-center gap-2 text-xs text-white/40">
                        <Spinner size={16} duration="1.25s" />
                        <span>Cargando archivos...</span>
                     </div>
                  {:else if fileInfos.length}
                     <ul class="flex flex-col gap-1">
                        {#each fileInfos as file (file.path)}
                           <li
                              class="flex items-center justify-between rounded-lg
                              bg-white/5 px-3 py-1.5 text-xs text-white/60 shrink-0"
                           >
                              <span class="truncate">{file.name}</span>
                              <div class="flex shrink-0 items-center gap-2 ml-2">
                                 <span class="text-white/30">{file.size_mb} MB</span>
                                 <button
                                    class="text-white/20 hover:text-red-400 transition-colors cursor-pointer"
                                    onclick={() => removeFile(file.path)}>✕</button
                                 >
                              </div>
                           </li>
                        {/each}
                     </ul>
                  {:else}
                     <div class="flex h-full items-center justify-center px-4 text-center text-xs text-white/20">
                        {appConfig.baseFolder ? "No se encontraron audios" : "Selecciona una carpeta base primero"}
                     </div>
                  {/if}
               </div>
            </div>
            <!-- Fila 1: dispositivo -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <span class="text-xs text-white/40">Device</span>
                  <HoverCard
                     text="CUDA usa la GPU NVIDIA para acelerar la transcripción. CPU es más lento pero funciona en cualquier máquina."
                  />
               </div>
               <div class="flex w-full gap-1.5">
                  {#each DEVICES as d (d)}
                     <button
                        type="button"
                        class="flex-1 rounded-md px-3 py-2 text-xs transition-colors cursor-pointer
            {device === d
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => changeDevice(d)}
                     >
                        {d.toUpperCase()}
                     </button>
                  {/each}
               </div>
            </div>

            <!-- Fila 2: modelo, idioma y compute type -->
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
               <!-- Modelo (ahora a la izquierda) -->
               <div class="flex min-w-0 flex-col gap-1.5">
                  <div class="flex items-center gap-1.5">
                     <label class="text-xs text-white/40" for="transcribe-model">Modelo</label>
                     <HoverCard
                        text="Modelos más grandes suelen ser más precisos, pero consumen más memoria y tardan más."
                     />
                  </div>
                  <select
                     id="transcribe-model"
                     bind:value={modelSize}
                     disabled={mode === "remote" && modelSizesToShow.length === 0}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 disabled:opacity-40 cursor-pointer"
                  >
                     {#each modelSizesToShow as size (size)}
                        <option value={size} class="bg-zinc-900 text-white">{size}</option>
                     {/each}
                  </select>
                  {#if mode === "remote" && modelSizesToShow.length === 0}
                     <span class="text-xs text-yellow-400">No hay modelos disponibles en este mediador.</span>
                  {/if}
               </div>

               <!-- Idioma -->
               <div class="flex min-w-0 flex-col gap-1.5">
                  <div class="flex items-center gap-1.5">
                     <label class="text-xs text-white/40" for="transcribe-language">Idioma</label>
                     <HoverCard
                        text="Selecciona el idioma del audio para mejorar la precisión y velocidad de la transcripción."
                     />
                  </div>
                  <select
                     id="transcribe-language"
                     value={language}
                     onchange={(event) => changeLanguage(event.currentTarget.value)}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each LANGUAGES as lang (lang.code)}
                        <option value={lang.code} class="bg-zinc-900 text-white">{lang.label}</option>
                     {/each}
                  </select>
               </div>

               <!-- Compute type -->
               <div class="flex min-w-0 flex-col gap-1.5">
                  <div class="flex items-center gap-1.5">
                     <label class="text-xs text-white/40" for="transcribe-compute-type">Compute type</label>
                     <HoverCard text="Controla la precisión numérica y el uso de memoria del modelo." />
                  </div>
                  <select
                     id="transcribe-compute-type"
                     bind:value={computeType}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each COMPUTE_BY_DEVICE[device] as ct (ct)}
                        <option value={ct} class="bg-zinc-900 text-white">{ct}</option>
                     {/each}
                  </select>
               </div>
            </div>

            <!-- Fila 2: beam size, formato y subcarpeta -->
            <div class="grid grid-cols-1 gap-4 border-t border-white/5 pt-4 sm:grid-cols-3">
               <!-- Beam size (ahora dropdown) -->
               <div class="flex min-w-0 flex-col gap-1.5">
                  <div class="flex items-center gap-1.5">
                     <label class="text-xs text-white/40" for="beam-size">Beam size</label>
                     <HoverCard
                        text="Número de hipótesis que el modelo evalúa en paralelo. Un valor más alto puede mejorar el resultado, pero es más lento."
                     />
                  </div>
                  <select
                     id="beam-size"
                     bind:value={beamSize}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each BEAM_SIZES as n (n)}
                        <option value={n} class="bg-zinc-900 text-white">{n}</option>
                     {/each}
                  </select>
               </div>

               <!-- Formato de salida -->
               <div class="flex min-w-0 flex-col gap-1.5">
                  <div class="flex items-center gap-1.5">
                     <label class="text-xs text-white/40" for="transcribe-output-format">Formato de salida</label>
                     <HoverCard
                        text="SRT es el formato estándar para subtítulos. VTT es compatible con HTML5 y TXT exporta solo el texto."
                     />
                  </div>
                  <select
                     id="transcribe-output-format"
                     bind:value={outputFormat}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each OUTPUT_FORMATS as fmt (fmt)}
                        <option value={fmt} class="bg-zinc-900 text-white">.{fmt}</option>
                     {/each}
                  </select>
               </div>

               <!-- Subcarpeta de salida -->
               <div class="flex min-w-0 flex-col gap-1.5">
                  <div class="flex items-center gap-1.5">
                     <label class="text-xs text-white/40" for="subfolder">Subcarpeta de salida</label>
                     <HoverCard
                        text="Los archivos se guardan en ./transcriptions/[subcarpeta]. Al cambiar el idioma, esta se actualiza al nombre correspondiente; también puedes editarla manualmente."
                     />
                  </div>
                  <input
                     id="subfolder"
                     type="text"
                     bind:value={outputSubfolder}
                     placeholder={LANGUAGE_FOLDERS[language]}
                     class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/20 outline-none transition-colors focus:border-indigo-500/50"
                  />
                  {#if appConfig.baseFolder}
                     <span class="truncate text-xs text-white/20">→ transcriptions/{outputSubfolder}/</span>
                  {/if}
               </div>
            </div>

            <!-- Opciones adicionales (estilo link sutil) -->
            <button
               type="button"
               class="self-start text-xs text-white/40 hover:text-white/70 transition-colors cursor-pointer"
               onclick={() => (showAdditionalOptions = true)}
            >
               Opciones adicionales
            </button>

            <!-- Ejecutar -->
            <button
               class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium
                 text-white transition-colors hover:bg-indigo-500 cursor-pointer
                 disabled:opacity-30 disabled:cursor-not-allowed"
               onclick={run}
               disabled={!canRun}
            >
               Ejecutar transcripción
            </button>
         </div>
      </main>
   </div>

   {#if showAdditionalOptions}
      <button
         type="button"
         class="fixed inset-0 z-40 cursor-default bg-black/60 backdrop-blur-sm"
         aria-label="Cerrar opciones adicionales"
         onclick={() => (showAdditionalOptions = false)}
      ></button>

      <div class="fixed inset-0 z-50 flex items-center justify-center p-5">
         <section
            class="flex max-h-[85vh] w-full max-w-xl flex-col gap-4 overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-5 shadow-2xl"
            aria-labelledby="additional-options-title"
            role="dialog"
            aria-modal="true"
         >
            <header class="flex shrink-0 items-center justify-between gap-3">
               <div class="flex flex-col gap-1">
                  <h2 id="additional-options-title" class="text-sm font-semibold text-white">Opciones adicionales</h2>
                  <p class="text-xs text-white/35">Parámetros avanzados de la transcripción.</p>
               </div>
               <button
                  type="button"
                  class="rounded-md px-2 py-1 text-white/40 transition-colors hover:text-white cursor-pointer"
                  aria-label="Cerrar"
                  onclick={() => (showAdditionalOptions = false)}
               >
                  ✕
               </button>
            </header>

            <div class="flex items-center justify-between gap-4">
               <div class="flex min-w-0 flex-col gap-1">
                  <div class="flex items-center gap-1.5">
                     <span class="text-sm text-white/70">VAD filter</span>
                     <HoverCard
                        text="Detecta y omite los silencios del audio antes de transcribir. Puede ayudar especialmente en audios con pausas largas."
                     />
                  </div>
               </div>
               <button
                  type="button"
                  role="switch"
                  aria-checked={vadFilter}
                  aria-label="VAD filter"
                  class="inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full p-0.5 transition-colors {vadFilter
                     ? 'bg-indigo-600'
                     : 'bg-white/10'}"
                  onclick={() => (vadFilter = !vadFilter)}
               >
                  <span
                     class="h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 {vadFilter
                        ? 'translate-x-4'
                        : 'translate-x-0'}"
                  ></span>
               </button>
            </div>

            <div class="flex items-center justify-between gap-4">
               <div class="flex min-w-0 flex-col gap-1">
                  <div class="flex items-center gap-1.5">
                     <span class="text-sm text-white/70">Condition on previous text</span>
                     <HoverCard
                        text="Usa el texto transcrito anteriormente como contexto para el siguiente segmento. Puede mejorar la coherencia, pero también causar alucinaciones en audios largos."
                     />
                  </div>
               </div>
               <button
                  type="button"
                  role="switch"
                  aria-checked={conditionOnPrev}
                  aria-label="Condition on previous text"
                  class="inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full p-0.5 transition-colors {conditionOnPrev
                     ? 'bg-indigo-600'
                     : 'bg-white/10'}"
                  onclick={() => (conditionOnPrev = !conditionOnPrev)}
               >
                  <span
                     class="h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 {conditionOnPrev
                        ? 'translate-x-4'
                        : 'translate-x-0'}"
                  ></span>
               </button>
            </div>

            <div class="flex items-center justify-between gap-4">
               <div class="flex min-w-0 flex-col gap-1">
                  <div class="flex items-center gap-1.5">
                     <span class="text-sm text-white/70">Word timestamps</span>
                     <HoverCard text="Calcula timestamps más precisos a nivel de palabra." />
                  </div>
               </div>
               <button
                  type="button"
                  role="switch"
                  aria-checked={wordTimestamps}
                  aria-label="Word timestamps"
                  class="inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full p-0.5 transition-colors {wordTimestamps
                     ? 'bg-indigo-600'
                     : 'bg-white/10'}"
                  onclick={() => (wordTimestamps = !wordTimestamps)}
               >
                  <span
                     class="h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 {wordTimestamps
                        ? 'translate-x-4'
                        : 'translate-x-0'}"
                  ></span>
               </button>
            </div>

            <div class="flex flex-col gap-1.5">
               <div class="flex items-center gap-1.5">
                  <label class="text-xs text-white/50" for="transcribe-initial-prompt">Initial prompt</label>
                  <HoverCard
                     text="Texto inicial que guía el estilo de transcripción. Puede influir en el idioma, la puntuación y el formato. El valor predeterminado se configura en config.py."
                     position="top"
                  />
               </div>
               <textarea
                  id="transcribe-initial-prompt"
                  bind:value={initialPrompt}
                  rows="4"
                  placeholder="Sin prompt..."
                  class="resize-y rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white placeholder-white/20 outline-none transition-colors focus:border-indigo-500/50"
               ></textarea>
            </div>

            <footer class="flex justify-end border-t border-white/5 pt-3">
               <button
                  type="button"
                  class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 cursor-pointer"
                  onclick={() => (showAdditionalOptions = false)}
               >
                  Listo
               </button>
            </footer>
         </section>
      </div>
   {/if}
{/if}
