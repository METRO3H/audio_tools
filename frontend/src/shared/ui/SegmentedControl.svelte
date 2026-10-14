<script>
   /**
    * SegmentedControl.svelte
    * ────────────────────────
    * Grupo de botones excluyentes (uno seleccionado a la vez).
    *
    *   <SegmentedControl
    *      label="Tipo"
    *      bind:value={mediaType}
    *      options={[{ value: "audio", label: "🎵 Audio" }, { value: "video", label: "🎬 Video" }]}
    *      fill
    *   />
    *
    * Props:
    *   options   { value, label }[]
    *   value     el valor seleccionado (enlazable)
    *   label     nombre accesible del grupo
    *   fill      los botones se reparten todo el ancho (flex-1)
    *   onchange  (value) => void — solo cuando el valor CAMBIA (no al pulsar el ya seleccionado)
    *
    * Accesibilidad: es un grupo de botones con `aria-pressed`.
    */

   let { options, value = $bindable(), label, fill = false, onchange } = $props();

   function select(next) {
      if (next === value) return;
      value = next;
      onchange?.(next);
   }
</script>

<div role="group" aria-label={label} class="flex gap-2">
   {#each options as option (option.value)}
      <button
         type="button"
         aria-pressed={value === option.value}
         onclick={() => select(option.value)}
         class="rounded-lg py-2 text-xs font-medium transition-colors {fill ? 'flex-1' : 'px-4'}
            {value === option.value
            ? 'bg-indigo-600 text-white'
            : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
      >
         {option.label}
      </button>
   {/each}
</div>
