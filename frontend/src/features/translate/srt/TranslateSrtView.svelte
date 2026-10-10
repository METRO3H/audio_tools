<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { appConfig } from "@shared/state/config.svelte.js";

   import TranslateProcessingView from "@translate/srt/TranslateProcessingView.svelte";
   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import BaseFolderPicker from "@shared/components/BaseFolderPicker.svelte";
   import Spinner from "@shared/ui/Spinner.svelte";
   import { persistentConfig } from "@shared/services/persistentConfig.js";

   let { goHome } = $props();

   // ── Selección local / remoto ─────────────────────────────────────────────────
   // Mismo patrón que TranscribeView.svelte: se pregunta cada vez que se
   // entra a la vista (no se persiste), y bloquea el resto del formulario
   // hasta elegir — así no hace falta lidiar con "cambiaste de modo a
   // mitad de carga" en ningún otro lado.
   let mode = $state(null); // null | "local" | "remote"
   let checkingRemote = $state(false);
   let remoteError = $state("");
   let remoteInfo = $state(null); // { host, port, models, state, busy_model }

   // ── Estado ───────────────────────────────────────────────────────────────────

   let processing = $state(false);

   let fileInfos = $state([]); // [{name, path, size_mb, duration_seconds}]
   let autoHint = $state("");
   let outputSubfolder = $state("english");

   let rawTitle = $state("");
   let rawPublisherInfo = $state("");
   let showTitleInfoModal = $state(false);
   let modalTab = $state("info"); // "info" | "prompt"

   // Prompt compartido de extracción de work info — se lee del backend
   // (core/translation/prompts/shared/work_info_extraction.txt) y es
   // editable/guardable desde la tab "Prompt extractor" del modal.
   let workInfoPrompt = $state("");
   let workInfoPromptDirty = $state(false);

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

   // ── Cargar configuración guardada ────────────────────────────────────────────
   // selectedModel/nGpuLayers/nCtx/temperature se guardan aparte, por modo
   // (translate_srt_local_config / translate_srt_remote_config) — los
   // valores pensados para la GPU de esta PC no tienen por qué servir
   // para la del mediador, y viceversa (ver selectLocal/selectRemote).

   $effect(() => {
      const saved = persistentConfig.get("translate_srt_config");
      if (saved) {
         selectedLanguage = saved.selectedLanguage ?? "";
         outputSubfolder = saved.outputSubfolder ?? "english";
      }
   });

   // ── Guardar configuración al cambiar ────────────────────────────────────────

   $effect(() => {
      persistentConfig.set("translate_srt_config", {
         selectedLanguage,
         outputSubfolder,
      });
   });

   $effect(() => {
      if (!mode) return;
      const key = mode === "local" ? "translate_srt_local_config" : "translate_srt_remote_config";
      persistentConfig.set(key, { selectedModel, nGpuLayers, nCtx, temperature });
   });

   // ── Carga inicial (idioma/prompt/glossary — independiente del modo) ─────────

   $effect(() => {
      (async () => {
         languages = await bridge.list_prompt_languages();
         if (languages.length && !selectedLanguage) {
            selectedLanguage = languages.includes("japanese") ? "japanese" : languages[0];
            translationPrompt = await bridge.get_translation_prompt(selectedLanguage, "srt");
            glossaryText = await bridge.get_glossary(selectedLanguage);
            promptDirty = false;
            glossaryDirty = false;
         }
         // El prompt de extracción es compartido entre todos los idiomas,
         // así que se carga una sola vez, sin depender de selectedLanguage.
         workInfoPrompt = await bridge.get_shared_prompt("work_info_extraction");
         workInfoPromptDirty = false;
      })();
   });

   // ── Selección local / remoto ─────────────────────────────────────────────────

   async function selectLocal() {
      mode = "local";
      const saved = persistentConfig.get("translate_srt_local_config");
      nGpuLayers = saved?.nGpuLayers ?? 20;
      nCtx = saved?.nCtx ?? 4096;
      temperature = saved?.temperature ?? 0.3;
      models = await bridge.list_translation_models();
      selectedModel =
         saved?.selectedModel && models.includes(saved.selectedModel)
            ? saved.selectedModel
            : (models[0] ?? "");
   }

   async function selectRemote() {
      checkingRemote = true;
      remoteError = "";
      const result = await bridge.check_remote_translation_server();
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
      const saved = persistentConfig.get("translate_srt_remote_config");
      nGpuLayers = saved?.nGpuLayers ?? 0;
      nCtx = saved?.nCtx ?? 4096;
      temperature = saved?.temperature ?? 0.3;
      models = result.models;
      selectedModel =
         saved?.selectedModel && models.includes(saved.selectedModel)
            ? saved.selectedModel
            : (models[0] ?? "");
      mode = "remote";
   }

   function changeMode() {
      mode = null;
      remoteError = "";
   }

   // ── Derivados ────────────────────────────────────────────────────────────────

   const outputPath = $derived(
      appConfig.baseFolder ? `${appConfig.baseFolder}\\transcriptions\\${outputSubfolder}` : "",
   );

   const canRun = $derived(fileInfos.length > 0 && !!appConfig.baseFolder && !!selectedModel && !progress.running);

   const hasTitleOrInfo = $derived(!!rawTitle.trim() || !!rawPublisherInfo.trim());

   // ── Carga / auto-scan ────────────────────────────────────────────────────────

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

   // Prompt compartido de work_info_extraction — no depende del idioma.
   function onWorkInfoPromptEdit() {
      workInfoPromptDirty = true;
   }

   async function saveWorkInfoPrompt() {
      await bridge.save_shared_prompt("work_info_extraction", workInfoPrompt);
      workInfoPromptDirty = false;
   }

   // Resetea la tab activa cada vez que se abre el modal, para que siempre
   // arranque en "Info" (la de uso más frecuente).
   function openTitleInfoModal() {
      modalTab = "info";
      showTitleInfoModal = true;
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
         selectedLanguage,
         mode === "remote" ? remoteInfo.host : null,
         mode === "remote" ? remoteInfo.port : null,
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
      <div
         class="w-full max-w-2xl h-[85vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4"
      >
         <!-- Header -->
         <div class="flex items-center justify-between shrink-0">
            <h2 class="text-sm font-semibold text-white">Título / info del publisher</h2>
            <button
               class="text-white/30 hover:text-white transition-colors cursor-pointer"
               onclick={() => (showTitleInfoModal = false)}
            >
               ✕
            </button>
         </div>

         <!-- Tabs -->
         <div class="flex gap-1 shrink-0 border-b border-white/5">
            <button
               class="px-3 py-1.5 text-xs transition-colors cursor-pointer
                  {modalTab === 'info'
                     ? 'text-white border-b-2 border-indigo-500'
                     : 'text-white/40 hover:text-white/70'}"
               onclick={() => (modalTab = 'info')}
            >
               Info
            </button>
            <button
               class="px-3 py-1.5 text-xs transition-colors cursor-pointer
                  {modalTab === 'prompt'
                     ? 'text-white border-b-2 border-indigo-500'
                     : 'text-white/40 hover:text-white/70'}"
               onclick={() => (modalTab = 'prompt')}
            >
               Prompt extractor{workInfoPromptDirty ? " ·" : ""}
            </button>
         </div>

         <!-- Contenido de la tab activa -->
         <div class="flex-1 min-h-0 overflow-hidden">
            {#if modalTab === 'info'}
               <div class="flex h-full flex-col gap-4">
                  <div class="flex flex-col gap-1.5 shrink-0">
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

                  <div class="flex flex-1 min-h-0 flex-col gap-1.5">
                     <label class="text-xs text-white/40" for="pubInfo">Info del publisher</label>
                     <textarea
                        id="pubInfo"
                        bind:value={rawPublisherInfo}
                        placeholder="Pega la descripción / ficha del trabajo"
                        class="flex-1 min-h-0 resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2
                           text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
                        style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
                     ></textarea>
                  </div>
               </div>
            {:else}
               <div class="flex h-full flex-col gap-3">
                  <div class="flex items-center justify-between gap-3 shrink-0">
                     <p class="text-[11px] text-white/35 leading-relaxed">
                        System prompt que se le manda al modelo para extraer la work info
                        (speakers, tono, sinopsis, glossary...) a partir del texto de arriba.
                        Es compartido entre todos los idiomas y afecta a las tres tools de traducción.
                     </p>
                     <button
                        class="shrink-0 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs
                           text-white/40 hover:text-white/80 transition-colors cursor-pointer
                           disabled:opacity-30 disabled:cursor-not-allowed"
                        onclick={saveWorkInfoPrompt}
                        disabled={!workInfoPromptDirty}
                        title="Guardar prompt"
                     >
                        {workInfoPromptDirty ? "Guardar" : "Guardado"}
                     </button>
                  </div>

                  <textarea
                     bind:value={workInfoPrompt}
                     oninput={onWorkInfoPromptEdit}
                     spellcheck="false"
                     class="flex-1 min-h-0 resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2
                        text-xs text-white/80 outline-none focus:border-indigo-500/50 transition-colors font-mono"
                     style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
                  ></textarea>
               </div>
            {/if}
         </div>

         <!-- Footer -->
         <div class="flex justify-end shrink-0 border-t border-white/5 pt-3">
            <button
               class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium
                  text-white hover:bg-indigo-500 transition-colors cursor-pointer"
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
      <div
         class="w-full max-w-5xl max-h-[90vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4"
      >
         <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-white">
               Prompt {promptDirty ? "· sin guardar" : ""}
            </h2>
            <button class="text-white/30 hover:text-white transition-colors cursor-pointer" onclick={() => (showPromptModal = false)}>
               ✕
            </button>
         </div>

         <div class="flex items-center gap-2 shrink-0">
            <select
               value={selectedLanguage}
               onchange={(e) => onSelectLanguage(e.target.value)}
               class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5
                  text-xs text-white outline-none focus:border-indigo-500/50 transition-colors cursor-pointer"
            >
               {#each languages as lang (lang)}
                  <option value={lang}>{languageLabel(lang)}</option>
               {/each}
            </select>
            <button
               class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10 cursor-pointer"
               onclick={savePrompt}
               title="Guardar"
            >
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
      <div
         class="w-full max-w-5xl max-h-[90vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4"
      >
         <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-white">
               Glossary {glossaryDirty ? "· sin guardar" : ""}
            </h2>
            <button class="text-white/30 hover:text-white transition-colors cursor-pointer" onclick={() => (showGlossaryModal = false)}>
               ✕
            </button>
         </div>
         <p class="text-[11px] text-white/30 shrink-0">
            Términos fijos por idioma, compartidos entre .srt, chapters y filenames — se inyectan solos en el prompt
            final.
         </p>

         <div class="flex items-center gap-2 shrink-0">
            <select
               value={selectedLanguage}
               onchange={(e) => onSelectLanguage(e.target.value)}
               class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5
                  text-xs text-white outline-none focus:border-indigo-500/50 transition-colors cursor-pointer"
            >
               {#each languages as lang (lang)}
                  <option value={lang}>{languageLabel(lang)}</option>
               {/each}
            </select>
            <button
               class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10 cursor-pointer"
               onclick={saveGlossary}
               title="Guardar"
            >
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

{#if mode === null}
   <div class="flex h-full flex-col">
      <ViewHeader title="Translate" {goHome} />

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
                        Traducir en remoto
                     </span>
                     <span class="text-xs text-white/50 leading-relaxed">
                        Usa el server mediador de la red para traducir sin cargar
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
                  Traducir en esta PC
               </span>
               <span class="text-xs text-white/50 leading-relaxed">
                  Carga el modelo localmente, como siempre.
               </span>
            </button>
         </div>
      </main>
   </div>
{:else if processing}
   <TranslateProcessingView {goHome} {fileInfos} {outputPath} onCancel={cancel} onBack={goBack} />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={mode === "remote" ? "Translate (remoto)" : "Translate"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <button
               class="self-start text-xs text-white/30 hover:text-white transition-colors cursor-pointer"
               onclick={changeMode}
            >
               ← Cambiar modo (local/remoto)
            </button>

            <!-- Carpeta base -->
            <BaseFolderPicker onPick={loadSrt} />

            <!-- Archivos -->
            <div class="flex flex-col gap-1.5">
               <div class="flex items-center justify-between">
                  <span class="text-xs text-white/40">
                     Archivos .srt
                     {#if fileInfos.length}
                        <span class="text-white/20">({fileInfos.length})</span>
                     {/if}
                  </span>
                  <button class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer" onclick={pickFiles}>
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
                                 class="text-white/20 hover:text-red-400 transition-colors cursor-pointer"
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

            <!-- Modelo -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">Modelo</span>
               <select
                  bind:value={selectedModel}
                  class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-xs text-white outline-none focus:border-indigo-500/50 transition-colors cursor-pointer"
               >
                  {#if !models.length}
                     <option value="">
                        {mode === "remote" ? "Sin modelos en el mediador" : "Sin modelos en /models"}
                     </option>
                  {/if}
                  {#each models as m (m)}
                     <option value={m}>{m}</option>
                  {/each}
               </select>
               {#if mode === "remote" && !models.length}
                  <span class="text-xs text-yellow-400">
                     Este mediador no tiene ningún .gguf copiado en translation_models/ todavía.
                  </span>
               {/if}
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

            <!-- Prompt + Glossary + Título/info — misma fila.
                 Título/info es opcional, por eso va último y con indicador
                 claro de si tiene contenido cargado. -->
            <div class="grid grid-cols-3 gap-2">
               <button
                  class="flex items-center justify-between rounded-lg border border-white/10
                     bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={() => (showPromptModal = true)}
               >
                  <span class="text-white/60 truncate">Prompt</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">
                     {languageLabel(selectedLanguage)}{promptDirty ? " ·" : ""}
                  </span>
               </button>

               <button
                  class="flex items-center justify-between rounded-lg border border-white/10
                     bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={() => (showGlossaryModal = true)}
               >
                  <span class="text-white/60 truncate">Glossary</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">
                     {languageLabel(selectedLanguage)}{glossaryDirty ? " ·" : ""}
                  </span>
               </button>

               <!-- Título/info: opcional. El borde y el fondo se tiñen de
                    esmeralda + aparece un ✓ cuando hay contenido cargado,
                    así se ve de un vistazo si el usuario lo completó o no. -->
               <button
                  class="flex items-center justify-between rounded-lg border px-3 py-2 text-xs text-left transition-all cursor-pointer
                     {hasTitleOrInfo
                        ? 'border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/50'
                        : 'border-white/10 bg-white/5 hover:border-white/20'}"
                  onclick={openTitleInfoModal}
               >
                  <span class="{hasTitleOrInfo ? 'text-white/80' : 'text-white/60'} truncate">
                     Título/info
                  </span>
                  {#if hasTitleOrInfo}
                     <span class="shrink-0 ml-2 text-emerald-400 text-xs font-medium">✓</span>
                  {:else}
                     <span class="shrink-0 ml-2 text-white/20 text-xs">—</span>
                  {/if}
               </button>
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
                 text-white transition-colors hover:bg-indigo-500 cursor-pointer
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
