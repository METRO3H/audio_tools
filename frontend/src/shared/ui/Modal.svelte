<script>
   /**
    * Modal.svelte
    * ─────────────
    * Diálogo modal sobre el elemento nativo <dialog>. Con showModal() el navegador
    * aporta, sin código propio: capa superior (sin pelear con z-index), foco atrapado
    * dentro del diálogo, resto de la página inerte y la tecla Escape.
    *
    * Se abre al montarse y se cierra al desmontarse, igual que los modales actuales:
    *
    *   {#if showLogs}
    *      <Modal onClose={() => (showLogs = false)} size="2xl" label="Logs" class="gap-3">
    *         …contenido…
    *      </Modal>
    *   {/if}
    *
    * Se cierra (llamando a `onClose`) con Escape o con un clic en el fondo. Un clic solo
    * cuenta como "fondo" si tanto el botón al pulsar como al soltar caen sobre el fondo:
    * así, seleccionar texto dentro del panel y soltar fuera no cierra el modal.
    *
    * Props:
    *   onClose     función que se llama al pedir el cierre (Escape / fondo). El padre decide
    *               qué hacer; normalmente desmonta el modal.
    *   size        "sm" | "xl" | "2xl" | "4xl" | "5xl"            (ancho máximo; por defecto "2xl")
    *   height      "auto" | "max-85" | "max-90" | "fixed-85"      (por defecto "auto")
    *   label       nombre accesible del diálogo (si no hay título visible)
    *   labelledby  id del elemento que lo titula (si hay título visible)
    *   class       clases extra del panel (p. ej. "gap-4 overflow-y-auto")
    *
    * Cada modal debe indicar `label` o `labelledby`.
    */

   const SIZES = {
      sm: "max-w-sm",
      xl: "max-w-xl",
      "2xl": "max-w-2xl",
      "4xl": "max-w-4xl",
      "5xl": "max-w-5xl",
   };

   const HEIGHTS = {
      auto: "",
      "max-85": "max-h-[85vh]",
      "max-90": "max-h-[90vh]",
      "fixed-85": "h-[85vh]",
   };

   let {
      onClose,
      size = "2xl",
      height = "auto",
      label = undefined,
      labelledby = undefined,
      class: className = "",
      children,
   } = $props();

   let dialog = $state(null);
   let pressedOnBackdrop = false;

   // Abrir al montar; al desmontar, cerrar y devolver el foco a quien abrió el modal.
   $effect(() => {
      if (!dialog) return;
      const opener = document.activeElement;
      if (!dialog.open) dialog.showModal();
      return () => {
         dialog.close();
         if (opener instanceof HTMLElement) opener.focus();
      };
   });

   // Escape: el navegador dispara `cancel`. Se evita su cierre automático y se delega en el padre.
   function handleCancel(event) {
      event.preventDefault();
      onClose?.();
   }

   function handlePointerDown(event) {
      pressedOnBackdrop = event.target === dialog;
   }

   function handleClick(event) {
      if (pressedOnBackdrop && event.target === dialog) onClose?.();
      pressedOnBackdrop = false;
   }
</script>

<dialog
   bind:this={dialog}
   aria-label={label}
   aria-labelledby={labelledby}
   oncancel={handleCancel}
   onpointerdown={handlePointerDown}
   onclick={handleClick}
   class="m-0 h-full max-h-none w-full max-w-none items-center justify-center bg-transparent p-6
      text-inherit open:flex backdrop:bg-black/60 backdrop:backdrop-blur-sm"
>
   <div
      class="flex w-full flex-col rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl
         {SIZES[size]} {HEIGHTS[height]} {className}"
   >
      {@render children?.()}
   </div>
</dialog>
