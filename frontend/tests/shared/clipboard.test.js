import { vi, describe, it, expect, afterEach } from "vitest";
import { copyToClipboard } from "@shared/services/clipboard.js";

function setClipboard(writeText) {
   Object.defineProperty(navigator, "clipboard", { value: writeText ? { writeText } : undefined, configurable: true });
}

afterEach(() => {
   document.body.innerHTML = "";
   delete document.execCommand;
   setClipboard(undefined);
});

describe("copyToClipboard", () => {
   it("usa la API moderna cuando está disponible", async () => {
      const writeText = vi.fn().mockResolvedValue();
      setClipboard(writeText);
      document.execCommand = vi.fn();
      expect(await copyToClipboard("hola")).toBe(true);
      expect(writeText).toHaveBeenCalledWith("hola");
      expect(document.execCommand).not.toHaveBeenCalled();
   });

   it("si la API moderna rechaza, recurre a execCommand y limpia el textarea", async () => {
      setClipboard(vi.fn().mockRejectedValue(new Error("denegado")));
      let copiedValue;
      document.execCommand = vi.fn((cmd) => {
         copiedValue = document.querySelector("textarea")?.value;
         return cmd === "copy";
      });
      expect(await copyToClipboard("texto largo")).toBe(true);
      expect(document.execCommand).toHaveBeenCalledWith("copy");
      expect(copiedValue).toBe("texto largo");
      expect(document.querySelector("textarea")).toBeNull();
   });

   it("sin navigator.clipboard también usa el plan B", async () => {
      setClipboard(undefined);
      document.execCommand = vi.fn().mockReturnValue(true);
      expect(await copyToClipboard("x")).toBe(true);
   });

   it("el plan B devuelve false si execCommand falla o lanza, y siempre limpia", async () => {
      setClipboard(undefined);
      document.execCommand = vi.fn().mockReturnValue(false);
      expect(await copyToClipboard("x")).toBe(false);
      expect(document.querySelector("textarea")).toBeNull();

      document.execCommand = vi.fn(() => {
         throw new Error("no soportado");
      });
      expect(await copyToClipboard("x")).toBe(false);
      expect(document.querySelector("textarea")).toBeNull();
   });

   it("con un modal abierto el textarea temporal va DENTRO del diálogo (fuera es inerte)", async () => {
      setClipboard(undefined);
      document.body.innerHTML = `<dialog open><button id="copiar">Copiar</button></dialog>`;
      document.getElementById("copiar").focus();

      let hostTag;
      document.execCommand = vi.fn(() => {
         hostTag = document.querySelector("textarea")?.parentElement?.tagName;
         return true;
      });
      expect(await copyToClipboard("x")).toBe(true);
      expect(hostTag).toBe("DIALOG");
   });

   it("sin modal el textarea va en <body>", async () => {
      setClipboard(undefined);
      let hostTag;
      document.execCommand = vi.fn(() => {
         hostTag = document.querySelector("textarea")?.parentElement?.tagName;
         return true;
      });
      await copyToClipboard("x");
      expect(hostTag).toBe("BODY");
   });
});
