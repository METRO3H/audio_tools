/**
 * persisted.svelte.js
 * ────────────────────
 * Estado reactivo que se recuerda entre sesiones (localStorage).
 *
 *   const cfg = persisted("diverge_config", { mediaType: "audio", intervalMins: 20, useSubfolder: true });
 *   cfg.intervalMins = 30;   // se guarda solo
 *
 * Reemplaza el trío que cada vista repetía —un efecto que carga, otro que guarda y, a
 * menudo, un tercero que "resetea"—, cuyo orden hacía que el reset pisara lo cargado.
 * Aquí lo guardado se aplica UNA vez, al crear el estado y antes de que ningún efecto
 * corra, así que nada puede sobrescribirlo al montar.
 *
 * Reglas:
 *   - Las claves de `defaults` definen qué se guarda. Lo guardado que no esté ahí se ignora
 *     y desaparece en el siguiente guardado (así se limpian campos obsoletos).
 *   - Un valor guardado solo se acepta si es del mismo tipo que su valor por defecto
 *     (número finito para números, lista para listas...). Si no, se usa el por defecto,
 *     clave por clave: un valor corrupto no invalida el resto.
 *   - Si el valor por defecto es `null`, se acepta cualquier valor guardado.
 *   - El formato en localStorage (clave y JSON plano) es el mismo de siempre, así que lo
 *     que el usuario ya tenía guardado sigue valiendo.
 *
 * Debe llamarse durante la inicialización de un componente (usa $effect para guardar).
 *
 * @template {Record<string, unknown>} T
 * @param {string} key
 * @param {T} defaults
 * @returns {T}
 */

import { persistentConfig } from "@shared/services/persistentConfig.js";

/** ¿`saved` es un valor aceptable para una clave cuyo valor por defecto es `fallback`? */
function sameKind(saved, fallback) {
   if (fallback === null) return saved !== undefined;
   if (Array.isArray(fallback)) return Array.isArray(saved);
   if (typeof fallback === "number") return typeof saved === "number" && Number.isFinite(saved);
   return saved !== null && typeof saved === typeof fallback;
}

export function persisted(key, defaults) {
   const initial = structuredClone(defaults);

   const saved = persistentConfig.get(key);
   if (saved && typeof saved === "object" && !Array.isArray(saved)) {
      for (const name of Object.keys(defaults)) {
         if (name in saved && sameKind(saved[name], defaults[name])) initial[name] = saved[name];
      }
   }

   const state = $state(initial);

   $effect(() => {
      persistentConfig.set(key, $state.snapshot(state));
   });

   return state;
}
