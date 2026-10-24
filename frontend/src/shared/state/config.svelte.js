/**
 * config.svelte.js
 * ─────────────────
 * Configuración global de la app, sincronizada con el backend.
 *
 * Se inicializa llamando a bridge.get_config() una sola vez
 * al arrancar la app (desde App.svelte).
 *
 * Uso:
 *   import { appConfig } from '@shared/state/config.svelte.js'
 *
 *   appConfig.baseFolder          // string — carpeta base actual
 *   appConfig.mediaExtensions     // { audio: ['.mp3', ...], video: ['.mp4', ...] } — del backend
 *   appConfig.outputFormats       // { audio: ['mp3', ...], video: ['mp4', ...] } — del backend; el primero es el de por defecto
 *   appConfig.videoEncoding       // capacidades de Audio→Video, del backend (ver core/video_encoding.py):
 *                                 // { encoders: [{id,label}], encoder_priority, presets, default_presets,
 *                                 //   fps, resolutions, quality_range }
 *   appConfig.transcription       // capacidades de Transcribe, del backend (ver core/transcription/options.py):
 *                                 // { model_sizes, devices, compute_types, beam_sizes, languages: [{code,label}],
 *                                 //   output_formats, defaults: {model_size, device, ..., initial_prompt} }
 *   appConfig.setBaseFolder(path) // actualiza la carpeta base
 *   await appConfig.init()        // carga config desde el backend
 */

import { bridge } from "@shared/services/bridge.svelte.js";

// ── Estado ─────────────────────────────────────────────────────────────────────

export const appConfig = $state({
   baseFolder: "",
   defaultBaseFolder: "",
   mediaExtensions: { audio: [], video: [] },
   outputFormats: { audio: [], video: [] },
   videoEncoding: {
      encoders: [],
      encoder_priority: [],
      presets: {},
      default_presets: {},
      fps: [],
      resolutions: [],
      quality_range: [0, 51],
   },
   transcription: {
      model_sizes: [],
      devices: [],
      compute_types: {},
      beam_sizes: [],
      languages: [],
      output_formats: [],
      defaults: {},
   },
   loaded: false,

   async init() {
      const cfg = await bridge.get_config();
      this.baseFolder = cfg.default_base_folder;
      this.defaultBaseFolder = cfg.default_base_folder;
      this.mediaExtensions = cfg.media_extensions ?? { audio: [], video: [] };
      this.outputFormats = cfg.output_formats ?? { audio: [], video: [] };
      if (cfg.video_encoding) this.videoEncoding = cfg.video_encoding;
      if (cfg.transcription) this.transcription = cfg.transcription;
      this.loaded = true;
   },

   setBaseFolder(path) {
      this.baseFolder = path;
   },

   resetBaseFolder() {
      this.baseFolder = this.defaultBaseFolder;
   },
});
