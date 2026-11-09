<script>
   /**
    * PromptEditorModal.svelte
    * ──────────────────────────
    * Editor de un texto por idioma (prompt de traducción, o glossary) — selector de idioma +
    * guardar + textarea grande. Reemplaza los 6 modales casi idénticos que había repetidos a
    * mano: uno de prompt y uno de glossary en cada una de las 3 vistas de traducción (.srt,
    * chapters, filenames). El estado (qué texto hay, si está "sucio", a qué idioma pertenece)
    * sigue viviendo en la vista que lo usa — este componente es solo la presentación.
    *
    * Props:
    *   title            "Prompt" | "Glossary" (o lo que corresponda)
    *   description       texto opcional debajo del título (Glossary lo usa, Prompt no)
    *   languages         ["japanese", "chinese", ...]
    *   selectedLanguage   idioma actual
    *   onSelectLanguage   (lang) => void — cambiar de idioma (la vista decide qué más recargar)
    *   value             $bindable: el texto del textarea
    *   dirty             si hay cambios sin guardar (el "· sin guardar" del título)
    *   onInput           () => void — se llama en cada tecla (para marcar dirty)
    *   onSave            () => void
    *   onClose           () => void
    */

   import Modal from "@shared/ui/Modal.svelte";

   let {
      title,
      description = "",
      languages,
      selectedLanguage,
      onSelectLanguage,
      value = $bindable(""),
      dirty = false,
      onInput,
      onSave,
      onClose,
   } = $props();

   function languageLabel(lang) {
      return lang ? lang.charAt(0).toUpperCase() + lang.slice(1) : "";
   }
</script>

<Modal {onClose} size="5xl" height="max-90" label={title} class="gap-4">
   <div class="flex items-center justify-between">
      <h2 class="text-sm font-semibold text-white">{title} {dirty ? "· sin guardar" : ""}</h2>
      <button class="text-white/30 hover:text-white transition-colors cursor-pointer" onclick={onClose}>✕</button>
   </div>

   {#if description}
      <p class="text-[11px] text-white/30 shrink-0">{description}</p>
   {/if}

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
         onclick={onSave}
         title="Guardar"
      >
         💾
      </button>
   </div>

   <textarea
      bind:value
      oninput={onInput}
      class="w-full flex-1 min-h-[65vh] resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2
         text-xs text-white/80 outline-none focus:border-indigo-500/50 transition-colors font-mono"
   ></textarea>
</Modal>
