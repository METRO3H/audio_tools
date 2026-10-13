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
   *
   * Escape o un clic en el fondo equivalen a cancelar.
   */

  import Modal from '@shared/ui/Modal.svelte'

  let {
    title        = 'Confirmar',
    message      = '¿Estás seguro?',
    confirmLabel = 'Confirmar',
    cancelLabel  = 'Cancelar',
    onConfirm,
    onCancel,
    danger       = false,
  } = $props()

  const titleId = $props.id()
</script>

<Modal onClose={onCancel} size="sm" labelledby={titleId} class="gap-4">
  <div class="flex flex-col gap-1.5">
    <h2 id={titleId} class="text-sm font-semibold text-white">{title}</h2>
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
</Modal>
