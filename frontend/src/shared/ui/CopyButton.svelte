<script>
   /**
    * CopyButton.svelte
    * ──────────────────
    * Botón "Copiar" con confirmación breve ("✓ Copiado").
    *
    * Props:
    *   text         string | () => string — el texto, o una función que lo produce.
    *                Con función solo se evalúa al pulsar (útil para logs largos).
    *   label        texto del botón            (por defecto "Copiar todo")
    *   copiedLabel  texto tras copiar          (por defecto "✓ Copiado")
    *   disabled     deshabilita el botón
    *   class        clases del botón; si se omite, se usa el estilo por defecto
    *
    * Si el texto está vacío no hace nada.
    */

   import { copyToClipboard } from "@shared/services/clipboard.js";

   const DEFAULT_CLASS =
      "rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/45 " +
      "transition-colors hover:text-white/80 disabled:cursor-not-allowed disabled:opacity-30";

   let {
      text,
      label = "Copiar todo",
      copiedLabel = "✓ Copiado",
      disabled = false,
      class: className = DEFAULT_CLASS,
   } = $props();

   let copied = $state(false);
   let timer;

   async function copy() {
      const value = typeof text === "function" ? text() : text;
      if (!value) return;
      if (!(await copyToClipboard(value))) return;

      copied = true;
      clearTimeout(timer);
      timer = setTimeout(() => (copied = false), 2000);
   }

   $effect(() => () => clearTimeout(timer));
</script>

<button type="button" class={className} {disabled} onclick={copy}>
   {copied ? copiedLabel : label}
</button>
