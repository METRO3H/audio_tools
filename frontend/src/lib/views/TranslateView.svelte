<script>
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";

   import TranslateProcessingView from "$lib/views/shared/TranslateProcessingView.svelte";
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";

   let { goHome } = $props();

   // ── Estado ───────────────────────────────────────────────────────────────────

   let processing = $state(false);

   let fileInfos = $state([]); // [{name, path, size_mb, duration_seconds}]
   let autoHint = $state("");
   let outputSubfolder = $state("english");

   let rawTitle = $state("");
   let rawPublisherInfo = $state("");

   let presets = $state([]);
   let activePreset = $state("");
   let basePrompt = $state("");
   let promptDirty = $state(false);

   let models = $state([]);
   let selectedModel = $state("");
   let nGpuLayers = $state(20);
   let nCtx = $state(4096);
   let temperature = $state(0.3);

   // ── Carga inicial ────────────────────────────────────────────────────────────

   $effect(() => {
      (async () => {
         models = await bridge.list_translation_models();
         if (models.length && !selectedModel) selectedModel = models[0];

         presets = await bridge.list_prompt_presets();
         if (presets.length && !activePreset) {
            activePreset = presets.includes("japanese") ? "japanese" : presets[0];
            basePrompt = await bridge.get_prompt_preset(activePreset);
            promptDirty = false;
         }
      })();
   });

   // ── Derivados ────────────────────────────────────────────────────────────────

   const outputPath = $derived(
      appConfig.baseFolder ? `${appConfig.baseFolder}\\transcriptions\\${outputSubfolder}` : "",
   );

   const canRun = $derived(fileInfos.length > 0 && !!appConfig.baseFolder && !!selectedModel && !progress.running);

   // ── Carga / auto-scan ────────────────────────────────────────────────────────

   async function pickBaseFolder() {
      const folder = await bridge.pick_folder();
      if (!folder) return;
      appConfig.setBaseFolder(folder);
      await loadSrt(folder);
   }

   async function loadSrt(folder) {
      const result = await bridge.scan_translate_input(folder);
      if (result.error) {
         fileInfos = [];
         autoHint = `⚠ ${result.error}`;
         return;
      }
      const infos = await Promise.all(result.files.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: result.files[i] }));
      autoHint = `✓ ${infos.length} archivo(s) detectados en transcriptions/${result.source}`;

      // Si hay un preset con el mismo nombre que el idioma detectado, lo activa
      if (presets.includes(result.source) && activePreset !== result.source) {
         await onSelectPreset(result.source);
      }
   }

   async function pickFiles() {
      const paths = await bridge.pick_files(["*.srt"], appConfig.baseFolder, "subtitles");
      if (!paths.length) return;
      const infos = await Promise.all(paths.map((p) => bridge.get_file_info(p)));
      fileInfos = infos.map((info, i) => ({ ...info, path: paths[i] }));
      autoHint = "";
   }

   function removeFile(path) {
      fileInfos = fileInfos.filter((f) => f.path !== path);
   }

   // ── Presets ──────────────────────────────────────────────────────────────────

   async function onSelectPreset(name) {
      activePreset = name;
      basePrompt = await bridge.get_prompt_preset(name);
      promptDirty = false;
   }

   function onPromptEdit() {
      promptDirty = true;
   }

   async function savePreset() {
      if (!activePreset) return;
      await bridge.save_prompt_preset(activePreset, basePrompt);
      promptDirty = false;
   }

   async function saveAsPreset() {
      const name = prompt("Nombre del nuevo preset:");
      if (!name) return;
      await bridge.save_prompt_preset(name, basePrompt);
      presets = await bridge.list_prompt_presets();
      activePreset = name;
      promptDirty = false;
   }

   async function deletePreset() {
      if (!activePreset) return;
      if (!confirm(`¿Borrar el preset "${activePreset}"?`)) return;
      await bridge.delete_prompt_preset(activePreset);
      presets = await bridge.list_prompt_presets();
      activePreset = presets[0] ?? "";
      basePrompt = activePreset ? await bridge.get_prompt_preset(activePreset) : "";
      promptDirty = false;
   }

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      progress.reset();
      processing = true;
      progress.running = true;

      await bridge.run_translate(
         fileInfos.map((f) => f.path),
         appConfig.baseFolder,
         outputSubfolder,
         rawTitle,
         rawPublisherInfo,
         basePrompt,
         selectedModel,
         nGpuLayers,
         nCtx,
         temperature,
      );
   }

   function cancel() {
      bridge.cancel_translate();
   }

   function goBack() {
      processing = false;
      progress.reset();
   }
</script>

{#if processing}
   <TranslateProcessingView {goHome} {fileInfos} {outputPath} onCancel={cancel} onBack={goBack} />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title="Translate" {goHome} />

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

            <!-- Archivos -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center justify-between">
                  <span class="text-xs text-white/40">
                     Archivos .srt
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
                     {appConfig.baseFolder ? "No se encontraron .srt" : "Selecciona una carpeta base primero"}
                  </div>
               {/if}
            </div>

            <!-- Carpeta de salida -->
            <div class="flex flex-col gap-1.5">
               <label class="text-xs text-white/40" for="outSub">Subcarpeta de salida</label>
               <div class="flex items-center gap-2">
                  <span class="text-xs text-white/30">transcriptions /</span>
                  <input
                     id="outSub"
                     type="text"
                     bind:value={outputSubfolder}
                     class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5
                        text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
                  />
               </div>
               {#if outputPath}
                  <span class="text-[11px] text-white/25">{outputPath}</span>
               {/if}
            </div>

            <!-- Título -->
            <div class="flex flex-col gap-1.5">
               <label class="text-xs text-white/40" for="title">Título original (opcional)</label>
               <input
                  id="title"
                  type="text"
                  bind:value={rawTitle}
                  placeholder="Título en el idioma original"
                  class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
               />
            </div>

            <!-- Info publisher -->
            <div class="flex flex-col gap-1.5">
               <label class="text-xs text-white/40" for="pubInfo">Info del publisher (opcional)</label>
               <textarea
                  id="pubInfo"
                  bind:value={rawPublisherInfo}
                  rows="4"
                  placeholder="Pega la descripción / ficha del trabajo"
                  class="w-full resize-y rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
               ></textarea>
            </div>

            <!-- Prompt / presets -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center justify-between">
                  <span class="text-xs text-white/40">Prompt {promptDirty ? "· sin guardar" : ""}</span>
                  <div class="flex gap-1">
                     <button
                        class="rounded px-2 py-1 text-[11px] text-white/50 hover:text-white hover:bg-white/10"
                        onclick={savePreset}
                        title="Guardar"
                     >
                        💾
                     </button>
                     <button
                        class="rounded px-2 py-1 text-[11px] text-white/50 hover:text-white hover:bg-white/10"
                        onclick={saveAsPreset}
                        title="Guardar como"
                     >
                        📄
                     </button>
                     <button
                        class="rounded px-2 py-1 text-[11px] text-white/50 hover:text-red-400 hover:bg-white/10"
                        onclick={deletePreset}
                        title="Borrar preset"
                     >
                        🗑
                     </button>
                  </div>
               </div>
               <select
                  value={activePreset}
                  onchange={(e) => onSelectPreset(e.target.value)}
                  class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-1.5
                     text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
               >
                  {#each presets as p (p)}
                     <option value={p}>{p}</option>
                  {/each}
               </select>
               <textarea
                  bind:value={basePrompt}
                  oninput={onPromptEdit}
                  rows="6"
                  class="w-full resize-y rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-xs text-white/80 outline-none focus:border-indigo-500/50 transition-colors font-mono"
               ></textarea>
            </div>

            <!-- Modelo -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">Modelo</span>
               <select
                  bind:value={selectedModel}
                  class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
               >
                  {#if !models.length}
                     <option value="">Sin modelos en /models</option>
                  {/if}
                  {#each models as m (m)}
                     <option value={m}>{m}</option>
                  {/each}
               </select>
            </div>

            <!-- Parámetros -->
            <div class="grid grid-cols-3 gap-3">
               <div class="flex flex-col gap-1.5">
                  <label class="text-[11px] text-white/40" for="gpuLayers">GPU layers</label>
                  <input
                     id="gpuLayers"
                     type="number"
                     bind:value={nGpuLayers}
                     min="0"
                     class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5
                        text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
                  />
               </div>
               <div class="flex flex-col gap-1.5">
                  <label class="text-[11px] text-white/40" for="ctx">Contexto</label>
                  <input
                     id="ctx"
                     type="number"
                     bind:value={nCtx}
                     min="512"
                     step="512"
                     class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5
                        text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
                  />
               </div>
               <div class="flex flex-col gap-1.5">
                  <label class="text-[11px] text-white/40" for="temp">Temperatura</label>
                  <input
                     id="temp"
                     type="number"
                     bind:value={temperature}
                     min="0"
                     max="2"
                     step="0.1"
                     class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5
                        text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
                  />
               </div>
            </div>

            <!-- Botón -->
            <button
               class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium
                 text-white transition-colors hover:bg-indigo-500
                 disabled:opacity-30 disabled:cursor-not-allowed"
               onclick={run}
               disabled={!canRun}
            >
               Ejecutar traducción
            </button>
         </div>
      </main>
   </div>
{/if}
