<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { appConfig } from "@shared/state/config.svelte.js";
   import { useToolRun } from "@shared/state/useToolRun.svelte.js";
   import { persisted } from "@shared/state/persisted.svelte.js";
   import { usePlan } from "@shared/state/usePlan.svelte.js";
   import { useFileSelection } from "@shared/state/useFileSelection.svelte.js";
   import { useExecutionTarget } from "@shared/state/useExecutionTarget.svelte.js";

   import ProcessingView from "@shared/components/ProcessingView.svelte";
   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import ExecutionModeGate from "@shared/components/ExecutionModeGate.svelte";
   import FileList from "@shared/components/FileList.svelte";
   import Modal from "@shared/ui/Modal.svelte";
   import Field from "@shared/ui/Field.svelte";
   import SegmentedControl from "@shared/ui/SegmentedControl.svelte";
   import SwitchField from "@shared/ui/SwitchField.svelte";
   import BaseFolderPicker from "@shared/components/BaseFolderPicker.svelte";

   let { goHome } = $props();

   const job = useToolRun("run_transcribe");

   // ── Dónde se ejecuta: esta PC o el mediador de la red ────────────────────────
   const target = useExecutionTarget({ check: () => bridge.check_remote_server() });

   // ── Preferencias que se recuerdan entre sesiones ─────────────────────────────
   // `null` = "el valor por defecto del backend" (core/transcription/options.py): solo se guarda lo
   // que el USUARIO elige, así que un valor recordado nunca queda atrapado por haber sido el
   // defecto de otra época (p. ej. el prompt de config.py). Lo guardado que ya no sirva se
   // resuelve más abajo sin tocar lo guardado.
   // `outputSubfolder: ""` = "la carpeta del idioma".
   const cfg = persisted("transcribe_config", {
      modelSize: null,
      device: null,
      computeType: null,
      beamSize: null,
      language: null,
      vadFilter: null,
      conditionOnPrev: null,
      wordTimestamps: null,
      initialPrompt: null,
      outputFormat: null,
      outputSubfolder: "",
   });

   // Lo que el backend sabe hacer (modelos, dispositivos, idiomas...) y sus valores por defecto.
   const caps = $derived(appConfig.transcription);
   const defaults = $derived(caps.defaults);

   // Nombres de carpeta que versiones anteriores guardaban como "la del idioma".
   const LEGACY_DEFAULT_FOLDERS = ["default", "ja", "zh", "auto", "korean", "spanish", "english", "japanese", "chinese"];

   // ── Valores efectivos ────────────────────────────────────────────────────────

   const isBool = (value, fallback) => (typeof value === "boolean" ? value : fallback);

   const device = $derived(caps.devices.includes(cfg.device) ? cfg.device : defaults.device);
   const computeOptions = $derived(caps.compute_types[device] ?? []);
   // El compute type guardado vale solo para los dispositivos que lo admiten: al pasar a CPU se
   // usa uno de CPU, y al volver a CUDA reaparece el que había.
   const computeType = $derived(
      computeOptions.includes(cfg.computeType)
         ? cfg.computeType
         : computeOptions.includes(defaults.compute_type)
           ? defaults.compute_type
           : (computeOptions[0] ?? ""),
   );
   const beamSize = $derived(caps.beam_sizes.includes(cfg.beamSize) ? cfg.beamSize : defaults.beam_size);
   const outputFormat = $derived(caps.output_formats.includes(cfg.outputFormat) ? cfg.outputFormat : defaults.output_format);
   const vadFilter = $derived(isBool(cfg.vadFilter, defaults.vad_filter));
   const conditionOnPrev = $derived(isBool(cfg.conditionOnPrev, defaults.condition_on_previous_text));
   const wordTimestamps = $derived(isBool(cfg.wordTimestamps, defaults.word_timestamps));
   const initialPrompt = $derived(typeof cfg.initialPrompt === "string" ? cfg.initialPrompt : (defaults.initial_prompt ?? ""));

   // Idioma: el guardado puede ser el código (ja) o, en versiones viejas, el nombre (chinese).
   const language = $derived(
      (
         caps.languages.find((l) => l.code === cfg.language) ??
         caps.languages.find((l) => l.label === cfg.language) ??
         caps.languages.find((l) => l.code === defaults.language)
      )?.code ?? "",
   );
   const languageLabel = $derived(caps.languages.find((l) => l.code === language)?.label ?? "");

   // Subcarpeta que escribió el usuario ("" = la del idioma).
   const subfolderInput = $derived(LEGACY_DEFAULT_FOLDERS.includes(cfg.outputSubfolder) ? "" : cfg.outputSubfolder);

   // Modelo: con un mediador remoto, el de su lista (sin tocar lo guardado para el uso local).
   const modelOptions = $derived(target.mode === "remote" && target.remote ? target.remote.models : caps.model_sizes);
   const modelSize = $derived(
      target.mode === "remote"
         ? modelOptions.includes(cfg.modelSize)
            ? cfg.modelSize
            : (modelOptions[0] ?? "")
         : caps.model_sizes.includes(cfg.modelSize)
           ? cfg.modelSize
           : defaults.model_size,
   );

   function changeLanguage(code) {
      cfg.language = code;
      cfg.outputSubfolder = ""; // al cambiar el idioma, la carpeta vuelve a ser la suya
   }

   // ── Archivos ─────────────────────────────────────────────────────────────────

   let showAdditionalOptions = $state(false);

   // Los audios con los que se va a trabajar: se detectan en la carpeta base (./audios/parts o
   // ./audios) o se eligen a mano.
   const selection = useFileSelection({
      scan: (folder) => bridge.scan_audio_parts_or_audios(folder),
      pick: () =>
         bridge.pick_files(
            (appConfig.mediaExtensions.audio ?? []).map((ext) => "*" + ext),
            appConfig.baseFolder,
            "audio",
         ),
      emptyHint: "No se encontraron audios",
      formatDetected: (n, result) => `✓ ${n} archivo(s) detectados desde ${result.source}`,
   });

   const fileInfos = $derived(selection.files);

   // ── Plan ─────────────────────────────────────────────────────────────────────

   // Opciones con las que se pide el plan, o null si todavía no hay con qué planificar. El backend
   // decide dónde queda cada transcripción, detecta nombres repetidos, valida la subcarpeta y avisa
   // de las salidas que ya existen. No incluye el prompt: no cambia el plan y se escribe por teclas.
   const planOptions = $derived.by(() => {
      if (!target.target || !fileInfos.length || !appConfig.baseFolder || !caps.model_sizes.length) return null;
      if (target.mode === "remote" && !modelSize) return null;
      return {
         file_paths: fileInfos.map((f) => f.path),
         base_folder: appConfig.baseFolder,
         model_size: modelSize,
         device,
         compute_type: computeType,
         beam_size: beamSize,
         language,
         vad_filter: vadFilter,
         condition_on_previous_text: conditionOnPrev,
         word_timestamps: wordTimestamps,
         output_format: outputFormat,
         output_subfolder: subfolderInput.trim() || null,
         target: target.target,
         durations: fileInfos.map((f) => (f.duration_seconds > 0 ? f.duration_seconds : null)),
      };
   });

   // plan = { output_dir, files: [{ index, name, path, duration, output, output_name, exists }], total_duration } | null
   const planState = usePlan(() => planOptions, (options) => bridge.plan_transcribe(options));
   const plan = $derived(planState.value);
   const planError = $derived(planState.error);
   const planPending = $derived(planState.pending);

   const overwrites = $derived((plan?.files ?? []).filter((f) => f.exists).map((f) => f.output_name));

   // Filas de ProcessingView.
   const processingFiles = $derived.by(() => {
      const sizeByPath = new Map(fileInfos.map((f) => [f.path, f.size_mb]));
      return (plan?.files ?? []).map((f) => ({
         name: f.name,
         size_mb: sizeByPath.get(f.path) ?? 0,
         duration_seconds: f.duration,
         path: f.path,
      }));
   });

   // No se ejecuta con una consulta de plan en vuelo: el plan que se ve podría no ser el último.
   const canRun = $derived(!!plan && !planPending && !progress.running);

   // ── Derivados de presentación ────────────────────────────────────────────────

   const outputHint = $derived(`transcriptions/${subfolderInput.trim() || languageLabel}/`);

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      await job.start({ ...planOptions, initial_prompt: initialPrompt });
   }
</script>

{#if target.mode === null}
   <ExecutionModeGate
      title="Transcribe"
      {goHome}
      {target}
      remoteTitle="Transcribir en remoto"
      remoteDescription="Usa el server mediador de la red para transcribir sin cargar el modelo en esta PC."
      localTitle="Transcribir en esta PC"
      localDescription="Carga el modelo localmente, como siempre."
   />
{:else if job.processing}
   <ProcessingView
      title="Transcribe"
      {goHome}
      fileInfos={processingFiles}
      outputPath={plan?.output_dir ?? ""}
      showOpenFile={false}
      enableFileLogs={true}
      onCancel={job.cancel}
      onBack={job.back}
   />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={target.mode === "remote" ? "Transcribe (remoto)" : "Transcribe"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-lg flex-col gap-5">
            <button
               class="self-start text-xs text-white/30 hover:text-white transition-colors cursor-pointer"
               onclick={target.change}
            >
               ← Cambiar modo (local/remoto)
            </button>

            <!-- Carpeta base con botón abrir -->
            <BaseFolderPicker onPick={selection.loadFromFolder} />

            <!-- Archivos -->
            <FileList
               fileInfos={selection.files}
               autoHint={selection.hint}
               loading={selection.loading}
               height="fixed"
               onPickFiles={selection.pickFiles}
               onRemove={selection.remove}
               emptyText={appConfig.baseFolder ? "No se encontraron audios" : "Selecciona una carpeta base primero"}
            />

            <!-- Fila 1: dispositivo -->
            <Field
               label="Device"
               help="CUDA usa la GPU NVIDIA para acelerar la transcripción. CPU es más lento pero funciona en cualquier máquina."
            >
               <SegmentedControl
                  label="Device"
                  fill
                  size="sm"
                  value={device}
                  options={caps.devices.map((d) => ({ value: d, label: d.toUpperCase() }))}
                  onchange={(d) => (cfg.device = d)}
               />
            </Field>

            <!-- Fila 2: modelo, idioma y compute type -->
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
               <Field
                  label="Modelo"
                  for="transcribe-model"
                  class="min-w-0"
                  help="Modelos más grandes suelen ser más precisos, pero consumen más memoria y tardan más."
               >
                  <select
                     id="transcribe-model"
                     value={modelSize}
                     onchange={(event) => (cfg.modelSize = event.currentTarget.value)}
                     disabled={target.mode === "remote" && modelOptions.length === 0}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 disabled:opacity-40 cursor-pointer"
                  >
                     {#each modelOptions as size (size)}
                        <option value={size} class="bg-zinc-900 text-white">{size}</option>
                     {/each}
                  </select>
                  {#if target.mode === "remote" && modelOptions.length === 0}
                     <span class="text-xs text-yellow-400">No hay modelos disponibles en este mediador.</span>
                  {/if}
               </Field>

               <Field
                  label="Idioma"
                  for="transcribe-language"
                  class="min-w-0"
                  help="Selecciona el idioma del audio para mejorar la precisión y velocidad de la transcripción."
               >
                  <select
                     id="transcribe-language"
                     value={language}
                     onchange={(event) => changeLanguage(event.currentTarget.value)}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each caps.languages as lang (lang.code)}
                        <option value={lang.code} class="bg-zinc-900 text-white">{lang.label}</option>
                     {/each}
                  </select>
               </Field>

               <Field
                  label="Compute type"
                  for="transcribe-compute-type"
                  class="min-w-0"
                  help="Controla la precisión numérica y el uso de memoria del modelo."
               >
                  <select
                     id="transcribe-compute-type"
                     value={computeType}
                     onchange={(event) => (cfg.computeType = event.currentTarget.value)}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each computeOptions as ct (ct)}
                        <option value={ct} class="bg-zinc-900 text-white">{ct}</option>
                     {/each}
                  </select>
               </Field>
            </div>

            <!-- Fila 3: beam size, formato y subcarpeta -->
            <div class="grid grid-cols-1 gap-4 border-t border-white/5 pt-4 sm:grid-cols-3">
               <Field
                  label="Beam size"
                  for="beam-size"
                  class="min-w-0"
                  help="Número de hipótesis que el modelo evalúa en paralelo. Un valor más alto puede mejorar el resultado, pero es más lento."
               >
                  <select
                     id="beam-size"
                     value={beamSize}
                     onchange={(event) => (cfg.beamSize = Number(event.currentTarget.value))}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each caps.beam_sizes as n (n)}
                        <option value={n} class="bg-zinc-900 text-white">{n}</option>
                     {/each}
                  </select>
               </Field>

               <Field
                  label="Formato de salida"
                  for="transcribe-output-format"
                  class="min-w-0"
                  help="SRT es el formato estándar para subtítulos. VTT es compatible con HTML5 y TXT exporta solo el texto."
               >
                  <select
                     id="transcribe-output-format"
                     value={outputFormat}
                     onchange={(event) => (cfg.outputFormat = event.currentTarget.value)}
                     class="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-indigo-500/50 cursor-pointer"
                  >
                     {#each caps.output_formats as fmt (fmt)}
                        <option value={fmt} class="bg-zinc-900 text-white">.{fmt}</option>
                     {/each}
                  </select>
               </Field>

               <Field
                  label="Subcarpeta de salida"
                  for="subfolder"
                  class="min-w-0"
                  help="Los archivos se guardan en ./transcriptions/[subcarpeta]. Al cambiar el idioma, esta se actualiza al nombre correspondiente; también puedes editarla manualmente."
               >
                  <input
                     id="subfolder"
                     type="text"
                     value={subfolderInput}
                     oninput={(event) => (cfg.outputSubfolder = event.currentTarget.value)}
                     placeholder={languageLabel}
                     class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/20 outline-none transition-colors focus:border-indigo-500/50"
                  />
                  {#if appConfig.baseFolder}
                     <span class="truncate text-xs text-white/20">→ {outputHint}</span>
                  {/if}
               </Field>
            </div>

            <!-- Opciones adicionales (estilo link sutil) -->
            <button
               type="button"
               class="self-start text-xs text-white/40 hover:text-white/70 transition-colors cursor-pointer"
               onclick={() => (showAdditionalOptions = true)}
            >
               Opciones adicionales
            </button>

            <!-- Estado del plan -->
            {#if overwrites.length}
               <span class="text-xs text-yellow-400 break-words">
                  Ya existen y se sobrescribirán: {overwrites.slice(0, 3).join(", ")}{overwrites.length > 3
                     ? ` y ${overwrites.length - 3} más`
                     : ""}
               </span>
            {/if}
            {#if planError}
               <span role="alert" class="text-xs text-red-400 break-words">{planError}</span>
            {/if}

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
      <Modal
         onClose={() => (showAdditionalOptions = false)}
         size="xl"
         height="max-85"
         labelledby="additional-options-title"
         class="gap-4 overflow-y-auto"
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

         <SwitchField
            checked={vadFilter}
            onchange={(value) => (cfg.vadFilter = value)}
            label="VAD filter"
            help="Detecta y omite los silencios del audio antes de transcribir. Puede ayudar especialmente en audios con pausas largas."
         />

         <SwitchField
            checked={conditionOnPrev}
            onchange={(value) => (cfg.conditionOnPrev = value)}
            label="Condition on previous text"
            help="Usa el texto transcrito anteriormente como contexto para el siguiente segmento. Puede mejorar la coherencia, pero también causar alucinaciones en audios largos."
         />

         <SwitchField
            checked={wordTimestamps}
            onchange={(value) => (cfg.wordTimestamps = value)}
            label="Word timestamps"
            help="Calcula timestamps más precisos a nivel de palabra."
         />

         <Field
            label="Initial prompt"
            for="transcribe-initial-prompt"
            help="Texto inicial que guía el estilo de transcripción. Puede influir en el idioma, la puntuación y el formato. El valor predeterminado se configura en config.py."
         >
            <textarea
               id="transcribe-initial-prompt"
               value={initialPrompt}
               oninput={(event) => (cfg.initialPrompt = event.currentTarget.value)}
               rows="4"
               placeholder="Sin prompt..."
               class="resize-y rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white placeholder-white/20 outline-none transition-colors focus:border-indigo-500/50"
            ></textarea>
         </Field>

         <footer class="flex justify-end border-t border-white/5 pt-3">
            <button
               type="button"
               class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 cursor-pointer"
               onclick={() => (showAdditionalOptions = false)}
            >
               Listo
            </button>
         </footer>
      </Modal>
   {/if}
{/if}
