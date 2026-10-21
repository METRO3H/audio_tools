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
    *   options   { value, label, disabled? }[] — un `disabled` no se puede elegir; si es el valor
    *             seleccionado se sigue viendo como seleccionado (p. ej. un valor recordado que aún
    *             se está comprobando); si no, se ve atenuado
    *   value     el valor seleccionado (enlazable, o solo lectura + onchange cuando es derivado)
    *   label     nombre accesible del grupo
    *   fill      los botones se reparten todo el ancho (flex-1)
    *   size      "md" (por defecto) | "sm": botones compactos para grupos con muchas opciones
    *   wrap      los botones pasan a la línea siguiente cuando no caben
    *   onchange  (value) => void — solo cuando el valor CAMBIA (no al pulsar el ya seleccionado)
    *
    * Accesibilidad: es un grupo de botones con `aria-pressed`.
    */

   let { options, value = $bindable(), label, fill = false, size = "md", wrap = false, onchange } = $props();

   const SIZES = {
      md: "rounded-lg py-2 text-xs font-medium",
      sm: "rounded-md px-3 py-1.5 text-xs",
   };

   function select(option) {
      if (option.disabled || option.value === value) return;
      value = option.value;
      onchange?.(option.value);
   }
</script>

<div role="group" aria-label={label} class="flex gap-2 {wrap ? 'flex-wrap' : ''}">
   {#each options as option (option.value)}
      <button
         type="button"
         aria-pressed={value === option.value}
         disabled={option.disabled}
         onclick={() => select(option)}
         class="{SIZES[size] ?? SIZES.md} transition-colors {fill ? 'flex-1' : size === 'md' ? 'px-4' : ''}
            {value === option.value
            ? 'bg-indigo-600 text-white'
            : option.disabled
              ? 'cursor-not-allowed border border-white/10 bg-white/5 text-white/30 opacity-30'
              : 'border border-white/10 bg-white/5 text-white/50 hover:text-white'}"
      >
         {option.label}
      </button>
   {/each}
</div>
