<script>
  /**
   * FileList.svelte
   * ────────────────
   * Lista de archivos seleccionados con auto-hint, scroll y selección manual.
   * Se alimenta de useFileSelection (selection.files, selection.hint...).
   *
   * Props:
   *   fileInfos   object[]  — lista de { name, size_mb, path, ... }
   *   autoHint    string    — mensaje de estado (auto-detección)
   *   onPickFiles function  — callback para selección manual
   *   onRemove    function(path) — callback para eliminar un archivo
   *   disabled    boolean
   *   emptyText   string    — texto cuando no hay archivos
   *   label       string    — label del campo (default 'Archivos')
   *   loading     boolean   — mientras se escanea o se lee información: un "Cargando archivos..." con
   *                           spinner en lugar de la lista (se alimenta de selection.loading)
   *   height      'auto' | 'fixed' — 'auto' (por defecto): la lista crece hasta un máximo; 'fixed': una
   *                           caja de altura reservada (≈5 filas) que evita saltos de layout al cargar
   */

  import Spinner from '@shared/ui/Spinner.svelte'

  let {
    fileInfos  = [],
    autoHint   = '',
    onPickFiles = null,
    onRemove   = null,
    disabled   = false,
    emptyText  = 'Selecciona una carpeta base primero',
    label      = 'Archivos',
    loading    = false,
    height     = 'auto',
  } = $props()

  const fixed = $derived(height === 'fixed')
</script>

<div class="flex flex-col gap-1.5">
  <div class="flex items-center justify-between">
    <span class="text-xs text-white/40">
      {label}
      {#if fileInfos.length}
        <span class="text-white/20">({fileInfos.length})</span>
      {/if}
    </span>
    {#if onPickFiles}
      <button
        type="button"
        class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors
               disabled:opacity-40"
        onclick={onPickFiles}
        {disabled}
      >
        Seleccionar manualmente
      </button>
    {/if}
  </div>

  {#if autoHint}
    <span class="text-xs {autoHint.startsWith('⚠') ? 'text-yellow-400' : 'text-emerald-400'}">
      {autoHint}
    </span>
  {/if}

  {#snippet list()}
    <ul class="flex flex-col gap-1 {fixed ? '' : 'overflow-y-auto max-h-40'}">
      {#each fileInfos as file (file.path)}
        <li class="flex items-center justify-between rounded-lg
                   bg-white/5 px-3 py-1.5 text-xs text-white/60 shrink-0">
          <span class="truncate">{file.name}</span>
          <div class="flex shrink-0 items-center gap-2 ml-2">
            {#if file.size_mb > 0}
              <span class="text-white/30">{file.size_mb} MB</span>
            {/if}
            {#if onRemove}
              <button
                type="button"
                class="text-white/20 hover:text-red-400 transition-colors disabled:opacity-40"
                aria-label="Quitar {file.name}"
                onclick={() => onRemove(file.path)}
                {disabled}
              >✕</button>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/snippet}

  {#if fixed}
    <div
      class="h-44 overflow-y-auto rounded-lg border border-white/5 bg-black/10 p-1.5"
      style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;"
    >
      {#if loading}
        <div class="flex h-full items-center justify-center gap-2 text-xs text-white/40">
          <Spinner size={16} duration="1.25s" />
          <span>Cargando archivos...</span>
        </div>
      {:else if fileInfos.length}
        {@render list()}
      {:else}
        <div class="flex h-full items-center justify-center px-4 text-center text-xs text-white/20">
          {emptyText}
        </div>
      {/if}
    </div>
  {:else if loading}
    <div class="flex items-center justify-center gap-2 rounded-lg border border-dashed border-white/10
                p-4 text-xs text-white/40">
      <Spinner size={16} duration="1.25s" />
      <span>Cargando archivos...</span>
    </div>
  {:else if fileInfos.length}
    {@render list()}
  {:else}
    <div class="rounded-lg border border-dashed border-white/10 p-4
                text-center text-xs text-white/20">
      {emptyText}
    </div>
  {/if}
</div>
