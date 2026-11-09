<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { appConfig } from "@shared/state/config.svelte.js";
   import { useToolRun } from "@shared/state/useToolRun.svelte.js";
   import { useExecutionTarget } from "@shared/state/useExecutionTarget.svelte.js";
   import { useFileSelection } from "@shared/state/useFileSelection.svelte.js";

   import TranslateChaptersProcessingView from "@translate/chapters/TranslateChaptersProcessingView.svelte";
   import TranslateChaptersPreviewView from "@translate/chapters/TranslateChaptersPreviewView.svelte";
   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import ExecutionModeGate from "@shared/components/ExecutionModeGate.svelte";
   import FileList from "@shared/components/FileList.svelte";
   import TranslationSettings from "@shared/components/TranslationSettings.svelte";
   import Modal from "@shared/ui/Modal.svelte";
   import PromptEditorModal from "@shared/components/PromptEditorModal.svelte";
   import { persisted } from "@shared/state/persisted.svelte.js";

   let { goHome } = $props();

   const job = useToolRun("run_translate_chapters");
   const target = useExecutionTarget({ check: () => bridge.check_remote_translation_server() });

   // ── Archivos (cola) ──────────────────────────────────────────────────────────
   const selection = useFileSelection({
      pick: () =>
         bridge.pick_files(
            ["*.mp3", "*.wav", "*.m4a", "*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm"],
            appConfig.baseFolder,
            "audio",
         ),
      emptyHint: "Selecciona uno o más archivos con capítulos embebidos",
   });
   const fileInfos = $derived(selection.files);

   // ── Estado ───────────────────────────────────────────────────────────────────

   let publisherInfo = $state("");
   let showInfoModal = $state(false);

   let languages = $state([]); // ["japanese", "chinese", ...] — carpetas de prompts/
   const langConfig = persisted("translate_chapters_config", { selectedLanguage: "" });
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
   let settings = $state(undefined); // lo llena TranslationSettings (bind:settings)

   // Vista previa: null mientras se traduce; {files:[...]} apenas llega
   // audiotools:chapters:preview_ready, ANTES de que llegue el audiotools:done del job (ver
   // core/translation/job.py). No se usa progress.success para decidir qué mostrar durante
   // job.processing: previewData es justo esa señal.
   let previewData = $state(null);

   function onPreviewReady(e) {
      previewData = e.detail;
   }
   window.addEventListener("audiotools:chapters:preview_ready", onPreviewReady);
   $effect(() => () => window.removeEventListener("audiotools:chapters:preview_ready", onPreviewReady));

   function backToForm() {
      previewData = null;
      job.back();
   }

   // ── Carga inicial (idioma/prompt/glossary — independiente del modo) ─────────
   // El idioma ya viene de localStorage vía persisted() (langConfig, arriba); acá solo falta
   // elegir un default si no había nada guardado, y traer prompt/glossary de ESE idioma.

   $effect(() => {
      (async () => {
         languages = await bridge.list_prompt_languages();
         if (languages.length && !langConfig.selectedLanguage) {
            langConfig.selectedLanguage = languages.includes("japanese") ? "japanese" : languages[0];
            translationPrompt = await bridge.get_translation_prompt(langConfig.selectedLanguage, "chapters");
            glossaryText = await bridge.get_glossary(langConfig.selectedLanguage);
            promptDirty = false;
            glossaryDirty = false;
         }
      })();
   });

   // ── Lista de modelos ─────────────────────────────────────────────────────────
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

   const canRun = $derived(fileInfos.length > 0 && !!settings?.selectedModel && !progress.running);

   // ── Idioma / prompt / glosario ──────────────────────────────────────────────

   async function onSelectLanguage(lang) {
      langConfig.selectedLanguage = lang;
      translationPrompt = await bridge.get_translation_prompt(lang, "chapters");
      glossaryText = await bridge.get_glossary(lang);
      promptDirty = false;
      glossaryDirty = false;
   }
   function onPromptEdit() {
      promptDirty = true;
   }
   async function savePrompt() {
      await bridge.save_translation_prompt(langConfig.selectedLanguage, "chapters", translationPrompt);
      promptDirty = false;
   }
   function onGlossaryEdit() {
      glossaryDirty = true;
   }
   async function saveGlossary() {
      await bridge.save_glossary(langConfig.selectedLanguage, glossaryText);
      glossaryDirty = false;
   }

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      previewData = null;
      await job.start({
         file_paths: fileInfos.map((f) => f.path),
         raw_publisher_info: publisherInfo,
         base_prompt: translationPrompt,
         glossary: glossaryText,
         model: settings.selectedModel,
         n_gpu_layers: settings.nGpuLayers,
         n_ctx: settings.nCtx,
         temperature: settings.temperature,
         target: target.target,
      });
   }
</script>

{#if showInfoModal}
   <Modal onClose={() => (showInfoModal = false)} size="xl" height="max-85" label="Info del publisher" class="gap-4">
      <div class="flex items-center justify-between">
         <h2 class="text-sm font-semibold text-white">Info del publisher</h2>
         <button class="text-white/30 hover:text-white transition-colors cursor-pointer" onclick={() => (showInfoModal = false)}>
            ✕
         </button>
      </div>
      <textarea
         bind:value={publisherInfo}
         rows="16"
         placeholder="Pega la descripción / ficha del trabajo — ideal si describe cada capítulo por separado"
         class="w-full resize-y rounded-lg border border-white/10 bg-white/5 px-3 py-2
            text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
      ></textarea>
      <div class="flex justify-end">
         <button
            class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
            onclick={() => (showInfoModal = false)}
         >
            Listo
         </button>
      </div>
   </Modal>
{/if}

{#if showPromptModal}
   <PromptEditorModal
      title="Prompt"
      {languages}
      selectedLanguage={langConfig.selectedLanguage}
      {onSelectLanguage}
      bind:value={translationPrompt}
      dirty={promptDirty}
      onInput={onPromptEdit}
      onSave={savePrompt}
      onClose={() => (showPromptModal = false)}
   />
{/if}

{#if showGlossaryModal}
   <PromptEditorModal
      title="Glossary"
      description="Términos fijos por idioma, compartidos entre .srt, chapters y filenames — se inyectan solos en el prompt final."
      {languages}
      selectedLanguage={langConfig.selectedLanguage}
      {onSelectLanguage}
      bind:value={glossaryText}
      dirty={glossaryDirty}
      onInput={onGlossaryEdit}
      onSave={saveGlossary}
      onClose={() => (showGlossaryModal = false)}
   />
{/if}

{#if target.mode === null}
   <ExecutionModeGate
      title="Translate — Chapters"
      {goHome}
      {target}
      remoteTitle="Traducir en remoto"
      remoteDescription="Usa el server mediador de la red para traducir sin cargar el modelo en esta PC."
      localTitle="Traducir en esta PC"
      localDescription="Carga el modelo localmente, como siempre."
   />
{:else if job.processing}
   {#if previewData}
      <TranslateChaptersPreviewView files={previewData.files} onDiscard={backToForm} {goHome} />
   {:else}
      <TranslateChaptersProcessingView {goHome} {fileInfos} onCancel={job.cancel} />
   {/if}
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={target.mode === "remote" ? "Translate — Chapters (remoto)" : "Translate — Chapters"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <button
               class="self-start text-xs text-white/30 hover:text-white transition-colors cursor-pointer"
               onclick={target.change}
            >
               ← Cambiar modo (local/remoto)
            </button>

            <FileList
               fileInfos={selection.files}
               autoHint={selection.hint}
               onPickFiles={selection.pickFiles}
               onRemove={selection.remove}
               loading={selection.loading}
               label="Archivos"
               emptyText="Selecciona uno o más archivos con capítulos embebidos"
            />

            <!-- Info publisher + Prompt + Glossary -->
            <div class="grid grid-cols-3 gap-2">
               <button
                  class="flex items-center justify-between rounded-lg border px-3 py-2 text-xs text-left transition-all cursor-pointer
                     {publisherInfo.trim()
                     ? 'border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/50'
                     : 'border-white/10 bg-white/5 hover:border-white/20'}"
                  onclick={() => (showInfoModal = true)}
               >
                  <span class="text-white/60 truncate">Info</span>
                  <span class="{publisherInfo.trim() ? 'text-emerald-400' : 'text-white/20'} shrink-0 ml-2">
                     {publisherInfo.trim() ? "✓" : "—"}
                  </span>
               </button>
               <button
                  class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={() => (showPromptModal = true)}
               >
                  <span class="text-white/60 truncate">Prompt</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">{languageLabel(langConfig.selectedLanguage)}{promptDirty ? " ·" : ""}</span>
               </button>
               <button
                  class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2
                     text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={() => (showGlossaryModal = true)}
               >
                  <span class="text-white/60 truncate">Glossary</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">{languageLabel(langConfig.selectedLanguage)}{glossaryDirty ? " ·" : ""}</span>
               </button>
            </div>

            <TranslationSettings
               {target}
               {models}
               storageKey="translate_chapters"
               bind:settings
               noModelsLabel={target.mode === "remote" ? "Sin modelos en el mediador" : "Sin modelos en /models"}
               remoteNoModelsHint="Este mediador no tiene ningún .gguf copiado en translation_models/ todavía."
            />

            <p class="text-[11px] text-white/25">
               No se escribe nada hasta confirmar la vista previa — los archivos originales no se tocan hasta ese paso.
            </p>

            <button
               class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white transition-colors
                  hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
               onclick={run}
               disabled={!canRun}
            >
               Traducir capítulos
            </button>
         </div>
      </main>
   </div>
{/if}
