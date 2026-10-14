<script>
   /**
    * Switch.svelte
    * ──────────────
    * Interruptor on/off accesible (role="switch").
    *
    *   <Switch bind:checked={vadFilter} label="VAD filter" />
    *
    * Props:
    *   checked    boolean   — estado (enlazable con bind:checked)
    *   label      string    — nombre accesible. OBLIGATORIO: el interruptor no tiene texto
    *                          propio, y sin nombre un lector de pantalla solo dice "interruptor".
    *   disabled   boolean
    *   onchange   (checked: boolean) => void — se llama con el nuevo valor tras alternarlo
    *
    * Para el caso habitual (etiqueta + ayuda + interruptor en una fila) usar SwitchField.
    */

   let { checked = $bindable(false), label, disabled = false, onchange } = $props();

   function toggle() {
      checked = !checked;
      onchange?.(checked);
   }
</script>

<button
   type="button"
   role="switch"
   aria-checked={checked}
   aria-label={label}
   {disabled}
   onclick={toggle}
   class="inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full p-0.5 transition-colors
      disabled:cursor-not-allowed disabled:opacity-40 {checked ? 'bg-indigo-600' : 'bg-white/10'}"
>
   <span
      class="h-4 w-4 rounded-full bg-white shadow transition-transform duration-200
         {checked ? 'translate-x-4' : 'translate-x-0'}"
   ></span>
</button>
