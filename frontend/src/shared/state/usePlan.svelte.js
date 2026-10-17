/**
 * usePlan.svelte.js
 * ──────────────────
 * Consulta al backend "qué va a producir esta tool" (nombres, rutas, duraciones...) cada
 * vez que cambian las opciones, sin saturarlo y sin que una respuesta vieja pise a una nueva.
 *
 *   const planState = usePlan(() => planOptions, (options) => bridge.plan_merge(options));
 *   planState.value     // el plan, o null
 *   planState.error     // mensaje si el backend devolvió { error }, o ""
 *   planState.pending   // true mientras hay una consulta en espera o en vuelo
 *
 * Reglas:
 *   - `getOptions` devuelve las opciones o `null` si todavía no hay con qué planificar
 *     (entonces se limpia el plan y no se llama al backend).
 *   - Se espera `debounceMs` desde el último cambio antes de preguntar.
 *   - Si llega una respuesta de una consulta que ya quedó desactualizada, se descarta.
 *   - Un fallo de la llamada (rechazo o excepción) se muestra como `error`, igual que
 *     un `{ error }` devuelto por el backend.
 *
 * Mientras `pending` sea true, el plan que se ve podría no corresponder a lo último que
 * cambió el usuario: la vista debe impedir ejecutar hasta que termine.
 *
 * Debe llamarse durante la inicialización de un componente (usa $effect).
 *
 * @param {() => object | null} getOptions
 * @param {(options: object) => Promise<any> | any} fetchPlan
 * @param {{ debounceMs?: number }} [config]
 */
export function usePlan(getOptions, fetchPlan, { debounceMs = 200 } = {}) {
   let value = $state(null);
   let error = $state("");
   let pending = $state(false);
   let latest = 0;

   $effect(() => {
      const options = getOptions();
      const mine = ++latest;

      if (!options) {
         value = null;
         error = "";
         pending = false;
         return;
      }

      pending = true;
      const timer = setTimeout(async () => {
         const result = await Promise.resolve()
            .then(() => fetchPlan(options))
            .catch((err) => ({ error: err instanceof Error ? err.message : String(err) }));
         if (mine !== latest) return; // llegó tarde: ya hay una consulta más reciente
         pending = false;
         if (result?.error) {
            value = null;
            error = result.error;
         } else {
            value = result;
            error = "";
         }
      }, debounceMs);

      return () => clearTimeout(timer);
   });

   return {
      get value() {
         return value;
      },
      get error() {
         return error;
      },
      get pending() {
         return pending;
      },
   };
}
