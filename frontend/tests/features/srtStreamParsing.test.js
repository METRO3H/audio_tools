import { describe, it, expect } from "vitest";
import { parseBlocks, extractContext, extractBlock } from "@translate/srt/srtStreamParsing.js";

describe("parseBlocks", () => {
   it("sin texto no hay bloques", () => {
      expect(parseBlocks("")).toEqual([]);
      expect(parseBlocks(undefined)).toEqual([]);
   });

   it("parte por encabezado y recorta el contenido", () => {
      const text = "═══ Bloque 1/2 ═══\n1: hola\n\n═══ Bloque 2/2 ═══\n2: chau\n";
      expect(parseBlocks(text)).toEqual([
         { header: "═══ Bloque 1/2 ═══", content: "1: hola" },
         { header: "═══ Bloque 2/2 ═══", content: "2: chau" },
      ]);
   });

   it("descarta lo que hay antes del primer encabezado", () => {
      expect(parseBlocks("basura\n═══ Bloque 1/1 ═══\nx")).toEqual([
         { header: "═══ Bloque 1/1 ═══", content: "x" },
      ]);
   });

   it("un encabezado sin contenido no genera bloque", () => {
      expect(parseBlocks("═══ Bloque 1/2 ═══\n═══ Bloque 2/2 ═══\ny")).toEqual([
         { header: "═══ Bloque 2/2 ═══", content: "y" },
      ]);
   });

   it("un texto sin encabezados no tiene bloques", () => {
      expect(parseBlocks("1: hola\n2: chau")).toEqual([]);
   });

   it("conserva los saltos de línea internos del bloque", () => {
      expect(parseBlocks("═══ Bloque 1/1 ═══\na\nb\nc")[0].content).toBe("a\nb\nc");
   });
});

describe("extractContext / extractBlock", () => {
   const MSG = "[Previous translated context]:\nCTX\nmás\n\n[Block to translate]:\n1: texto\n2: otro";

   it("separa contexto y bloque de un mensaje completo", () => {
      expect(extractContext(MSG)).toBe("CTX\nmás");
      expect(extractBlock(MSG)).toBe("1: texto\n2: otro");
   });

   it("sin contexto previo: contexto vacío y bloque con la marca", () => {
      const msg = "[Block to translate]:\n1: x";
      expect(extractContext(msg)).toBe("");
      expect(extractBlock(msg)).toBe("1: x");
   });

   it("sin ninguna marca: contexto vacío y el bloque es el mensaje entero", () => {
      expect(extractContext("1: x")).toBe("");
      expect(extractBlock("1: x")).toBe("1: x");
   });

   it("vacío o undefined devuelven ''", () => {
      for (const v of ["", undefined, null]) {
         expect(extractContext(v)).toBe("");
         expect(extractBlock(v)).toBe("");
      }
   });
});
