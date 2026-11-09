import { render, screen, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import TranslateChaptersProcessingView from "@translate/chapters/TranslateChaptersProcessingView.svelte";

const emit = async (name, detail) => {
   window.dispatchEvent(new CustomEvent(`audiotools:translation:${name}`, { detail }));
   await tick();
};

describe("TranslateChaptersProcessingView — eventos audiotools:translation:*", () => {
   beforeEach(() => {
      render(TranslateChaptersProcessingView, {
         props: { goHome: vi.fn(), onCancel: vi.fn(), fileInfos: [{ path: "C:/a.m4b", name: "a.m4b", size_mb: 10 }] },
      });
   });
   afterEach(() => cleanup());

   it("muestra la fase que llega por :phase", async () => {
      expect(screen.getByText("Iniciando...")).toBeTruthy();
      await emit("phase", { phase: "Cargando modelo..." });
      expect(screen.getByText("Cargando modelo...")).toBeTruthy();
   });

   it("el work_info final reemplaza al texto crudo del stream", async () => {
      await emit("work_info_stream", { text: "<think>razono</think>\n Obra X \n" });
      expect(document.body.textContent).toContain("<think>razono</think>");

      await emit("work_info", { work_info: "Obra X" });
      expect(document.body.textContent).not.toContain("<think>");
      expect(screen.getByText("Obra X")).toBeTruthy();
   });

   it("muestra los títulos de un archivo apenas llegan por :file_titles", async () => {
      await emit("file_titles", {
         file_index: 0,
         chapters: [{ index: 1, start: 0, end: 5, original_title: "第一章", translated_title: "Chapter One" }],
      });
      expect(screen.getByText("Chapter One")).toBeTruthy();
   });

   it("ignora los nombres de evento anteriores (audiotools:chapters:*)", async () => {
      window.dispatchEvent(new CustomEvent("audiotools:chapters:phase", { detail: { phase: "vieja" } }));
      await tick();
      expect(screen.queryByText("vieja")).toBeNull();
   });
});
