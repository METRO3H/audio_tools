<script>
  /**
   * ConfirmModal.svelte
   * ────────────────────
   * Modal de confirmación reutilizable.
   *
   * Props:
   *   title      string    — título de la modal
   *   message    string    — mensaje descriptivo
   *   confirmLabel string  — texto del botón de confirmación (default "Confirmar")
   *   cancelLabel  string  — texto del botón de cancelar (default "Cancelar")
   *   onConfirm  function  — callback al confirmar
   *   onCancel   function  — callback al cancelar
   *   danger     boolean   — si el botón de confirmación es destructivo (rojo)
   */

  let {
    title        = 'Confirmar',
    message      = '¿Estás seguro?',
    confirmLabel = 'Confirmar',
    cancelLabel  = 'Cancelar',
    onConfirm,
    onCancel,
    danger       = false,
  } = $props()
</script>

<!-- Backdrop -->
<div
  class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
  role="presentation"
  onclick={onCancel}
></div>

<!-- Modal -->
<div class="fixed inset-0 z-50 flex items-center justify-center p-6">
  <div class="w-full max-w-sm rounded-2xl border border-white/10
              bg-zinc-900 p-6 shadow-2xl flex flex-col gap-4">

    <div class="flex flex-col gap-1.5">
      <h2 class="text-sm font-semibold text-white">{title}</h2>
      <p class="text-xs text-white/50 leading-relaxed">{message}</p>
    </div>

    <div class="flex gap-2 justify-end">
      <button
        class="rounded-lg border border-white/10 bg-white/5 px-4 py-2
               text-xs text-white/60 hover:text-white transition-colors"
        onclick={onCancel}
      >
        {cancelLabel}
      </button>
      <button
        class="rounded-lg px-4 py-2 text-xs font-medium transition-colors
               {danger
                 ? 'bg-red-600 text-white hover:bg-red-500'
                 : 'bg-indigo-600 text-white hover:bg-indigo-500'}"
        onclick={onConfirm}
      >
        {confirmLabel}
      </button>
    </div>

  </div>
</div>