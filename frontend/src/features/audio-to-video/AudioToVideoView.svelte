<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { appConfig } from "@shared/state/config.svelte.js";
   import { useToolRun } from "@shared/state/useToolRun.svelte.js";
   import { persisted } from "@shared/state/persisted.svelte.js";
   import { usePlan } from "@shared/state/usePlan.svelte.js";
   import { useFileSelection } from "@shared/state/useFileSelection.svelte.js";
   import Spinner from "@shared/ui/Spinner.svelte";
   import Field from "@shared/ui/Field.svelte";
   import SegmentedControl from "@shared/ui/SegmentedControl.svelte";
   import ProcessingView from "@shared/components/ProcessingView.svelte";
   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import FileList from "@shared/components/FileList.svelte";
   import { basename } from "@shared/utils.js";
   let { goHome } = $props();

   const job = useToolRun("run_audio_to_video");

   // ── Estado ───────────────────────────────────────────────────────────────────

   let imageInfo = $state(null); // { path, name, optimized }
   let imageHint = $state("");

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
      formatDetected: (n, result) => `✓ ${n} audio(s) detectados desde ${result.source}`,
   });

   const fileInfos = $derived(selection.files);

   // Preferencias que se recuerdan entre sesiones. `encoder: null` = "el mejor disponible":
   // solo se guarda un encoder cuando el USUARIO lo elige, y uno guardado se respeta al montar
   // (la detección ya no lo pisa). Lo guardado que no sirva (config manipulada, GPU que ya no
   // está) se resuelve más abajo sin tocar lo guardado.
   const cfg = persisted("audio_to_video_config", {
      encoder: null,
      fps: 1,
      crf: 23,
      preset: "medium",
      resolution: "1280x720",
      copyAudio: true,
      showAdvanced: false,
   });

   // Lo que el backend sabe codificar (encoders, presets, fps, resoluciones).
   const caps = $derived(appConfig.videoEncoding);

   // ── Encoders disponibles en esta máquina ─────────────────────────────────────

   let availableEncoders = $state({ cpu: true });
   let detectingEncoders = $state(true);
   let detectError = $state("");

   $effect(() => {
      Promise.resolve()
         .then(() => bridge.detect_encoders())
         .then((result) => {
            availableEncoders = result;
         })
         .catch((err) => {
            detectError = `No se pudieron detectar los encoders (${err instanceof Error ? err.message : err}). Solo se ofrece CPU.`;
         })
         .finally(() => {
            detectingEncoders = false;
         });
   });

   const isAvailable = (id) => availableEncoders[id] === true;

   // ── Valores efectivos ────────────────────────────────────────────────────────

   // Encoder: el guardado si sigue disponible; si no, el mejor disponible. Mientras se detecta
   // se muestra lo guardado (y no se puede ejecutar): así nunca "salta" de uno a otro al abrir.
   const encoder = $derived.by(() => {
      const saved = caps.encoders.some((e) => e.id === cfg.encoder) ? cfg.encoder : null;
      if (detectingEncoders) return saved ?? "cpu";
      if (saved && isAvailable(saved)) return saved;
      return caps.encoder_priority.find(isAvailable) ?? "cpu";
   });

   const presetOptions = $derived(caps.presets[encoder] ?? []);
   // Un preset de otro encoder (p4 con CPU) no vale: se usa el de por defecto del encoder.
   const preset = $derived(presetOptions.includes(cfg.preset) ? cfg.preset : (caps.default_presets[encoder] ?? ""));
   const fps = $derived(caps.fps.includes(cfg.fps) ? cfg.fps : (caps.fps[0] ?? 1));
   const resolution = $derived(caps.resolutions.includes(cfg.resolution) ? cfg.resolution : (caps.resolutions[0] ?? "1280x720"));
   const crf = $derived(Math.min(caps.quality_range[1], Math.max(caps.quality_range[0], cfg.crf)));

   // ── Carga ────────────────────────────────────────────────────────────────────

   async function pickBaseFolder() {
      const folder = await bridge.pick_folder();
      if (!folder) return;
      appConfig.setBaseFolder(folder);
      await loadAll(folder);
   }

   async function loadAll(folder) {
      await Promise.all([selection.loadFromFolder(folder), loadImage(folder)]);
   }

   // Si se cambia de carpeta mientras una búsqueda sigue en curso, solo cuenta la última.
   let imageLoad = 0;

   async function loadImage(folder) {
      const mine = ++imageLoad;
      const result = await bridge.scan_images_folder(folder);
      if (mine !== imageLoad) return;
      if (!result) {
         imageInfo = null;
         imageHint = "⚠ No se encontró imagen en ./images — se usará fondo negro";
         return;
      }
      imageInfo = result;
      imageHint = result.optimized ? `✓ Imagen optimizada: ${result.name}` : `✓ Imagen detectada: ${result.name}`;
   }

   // La imagen elegida a mano se usa tal cual: no se vuelve a escanear la carpeta (el escaneo
   // optimiza imágenes y su resultado se descartaba).
   async function pickImage() {
      const path = await bridge.pick_image(appConfig.baseFolder);
      if (!path) return;
      imageLoad++; // una detección automática que siga en curso no debe pisar esta elección
      imageInfo = { path, name: basename(path), optimized: false };
      imageHint = `✓ Imagen seleccionada: ${basename(path)}`;
   }

   function clearImage() {
      imageLoad++;
      imageInfo = null;
      imageHint = "Sin imagen — se usará fondo negro";
   }

   // ── Plan ─────────────────────────────────────────────────────────────────────

   // Opciones que se le envían al backend, o null si todavía no hay con qué planificar.
   // El backend decide dónde queda cada video, detecta nombres repetidos y avisa de los
   // videos que ya existen.
   const planOptions = $derived.by(() => {
      if (!fileInfos.length || !appConfig.baseFolder || !caps.encoders.length) return null;
      return {
         file_paths: fileInfos.map((f) => f.path),
         base_folder: appConfig.baseFolder,
         background_image: imageInfo?.path ?? null,
         encoder,
         fps,
         crf,
         preset,
         resolution,
         copy_audio: cfg.copyAudio,
         durations: fileInfos.map((f) => (f.duration_seconds > 0 ? f.duration_seconds : null)),
      };
   });

   // plan = { output_dir, files: [{ index, name, path, duration, output, output_name, exists }], total_duration } | null
   const planState = usePlan(() => planOptions, (options) => bridge.plan_audio_to_video(options));
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

   // No se ejecuta con una consulta de plan en vuelo (el plan que se ve podría no ser el último)
   // ni mientras se detectan los encoders (el que se muestra todavía es provisional).
   const canRun = $derived(!!plan && !planPending && !progress.running && !detectingEncoders);

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      await job.start(planOptions);
   }
</script>

{#if job.processing}
   <ProcessingView
      title="Audio → Video"
      {goHome}
      fileInfos={processingFiles}
      outputPath={plan?.output_dir ?? ""}
      showOpenFile={false}
      onCancel={job.cancel}
      onBack={job.back}
   />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title="Audio → Video" {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <!-- Carpeta base -->
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

            <!-- Archivos de audio -->
            <FileList
               fileInfos={selection.files}
               autoHint={selection.hint}
               onPickFiles={selection.pickFiles}
               onRemove={selection.remove}
               emptyText={appConfig.baseFolder ? "No se encontraron audios" : "Selecciona una carpeta base primero"}
            />

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
                     Fondo negro {resolution.replace("x", "×")}
                  </div>
               {/if}
            </div>

            <!-- Encoder -->
            <Field label="Encoder">
               {#if detectingEncoders}
                  <div class="flex items-center gap-2">
                     <Spinner size={12} color="text-white/30" duration="1s" />
                     <span class="text-xs text-white/20">Detectando...</span>
                  </div>
               {/if}
               <SegmentedControl
                  label="Encoder"
                  size="sm"
                  wrap
                  value={encoder}
                  options={caps.encoders.map((e) => ({ value: e.id, label: e.label, disabled: !isAvailable(e.id) }))}
                  onchange={(id) => (cfg.encoder = id)}
               />
               {#if detectError}
                  <span role="alert" class="text-xs text-yellow-400">{detectError}</span>
               {/if}
            </Field>

            <!-- FPS -->
            <Field label="FPS">
               <SegmentedControl
                  label="FPS"
                  size="sm"
                  value={fps}
                  options={caps.fps.map((f) => ({ value: f, label: String(f) }))}
                  onchange={(f) => (cfg.fps = f)}
               />
            </Field>

            <!-- Toggle opciones avanzadas -->
            <button
               class="flex items-center gap-2 text-xs text-white/30 hover:text-white/60
                 transition-colors w-fit"
               onclick={() => (cfg.showAdvanced = !cfg.showAdvanced)}
            >
               <span>{cfg.showAdvanced ? "▼" : "▶"}</span>
               <span>Opciones avanzadas</span>
            </button>

            {#if cfg.showAdvanced}
               <div class="flex flex-col gap-4 rounded-xl border border-white/5 bg-white/3 p-4">
                  <!-- CRF -->
                  <Field label="Calidad (CRF) — menor es mejor" for="crf">
                     <input
                        id="crf"
                        type="range"
                        value={crf}
                        oninput={(e) => (cfg.crf = Number(e.currentTarget.value))}
                        min={caps.quality_range[0]}
                        max={caps.quality_range[1]}
                        step="1"
                        class="accent-indigo-500 w-full"
                     />
                     <div class="flex justify-between text-xs text-white/20">
                        <span>{caps.quality_range[0]} (mejor)</span>
                        <span class="text-white/50">{crf}</span>
                        <span>{caps.quality_range[1]} (peor)</span>
                     </div>
                  </Field>

                  <!-- Preset -->
                  <Field label="Preset">
                     <SegmentedControl
                        label="Preset"
                        size="sm"
                        wrap
                        value={preset}
                        options={presetOptions.map((p) => ({ value: p, label: p }))}
                        onchange={(p) => (cfg.preset = p)}
                     />
                  </Field>

                  <!-- Resolución (solo si no hay imagen) -->
                  {#if !imageInfo}
                     <Field label="Resolución (fondo negro)">
                        <SegmentedControl
                           label="Resolución"
                           size="sm"
                           wrap
                           value={resolution}
                           options={caps.resolutions.map((r) => ({ value: r, label: r }))}
                           onchange={(r) => (cfg.resolution = r)}
                        />
                     </Field>
                  {/if}

                  <!-- Audio -->
                  <Field label="Audio">
                     <SegmentedControl
                        label="Audio"
                        size="sm"
                        wrap
                        value={cfg.copyAudio}
                        options={[
                           { value: true, label: "Copy (sin re-encodear)" },
                           { value: false, label: "AAC 192k" },
                        ]}
                        onchange={(copy) => (cfg.copyAudio = copy)}
                     />
                  </Field>
               </div>
            {/if}

            <!-- Salida: lo que dice el plan -->
            {#if plan}
               <span class="text-xs text-white/20 truncate">→ {plan.output_dir}</span>
            {/if}
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
