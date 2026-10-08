
/**
 * config.svelte.js
 * ─────────────────
 * Configuración global de la app, sincronizada con el backend.
 *
 * Se inicializa llamando a bridge.get_config() una sola vez
 * al arrancar la app (desde App.svelte).
 *
 * Uso:
 *   import { appConfig } from '$lib/stores/config.svelte.js'
 *
 *   appConfig.baseFolder          // string — carpeta base actual
 *   appConfig.setBaseFolder(path) // actualiza la carpeta base
 *   await appConfig.init()        // carga config desde el backend
 */

import { bridge } from "./bridge.svelte.js";

// ── Estado ─────────────────────────────────────────────────────────────────────

export const appConfig = $state({
   baseFolder: "",
   defaultBaseFolder: "",
   loaded: false,

   async init() {
      const cfg = await bridge.get_config();
      this.baseFolder = cfg.default_base_folder;
      this.defaultBaseFolder = cfg.default_base_folder;
      this.transcribeInitialPrompt = cfg.transcribe_initial_prompt ?? "";
      this.loaded = true;
   },

   setBaseFolder(path) {
      this.baseFolder = path;
   },

   resetBaseFolder() {
      this.baseFolder = this.defaultBaseFolder;
   },
});

