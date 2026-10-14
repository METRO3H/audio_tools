<script>
   /**
    * SwitchField.svelte
    * ───────────────────
    * Fila "etiqueta (+ ayuda) ........ interruptor".
    *
    *   <SwitchField bind:checked={vadFilter} label="VAD filter" help="Omite los silencios…" />
    *
    * Con una etiqueta que lleva formato propio, el contenido de la etiqueta se pasa como hijo
    * (`label` sigue siendo el nombre accesible del interruptor):
    *
    *   <SwitchField bind:checked={sub} label="Guardar en subcarpeta" description={ruta}>
    *      Guardar en subcarpeta <code>audios/parts</code>
    *   </SwitchField>
    *
    * Props:
    *   checked      boolean   — enlazable
    *   label        string    — texto de la etiqueta y nombre accesible del interruptor
    *   help         string    — si se da, muestra un HoverCard con esta ayuda junto a la etiqueta
    *   description  string    — línea secundaria bajo la etiqueta (se recorta si es larga)
    *   size         "md" | "sm"   — tamaño del texto de la etiqueta (por defecto "md")
    *   disabled     boolean
    *   onchange     (checked: boolean) => void
    *   class        clases extra de la fila (p. ej. para darle aspecto de tarjeta)
    */

   import Switch from "@shared/ui/Switch.svelte";
   import HoverCard from "@shared/ui/HoverCard.svelte";

   const LABEL_SIZES = { md: "text-sm", sm: "text-xs" };

   let {
      checked = $bindable(false),
      label,
      help = undefined,
      description = undefined,
      size = "md",
      disabled = false,
      onchange,
      class: className = "",
      children,
   } = $props();
</script>

<div class="flex items-center justify-between gap-4 {className}">
   <div class="flex min-w-0 flex-col gap-0.5">
      <div class="flex items-center gap-1.5">
         <span class="{LABEL_SIZES[size]} text-white/70">
            {#if children}{@render children()}{:else}{label}{/if}
         </span>
         {#if help}
            <HoverCard text={help} />
         {/if}
      </div>
      {#if description}
         <span class="truncate text-[11px] text-white/30">{description}</span>
      {/if}
   </div>
   <Switch bind:checked {label} {disabled} {onchange} />
</div>
