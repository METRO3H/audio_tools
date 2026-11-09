<script>
   import { bridge } from "@shared/services/bridge.svelte.js";
   import { progress } from "@shared/state/progress.svelte.js";
   import { useToolRun } from "@shared/state/useToolRun.svelte.js";
   import { useExecutionTarget } from "@shared/state/useExecutionTarget.svelte.js";
   import ViewHeader from "@shared/components/ViewHeader.svelte";
   import ExecutionModeGate from "@shared/components/ExecutionModeGate.svelte";
   import TranslationSettings from "@shared/components/TranslationSettings.svelte";
   import Modal from "@shared/ui/Modal.svelte";
   import PromptEditorModal from "@shared/components/PromptEditorModal.svelte";
   import ConfirmModal from "@shared/ui/ConfirmModal.svelte";
   import Spinner from "@shared/ui/Spinner.svelte";
   import LogsModal from "@shared/components/LogsModal.svelte";
   import { persisted } from "@shared/state/persisted.svelte.js";

   let { goHome } = $props();

   const job = useToolRun("run_translate_filenames_preview");
   const target = useExecutionTarget({ check: () => bridge.check_remote_translation_server() });

   // ── Carpeta / escaneo (instantáneo, sin IA — no pasa por el job contract) ────

   let folder = $state("");
   let scannedFiles = $state([]);
   let scanning = $state(false);

   async function pickFolder() {
      const picked = await bridge.pick_folder();
      if (!picked) return;
      folder = picked;
      previewData = null;
      applyResult = null;
      scanning = true;
      scannedFiles = await bridge.scan_filenames_folder(folder);
      scanning = false;
   }

   // ── Estado ───────────────────────────────────────────────────────────────────

   let publisherInfo = $state("");
   let showInfoModal = $state(false);

   let languages = $state([]);
   const langConfig = persisted("translate_filenames_config", { selectedLanguage: "" });
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

   let phaseText = $state("Iniciando...");
   let workInfoText = $state("");
   let translateStreamText = $state("");
   let showLogs = $state(false);
   let showModelLogModal = $state(false);
   let copyFeedback = $state("");

   let streamBoxEl = $state(null);
   let stickToBottom = $state(true);
   function onStreamScroll() {
      if (!streamBoxEl) return;
      const { scrollTop, scrollHeight, clientHeight } = streamBoxEl;
      stickToBottom = scrollHeight - (scrollTop + clientHeight) < 24;
   }
   $effect(() => {
      translateStreamText;
      if (stickToBottom && streamBoxEl) streamBoxEl.scrollTop = streamBoxEl.scrollHeight;
   });

   async function copyToClipboard(text, feedbackKey) {
      try {
         await navigator.clipboard.writeText(text);
         copyFeedback = feedbackKey;
         setTimeout(() => {
            if (copyFeedback === feedbackKey) copyFeedback = "";
         }, 1500);
      } catch {
         // clipboard no disponible
      }
   }

   // Vista previa: null mientras se traduce; {files:[...]} apenas llega
   // audiotools:translation:preview_ready, ANTES del audiotools:done del job (ver
   // core/translation/job.py::run_translate_filenames_job) — mismo patrón que Chapters.
   let previewData = $state(null);
   // Copia editable: cada fila de previewData.files + {checked, title} — "title" es lo que se
   // termina mandando a apply_filename_renames (arranca igual al traducido, editable a mano;
   // antes NO se podía editar, solo aceptar/descartar tal cual venía del modelo).
   let previewRows = $state([]);
   let applyResult = $state(null);

   function onPreviewReady(e) {
      previewData = e.detail;
      previewRows = e.detail.files.map((f) => ({ ...f, checked: f.needs_translation, title: f.translated_name }));
   }
   function onPhase(e) {
      phaseText = e.detail.phase;
   }
   function onWorkInfoStream(e) {
      workInfoText = e.detail.text;
   }
   // El stream trae el texto crudo del modelo (con <think> y espacios); el final es el que el
   // runner realmente usa en el prompt, ya limpio. Igual que SRT, el final reemplaza al stream.
   function onWorkInfoFinal(e) {
      workInfoText = e.detail.work_info;
   }
   function onNameStream(e) {
      translateStreamText = e.detail.text;
   }
   window.addEventListener("audiotools:translation:preview_ready", onPreviewReady);
   window.addEventListener("audiotools:translation:phase", onPhase);
   window.addEventListener("audiotools:translation:work_info_stream", onWorkInfoStream);
   window.addEventListener("audiotools:translation:work_info", onWorkInfoFinal);
   window.addEventListener("audiotools:translation:name_stream", onNameStream);
   $effect(() => () => {
      window.removeEventListener("audiotools:translation:preview_ready", onPreviewReady);
      window.removeEventListener("audiotools:translation:phase", onPhase);
      window.removeEventListener("audiotools:translation:work_info_stream", onWorkInfoStream);
      window.removeEventListener("audiotools:translation:work_info", onWorkInfoFinal);
      window.removeEventListener("audiotools:translation:name_stream", onNameStream);
   });

   function backToForm() {
      previewData = null;
      previewRows = [];
      applyResult = null;
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
            translationPrompt = await bridge.get_translation_prompt(langConfig.selectedLanguage, "filenames");
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

   const needsCount = $derived(scannedFiles.filter((f) => f.needs_translation).length);
   const canRun = $derived(needsCount > 0 && !!settings?.selectedModel && !progress.running);
   const checkedCount = $derived(previewRows.filter((f) => f.checked).length);

   const groupedPreview = $derived.by(() => {
      const byRelPath = new Map(previewRows.map((f) => [f.relative_path, f]));
      const groups = {};
      for (const f of previewRows) {
         const parts = f.relative_path.split(/[\\/]/);
         const dir = parts.slice(0, -1).join("/") || ".";
         if (!groups[dir]) groups[dir] = [];
         groups[dir].push(f);
      }
      for (const dir of Object.keys(groups)) {
         if (dir === ".") continue;
         const dirEntry = byRelPath.get(dir);
         if (!dirEntry) continue;
         const parentKey = dir.includes("/") ? dir.slice(0, dir.lastIndexOf("/")) : ".";
         const parentGroup = groups[parentKey];
         const idx = parentGroup ? parentGroup.indexOf(dirEntry) : -1;
         if (idx !== -1) parentGroup.splice(idx, 1);
      }
      return Object.entries(groups)
         .sort(([a], [b]) => a.localeCompare(b))
         .map(([dir, entries]) => [dir, entries, dir !== "." ? (byRelPath.get(dir) ?? null) : null]);
   });

   function baseName(p) {
      const parts = p.split(/[\\/]/);
      return parts[parts.length - 1] || p;
   }

   // ── Idioma / prompt / glosario ──────────────────────────────────────────────

   async function onSelectLanguage(lang) {
      langConfig.selectedLanguage = lang;
      translationPrompt = await bridge.get_translation_prompt(lang, "filenames");
      glossaryText = await bridge.get_glossary(lang);
      promptDirty = false;
      glossaryDirty = false;
   }
   function onPromptEdit() {
      promptDirty = true;
   }
   async function savePrompt() {
      await bridge.save_translation_prompt(langConfig.selectedLanguage, "filenames", translationPrompt);
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
      previewRows = [];
      phaseText = "Iniciando...";
      workInfoText = "";
      translateStreamText = "";
      stickToBottom = true;
      await job.start({
         files: scannedFiles,
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

   // "← Inicio" con la traducción en curso: mismo criterio que SRT/Chapters.
   let showLeaveConfirm = $state(false);
   function requestGoHome() {
      if (progress.running) {
         showLeaveConfirm = true;
      } else {
         goHome();
      }
   }
   function confirmLeave() {
      showLeaveConfirm = false;
      job.cancel();
      goHome();
   }

   // ── Confirmar renombrado ─────────────────────────────────────────────────────

   async function applyRenames() {
      const renames = previewRows.filter((f) => f.checked && f.needs_translation).map((f) => [f.path, f.title]);
      if (!renames.length) {
         backToForm();
         return;
      }
      applyResult = await bridge.apply_filename_renames(renames);
   }

   async function rescan() {
      backToForm();
      scanning = true;
      scannedFiles = await bridge.scan_filenames_folder(folder);
      scanning = false;
   }
</script>

{#if showLeaveConfirm}
   <ConfirmModal
      title="Hay una traducción en curso"
      message="Si vuelves al inicio ahora, se cancela. ¿Seguro que quieres salir?"
      confirmLabel="Cancelar y volver al inicio"
      cancelLabel="Seguir traduciendo"
      danger
      onConfirm={confirmLeave}
      onCancel={() => (showLeaveConfirm = false)}
   />
{/if}

{#if showInfoModal}
   <Modal onClose={() => (showInfoModal = false)} size="xl" height="max-85" label="Info del publisher" class="gap-4">
      <div class="flex items-center justify-between">
         <h2 class="text-sm font-semibold text-white">Info del publisher</h2>
         <button class="text-white/30 hover:text-white transition-colors cursor-pointer" onclick={() => (showInfoModal = false)}>✕</button>
      </div>
      <textarea
         bind:value={publisherInfo}
         rows="16"
         placeholder="Pega la descripción / ficha del trabajo (opcional)"
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

{#if showLogs}
   <LogsModal logs={progress.logs} onClose={() => (showLogs = false)} />
{/if}

{#if showModelLogModal}
   <Modal onClose={() => (showModelLogModal = false)} size="2xl" height="max-85" label="Log del modelo" class="gap-4">
      <div class="flex items-center justify-between shrink-0">
         <h2 class="text-sm font-semibold text-white">Log del modelo</h2>
         <button class="text-white/30 hover:text-white transition-colors cursor-pointer" onclick={() => (showModelLogModal = false)}>✕</button>
      </div>
      <p class="text-[11px] text-white/30 shrink-0">
         Salida cruda tal cual la generó el modelo (incluye razonamiento si el modelo lo generó, sin filtrar nada).
      </p>
      <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60">{translateStreamText}</pre>
      <div class="flex justify-end gap-2 shrink-0 border-t border-white/5 pt-4">
         <button
            class="rounded-lg border border-white/10 px-4 py-2 text-xs text-white/60 hover:text-white transition-colors cursor-pointer"
            onclick={() => copyToClipboard(translateStreamText, "modal")}
         >
            {copyFeedback === "modal" ? "Copiado" : "Copiar"}
         </button>
         <button
            class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors cursor-pointer"
            onclick={() => (showModelLogModal = false)}
         >
            Cerrar
         </button>
      </div>
   </Modal>
{/if}

{#if target.mode === null}
   <ExecutionModeGate
      title="Translate — Nombres de archivo"
      {goHome}
      {target}
      remoteTitle="Traducir en remoto"
      remoteDescription="Usa el server mediador de la red para traducir sin cargar el modelo en esta PC."
      localTitle="Traducir en esta PC"
      localDescription="Carga el modelo localmente, como siempre."
   />
{:else if job.processing && !previewData}
   <div class="flex h-full flex-col">
      <div class="flex items-center justify-between px-6 py-4 shrink-0">
         <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={requestGoHome}> ← Inicio </button>
         <div class="flex items-center gap-2">
            {#if progress.running}<Spinner size={14} duration="1.5s" />{/if}
            <button
               class="rounded-md border border-red-500/20 bg-red-500/10 px-2.5 py-1 text-xs text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer"
               onclick={job.cancel}
            >
               Cancelar
            </button>
            <button
               class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors cursor-pointer"
               onclick={() => (showLogs = !showLogs)}
            >
               Logs
            </button>
         </div>
      </div>

      <main class="flex flex-1 min-h-0 flex-col items-center px-8 py-10">
         <div class="flex w-full max-w-xl flex-1 min-h-0 flex-col gap-4">
            <div class="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3 shrink-0">
               <Spinner size={14} duration="1.5s" />
               <span class="text-sm text-white/80">{phaseText}</span>
            </div>

            {#if workInfoText}
               <div class="flex flex-col gap-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2 shrink-0">
                  <span class="text-[11px] text-white/30">Work info</span>
                  <p class="text-xs text-white/50 whitespace-pre-wrap max-h-32 overflow-y-auto">{workInfoText}</p>
               </div>
            {/if}

            {#if translateStreamText}
               <div class="flex flex-1 min-h-0 flex-col gap-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                  <div class="flex items-center justify-between shrink-0">
                     <span class="text-[11px] text-white/30">Traduciendo — salida del modelo en vivo</span>
                     <button
                        class="text-[11px] text-white/30 hover:text-white transition-colors cursor-pointer"
                        onclick={() => copyToClipboard(translateStreamText, "stream")}
                     >
                        {copyFeedback === "stream" ? "Copiado" : "Copiar"}
                     </button>
                  </div>
                  <p
                     bind:this={streamBoxEl}
                     onscroll={onStreamScroll}
                     class="flex-1 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-white/60"
                  >{translateStreamText}</p>
               </div>
            {/if}
         </div>
      </main>
   </div>
{:else if job.processing && previewData}
   {#if applyResult}
      <div class="flex h-full flex-col">
         <ViewHeader title="Translate — Resultado" {goHome} />
         <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
            <div class="flex w-full max-w-2xl flex-1 flex-col gap-4">
               <h2 class="text-sm font-semibold text-white shrink-0">
                  Listo — {applyResult.renamed.length} renombrado{applyResult.renamed.length === 1 ? "" : "s"}
                  {#if applyResult.errors.length}
                     <span class="text-red-400"> · {applyResult.errors.length} con error{applyResult.errors.length === 1 ? "" : "es"}</span>
                  {/if}
               </h2>

               <div class="flex flex-1 flex-col gap-4 overflow-y-auto" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
                  {#if applyResult.renamed.length}
                     <div class="flex flex-col gap-1">
                        <span class="text-[11px] text-white/30">Renombrados</span>
                        <table class="w-full border-separate border-spacing-0 text-xs">
                           <tbody>
                              {#each applyResult.renamed as r (r.old)}
                                 <tr class="hover:bg-white/5">
                                    <td class="max-w-[280px] truncate py-1 align-middle text-white/50">{baseName(r.old)}</td>
                                    <td class="w-6 py-1 align-middle text-white/20">→</td>
                                    <td class="max-w-[280px] truncate py-1 align-middle text-emerald-400/80">{baseName(r.new)}</td>
                                 </tr>
                              {/each}
                           </tbody>
                        </table>
                     </div>
                  {/if}
                  {#if applyResult.errors.length}
                     <div class="flex flex-col gap-1">
                        <span class="text-[11px] text-red-400/70">Errores</span>
                        <div class="flex flex-col gap-1">
                           {#each applyResult.errors as err (err.path)}
                              <div class="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-1.5 text-xs">
                                 <div class="text-white/50">{baseName(err.path)}</div>
                                 <div class="text-red-400/80 text-[11px]">{err.error}</div>
                              </div>
                           {/each}
                        </div>
                     </div>
                  {/if}
               </div>

               <div class="flex justify-end shrink-0 border-t border-white/5 pt-4">
                  <button class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors cursor-pointer" onclick={rescan}>
                     Volver
                  </button>
               </div>
            </div>
         </main>
      </div>
   {:else}
      <div class="flex h-full flex-col">
         <ViewHeader title="Translate — Seleccionar renombres" {goHome} />
         <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
            <div class="flex w-full max-w-3xl flex-1 flex-col gap-4">
               <div class="flex items-center justify-between shrink-0">
                  <h2 class="text-sm font-semibold text-white">
                     {checkedCount} de {previewRows.filter((f) => f.needs_translation).length} marcados
                  </h2>
                  {#if translateStreamText}
                     <button
                        class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors cursor-pointer"
                        onclick={() => (showModelLogModal = true)}
                     >
                        Ver log del modelo
                     </button>
                  {/if}
               </div>

               <div class="flex-1 overflow-y-auto" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
                  <table class="w-full border-separate border-spacing-0 text-xs">
                     <thead>
                        <tr class="text-white/30">
                           <th class="w-7 pb-1 text-left font-normal"></th>
                           <th class="w-6 pb-1 text-left font-normal"></th>
                           <th class="pb-1 text-left font-normal">Nombre original</th>
                           <th class="pb-1 text-left font-normal">Nombre traducido</th>
                        </tr>
                     </thead>
                     <tbody>
                        {#each groupedPreview as [dir, entries, dirEntry] (dir)}
                           {#if dirEntry}
                              <tr class={dirEntry.needs_translation ? "hover:bg-white/5" : "opacity-35"}>
                                 <td class="pt-3 pb-1 align-middle">
                                    <input type="checkbox" bind:checked={dirEntry.checked} disabled={!dirEntry.needs_translation} class="accent-indigo-500" />
                                 </td>
                                 <td class="pt-3 pb-1 align-middle text-white/30" title="Carpeta">📁</td>
                                 <td class="max-w-[280px] truncate pt-3 pb-1 align-middle font-mono text-[11px] text-white/40">{dir}</td>
                                 {#if dirEntry.needs_translation}
                                    <td class="max-w-[220px] pt-3 pb-1 align-middle">
                                       <input
                                          type="text"
                                          bind:value={dirEntry.title}
                                          disabled={!dirEntry.checked}
                                          class="w-full rounded border border-white/10 bg-white/5 px-2 py-1
                                             text-emerald-400/90 outline-none focus:border-indigo-500/50 transition-colors disabled:opacity-40"
                                       />
                                    </td>
                                 {:else}
                                    <td class="pt-3 pb-1 align-middle text-[10px] text-white/20">(ya en inglés)</td>
                                 {/if}
                              </tr>
                           {:else}
                              <tr>
                                 <td colspan="4" class="pt-3 pb-1 font-mono text-[11px] text-white/30">{dir === "." ? "/" : dir}</td>
                              </tr>
                           {/if}
                           {#each entries as f (f.path)}
                              <tr class={f.needs_translation ? "hover:bg-white/5" : "opacity-35"}>
                                 <td class="py-1.5 pl-4 align-middle">
                                    <input type="checkbox" bind:checked={f.checked} disabled={!f.needs_translation} class="accent-indigo-500" />
                                 </td>
                                 <td class="py-1.5 align-middle text-white/30" title={f.is_dir ? "Carpeta" : "Archivo"}>{f.is_dir ? "📁" : "📄"}</td>
                                 <td class="max-w-[280px] truncate py-1.5 align-middle text-white/50">{f.name}</td>
                                 {#if f.needs_translation}
                                    <td class="max-w-[220px] py-1.5 align-middle">
                                       <input
                                          type="text"
                                          bind:value={f.title}
                                          disabled={!f.checked}
                                          class="w-full rounded border border-white/10 bg-white/5 px-2 py-1
                                             text-emerald-400/90 outline-none focus:border-indigo-500/50 transition-colors disabled:opacity-40"
                                       />
                                    </td>
                                 {:else}
                                    <td class="py-1.5 align-middle text-[10px] text-white/20">(ya en inglés)</td>
                                 {/if}
                              </tr>
                           {/each}
                        {/each}
                     </tbody>
                  </table>
               </div>

               <div class="flex justify-end gap-2 shrink-0 border-t border-white/5 pt-4">
                  <button class="rounded-lg border border-white/10 px-4 py-2 text-xs text-white/60 hover:text-white transition-colors cursor-pointer" onclick={backToForm}>
                     Descartar
                  </button>
                  <button
                     class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-30 cursor-pointer"
                     onclick={applyRenames}
                     disabled={checkedCount === 0}
                  >
                     Renombrar {checkedCount} elemento{checkedCount === 1 ? "" : "s"}
                  </button>
               </div>
            </div>
         </main>
      </div>
   {/if}
{:else}
   <div class="flex h-full flex-col">
      <ViewHeader title={target.mode === "remote" ? "Translate — Nombres de archivo (remoto)" : "Translate — Nombres de archivo"} {goHome} />

      <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
         <div class="flex w-full max-w-md flex-col gap-5">
            <button class="self-start text-xs text-white/30 hover:text-white transition-colors cursor-pointer" onclick={target.change}>
               ← Cambiar modo (local/remoto)
            </button>

            <!-- Carpeta -->
            <div class="flex flex-col gap-1.5">
               <span class="text-xs text-white/40">Carpeta (se escanea recursivamente)</span>
               <button
                  class="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={pickFolder}
               >
                  <span>📁</span>
                  <span class="truncate text-white/60">{folder || "Sin seleccionar"}</span>
               </button>
            </div>

            {#if scanning}
               <div class="flex items-center gap-2 text-xs text-white/40">
                  <Spinner size={12} duration="1.5s" /> Escaneando...
               </div>
            {:else if scannedFiles.length}
               <div class="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/60">
                  {scannedFiles.length} elementos encontrados — {needsCount} necesitan traducción
                  <span class="text-white/25">(detectado sin IA)</span>
               </div>
            {:else if folder}
               <div class="rounded-lg border border-dashed border-white/10 p-4 text-center text-xs text-white/20">
                  No se encontraron archivos ni carpetas
               </div>
            {/if}

            <!-- Info publisher + Prompt + Glossary -->
            <div class="grid grid-cols-3 gap-2">
               <button
                  class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={() => (showInfoModal = true)}
               >
                  <span class="text-white/60 truncate">Info</span>
                  <span class="{publisherInfo.trim() ? 'text-emerald-400' : 'text-white/30'} shrink-0 ml-2">{publisherInfo.trim() ? "✓" : "—"}</span>
               </button>
               <button
                  class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={() => (showPromptModal = true)}
               >
                  <span class="text-white/60 truncate">Prompt</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">{languageLabel(langConfig.selectedLanguage)}{promptDirty ? " ·" : ""}</span>
               </button>
               <button
                  class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20 cursor-pointer"
                  onclick={() => (showGlossaryModal = true)}
               >
                  <span class="text-white/60 truncate">Glossary</span>
                  <span class="text-white/30 shrink-0 ml-2 truncate">{languageLabel(langConfig.selectedLanguage)}{glossaryDirty ? " ·" : ""}</span>
               </button>
            </div>

            <TranslationSettings
               {target}
               {models}
               storageKey="translate_filenames"
               bind:settings
               noModelsLabel={target.mode === "remote" ? "Sin modelos en el mediador" : "Sin modelos en /models"}
               remoteNoModelsHint="Este mediador no tiene ningún .gguf copiado en translation_models/ todavía."
            />

            <button
               class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
               onclick={run}
               disabled={!canRun}
            >
               Traducir nombres ({needsCount})
            </button>
         </div>
      </main>
   </div>
{/if}
