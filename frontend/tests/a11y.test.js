import fs from "node:fs";
import path from "node:path";
import { compile } from "svelte/compiler";
import { describe, it, expect } from "vitest";

// Compila cada componente de src/ y exige que Svelte no emita ningún aviso de accesibilidad.
// Si aparece uno, el test dice exactamente cuál y dónde.

const SRC = path.resolve(import.meta.dirname, "../src");

// Pendientes conocidos: se quitan de esta lista al corregirse.
const KNOWN_PENDING = ["features/diverge/DivergeView.svelte"];

function svelteFiles(dir) {
   return fs.readdirSync(dir, { recursive: true, withFileTypes: true })
      .filter((e) => e.isFile() && e.name.endsWith(".svelte"))
      .map((e) => path.relative(SRC, path.join(e.parentPath, e.name)).replaceAll("\\", "/"))
      .sort();
}

describe("accesibilidad: sin avisos a11y de Svelte", () => {
   const files = svelteFiles(SRC);

   it("hay componentes que revisar", () => {
      expect(files.length).toBeGreaterThan(20);
   });

   it.each(files.filter((f) => !KNOWN_PENDING.includes(f)))("%s", (file) => {
      const source = fs.readFileSync(path.join(SRC, file), "utf8");
      const { warnings } = compile(source, { filename: file, generate: "client" });
      const a11y = warnings
         .filter((w) => w.code.startsWith("a11y"))
         .map((w) => `${w.code} (línea ${w.start?.line}): ${w.message}`);
      expect(a11y).toEqual([]);
   });

   it("los pendientes conocidos siguen teniendo el aviso (si no, hay que quitarlos de la lista)", () => {
      for (const file of KNOWN_PENDING) {
         const source = fs.readFileSync(path.join(SRC, file), "utf8");
         const { warnings } = compile(source, { filename: file, generate: "client" });
         expect(warnings.some((w) => w.code.startsWith("a11y")), file).toBe(true);
      }
   });
});
