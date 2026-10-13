/**
 * stickyScroll.js
 * ────────────────
 * Acción de Svelte para contenedores que reciben contenido al final (logs, texto en
 * streaming): mientras el usuario está al final, el scroll lo sigue; si se desplaza
 * hacia arriba para leer, deja de moverlo, y vuelve a seguirlo cuando regresa al final.
 *
 * Uso:
 *   <div use:stickyScroll={logs.length} class="overflow-y-auto">…</div>
 *
 * El parámetro es solo un "disparador": cuando cambia, se reevalúa el scroll.
 */

/** Distancia (px) al final a partir de la cual se considera que el usuario "está al final". */
export const STICK_THRESHOLD = 48;

/**
 * @param {HTMLElement} node
 * @param {unknown} [_trigger]
 */
export function stickyScroll(node, _trigger) {
   let stick = true;

   const atBottom = () => node.scrollHeight - node.scrollTop - node.clientHeight <= STICK_THRESHOLD;
   const onScroll = () => {
      stick = atBottom();
   };
   const follow = () => {
      if (stick) node.scrollTop = node.scrollHeight;
   };

   node.addEventListener("scroll", onScroll, { passive: true });
   follow();

   return {
      update() {
         follow();
      },
      destroy() {
         node.removeEventListener("scroll", onScroll);
      },
   };
}
