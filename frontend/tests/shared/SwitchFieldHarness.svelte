<script>
   import SwitchField from "@shared/ui/SwitchField.svelte";
   let { initial = false, rich = false, ...rest } = $props();
   let checked = $state(initial);
</script>

{#if rich}
   <SwitchField bind:checked {...rest}>Texto <code>con formato</code></SwitchField>
{:else}
   <SwitchField bind:checked {...rest} />
{/if}
<output data-testid="state">{String(checked)}</output>
