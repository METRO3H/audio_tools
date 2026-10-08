
<script>
  import { bridge } from "$lib/stores/bridge.svelte.js";
  import { progress } from "$lib/stores/progress.svelte.js";
  import ViewHeader from "$lib/views/shared/ViewHeader.svelte";
  import LogsModal from "$lib/components/LogsModal.svelte";
  import Spinner from "$lib/components/Spinner.svelte";
  import BaseFolderPicker from "$lib/components/BaseFolderPicker.svelte";
  import { persistentConfig } from "$lib/stores/persistentConfig.js";

  let { goHome } = $props();

  // ── Selección local / remoto ─────────────────────────────────────────────────
  // Mismo patrón que TranscribeView.svelte / TranslateSrtView.svelte /
  // TranslateChaptersView.svelte: se pregunta cada vez que se entra a la
  // vista, bloquea el resto del formulario (etapa "config") hasta elegir.
  let mode = $state(null); // null | "local" | "remote"
  let checkingRemote = $state(false);
  let remoteError = $state("");
  let remoteInfo = $state(null); // { host, port, models, state, busy_model }

  // ── Estado ───────────────────────────────────────────────────────────────────

  let stage = $state("config");

  let folder = $state("");
  let scannedFiles = $state([]);

  let publisherInfo = $state("");
  let showInfoModal = $state(false);

  let languages = $state([]);
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

  let scanning = $state(false);
  let phaseText = $state("");
  let workInfoText = $state("");
  let translateStreamText = $state("");
  let showLogs = $state(false);

  let previewFiles = $state([]);
  let applyResult = $state(null);

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
    if (stickToBottom && streamBoxEl) {
      streamBoxEl.scrollTop = streamBoxEl.scrollHeight;
    }
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

  // ── Cargar configuración guardada ────────────────────────────────────────────
  // selectedModel/nGpuLayers/nCtx/temperature se guardan aparte por modo
  // (ver selectLocal/selectRemote) — mismo motivo que en las otras dos
  // vistas de traducción.

  $effect(() => {
    const saved = persistentConfig.get('translate_filenames_config');
    if (saved) {
      selectedLanguage = saved.selectedLanguage ?? "";
    }
  });

  // ── Guardar configuración al cambiar ────────────────────────────────────────

  $effect(() => {
    persistentConfig.set('translate_filenames_config', { selectedLanguage });
  });

  $effect(() => {
    if (!mode) return;
    const key = mode === "local" ? "translate_filenames_local_config" : "translate_filenames_remote_config";
    persistentConfig.set(key, { selectedModel, nGpuLayers, nCtx, temperature });
  });

  // ── Carga inicial (idioma/prompt/glossary — independiente del modo) ─────────

  $effect(() => {
    (async () => {
      languages = await bridge.list_prompt_languages();
      if (languages.length && !selectedLanguage) {
        selectedLanguage = languages.includes("japanese") ? "japanese" : languages[0];
        translationPrompt = await bridge.get_translation_prompt(selectedLanguage, "filenames");
        glossaryText = await bridge.get_glossary(selectedLanguage);
        promptDirty = false;
        glossaryDirty = false;
      }
    })();
  });

  // ── Selección local / remoto ─────────────────────────────────────────────────

  async function selectLocal() {
    mode = "local";
    const saved = persistentConfig.get("translate_filenames_local_config");
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
      remoteError = `El mediador está ocupado en este momento (modelo: ${result.busy_model ?? "desconocido"}). Probá de nuevo en un rato.`;
      return;
    }

    remoteInfo = result;
    const saved = persistentConfig.get("translate_filenames_remote_config");
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

  const needsCount = $derived(scannedFiles.filter((f) => f.needs_translation).length);
  const canRun = $derived(needsCount > 0 && !!selectedModel && stage === "config");

  const groupedPreview = $derived.by(() => {
    const byRelPath = new Map(previewFiles.map((f) => [f.relative_path, f]));
    const groups = {};
    for (const f of previewFiles) {
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

  const checkedCount = $derived(previewFiles.filter((f) => f.checked).length);

  function baseName(p) {
    const parts = p.split(/[\\/]/);
    return parts[parts.length - 1] || p;
  }

  // ── Carpeta / escaneo ────────────────────────────────────────────────────────

  async function pickFolder() {
    const picked = await bridge.pick_folder();
    if (!picked) return;
    folder = picked;
    applyResult = null;
    scanning = true;
    scannedFiles = await bridge.scan_filenames_folder(folder);
    scanning = false;
  }

  // ── Idioma / prompt / glosario ──────────────────────────────────────────────

  async function onSelectLanguage(lang) {
    selectedLanguage = lang;
    translationPrompt = await bridge.get_translation_prompt(lang, "filenames");
    glossaryText = await bridge.get_glossary(lang);
    promptDirty = false;
    glossaryDirty = false;
  }
  function onPromptEdit() {
    promptDirty = true;
  }
  async function savePrompt() {
    await bridge.save_translation_prompt(selectedLanguage, "filenames", translationPrompt);
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
  function onTranslateStream(e) {
    translateStreamText = e.detail.text;
  }
  function onPreviewDone(e) {
    if (!e.detail.success) {
      stage = "config";
      return;
    }
    previewFiles = e.detail.files.map((f) => ({ ...f, checked: f.needs_translation }));
    stage = "selection";
  }

  window.addEventListener("audiotools:filenames:phase", onPhase);
  window.addEventListener("audiotools:filenames:work_info_stream", onWorkInfoStream);
  window.addEventListener("audiotools:filenames:translate_stream", onTranslateStream);
  window.addEventListener("audiotools:filenames:preview_done", onPreviewDone);

  // ── Ejecutar traducción (preview) ───────────────────────────────────────────

  async function runPreview() {
    if (!canRun) return;
    stage = "processing";
    phaseText = "Iniciando...";
    workInfoText = "";
    translateStreamText = "";
    stickToBottom = true;
    progress.logs = [];

    await bridge.run_translate_filenames_preview(
      scannedFiles,
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

  function cancelPreview() {
    bridge.cancel_translate_filenames();
  }

  // ── Confirmar renombrado ─────────────────────────────────────────────────────

  async function applyRenames() {
    const renames = previewFiles
      .filter((f) => f.checked && f.needs_translation)
      .map((f) => [f.path, f.translated_name]);

    if (!renames.length) {
      stage = "config";
      return;
    }

    applyResult = await bridge.apply_filename_renames(renames);
    stage = "summary";
  }

  function discardSelection() {
    stage = "config";
  }

  async function backToConfig() {
    stage = "config";
    scanning = true;
    scannedFiles = await bridge.scan_filenames_folder(folder);
    scanning = false;
  }
</script>

{#if showInfoModal}
  <div class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" role="presentation" onclick={() => (showInfoModal = false)}></div>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
    <div class="w-full max-w-xl max-h-[85vh] overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-white">Info del publisher</h2>
        <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showInfoModal = false)}>✕</button>
      </div>
      <textarea
        bind:value={publisherInfo}
        rows="16"
        placeholder="Pega la descripción / ficha del trabajo (opcional)"
        class="w-full resize-y rounded-lg border border-white/10 bg-white/5 px-3 py-2
               text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
      ></textarea>
      <div class="flex justify-end">
        <button class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors" onclick={() => (showInfoModal = false)}>
          Listo
        </button>
      </div>
    </div>
  </div>
{/if}

{#if showPromptModal}
  <div class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" role="presentation" onclick={() => (showPromptModal = false)}></div>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
    <div class="w-full max-w-5xl max-h-[90vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-white">Prompt {promptDirty ? "· sin guardar" : ""}</h2>
        <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showPromptModal = false)}>✕</button>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <select
          value={selectedLanguage}
          onchange={(e) => onSelectLanguage(e.target.value)}
          class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
        >
          {#each languages as lang (lang)}<option value={lang}>{languageLabel(lang)}</option>{/each}
        </select>
        <button class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10" onclick={savePrompt} title="Guardar">💾</button>
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
  <div class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" role="presentation" onclick={() => (showGlossaryModal = false)}></div>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
    <div class="w-full max-w-5xl max-h-[90vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-white">Glossary {glossaryDirty ? "· sin guardar" : ""}</h2>
        <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showGlossaryModal = false)}>✕</button>
      </div>
      <p class="text-[11px] text-white/30 shrink-0">
        Términos fijos por idioma, compartidos entre .srt, chapters y filenames — se inyectan solos en el prompt final.
      </p>
      <div class="flex items-center gap-2 shrink-0">
        <select
          value={selectedLanguage}
          onchange={(e) => onSelectLanguage(e.target.value)}
          class="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white outline-none focus:border-indigo-500/50 transition-colors"
        >
          {#each languages as lang (lang)}<option value={lang}>{languageLabel(lang)}</option>{/each}
        </select>
        <button class="rounded px-2 py-1.5 text-[11px] text-white/50 hover:text-white hover:bg-white/10" onclick={saveGlossary} title="Guardar">💾</button>
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

{#if showModelLogModal}
  <div class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" role="presentation" onclick={() => (showModelLogModal = false)}></div>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-6">
    <div class="w-full max-w-2xl max-h-[85vh] rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">
      <div class="flex items-center justify-between shrink-0">
        <h2 class="text-sm font-semibold text-white">Log del modelo</h2>
        <button class="text-white/30 hover:text-white transition-colors" onclick={() => (showModelLogModal = false)}>✕</button>
      </div>
      <p class="text-[11px] text-white/30 shrink-0">
        Salida cruda tal cual la generó el modelo (incluye razonamiento si el modelo lo generó, sin filtrar nada).
      </p>
      <pre class="flex-1 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-white/60">{translateStreamText}</pre>
      <div class="flex justify-end gap-2 shrink-0 border-t border-white/5 pt-4">
        <button
          class="rounded-lg border border-white/10 px-4 py-2 text-xs text-white/60 hover:text-white transition-colors"
          onclick={() => copyToClipboard(translateStreamText, "modal")}
        >
          {copyFeedback === "modal" ? "Copiado" : "Copiar"}
        </button>
        <button
          class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
          onclick={() => (showModelLogModal = false)}
        >
          Cerrar
        </button>
      </div>
    </div>
  </div>
{/if}

{#if stage === "processing"}
  <div class="flex h-full flex-col">
    <header class="flex items-center border-b border-white/5 px-8 py-5 shrink-0">
      <button class="text-white/30 hover:text-white transition-colors text-sm" onclick={goHome}> ← Inicio </button>
      <span class="text-white/10 mx-3">/</span>
      <h1 class="text-sm font-semibold flex-1">Translate — Nombres de archivo</h1>

      <div class="flex items-center gap-2">
        <Spinner size={14} duration="1.5s" />
        <button
          class="rounded-md border border-red-500/20 bg-red-500/10 px-2.5 py-1
                  text-xs text-red-400 hover:bg-red-500/20 transition-colors"
          onclick={cancelPreview}
        >
          Cancelar
        </button>
        <button
          class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1
                  text-xs text-white/40 hover:text-white/70 transition-colors"
          onclick={() => (showLogs = !showLogs)}
        >
          Logs
        </button>
      </div>
    </header>

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
                class="text-[11px] text-white/30 hover:text-white transition-colors"
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
{:else if stage === "selection"}
  <div class="flex h-full flex-col">
    <ViewHeader title="Translate — Seleccionar renombres" {goHome} />
    <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
      <div class="flex w-full max-w-3xl flex-1 flex-col gap-4">
        <div class="flex items-center justify-between shrink-0">
          <h2 class="text-sm font-semibold text-white">
            {checkedCount} de {previewFiles.filter((f) => f.needs_translation).length} marcados
          </h2>
          {#if translateStreamText}
            <button
              class="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/40 hover:text-white/70 transition-colors"
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
                  <tr class="{dirEntry.needs_translation ? 'hover:bg-white/5' : 'opacity-35'}">
                    <td class="pt-3 pb-1 align-middle">
                      <input
                        type="checkbox"
                        bind:checked={dirEntry.checked}
                        disabled={!dirEntry.needs_translation}
                        class="accent-indigo-500"
                      />
                    </td>
                    <td class="pt-3 pb-1 align-middle text-white/30" title="Carpeta">📁</td>
                    <td class="max-w-[280px] truncate pt-3 pb-1 align-middle font-mono text-[11px] text-white/40">{dir}</td>
                    {#if dirEntry.needs_translation}
                      <td class="max-w-[280px] truncate pt-3 pb-1 align-middle text-emerald-400/80">{dirEntry.translated_name}</td>
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
                  <tr class="{f.needs_translation ? 'hover:bg-white/5' : 'opacity-35'}">
                    <td class="py-1.5 pl-4 align-middle">
                      <input
                        type="checkbox"
                        bind:checked={f.checked}
                        disabled={!f.needs_translation}
                        class="accent-indigo-500"
                      />
                    </td>
                    <td class="py-1.5 align-middle text-white/30" title={f.is_dir ? "Carpeta" : "Archivo"}>
                      {f.is_dir ? "📁" : "📄"}
                    </td>
                    <td class="max-w-[280px] truncate py-1.5 align-middle text-white/50">{f.name}</td>
                    {#if f.needs_translation}
                      <td class="max-w-[280px] truncate py-1.5 align-middle text-emerald-400/80">{f.translated_name}</td>
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
          <button class="rounded-lg border border-white/10 px-4 py-2 text-xs text-white/60 hover:text-white transition-colors" onclick={discardSelection}>
            Cancelar
          </button>
          <button
            class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-30"
            onclick={applyRenames}
            disabled={checkedCount === 0}
          >
            Renombrar {checkedCount} elemento{checkedCount === 1 ? "" : "s"}
          </button>
        </div>
      </div>
    </main>
  </div>
{:else if stage === "summary"}
  <div class="flex h-full flex-col">
    <ViewHeader title="Translate — Resultado" {goHome} />
    <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
      <div class="flex w-full max-w-2xl flex-1 flex-col gap-4">
        {#if applyResult}
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
        {/if}

        <div class="flex justify-end shrink-0 border-t border-white/5 pt-4">
          <button class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors" onclick={backToConfig}>
            Volver
          </button>
        </div>
      </div>
    </main>
  </div>
{:else if mode === null}
  <div class="flex h-full flex-col">
    <ViewHeader title="Translate — Nombres de archivo" {goHome} />

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
              <span class="text-sm font-semibold text-white tracking-wide">Traducir en remoto</span>
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
          <span class="text-sm font-semibold text-white tracking-wide">Traducir en esta PC</span>
          <span class="text-xs text-white/50 leading-relaxed">Carga el modelo localmente, como siempre.</span>
        </button>
      </div>
    </main>
  </div>
{:else}
  <div class="flex h-full flex-col">
    <ViewHeader title={mode === "remote" ? "Translate — Nombres de archivo (remoto)" : "Translate — Nombres de archivo"} {goHome} />

    <main class="flex flex-1 flex-col items-center overflow-y-auto px-8 py-10">
      <div class="flex w-full max-w-md flex-col gap-5">
        <button class="self-start text-xs text-white/30 hover:text-white transition-colors" onclick={changeMode}>
          ← Cambiar modo (local/remoto)
        </button>

        <!-- Carpeta -->
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-white/40">Carpeta (se escanea recursivamente)</span>
          <button
            class="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
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

        <!-- Info publisher + Prompt + Glossary en una fila -->
        <div class="grid grid-cols-3 gap-2">
          <button
            class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
            onclick={() => (showInfoModal = true)}
          >
            <span class="text-white/60 truncate">Info</span>
            <span class="{publisherInfo.trim() ? 'text-emerald-400' : 'text-white/30'} shrink-0 ml-2">
              {publisherInfo.trim() ? "✓" : "—"}
            </span>
          </button>
          <button
            class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
            onclick={() => (showPromptModal = true)}
          >
            <span class="text-white/60 truncate">Prompt</span>
            <span class="text-white/30 shrink-0 ml-2 truncate">{languageLabel(selectedLanguage)}{promptDirty ? " ·" : ""}</span>
          </button>
          <button
            class="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-left transition-all hover:border-white/20"
            onclick={() => (showGlossaryModal = true)}
          >
            <span class="text-white/60 truncate">Glossary</span>
            <span class="text-white/30 shrink-0 ml-2 truncate">{languageLabel(selectedLanguage)}{glossaryDirty ? " ·" : ""}</span>
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
              <option value="">{mode === "remote" ? "Sin modelos en el mediador" : "Sin modelos en /models"}</option>
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
            <input id="gpuLayers" type="number" bind:value={nGpuLayers} min="0"
              class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-[11px] text-white/40" for="ctx">Contexto</label>
            <input id="ctx" type="number" bind:value={nCtx} min="512" step="512"
              class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-[11px] text-white/40" for="temp">Temperatura</label>
            <input id="temp" type="number" bind:value={temperature} min="0" max="2" step="0.1"
              class="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white text-center outline-none focus:border-indigo-500/50 transition-colors" />
          </div>
        </div>

        <button
          class="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed"
          onclick={runPreview}
          disabled={!canRun}
        >
          Traducir nombres ({needsCount})
        </button>
      </div>
    </main>
  </div>
{/if}

