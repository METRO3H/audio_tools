<script>
   import SegmentedControl from "@shared/ui/SegmentedControl.svelte";
   let { initial, options, label = "Tipo", fill = false, onchange } = $props();
   let value = $state(initial);
</script>

<SegmentedControl {options} bind:value {label} {fill} {onchange} />
<output data-testid="value">{String(value)}</output>
