/**
 * useExecutionTarget.svelte.js
 * ─────────────────────────────
 * Dónde se ejecuta una tool que puede correr en esta PC o en el server mediador de la red: la
 * elección del usuario (la pantalla de ExecutionModeGate) y la consulta al mediador.
 *
 *   const target = useExecutionTarget({ check: () => bridge.check_remote_server() });
 *   target.mode        // null (sin elegir) | "local" | "remote"
 *   target.checking    // true mientras se busca el mediador
 *   target.error       // mensaje cuando no se pudo usar el mediador ("" = sin error)
 *   target.remote      // lo que respondió el mediador (host, port, models...) cuando mode === "remote"
 *   target.target      // lo que se envía al backend: { mode: "local" } | { mode: "remote", host, port } | null
 *   target.selectLocal();   await target.selectRemote();   target.change();   // volver a elegir
 *
 * `check` consulta al mediador y devuelve { found, state, busy_model?, host, port, models }. Cada tool
 * aporta la suya (Transcribe pregunta por los modelos de whisper, Traducir por los de traducción);
 * el resto —los mensajes, el "buscando...", que un fallo no deje la pantalla colgada— es igual y vive aquí.
 *
 * Solo se pasa a "remote" si el mediador está libre. Cambiar de modo no toca nada de lo guardado.
 */

const messageOf = (err) => (err instanceof Error ? err.message : String(err));

/**
 * @param {{ check: () => Promise<{ found: boolean, state?: string, busy_model?: string | null, host?: string, port?: number, models?: string[] }> }} options
 */
export function useExecutionTarget({ check }) {
   let mode = $state(null);
   let checking = $state(false);
   let error = $state("");
   let remote = $state(null);

   function selectLocal() {
      mode = "local";
   }

   async function selectRemote() {
      if (checking) return;
      checking = true;
      error = "";
      try {
         const result = await check();

         if (!result.found) {
            error = "No se encontró el server mediador en la red. ¿Está prendido?";
            return;
         }
         if (result.state === "busy" || result.state === "loading") {
            error = `El mediador está ocupado en este momento (modelo: ${
               result.busy_model ?? "desconocido"
            }). Probá de nuevo en un rato.`;
            return;
         }

         remote = result;
         mode = "remote";
      } catch (err) {
         error = `No se pudo consultar el mediador (${messageOf(err)}).`;
      } finally {
         checking = false;
      }
   }

   /** Volver a la pantalla de elección. */
   function change() {
      mode = null;
      error = "";
   }

   return {
      get mode() {
         return mode;
      },
      get checking() {
         return checking;
      },
      get error() {
         return error;
      },
      get remote() {
         return remote;
      },
      get target() {
         if (mode === "local") return { mode: "local" };
         if (mode === "remote" && remote) return { mode: "remote", host: remote.host, port: remote.port };
         return null;
      },
      selectLocal,
      selectRemote,
      change,
   };
}
