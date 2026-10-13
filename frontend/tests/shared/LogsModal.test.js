import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import LogsModal from "@shared/components/LogsModal.svelte";

let writeText;
beforeEach(() => {
   writeText = vi.fn().mockResolvedValue();
   Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => cleanup());

const open = (props = {}) => {
   const onClose = vi.fn();
   render(LogsModal, { props: { logs: ["línea 1", "línea 2"], onClose, ...props } });
   return onClose;
};

describe("LogsModal", () => {
   it("muestra cada línea de log y se identifica como diálogo", () => {
      open();
      expect(screen.getByRole("dialog", { name: "Logs de ffmpeg" })).toBeTruthy();
      expect(screen.getByText("línea 1")).toBeTruthy();
      expect(screen.getByText("línea 2")).toBeTruthy();
   });

   it("las líneas repetidas se muestran todas (no se pierden por claves duplicadas)", () => {
      open({ logs: ["igual", "igual", "igual"] });
      expect(screen.getAllByText("igual").length).toBe(3);
   });

   it("sin logs: mensaje vacío y copiar deshabilitado", () => {
      open({ logs: [] });
      expect(screen.getByText("Sin logs aún...")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Copiar todo" }).disabled).toBe(true);
   });

   it("copia todas las líneas unidas por saltos de línea", async () => {
      open();
      await fireEvent.click(screen.getByRole("button", { name: "Copiar todo" }));
      await tick();
      await Promise.resolve();
      expect(writeText).toHaveBeenCalledWith("línea 1\nlínea 2");
   });

   it("el botón ✕ tiene nombre accesible y cierra", async () => {
      const onClose = open();
      await fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
      expect(onClose).toHaveBeenCalledTimes(1);
   });

   it("Escape pide cerrar", () => {
      const onClose = open();
      screen.getByRole("dialog").dispatchEvent(new Event("cancel", { cancelable: true }));
      expect(onClose).toHaveBeenCalledTimes(1);
   });

   it("el área de logs permite seleccionar texto (la raíz de la app lo desactiva)", () => {
      open();
      expect(screen.getByText("línea 1").parentElement.className).toContain("select-text");
   });
});
