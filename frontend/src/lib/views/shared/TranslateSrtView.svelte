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
   let showTitleInfoModal = $state(false);

   let languages = $state([]); // ["japanese", "chinese", ...] — carpetas de prompts/
   let selectedLanguage = $state("");
   let translationPrompt = $state("");
   let promptDirty = $state(false);
   let showPromptModal = $state(false);
   let glossaryText = $state("");
   let glossaryDirty = $state(false);
   let showGlossaryModal = $state(false);

   function languageLabel(lang) {
      return lang ? lang.charAt(0).toUpperCase() + lang.slice(1) : "";
   }

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

         languages = await bridge.list_prompt_languages();
         if (languages.length && !selectedLanguage) {
            selectedLanguage = languages.includes("japanese") ? "japanese" : languages[0];
            translationPrompt = await bridge.get_translation_prompt(selectedLanguage, "srt");
            glossaryText = await bridge.get_glossary(selectedLanguage);
            promptDirty = false;
            glossaryDirty = false;
         }
      })();
   });

   // ── Derivados ────────────────────────────────────────────────────────────────

   const outputPath = $derived(
      appConfig.baseFolder ? `${appConfig.baseFolder}\\transcriptions\\${outputSubfolder}` : "",
   );

   const canRun = $derived(
      fileInfos.length > 0 && !!appConfig.baseFolder && !!selectedModel && !progress.running,
   );

   const hasTitleOrInfo = $derived(!!rawTitle.trim() || !!rawPublisherInfo.trim());

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

      if (languages.includes(result.source) && selectedLanguage !== result.source) {
         await onSelectLanguage(result.source);
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

   // ── Idioma / prompt / glosario ──────────────────────────────────────────────

   async function onSelectLanguage(lang) {
      selectedLanguage = lang;
      translationPrompt = await bridge.get_translation_prompt(lang, "srt");
      glossaryText = await bridge.get_glossary(lang);
      promptDirty = false;
      glossaryDirty = false;
   }

   function onPromptEdit() {
      promptDirty = true;
   }

   async function savePrompt() {
      await bridge.save_translation_prompt(selectedLanguage, "srt", translationPrompt);
      promptDirty = false;
   }

   function onGlossaryEdit() {
      glossaryDirty = true;
   }

   async function saveGlossary() {
      await bridge.save_glossary(selectedLanguage, glossaryText);
      glossaryDirty = false;
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
         translationPrompt,
         glossaryText,
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

{#if showTitleInfoModal}
   <div
      class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
      role="presentation"
      onclick={() => (showTitleInfoModal = false)}
   ></div>
   <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div class="w-full max-w-xl max-h-[85vh] overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">
         <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-white">Título / info del publisher</h2>
            <button
               class="text-white/30 hover:text-white transition-colors"
               onclick={() => (showTitleInfoModal = false)}
            >
               ✕
            </button>
         </div>

         <div class="flex flex-col gap-1.5">
            <label class="text-xs text-white/40" for="title">Título original</label>
            <input
               id="title"
               type="text"
               bind:value={rawTitle}
               placeholder="Título en el idioma original"
               class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2
                  text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
            />
         </div>

         <div class="flex flex-1 flex-col gap-1.5">
            <label class="text-xs text-white/40" for="pubInfo">Info del publisher</label>
            <textarea
               id="pubInfo"
               bind:value={rawPublisherInfo}
               rows="16"
               placeholder="Pega la descripción / ficha del trabajo"
               class="w-full resize-y rounded-lg border border-white/10 bg-white/5 px-3 py-2
                  text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
            ></textarea>
         </div>

         <div class="flex justify-end">
            <button
               class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium
                  text-white hover:bg-indigo-500 transition-colors"
               onclick={() => (showTitleInfoModal = false)}
            >
               Listo
            </button>
         </div>
      </div>
   </div>
{/if}

{#if showPromptModal}
   <div
      class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
      role="presentation"
      onclick={() => (showPromptModal = false)}
   ></div>
   <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div class="w-full max-w-5xl max-h-[90vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">
         <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-white">
               Prompt {promptDirty ? "· sin guardar" : ""}
            </h2>
            <button
               class="text-white/30 hover:text-white transition-colors"
               onclick={() => (showPromptModal = false)}
            >
               ✕
            </button>
         </div>

         <div class="flex items-center gap-2 shrink-0">
            <select
               value={selectedLanguage}
               onchange={(e) => onSelectLanguage(e.target.value)}
               class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5
                  text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
            >
               {#each languages as lang (lang)}
                  <option value={lang}>{languageLabel(lang)}</option>
               {/each}
            </select>
            <button class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10" onclick={savePrompt} title="Guardar">
               💾
            </button>
         </div>

         <textarea
            bind:value={translationPrompt}
            oninput={onPromptEdit}
            class="w-full flex-1 min-h-[65vh] resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2
               text-xs text-white/80 outline-none focus:border-indigo-500/50 transition-colors font-mono"
         ></textarea>
      </div>
   </div>
{/if}

{#if showGlossaryModal}
   <div
      class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
      role="presentation"
      onclick={() => (showGlossaryModal = false)}
   ></div>
   <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div class="w-full max-w-5xl max-h-[90vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">
         <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-white">
               Glossary {glossaryDirty ? "· sin guardar" : ""}
            </h2>
            <button
               class="text-white/30 hover:text-white transition-colors"
               onclick={() => (showGlossaryModal = false)}
            >
               ✕
            </button>
         </div>
         <p class="text-[11px] text-white/30 shrink-0">
            Términos fijos por idioma, compartidos entre .srt, chapters y filenames — se inyectan solos en el prompt final.
         </p>

         <div class="flex items-center gap-2 shrink-0">
            <select
               value={selectedLanguage}
               onchange={(e) => onSelectLanguage(e.target.value)}
               class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5
                  text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
            >
               {#each languages as lang (lang)}
                  <option value={lang}>{languageLabel(lang)}</option>
               {/each}
            </select>
            <button class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10" onclick={saveGlossary} title="Guardar">
               💾
            </button>
         </div>

         <textarea
            bind:value={glossaryText}
            oninput={onGlossaryEdit}
            class="w-full flex-1 min-h-[65vh] resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2
               text-xs text-white/80 outline-none focus:border-indigo-500/50 transition-colors font-mono"
         ></textarea>
      </div>
   </div>
{/if}

{#if processing}
   <TranslateProcessingView
      {goHome}
      {fileInfos}
      {outputPath}
      onCancel={cancel}
      onBack={goBack}
   />
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

            <!-- Título/info del publisher + Prompt + Glossary — misma fila -->
            <div class="grid grid-cols-3 gap-2">
               <button
                  class="flex items-center justify-between rounded-lg border border-white/10
                     bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
                  onclick={() => (showTitleInfoModal = true)}
               >
                  <span class="text-white/60 truncate">Título/info</span>
                  <span class="{hasTitleOrInfo ? 'text-emerald-400' : 'text-white/30'} shrink-0 ml-2">
                     {hasTitleOrInfo ? "✓" : "—"}
                  </span>
               </button>

               <button
                  class="flex items-center justify-between rounded-lg border border-white/10
                     bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
                  onclick={() => (showPromptModal = true)}
               >
                  <span class="text-white/60 truncate">Prompt</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">
                     {languageLabel(selectedLanguage)}{promptDirty ? " ·" : ""}
                  </span>
               </button>

               <button
                  class="flex items-center justify-between rounded-lg border border-white/10
                     bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
                  onclick={() => (showGlossaryModal = true)}
               >
                  <span class="text-white/60 truncate">Glossary</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">
                     {languageLabel(selectedLanguage)}{glossaryDirty ? " ·" : ""}
                  </span>
               </button>
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

