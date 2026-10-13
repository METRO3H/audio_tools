/**
 * clipboard.js
 * ─────────────
 * Copiar texto al portapapeles.
 *
 * Intenta primero la API moderna y, si falla (permiso denegado, contexto sin
 * foco, WebView antiguo...), recurre a `execCommand("copy")`.
 *
 * El plan B inserta el <textarea> temporal DENTRO del <dialog> modal activo
 * cuando lo hay: mientras un modal está abierto, todo lo que queda fuera de él
 * es inerte y no se puede seleccionar, así que un <textarea> en <body> no copiaría.
 *
 * @param {string} text
 * @returns {Promise<boolean>} true si se copió
 */
export async function copyToClipboard(text) {
   try {
      await navigator.clipboard.writeText(text);
      return true;
   } catch {
      return legacyCopy(text);
   }
}

/** @param {string} text */
function legacyCopy(text) {
   const active = document.activeElement;
   const host = (active instanceof Element && active.closest("dialog")) || document.body;

   const textarea = document.createElement("textarea");
   textarea.value = text;
   textarea.setAttribute("readonly", "");
   textarea.style.position = "fixed";
   textarea.style.opacity = "0";
   host.appendChild(textarea);
   textarea.select();
   try {
      return document.execCommand("copy");
   } catch {
      return false;
   } finally {
      host.removeChild(textarea);
   }
}
