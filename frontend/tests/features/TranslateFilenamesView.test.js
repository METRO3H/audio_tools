import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import TranslateFilenamesView from "@translate/filenames/TranslateFilenamesView.svelte";
import { progress } from "@shared/state/progress.svelte.js";

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};

const emit = async (name, detail) => {
   window.dispatchEvent(new CustomEvent(`audiotools:translation:${name}`, { detail }));
   await flush();
};

// Lleva la vista hasta la pantalla de progreso: modo local, carpeta con un archivo por traducir,
// modelo elegido (TranslationSettings toma el primero) y "Traducir nombres".
async function startRun() {
   render(TranslateFilenamesView, { props: { goHome: vi.fn() } });
   await flush();
   await fireEvent.click(screen.getByRole("button", { name: /Traducir en esta PC/ }));
   await flush();
   await fireEvent.click(screen.getByText("Sin seleccionar"));
   await flush();
   await flush();
   await fireEvent.click(screen.getByRole("button", { name: /Traducir nombres \(1\)/ }));
   await flush();
}

describe("TranslateFilenamesView — eventos audiotools:translation:*", () => {
   beforeEach(async () => {
      localStorage.clear();
      progress.reset();
      vi.resetAllMocks();
      bridge.check_remote_translation_server.mockResolvedValue({ found: false });
      bridge.list_prompt_languages.mockResolvedValue(["japanese"]);
      bridge.get_translation_prompt.mockResolvedValue("prompt");
      bridge.get_glossary.mockResolvedValue("");
      bridge.list_translation_models.mockResolvedValue(["modelo-a"]);
      bridge.pick_folder.mockResolvedValue("C:/Proj/carpeta");
      bridge.scan_filenames_folder.mockResolvedValue([
         { path: "C:/Proj/carpeta/日本語.mp3", relative_path: "日本語.mp3", needs_translation: true },
      ]);
      bridge.run_translate_filenames_preview.mockResolvedValue(undefined);
      await startRun();
   });
   afterEach(() => cleanup());

   it("arranca el job y muestra la fase que llega por :phase", async () => {
      expect(bridge.run_translate_filenames_preview).toHaveBeenCalledOnce();
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

   it("muestra la salida del modelo que llega por :name_stream", async () => {
      await emit("name_stream", { text: "1: Japanese Title" });
      expect(screen.getByText("1: Japanese Title")).toBeTruthy();
   });

   it("ignora los nombres de evento anteriores (audiotools:filenames:*)", async () => {
      window.dispatchEvent(new CustomEvent("audiotools:filenames:phase", { detail: { phase: "vieja" } }));
      window.dispatchEvent(new CustomEvent("audiotools:filenames:translate_stream", { detail: { text: "vieja" } }));
      await flush();
      expect(screen.queryByText("vieja")).toBeNull();
   });
});
