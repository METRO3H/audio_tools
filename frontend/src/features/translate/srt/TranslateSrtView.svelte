<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { appConfig } from "@shared/state/config.svelte.js";
   import { useToolRun } from "@shared/state/useToolRun.svelte.js";
   import { useExecutionTarget } from "@shared/state/useExecutionTarget.svelte.js";

   import TranslateProcessingView from "@translate/srt/TranslateProcessingView.svelte";
   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import ExecutionModeGate from "@shared/components/ExecutionModeGate.svelte";
   import BaseFolderPicker from "@shared/components/BaseFolderPicker.svelte";
   import TranslationSettings from "@shared/components/TranslationSettings.svelte";
   import Modal from "@shared/ui/Modal.svelte";
   import { persistentConfig } from "@shared/services/persistentConfig.js";

   let { goHome } = $props();

   const job = useToolRun("run_translate");

   // ── Dónde se ejecuta: esta PC o el mediador de la red ────────────────────────
   const target = useExecutionTarget({ check: () => bridge.check_remote_translation_server() });

   // ── Estado ───────────────────────────────────────────────────────────────────

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
   // selectedModel/nGpuLayers/nCtx/temperature viven en `settings`, que llena
   // TranslationSettings (bind:settings más abajo) — ver ese componente para
   // el porqué de guardarlos por separado según el modo.
   let settings = $state(undefined);

   // ── Cargar configuración guardada (idioma/subcarpeta — independiente del modo) ──

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

   // ── Lista de modelos ─────────────────────────────────────────────────────────
   // Local: escanea el disco (bridge). Remoto: ya viene en target.remote.models, no hay nada
   // que pedirle a nadie (lo pidió useExecutionTarget al consultar al mediador). La config
   // (selectedModel/nGpuLayers/nCtx/temperature) y su persistencia por modo las maneja
   // TranslationSettings — ver bind:settings más abajo.

   $effect(() => {
      if (target.mode === "local") {
         (async () => {
            models = await bridge.list_translation_models();
         })();
      } else if (target.mode === "remote" && target.remote) {
         models = target.remote.models;
      }
   });

   // ── Derivados ────────────────────────────────────────────────────────────────

   const outputPath = $derived(
      appConfig.baseFolder ? `${appConfig.baseFolder}\\transcriptions\\${outputSubfolder}` : "",
   );

   const canRun = $derived(
      fileInfos.length > 0 && !!appConfig.baseFolder && !!settings?.selectedModel && !progress.running,
   );

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
      await job.start({
         file_paths: fileInfos.map((f) => f.path),
         base_folder: appConfig.baseFolder,
         output_subfolder: outputSubfolder,
         raw_title: rawTitle,
         raw_publisher_info: rawPublisherInfo,
         base_prompt: translationPrompt,
         glossary: glossaryText,
         model: settings.selectedModel,
         n_gpu_layers: settings.nGpuLayers,
         n_ctx: settings.nCtx,
         temperature: settings.temperature,
         source_language: selectedLanguage,
         target: target.target,
      });
   }
</script>

{#if showTitleInfoModal}
   <Modal
      onClose={() => (showTitleInfoModal = false)}
      size="2xl"
      height="fixed-85"
      label="Título / info del publisher"
      class="gap-4"
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
   </Modal>
{/if}

{#if showPromptModal}
   <Modal onClose={() => (showPromptModal = false)} size="5xl" height="max-90" label="Prompt" class="gap-4">
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
   </Modal>
{/if}

{#if showGlossaryModal}
   <Modal onClose={() => (showGlossaryModal = false)} size="5xl" height="max-90" label="Glossary" class="gap-4">
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
   </Modal>
{/if}

{#if target.mode === null}
   <ExecutionModeGate
      title="Translate"
      {goHome}
      {target}
      remoteTitle="Traducir en remoto"
      remoteDescription="Usa el server mediador de la red para traducir sin cargar el modelo en esta PC."
      localTitle="Traducir en esta PC"
      localDescription="Carga el modelo localmente, como siempre."
   />
{:else if job.processing}
   <TranslateProcessingView {goHome} {fileInfos} {outputPath} onCancel={job.cancel} onBack={job.back} />
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={target.mode === "remote" ? "Translate (remoto)" : "Translate"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <button
               class="self-start text-xs text-white/30 hover:text-white transition-colors cursor-pointer"
               onclick={target.change}
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

            <TranslationSettings
               {target}
               {models}
               storageKey="translate_srt"
               bind:settings
               noModelsLabel={target.mode === "remote" ? "Sin modelos en el mediador" : "Sin modelos en /models"}
               remoteNoModelsHint="Este mediador no tiene ningún .gguf copiado en translation_models/ todavía."
            />

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
