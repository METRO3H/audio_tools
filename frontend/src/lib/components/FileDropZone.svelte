<script>
  /**
   * FileDropZone.svelte
   * ────────────────────
   * Zona de drag & drop para seleccionar archivos.
   *
   * Nota: pywebview no expone el path real de archivos dropeados
   * por seguridad. El drop visual activa el diálogo nativo de
   * selección de archivos via bridge.pick_files().
   *
   * Props:
   *   files       string[]          — lista de rutas seleccionadas (bindable)
   *   accept      string[]          — extensiones permitidas (ej: ['*.mp3'])
   *   multiple    boolean           — permite selección múltiple (default true)
   *   onchange    function          — callback cuando cambian los archivos
   *   disabled    boolean           — deshabilita la interacción
   */

  import { bridge, bridgeReady } from '$lib/stores/bridge.svelte.js'

  let {
    files    = $bindable([]),
    accept   = [],
    multiple = true,
    onchange = null,
    disabled = false,
  } = $props()

  let dragging = $state(false)

  async function openPicker() {
    if (disabled || !bridgeReady.value) return
    const picked = await bridge.pick_files(accept.length ? accept : null)
    if (!picked.length) return

    files = multiple ? [...files, ...picked] : [picked[0]]
    // Deduplica por ruta
    files = [...new Map(files.map(f => [f, f])).values()]
    onchange?.(files)
  }

  function removeFile(path) {
    files = files.filter(f => f !== path)
    onchange?.(files)
  }

  function onDragOver(e) {
    e.preventDefault()
    if (!disabled) dragging = true
  }

  function onDragLeave() {
    dragging = false
  }

  function onDrop(e) {
    e.preventDefault()
    dragging = false
    // pywebview bloquea el path real del drop por seguridad,
    // así que abrimos el picker nativo igual
    if (!disabled) openPicker()
  }

  // Nombre corto del archivo para mostrar en la lista
  function basename(path) {
    return path.split(/[\\/]/).pop()
  }
</script>

<div class="flex flex-col gap-2 w-full">

  <!-- Drop zone -->
  <button
    class="flex flex-col items-center justify-center gap-2 rounded-xl
           border-2 border-dashed p-8 text-center transition-all duration-150
           {dragging
             ? 'border-indigo-400 bg-indigo-500/10'
             : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/8'}
           {disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}"
    ondragover={onDragOver}
    ondragleave={onDragLeave}
    ondrop={onDrop}
    onclick={openPicker}
    {disabled}
  >
    <span class="text-2xl">🎵</span>
    <span class="text-sm text-white/50">
      Arrastra archivos o <span class="text-indigo-400 underline">selecciona</span>
    </span>
    {#if accept.length}
      <span class="text-xs text-white/25">{accept.join(', ')}</span>
    {/if}
  </button>

  <!-- Lista de archivos seleccionados -->
  {#if files.length}
    <ul class="flex flex-col gap-1">
      {#each files as file (file)}
        <li class="flex items-center justify-between rounded-lg
                   bg-white/5 px-3 py-2 text-xs text-white/70">
          <span class="truncate">{basename(file)}</span>
          <button
            class="ml-2 shrink-0 text-white/30 hover:text-red-400 transition-colors"
            onclick={() => removeFile(file)}
            disabled={disabled}
          >
            ✕
          </button>
        </li>
      {/each}
    </ul>
  {/if}

</div>