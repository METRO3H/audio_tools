import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import ConfirmModal from "@shared/ui/ConfirmModal.svelte";

afterEach(() => cleanup());

function open(props = {}) {
   const handlers = { onConfirm: vi.fn(), onCancel: vi.fn() };
   render(ConfirmModal, { props: { title: "Salir", message: "Hay un proceso en curso.", ...handlers, ...props } });
   return handlers;
}

describe("ConfirmModal", () => {
   it("es un diálogo titulado por su encabezado, con el mensaje visible", () => {
      open();
      expect(screen.getByRole("dialog", { name: "Salir" })).toBeTruthy();
      expect(screen.getByText("Hay un proceso en curso.")).toBeTruthy();
   });

   it("confirmar y cancelar llaman a su callback", async () => {
      const { onConfirm, onCancel } = open({ confirmLabel: "Salir ya", cancelLabel: "Quedarme" });
      await fireEvent.click(screen.getByRole("button", { name: "Salir ya" }));
      expect(onConfirm).toHaveBeenCalledTimes(1);
      await fireEvent.click(screen.getByRole("button", { name: "Quedarme" }));
      expect(onCancel).toHaveBeenCalledTimes(1);
   });

   it("Escape equivale a cancelar, nunca a confirmar", () => {
      const { onConfirm, onCancel } = open();
      screen.getByRole("dialog").dispatchEvent(new Event("cancel", { cancelable: true }));
      expect(onCancel).toHaveBeenCalledTimes(1);
      expect(onConfirm).not.toHaveBeenCalled();
   });

   it("un clic en el fondo equivale a cancelar", async () => {
      const { onConfirm, onCancel } = open();
      await fireEvent.pointerDown(screen.getByRole("dialog"));
      await fireEvent.click(screen.getByRole("dialog"));
      expect(onCancel).toHaveBeenCalledTimes(1);
      expect(onConfirm).not.toHaveBeenCalled();
   });

   it("danger pinta la confirmación en rojo; por defecto, en índigo", () => {
      open({ danger: true, confirmLabel: "Borrar" });
      expect(screen.getByRole("button", { name: "Borrar" }).className).toContain("bg-red-600");
      cleanup();
      open({ confirmLabel: "Seguir" });
      expect(screen.getByRole("button", { name: "Seguir" }).className).toContain("bg-indigo-600");
   });

   it("usa un ancho pequeño", () => {
      open();
      expect(screen.getByRole("dialog").firstElementChild.className).toContain("max-w-sm");
   });
});
