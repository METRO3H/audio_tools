<script>
  /**
   * FileList.svelte
   * ────────────────
   * Lista de archivos seleccionados con auto-hint, scroll y selección manual.
   *
   * Props:
   *   fileInfos   object[]  — lista de { name, size_mb, path, ... }
   *   autoHint    string    — mensaje de estado (auto-detección)
   *   onPickFiles function  — callback para selección manual
   *   onRemove    function(path) — callback para eliminar un archivo
   *   disabled    boolean
   *   emptyText   string    — texto cuando no hay archivos
   *   label       string    — label del campo (default 'Archivos')
   */

  let {
    fileInfos  = [],
    autoHint   = '',
    onPickFiles = null,
    onRemove   = null,
    disabled   = false,
    emptyText  = 'Selecciona una carpeta base primero',
    label      = 'Archivos',
  } = $props()
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

  {#if fileInfos.length}
    <ul class="flex flex-col gap-1 overflow-y-auto max-h-40">
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
                class="text-white/20 hover:text-red-400 transition-colors disabled:opacity-40"
                onclick={() => onRemove(file.path)}
                {disabled}
              >✕</button>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {:else}
    <div class="rounded-lg border border-dashed border-white/10 p-4
                text-center text-xs text-white/20">
      {emptyText}
    </div>
  {/if}
</div>
