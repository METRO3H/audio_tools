<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { appConfig } from "@shared/state/config.svelte.js";
   import ProcessingView from "@shared/components/ProcessingView.svelte";
   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import { formatDuration } from "@shared/utils.js";
   import { useToolRun } from "@shared/state/useToolRun.svelte.js";
   import { persisted } from "@shared/state/persisted.svelte.js";
   import { usePlan } from "@shared/state/usePlan.svelte.js";
   import Field from "@shared/ui/Field.svelte";
   import SegmentedControl from "@shared/ui/SegmentedControl.svelte";
   import SwitchField from "@shared/ui/SwitchField.svelte";
   let { goHome } = $props();

   const MEDIA_TYPES = [
      { value: "audio", label: "🎵 Audio" },
      { value: "video", label: "🎬 Video" },
   ];

   const job = useToolRun("run_diverge");

   // ── Estado ───────────────────────────────────────────────────────────────────

   // Preferencias que se recuerdan entre sesiones. El modo de segmentación NO se guarda: lo decide
   // cada archivo (con capítulos → "chapters"; sin ellos → "interval").
   const cfg = persisted("diverge_config", { mediaType: "audio", intervalMins: 20, useSubfolder: true });

   let fileInfo = $state(null);
   let chapters = $state([]);
   let hasChapters = $state(false);
   let segmentMode = $state("chapters");
   let outputFolder = $state("");
   let autoHint = $state("");


   // ── Derivados ────────────────────────────────────────────────────────────────

   const intervalSeconds = $derived(cfg.intervalMins * 60);

   // Solo una etiqueta de la interfaz; las rutas reales las decide el backend (plan.output_dir).
   const outputSubfolder = $derived(cfg.mediaType === "video" ? "videos" : "audios");

   // Opciones que se le envían al backend, o null si todavía no hay con qué planificar.
   // El backend deduce la carpeta de salida, el formato y los nombres; los capítulos
   // los lee él mismo del archivo.
   const planOptions = $derived.by(() => {
      if (!fileInfo?.path || !appConfig.baseFolder) return null;
      if (segmentMode === "interval" && !(cfg.intervalMins > 0)) return null;
      if (!cfg.useSubfolder && !outputFolder) return null;
      return {
         file_path: fileInfo.path,
         base_folder: appConfig.baseFolder,
         segment_mode: segmentMode,
         interval_seconds: segmentMode === "interval" ? intervalSeconds : null,
         output_folder: cfg.useSubfolder ? null : outputFolder,
         media_type: cfg.mediaType,
         use_subfolder: cfg.useSubfolder,
         duration_seconds: fileInfo.duration_seconds > 0 ? fileInfo.duration_seconds : null,
      };
   });

   // Filas que muestra ProcessingView: salen del plan.
   const fileInfos = $derived(
      (plan?.segments ?? []).map((s) => ({ name: s.name, size_mb: 0, duration_seconds: s.duration, path: "" })),
   );

   // No se puede ejecutar mientras haya una consulta de plan en vuelo: el plan que se
   // ve podría no corresponder todavía a lo que el usuario acaba de cambiar.
   const canRun = $derived(!!fileInfo && !!plan && !planPending && !progress.running);

   // ── Plan ─────────────────────────────────────────────────────────────────────

   // Plan que calcula el backend (nombres, rutas y duraciones de los segmentos).
   // Es la única fuente: lo que se muestra aquí es exactamente lo que se ejecutará.
   // plan = { output_dir, segments: [{ index, name, start, end, duration, output }] } | null
   const planState = usePlan(() => planOptions, (options) => bridge.plan_diverge(options));
   const plan = $derived(planState.value);
   const planError = $derived(planState.error);
   const planPending = $derived(planState.pending);

   // ── Cambio de tipo ───────────────────────────────────────────────────────────

   // Al cambiar entre audio y video se descarta el archivo elegido y todo lo que dependía de él.
   // Es una acción del usuario (onchange del selector) y no un efecto: así no se ejecuta al montar.
   function resetForNewType() {
      fileInfo = null;
      chapters = [];
      hasChapters = false;
      segmentMode = "chapters";
      outputFolder = "";
      autoHint = "";
   }

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
      const exts = appConfig.mediaExtensions[cfg.mediaType].map((ext) => "*" + ext);
      const paths = await bridge.pick_files(exts, appConfig.baseFolder, cfg.mediaType);
      if (!paths.length) return;

      const info = await bridge.get_file_info(paths[0]);
      fileInfo = { ...info, path: paths[0] };
      autoHint = "";

      if (cfg.mediaType === "audio") {
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
      // El run relee la duración del archivo en vez de fiarse de la del preview.
      const { duration_seconds, ...options } = planOptions;
      await job.start(options);
   }
</script>

{#if job.processing}
   <ProcessingView
      title="Diverge"
      {goHome}
      {fileInfos}
      outputPath={plan?.output_dir ?? ""}
      showOpenFile={false}
      onCancel={job.cancel}
      onBack={job.back}
   />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title="Diverge" {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <!-- Toggle Audio / Video -->
            <Field label="Tipo">
               <SegmentedControl label="Tipo" options={MEDIA_TYPES} bind:value={cfg.mediaType} onchange={resetForNewType} fill />
            </Field>

            <!-- Carpeta base (solo audio) -->
            {#if cfg.mediaType === "audio"}
               <Field label="Carpeta base">
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
               </Field>
            {/if}

            <!-- Archivo -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center justify-between">
                  <span class="text-xs text-white/40">Archivo</span>
                  <button class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors" onclick={pickFile}>
                     {cfg.mediaType === "audio" ? "Seleccionar manualmente" : "Seleccionar archivo"}
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
                     {cfg.mediaType === "audio"
                        ? "Selecciona una carpeta base o elige manualmente"
                        : "Selecciona un archivo de video"}
                  </div>
               {/if}
            </div>

            <!-- Modo de segmentación — horizontal -->
            <Field label="Modo de segmentación">
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
            </Field>

            <!-- Intervalo — input pequeño -->
            {#if segmentMode === "interval"}
               <Field label="Intervalo (minutos)" for="interval">
                  <div class="flex items-center gap-3">
                     <input
                        id="interval"
                        type="number"
                        bind:value={cfg.intervalMins}
                        min="1"
                        max="999"
                        class="w-20 rounded-lg border border-white/10 bg-white/5 px-3 py-2
                       text-sm text-white outline-none focus:border-indigo-500/50
                       transition-colors text-center"
                     />
                     {#if plan}
                        <span class="text-xs text-white/30">
                           {plan.segments.length} segmentos
                        </span>
                     {/if}
                  </div>
               </Field>
            {/if}

            <!-- Toggle subcarpeta audios/parts o videos/parts -->
            <SwitchField
               bind:checked={cfg.useSubfolder}
               label="Guardar en subcarpeta {outputSubfolder}/parts"
               description={plan?.output_dir}
               size="sm"
               class="rounded-lg border border-white/10 bg-white/5 px-3 py-2.5"
            >
               Guardar en subcarpeta <code class="text-white/40">{outputSubfolder}/parts</code>
            </SwitchField>

            <!-- Carpeta de salida (solo si se desactiva la subcarpeta automática) -->
            {#if !cfg.useSubfolder}
               <Field label="Carpeta de salida">
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
               </Field>
            {/if}

            {#if planError}
               <span role="alert" class="text-xs text-red-400 break-words">{planError}</span>
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
