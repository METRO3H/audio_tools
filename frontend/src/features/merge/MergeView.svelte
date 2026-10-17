<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { appConfig } from "@shared/state/config.svelte.js";
   import { basename, folderName } from "@shared/utils.js";
   import { useToolRun } from "@shared/state/useToolRun.svelte.js";
   import { persisted } from "@shared/state/persisted.svelte.js";
   import { usePlan } from "@shared/state/usePlan.svelte.js";
   import ProcessingView from "@shared/components/ProcessingView.svelte";
   import ViewHeader from "@shared/components/ViewHeader.svelte";

   let { goHome } = $props();

   const job = useToolRun("run_merge");

   // ── Estado ──────────────────────────────────────────────────────────────────

   // Preferencias que se recuerdan entre sesiones. El formato guardado se respeta: solo se
   // restablece cuando el USUARIO cambia el tipo (changeMediaType), nunca al montar.
   const cfg = persisted("merge_config", { mediaType: "audio", outputFormat: "mp3" });

   let fileInfos = $state([]);
   let outputName = $state("");
   let autoHint = $state("");

   // ── Derivados ────────────────────────────────────────────────────────────────

   const formatOptions = $derived(appConfig.outputFormats[cfg.mediaType] ?? []);

   // Si lo guardado no es válido para el tipo actual (config manipulada o corrupta), se usa el primero.
   const outputFormat = $derived(formatOptions.includes(cfg.outputFormat) ? cfg.outputFormat : (formatOptions[0] ?? ""));

   const effectiveName = $derived(outputName.trim() || folderName(appConfig.baseFolder));

   // ── Cambio de tipo ───────────────────────────────────────────────────────────

   // Al cambiar entre audio y video se restablece el formato y se descartan los archivos.
   // Es una acción del usuario y no un efecto: así no corre al montar ni pisa lo guardado.
   function changeMediaType(type) {
      if (type === cfg.mediaType) return;
      cfg.mediaType = type;
      cfg.outputFormat = appConfig.outputFormats[type]?.[0] ?? "";
      fileInfos = [];
      autoHint = "";
   }

   // ── Carga de archivos ────────────────────────────────────────────────────────

   async function loadMedia(folder) {
      const result = await bridge.scan_media_folder(folder, cfg.mediaType);
      if (result.error) {
         fileInfos = [];
         autoHint = `⚠ ${result.error}`;
         return;
      }
      if (!result.files.length) {
         fileInfos = [];
         autoHint = `⚠ No se encontraron archivos en ./${cfg.mediaType === "audio" ? "audios" : "videos"}`;
         return;
      }
      const infos = await Promise.all(result.files.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: result.files[i] }));
      autoHint = `✓ ${infos.length} archivo(s) detectados`;
      if (!outputName) outputName = folderName(folder);
   }

   // ── Selección manual ─────────────────────────────────────────────────────────

   async function pickFiles() {
      const exts = (appConfig.mediaExtensions[cfg.mediaType] ?? []).map((ext) => "*" + ext);
      const paths = await bridge.pick_files(exts, appConfig.baseFolder, cfg.mediaType);
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

   // ── Plan ─────────────────────────────────────────────────────────────────────

   // Opciones que se le envían al backend, o null si todavía no hay con qué planificar.
   // El backend decide dónde queda el resultado (junto al primer archivo), limpia el nombre
   // y descarta de la lista el merge anterior si estaba entre las entradas.
   const planOptions = $derived.by(() => {
      if (fileInfos.length < 2 || !effectiveName || !outputFormat) return null;
      return {
         file_paths: fileInfos.map((f) => f.path),
         output_name: effectiveName,
         output_format: outputFormat,
         media_type: cfg.mediaType,
         durations: fileInfos.map((f) => (f.duration_seconds > 0 ? f.duration_seconds : null)),
      };
   });

   // plan = { output_path, output_name, files, excluded, total_duration, chapters } | null
   const planState = usePlan(() => planOptions, (options) => bridge.plan_merge(options));
   const plan = $derived(planState.value);
   const planError = $derived(planState.error);
   const planPending = $derived(planState.pending);

   const excludedNames = $derived((plan?.excluded ?? []).map((path) => basename(path)));

   // Filas de ProcessingView: los archivos que REALMENTE se unen (sin el merge anterior).
   const processingFiles = $derived.by(() => {
      const sizeByPath = new Map(fileInfos.map((f) => [f.path, f.size_mb]));
      return (plan?.files ?? []).map((f) => ({
         name: f.name,
         size_mb: sizeByPath.get(f.path) ?? 0,
         duration_seconds: f.duration,
         path: f.path,
      }));
   });

   // ── Validación ───────────────────────────────────────────────────────────────

   // No se puede ejecutar mientras haya una consulta de plan en vuelo: el plan que se ve
   // podría no corresponder todavía a lo que el usuario acaba de cambiar.
   const canRun = $derived(!!plan && !planPending && !progress.running);

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      await job.start(planOptions);
   }
</script>

{#if job.processing}
   <ProcessingView
      title="Merge"
      {goHome}
      fileInfos={processingFiles}
      outputPath={plan?.output_path ?? ""}
      onCancel={job.cancel}
      onBack={job.back}
   />
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
                       {cfg.mediaType === type
                           ? 'bg-indigo-600 text-white'
                           : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
                        onclick={() => changeMediaType(type)}
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
                  <ul class="flex flex-col gap-1 max-h-40 overflow-y-auto">
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
                        ? `No se encontraron ${cfg.mediaType === "audio" ? "audios en ./audios" : "videos en ./videos"}`
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
                     value={outputFormat}
                     onchange={(e) => (cfg.outputFormat = e.currentTarget.value)}
                     aria-label="Formato de salida"
                     class="rounded-lg border border-white/10 bg-zinc-900 px-2 py-2
                     text-xs text-white/70 outline-none focus:border-indigo-500/50"
                  >
                     {#each formatOptions as fmt (fmt)}
                        <option value={fmt}>{fmt}</option>
                     {/each}
                  </select>
               </div>
               {#if plan}
                  <span class="text-xs text-white/20 truncate">→ {plan.output_name}</span>
               {/if}
               {#if excludedNames.length}
                  <span class="text-xs text-yellow-400">
                     Se excluirá del merge: {excludedNames.join(", ")} (es el archivo de salida)
                  </span>
               {/if}
            </div>

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
               Ejecutar merge
            </button>
         </div>
      </main>
   </div>
{/if}
