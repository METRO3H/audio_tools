<script>
   // Crea un estado persistido dentro de un componente y lo entrega al test.
   import { persisted } from "@shared/state/persisted.svelte.js";
   let { storageKey, defaults, onready } = $props();
   const cfg = persisted(storageKey, defaults);
   onready?.(cfg);
</script>

<output data-testid="json">{JSON.stringify(cfg)}</output>
