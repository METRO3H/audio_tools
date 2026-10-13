import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.js";

// Reutiliza la configuración de Vite (plugin de Svelte y alias @app/@shared/@<feature>)
// y añade solo lo propio de los tests.
export default mergeConfig(
   viteConfig,
   defineConfig({
      // Svelte 5 debe resolverse con su build de navegador para poder montar componentes.
      resolve: { conditions: ["browser"] },
      test: {
         environment: "jsdom",
         include: ["tests/**/*.test.js"],
         setupFiles: ["./tests/setup.js"],
      },
   }),
);
