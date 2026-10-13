<script>
   // Envuelve Modal con contenido de prueba (Modal recibe su contenido como snippet).
   import Modal from "@shared/ui/Modal.svelte";
   let { onClose, size, height, label, labelledby, class: className } = $props();
</script>

<Modal {onClose} {size} {height} {label} {labelledby} class={className}>
   <h2 id="harness-title">Título del modal</h2>
   <p data-testid="inside">Contenido</p>
   <button type="button">Aceptar</button>
</Modal>
