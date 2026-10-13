import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import TranscribeFileLogsModal from "@shared/components/TranscribeFileLogsModal.svelte";

let writeText;
beforeEach(() => {
   writeText = vi.fn().mockResolvedValue();
   Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => cleanup());

const open = (props = {}) => {
   const onClose = vi.fn();
   render(TranscribeFileLogsModal, { props: { name: "ep1.mp3", logs: [], onClose, ...props } });
   return onClose;
};

describe("TranscribeFileLogsModal", () => {
   it("el diálogo se nombra con el archivo y tiene alto fijo y ancho 4xl", () => {
      open();
      const dialog = screen.getByRole("dialog", { name: "Procesamiento de ep1.mp3" });
      expect(dialog.firstElementChild.className).toContain("h-[85vh]");
      expect(dialog.firstElementChild.className).toContain("max-w-4xl");
   });

   it.each([
      ["Completado", "text-emerald-400"],
      ["Finalizado con error", "text-red-400"],
      ["Cancelado", "text-amber-400"],
      ["Procesando", "text-indigo-300"],
      ["En espera", "text-white/40"],
   ])("el estado «%s» se pinta con %s", (status, cls) => {
      open({ status });
      expect(screen.getAllByText(status).find((el) => el.tagName === "SPAN").className).toContain(cls);
   });

   it("sin logs, el mensaje depende de si el archivo ya empezó", () => {
      open({ status: "En espera" });
      expect(screen.getByText(/todavía no ha comenzado/)).toBeTruthy();
      cleanup();
      open({ status: "Procesando" });
      expect(screen.getByText(/Esperando los primeros mensajes/)).toBeTruthy();
   });

   it("distingue segmentos y errores por color", () => {
      open({ logs: ["[0.0s -> 3.2s] hola", "[error] falló", "normal"], status: "Procesando" });
      expect(screen.getByText("[0.0s -> 3.2s] hola").className).toContain("text-white/85");
      expect(screen.getByText("[error] falló").className).toContain("text-red-300");
      expect(screen.getByText("normal").className).toContain("text-white/45");
   });

   it("copia los logs, y el botón está deshabilitado si no hay", async () => {
      open({ logs: ["a", "b"] });
      await fireEvent.click(screen.getByRole("button", { name: "Copiar todo" }));
      await tick();
      await Promise.resolve();
      expect(writeText).toHaveBeenCalledWith("a\nb");
      cleanup();
      open({ logs: [] });
      expect(screen.getByRole("button", { name: "Copiar todo" }).disabled).toBe(true);
   });

   it("cierra con el botón ✕ y con Escape", async () => {
      const onClose = open();
      await fireEvent.click(screen.getByRole("button", { name: "Cerrar modal" }));
      screen.getByRole("dialog").dispatchEvent(new Event("cancel", { cancelable: true }));
      expect(onClose).toHaveBeenCalledTimes(2);
   });
});
