<script>
   /**
    * Field.svelte
    * ─────────────
    * Etiqueta (+ ayuda opcional) encima de un control.
    *
    *   <Field label="Intervalo (minutos)" for="interval">
    *      <input id="interval" … />
    *   </Field>
    *
    * Props:
    *   label   string — texto de la etiqueta
    *   for     string — id del control. Si se da, la etiqueta es un <label for> y queda
    *                    asociada al control (clic en la etiqueta enfoca el control y los
    *                    lectores de pantalla la leen). Sin él, es un texto suelto.
    *   help    string — si se da, muestra un HoverCard con esta ayuda junto a la etiqueta
    *   class   clases extra del contenedor
    */

   import HoverCard from "@shared/ui/HoverCard.svelte";

   let { label, for: htmlFor = undefined, help = undefined, class: className = "", children } = $props();
</script>

<div class="flex flex-col gap-1.5 {className}">
   <div class="flex items-center gap-1.5">
      {#if htmlFor}
         <label class="text-xs text-white/40" for={htmlFor}>{label}</label>
      {:else}
         <span class="text-xs text-white/40">{label}</span>
      {/if}
      {#if help}
         <HoverCard text={help} />
      {/if}
   </div>
   {@render children?.()}
</div>
