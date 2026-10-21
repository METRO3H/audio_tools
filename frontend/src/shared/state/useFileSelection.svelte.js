/**
 * useFileSelection.svelte.js
 * ───────────────────────────
 * Los archivos con los que va a trabajar una tool: los detecta en una carpeta o los elige el usuario,
 * lee su información (peso, duración) y mantiene el mensaje de estado que se le muestra.
 *
 *   const selection = useFileSelection({
 *      scan: (folder) => bridge.scan_media_folder(folder, mediaType),
 *      pick: () => bridge.pick_files(extensions, baseFolder, mediaType),
 *      emptyHint: () => "No se encontraron archivos en ./audios",
 *   });
 *   selection.files     // [{ name, size_mb, duration_seconds, path }, ...]
 *   selection.hint      // "✓ 3 archivo(s) detectados" | "⚠ ..." | ""
 *   selection.loading   // true mientras escanea o lee información
 *   await selection.loadFromFolder(folder);   await selection.pickFiles();
 *   selection.remove(path);   selection.clear();
 *
 * Opciones:
 *   scan            (folder) => Promise<{ files: string[], error?: string | null }>   (puede traer más campos)
 *   pick            () => Promise<string[] | null>   — el diálogo de selección manual
 *   emptyHint       string | () => string — texto cuando el escaneo no encuentra nada (se muestra con ⚠)
 *   formatDetected  (n, scanResult) => string — mensaje de éxito (por defecto "✓ n archivo(s) detectados")
 *   onLoaded        (files, origin) => void — tras cargar archivos; origin es "folder" o "manual"
 *
 * Garantías:
 *   - Si se lanza una carga mientras otra sigue en curso, solo cuenta la última: una respuesta
 *     vieja nunca pisa a una nueva.
 *   - Un archivo cuya información no se puede leer (p. ej. desapareció entre el escaneo y la
 *     lectura) se omite y se avisa, en vez de hacer fallar toda la carga.
 *   - Cancelar el diálogo de selección no cambia nada.
 *
 * Los mensajes de ⚠ llevan ese prefijo: FileList los pinta en amarillo y el resto en verde.
 */

import { bridge } from "@shared/services/bridge.svelte.js";

const defaultDetected = (n) => `✓ ${n} archivo(s) detectados`;

const messageOf = (err) => (err instanceof Error ? err.message : String(err));

/** Aviso cuando alguno de los archivos no se pudo leer. */
function unreadableHint(readable, failed) {
   if (readable === 0) return "⚠ No se pudo leer ninguno de los archivos";
   return `⚠ ${readable} archivo(s) detectados; ${failed} no se pudieron leer`;
}

/**
 * @param {{
 *   scan?: (folder: string) => Promise<{ files: string[], error?: string | null }>,
 *   pick?: () => Promise<string[] | null | undefined>,
 *   emptyHint?: string | (() => string),
 *   formatDetected?: (n: number, scanResult: any) => string,
 *   onLoaded?: (files: any[], origin: "folder" | "manual") => void,
 * }} [options]
 */
export function useFileSelection({ scan, pick, emptyHint = "No se encontraron archivos", formatDetected = defaultDetected, onLoaded } = {}) {
   let files = $state([]);
   let hint = $state("");
   let loading = $state(false);
   let latest = 0;

   /** Lee la información de cada ruta; devuelve las que se pudieron leer y cuántas fallaron. */
   async function readInfos(paths) {
      const settled = await Promise.allSettled(paths.map((path) => bridge.get_file_info(path)));
      const infos = [];
      let failed = 0;
      settled.forEach((result, i) => {
         if (result.status === "fulfilled") infos.push({ ...result.value, path: paths[i] });
         else failed++;
      });
      return { infos, failed };
   }

   async function loadFromFolder(folder) {
      const mine = ++latest;
      loading = true;
      try {
         let result;
         try {
            result = await scan(folder);
         } catch (err) {
            if (mine !== latest) return;
            files = [];
            hint = `⚠ ${messageOf(err)}`;
            return;
         }
         if (mine !== latest) return;

         if (result.error) {
            files = [];
            hint = `⚠ ${result.error}`;
            return;
         }
         if (!result.files.length) {
            files = [];
            hint = `⚠ ${typeof emptyHint === "function" ? emptyHint() : emptyHint}`;
            return;
         }

         const { infos, failed } = await readInfos(result.files);
         if (mine !== latest) return;

         files = infos;
         hint = failed ? unreadableHint(infos.length, failed) : formatDetected(infos.length, result);
         if (infos.length) onLoaded?.(infos, "folder");
      } finally {
         if (mine === latest) loading = false;
      }
   }

   async function pickFiles() {
      let paths;
      try {
         paths = await pick();
      } catch (err) {
         hint = `⚠ ${messageOf(err)}`;
         return;
      }
      if (!paths?.length) return; // diálogo cancelado: no cambia nada ni interrumpe una carga en curso

      const mine = ++latest;
      loading = true;
      try {
         const { infos, failed } = await readInfos(paths);
         if (mine !== latest) return;

         files = infos;
         hint = failed ? unreadableHint(infos.length, failed) : "";
         if (infos.length) onLoaded?.(infos, "manual");
      } finally {
         if (mine === latest) loading = false;
      }
   }

   function remove(path) {
      files = files.filter((file) => file.path !== path);
   }

   function clear() {
      latest++; // descarta cualquier carga en curso
      files = [];
      hint = "";
      loading = false;
   }

   return {
      get files() {
         return files;
      },
      get hint() {
         return hint;
      },
      get loading() {
         return loading;
      },
      loadFromFolder,
      pickFiles,
      remove,
      clear,
   };
}
