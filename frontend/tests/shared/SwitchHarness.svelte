<script>
   import Switch from "@shared/ui/Switch.svelte";
   let { initial = false, label = "Opción", onchange, disabled = false } = $props();
   let checked = $state(initial);
</script>

<Switch bind:checked {label} {onchange} {disabled} />
<output data-testid="state">{String(checked)}</output>
