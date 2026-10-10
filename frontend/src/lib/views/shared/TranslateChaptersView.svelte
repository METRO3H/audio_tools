<script>
   import { bridge } from "$lib/stores/bridge.svelte.js";
   import { progress } from "$lib/stores/progress.svelte.js";
   import { appConfig } from "$lib/stores/config.svelte.js";
   import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
   import LogsModal from "$lib/components/LogsModal.svelte";
   import Spinner from "$lib/components/Spinner.svelte";
   import BaseFolderPicker from "$lib/components/BaseFolderPicker.svelte";
   import { persistentConfig } from "$lib/stores/persistentConfig.js";

   let { goHome } = $props();

   // ── Selección local / remoto ─────────────────────────────────────────────────
   // Mismo patrón que TranscribeView.svelte / TranslateSrtView.svelte: se
   // pregunta cada vez que se entra a la vista, bloquea el resto del
   // formulario hasta elegir.
   let mode = $state(null); // null | "local" | "remote"
   let checkingRemote = $state(false);
   let remoteError = $state("");
   let remoteInfo = $state(null); // { host, port, models, state, busy_model }

   // ── Estado ───────────────────────────────────────────────────────────────────

   let fileInfo = $state(null); // {name, path, size_mb, duration_seconds}
   let chapters = $state([]); // [{index, title, start, end}]

   let publisherInfo = $state("");
   let showInfoModal = $state(false);

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

   let processing = $state(false);
   let phaseText = $state("");
   let workInfoText = $state("");
   let showLogs = $state(false);
   let done = $state(null); // null | true | false

   // ── Cargar configuración guardada ────────────────────────────────────────────
   // selectedModel/nGpuLayers/nCtx/temperature se guardan aparte por modo
   // (ver selectLocal/selectRemote) — mismo motivo que en TranslateSrtView.

   $effect(() => {
      const saved = persistentConfig.get("translate_chapters_config");
      if (saved) {
         selectedLanguage = saved.selectedLanguage ?? "";
      }
   });

   // ── Guardar configuración al cambiar ────────────────────────────────────────

   $effect(() => {
      persistentConfig.set("translate_chapters_config", { selectedLanguage });
   });

   $effect(() => {
      if (!mode) return;
      const key = mode === "local" ? "translate_chapters_local_config" : "translate_chapters_remote_config";
      persistentConfig.set(key, { selectedModel, nGpuLayers, nCtx, temperature });
   });

   // ── Carga inicial (idioma/prompt/glossary — independiente del modo) ─────────

   $effect(() => {
      (async () => {
         languages = await bridge.list_prompt_languages();
         if (languages.length && !selectedLanguage) {
            selectedLanguage = languages.includes("japanese") ? "japanese" : languages[0];
            translationPrompt = await bridge.get_translation_prompt(selectedLanguage, "chapters");
            glossaryText = await bridge.get_glossary(selectedLanguage);
            promptDirty = false;
            glossaryDirty = false;
         }
      })();
   });

   // ── Selección local / remoto ─────────────────────────────────────────────────

   async function selectLocal() {
      mode = "local";
      const saved = persistentConfig.get("translate_chapters_local_config");
      nGpuLayers = saved?.nGpuLayers ?? 20;
      nCtx = saved?.nCtx ?? 4096;
      temperature = saved?.temperature ?? 0.3;
      models = await bridge.list_translation_models();
      selectedModel =
         saved?.selectedModel && models.includes(saved.selectedModel) ? saved.selectedModel : (models[0] ?? "");
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
      const saved = persistentConfig.get("translate_chapters_remote_config");
      nGpuLayers = saved?.nGpuLayers ?? 0;
      nCtx = saved?.nCtx ?? 4096;
      temperature = saved?.temperature ?? 0.3;
      models = result.models;
      selectedModel =
         saved?.selectedModel && models.includes(saved.selectedModel) ? saved.selectedModel : (models[0] ?? "");
      mode = "remote";
   }

   function changeMode() {
      mode = null;
      remoteError = "";
   }

   // ── Derivados ────────────────────────────────────────────────────────────────

   const outputPath = $derived(fileInfo ? fileInfo.path.replace(/(\.[^./\\]+)$/, " [EN]$1") : "");
   const canRun = $derived(!!fileInfo && chapters.length > 0 && !!selectedModel && !processing);

   // ── Archivo ──────────────────────────────────────────────────────────────────

   async function pickFile() {
      const paths = await bridge.pick_files(
         ["*.mp3", "*.wav", "*.m4a", "*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm"],
         appConfig.baseFolder,
         "audio",
      );
      if (!paths.length) return;
      const info = await bridge.get_file_info(paths[0]);
      fileInfo = { ...info, path: paths[0] };
      chapters = await bridge.get_chapters_for_file(paths[0]);
      done = null;
   }

   // ── Idioma / prompt / glosario ──────────────────────────────────────────────

   async function onSelectLanguage(lang) {
      selectedLanguage = lang;
      translationPrompt = await bridge.get_translation_prompt(lang, "chapters");
      glossaryText = await bridge.get_glossary(lang);
      promptDirty = false;
      glossaryDirty = false;
   }
   function onPromptEdit() {
      promptDirty = true;
   }
   async function savePrompt() {
      await bridge.save_translation_prompt(selectedLanguage, "chapters", translationPrompt);
      promptDirty = false;
   }
   function onGlossaryEdit() {
      glossaryDirty = true;
   }
   async function saveGlossary() {
      await bridge.save_glossary(selectedLanguage, glossaryText);
      glossaryDirty = false;
   }

   // ── Eventos de progreso propios ──────────────────────────────────────────────

   function onPhase(e) {
      phaseText = e.detail.phase;
   }
   function onWorkInfoStream(e) {
      workInfoText = e.detail.text;
   }
   function onDoneEvt(e) {
      processing = false;
      done = e.detail.success;
   }

   window.addEventListener("audiotools:chapters:phase", onPhase);
   window.addEventListener("audiotools:chapters:work_info_stream", onWorkInfoStream);
   window.addEventListener("audiotools:chapters:done", onDoneEvt);

   // ── Ejecutar ─────────────────────────────────────────────────────────────────

   async function run() {
      if (!canRun) return;
      processing = true;
      done = null;
      phaseText = "Iniciando...";
      workInfoText = "";
      progress.logs = [];

      await bridge.run_translate_chapters(
         fileInfo.path,
         outputPath,
         chapters,
         publisherInfo,
         translationPrompt,
         glossaryText,
         selectedModel,
         nGpuLayers,
         nCtx,
         temperature,
         mode === "remote" ? remoteInfo.host : null,
         mode === "remote" ? remoteInfo.port : null,
      );
   }

   function cancel() {
      bridge.cancel_translate_chapters();
   }
</script>

{#if showInfoModal}
   <div
      class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
      role="presentation"
      onclick={() => (showInfoModal = false)}
   ></div>
   <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div
         class="w-full max-w-xl max-h-[85vh] overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4"
      >
         <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-white">Info del publisher</h2>
            <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showInfoModal = false)}
               >✕</button
            >
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
            <h2 class="text-sm font-semibold text-white">Prompt {promptDirty ? "· sin guardar" : ""}</h2>
            <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showPromptModal = false)}
               >✕</button
            >
         </div>
         <div class="flex items-center gap-2 shrink-0">
            <select
               value={selectedLanguage}
               onchange={(e) => onSelectLanguage(e.target.value)}
               class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
            >
               {#each languages as lang (lang)}<option value={lang}>{languageLabel(lang)}</option>{/each}
            </select>
            <button
               class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10"
               onclick={savePrompt}
               title="Guardar">💾</button
            >
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
            <h2 class="text-sm font-semibold text-white">Glossary {glossaryDirty ? "· sin guardar" : ""}</h2>
            <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showGlossaryModal = false)}
               >✕</button
            >
         </div>
         <p class="text-[11px] text-white/30 shrink-0">
            Términos fijos por idioma, compartidos entre .srt, chapters y filenames — se inyectan solos en el prompt
            final.
         </p>
         <div class="flex items-center gap-2 shrink-0">
            <select
               value={selectedLanguage}
               onchange={(e) => onSelectLanguage(e.target.value)}
               class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
            >
               {#each languages as lang (lang)}<option value={lang}>{languageLabel(lang)}</option>{/each}
            </select>
            <button
               class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10"
               onclick={saveGlossary}
               title="Guardar">💾</button
            >
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

{#if showLogs}
   <LogsModal logs={progress.logs} onClose={() => (showLogs = false)} />
{/if}

{#if mode === null}
   <div class="flex h-full flex-col">
      <ViewHeader title="Translate — Chapters" {goHome} />

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
                     <span class="text-sm font-semibold text-white tracking-wide"> Traducir en remoto </span>
                     <span class="text-xs text-white/50 leading-relaxed">
                        Usa el server mediador de la red para traducir sin cargar el modelo en esta PC.
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
               <span class="text-sm font-semibold text-white tracking-wide"> Traducir en esta PC </span>
               <span class="text-xs text-white/50 leading-relaxed"> Carga el modelo localmente, como siempre. </span>
            </button>
         </div>
      </main>
   </div>
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={mode === "remote" ? "Translate — Chapters (remoto)" : "Translate — Chapters"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            {#if !processing && done === null}
               <button class="self-start text-xs text-white/30 hover:text-white transition-colors" onclick={changeMode}>
                  ← Cambiar modo (local/remoto)
               </button>

               <!-- Archivo -->
               <div class="flex flex-col gap-1.5">
                  <div class="flex items-center justify-between">
                     <span class="text-xs text-white/40">Archivo</span>
                     <button class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors" onclick={pickFile}>
                        Seleccionar
                     </button>
                  </div>
                  {#if fileInfo}
                     <div
                        class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2"
                     >
                        <span class="truncate text-xs text-white/70">{fileInfo.name}</span>
                        <span class="text-xs text-white/30 shrink-0 ml-2">{chapters.length} chapters</span>
                     </div>
                  {:else}
                     <div class="rounded-lg border border-dashed border-white/10 p-4 text-center text-xs text-white/20">
                        Selecciona un archivo con chapters embebidos
                     </div>
                  {/if}
               </div>

               {#if chapters.length}
                  <ul class="flex flex-col gap-1 overflow-y-auto max-h-48">
                     {#each chapters as ch (ch.index)}
                        <li class="rounded-lg bg-white/5 px-3 py-1.5 text-xs text-white/60">
                           [{ch.index}] {ch.title}
                        </li>
                     {/each}
                  </ul>
               {:else if fileInfo}
                  <span class="text-xs text-yellow-400">⚠ Este archivo no tiene chapters embebidos</span>
               {/if}

               <!-- Info publisher + Prompt + Glossary en una fila -->
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
                     class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
                     onclick={() => (showPromptModal = true)}
                  >
                     <span class="text-white/60 truncate">Prompt</span>
                     <span class="text-white/30 shrink-0 ml-2 truncate"
                        >{languageLabel(selectedLanguage)}{promptDirty ? " ·" : ""}</span
                     >
                  </button>
                  <button
                     class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
                     onclick={() => (showGlossaryModal = true)}
                  >
                     <span class="text-white/60 truncate">Glossary</span>
                     <span class="text-white/30 shrink-0 ml-2 truncate"
                        >{languageLabel(selectedLanguage)}{glossaryDirty ? " ·" : ""}</span
                     >
                  </button>
               </div>

               <!-- Modelo -->
               <div class="flex flex-col gap-1.5">
                  <span class="text-xs text-white/40">Modelo</span>
                  <select
                     bind:value={selectedModel}
                     class="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
                  >
                     {#if !models.length}
                        <option value="">
                           {mode === "remote" ? "Sin modelos en el mediador" : "Sin modelos en /models"}
                        </option>
                     {/if}
                     {#each models as m (m)}<option value={m}>{m}</option>{/each}
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
                        class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
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
                        class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
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
                        class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors"
                     />
                  </div>
               </div>

               {#if outputPath}
                  <span class="text-[11px] text-white/25 truncate">Salida: {outputPath}</span>
               {/if}

               <button
                  class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed"
                  onclick={run}
                  disabled={!canRun}
               >
                  Ejecutar traducción
               </button>
            {:else}
               <!-- Progreso simple -->
               <div class="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                  {#if processing}<Spinner size={14} duration="1.5s" />{/if}
                  <span class="text-sm text-white/80">
                     {#if done === true}Completado ✓{:else if done === false}Falló / cancelado ✕{:else}{phaseText}{/if}
                  </span>
               </div>

               {#if workInfoText}
                  <div class="flex flex-col gap-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                     <span class="text-[11px] text-white/30">Work info</span>
                     <p class="text-xs text-white/50 whitespace-pre-wrap max-h-40 overflow-y-auto">{workInfoText}</p>
                  </div>
               {/if}

               <div class="flex gap-2">
                  {#if processing}
                     <button
                        class="flex-1 rounded-lg border border-red-500/30 py-2 text-xs text-red-400 hover:bg-red-500/10 transition-colors"
                        onclick={cancel}
                     >
                        Detener
                     </button>
                  {/if}
                  <button
                     class="flex-1 rounded-lg border border-white/10 py-2 text-xs text-white/60 hover:text-white transition-colors"
                     onclick={() => (showLogs = true)}
                  >
                     Ver logs
                  </button>
               </div>

               {#if done !== null && !processing}
                  <div class="flex gap-2">
                     {#if done === true}
                        <button
                           class="flex-1 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-xs text-white/60 hover:text-white transition-colors"
                           onclick={() => bridge.open_folder(outputPath)}
                        >
                           Abrir carpeta
                        </button>
                     {/if}
                     <button
                        class="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
                        onclick={() => {
                           done = null;
                        }}
                     >
                        Volver
                     </button>
                  </div>
               {/if}
            {/if}
         </div>
      </main>
   </div>
{/if}
