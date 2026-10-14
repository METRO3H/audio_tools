import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import TranscribeView from "@transcribe/TranscribeView.svelte";
import { appConfig } from "@shared/state/config.svelte.js";
import { progress } from "@shared/state/progress.svelte.js";

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};

beforeEach(async () => {
   localStorage.clear();
   progress.reset();
   vi.resetAllMocks();
   appConfig.baseFolder = "C:/Proj";
   appConfig.transcribeInitialPrompt = "";
   render(TranscribeView, { props: { goHome: vi.fn() } });
   await fireEvent.click(screen.getByRole("button", { name: /Transcribir en esta PC/ }));
   await flush();
   await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
   await flush();
});
afterEach(() => cleanup());

const dialog = () => screen.getByRole("dialog", { name: "Opciones adicionales" });
const toggle = (name) => within(dialog()).getByRole("switch", { name });

describe("Transcribe: modal de opciones adicionales", () => {
   it("se abre como diálogo titulado por su encabezado", () => {
      expect(dialog()).toBeTruthy();
   });

   it("muestra los tres interruptores con su nombre y su valor inicial", () => {
      expect(toggle("VAD filter").getAttribute("aria-checked")).toBe("true");
      expect(toggle("Condition on previous text").getAttribute("aria-checked")).toBe("false");
      expect(toggle("Word timestamps").getAttribute("aria-checked")).toBe("true");
   });

   it("cada interruptor alterna de forma independiente", async () => {
      await fireEvent.click(toggle("VAD filter"));
      await fireEvent.click(toggle("Condition on previous text"));
      expect(toggle("VAD filter").getAttribute("aria-checked")).toBe("false");
      expect(toggle("Condition on previous text").getAttribute("aria-checked")).toBe("true");
      expect(toggle("Word timestamps").getAttribute("aria-checked")).toBe("true");
   });

   it("cada fila tiene su icono de ayuda, y el prompt inicial también", () => {
      expect(within(dialog()).getAllByRole("button", { name: "?" }).length).toBe(4);
   });

   it("el campo «Initial prompt» está asociado a su caja de texto", async () => {
      const textarea = within(dialog()).getByLabelText("Initial prompt");
      expect(textarea.tagName).toBe("TEXTAREA");
      await fireEvent.input(textarea, { target: { value: "Transcribe en japonés." } });
      expect(textarea.value).toBe("Transcribe en japonés.");
   });

   it("Escape cierra el modal y lo elegido se conserva al reabrirlo", async () => {
      await fireEvent.click(toggle("Word timestamps"));
      await fireEvent.input(within(dialog()).getByLabelText("Initial prompt"), { target: { value: "hola" } });

      dialog().dispatchEvent(new Event("cancel", { cancelable: true }));
      await flush();
      expect(screen.queryByRole("dialog")).toBeNull();

      await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
      await flush();
      expect(toggle("Word timestamps").getAttribute("aria-checked")).toBe("false");
      expect(within(dialog()).getByLabelText("Initial prompt").value).toBe("hola");
   });

   it("«Listo» y el clic en el fondo también lo cierran", async () => {
      await fireEvent.click(screen.getByRole("button", { name: "Listo" }));
      await flush();
      expect(screen.queryByRole("dialog")).toBeNull();

      await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
      await flush();
      await fireEvent.pointerDown(dialog());
      await fireEvent.click(dialog());
      await flush();
      expect(screen.queryByRole("dialog")).toBeNull();
   });
});
