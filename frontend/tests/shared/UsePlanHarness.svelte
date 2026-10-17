<script>
   // Monta usePlan dentro de un componente y entrega al test cómo cambiar las opciones.
   import { usePlan } from "@shared/state/usePlan.svelte.js";
   let { fetchPlan, initial = null, debounceMs, onready } = $props();
   let options = $state(initial);
   const planState = usePlan(() => options, fetchPlan, debounceMs === undefined ? undefined : { debounceMs });
   onready?.({ setOptions: (value) => (options = value) });
</script>

<output data-testid="state">{JSON.stringify({ value: planState.value, error: planState.error, pending: planState.pending })}</output>
