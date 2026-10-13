import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import ModalHarness from "./ModalHarness.svelte";

afterEach(() => {
   cleanup();
   vi.restoreAllMocks();
   document.body.innerHTML = "";
});

const open = (props = {}) => render(ModalHarness, { props: { label: "Prueba", ...props } });
const dialog = () => screen.getByRole("dialog");
const panel = () => dialog().firstElementChild;

describe("Modal: apertura y accesibilidad", () => {
   it("se abre como modal nativo al montarse", () => {
      const showModal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
      open();
      expect(showModal).toHaveBeenCalledTimes(1);
      expect(dialog().hasAttribute("open")).toBe(true);
   });

   it("es un diálogo con nombre accesible desde `label`", () => {
      open({ label: "Logs de ffmpeg" });
      expect(screen.getByRole("dialog", { name: "Logs de ffmpeg" })).toBeTruthy();
   });

   it("el nombre accesible puede venir de un título visible (`labelledby`)", () => {
      open({ label: undefined, labelledby: "harness-title" });
      expect(screen.getByRole("dialog", { name: "Título del modal" })).toBeTruthy();
   });

   it("muestra su contenido", () => {
      open();
      expect(screen.getByTestId("inside").textContent).toBe("Contenido");
      expect(screen.getByRole("button", { name: "Aceptar" })).toBeTruthy();
   });
});

describe("Modal: tamaño y clases", () => {
   it("por defecto: ancho 2xl y sin límite de altura", () => {
      open();
      expect(panel().className).toContain("max-w-2xl");
      expect(panel().className).not.toMatch(/max-h-|\bh-\[/);
   });

   it.each([
      ["sm", "max-w-sm"],
      ["xl", "max-w-xl"],
      ["2xl", "max-w-2xl"],
      ["4xl", "max-w-4xl"],
      ["5xl", "max-w-5xl"],
   ])("size=%s → %s", (size, cls) => {
      open({ size });
      expect(panel().className).toContain(cls);
   });

   it.each([
      ["max-85", "max-h-[85vh]"],
      ["max-90", "max-h-[90vh]"],
      ["fixed-85", "h-[85vh]"],
   ])("height=%s → %s", (height, cls) => {
      open({ height });
      expect(panel().className).toContain(cls);
   });

   it("añade las clases extra del llamador al panel", () => {
      open({ class: "gap-4 overflow-y-auto" });
      expect(panel().className).toContain("gap-4");
      expect(panel().className).toContain("overflow-y-auto");
   });
});

describe("Modal: cierre", () => {
   it("Escape (evento cancel): pide cerrar y evita el cierre automático del navegador", () => {
      const onClose = vi.fn();
      open({ onClose });
      const cancel = new Event("cancel", { cancelable: true });
      dialog().dispatchEvent(cancel);
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(cancel.defaultPrevented).toBe(true);
      expect(dialog().hasAttribute("open")).toBe(true); // lo desmonta el padre, no el navegador
   });

   it("un clic en el fondo pide cerrar", async () => {
      const onClose = vi.fn();
      open({ onClose });
      await fireEvent.pointerDown(dialog());
      await fireEvent.click(dialog());
      expect(onClose).toHaveBeenCalledTimes(1);
   });

   it("un clic dentro del panel no cierra", async () => {
      const onClose = vi.fn();
      open({ onClose });
      const inside = screen.getByTestId("inside");
      await fireEvent.pointerDown(inside);
      await fireEvent.click(inside);
      expect(onClose).not.toHaveBeenCalled();
   });

   it("seleccionar texto dentro del panel y soltar sobre el fondo NO cierra", async () => {
      const onClose = vi.fn();
      open({ onClose });
      await fireEvent.pointerDown(screen.getByTestId("inside")); // empieza dentro
      await fireEvent.click(dialog()); // el navegador dispara el clic sobre el ancestro común
      expect(onClose).not.toHaveBeenCalled();
   });

   it("empezar sobre el fondo y soltar dentro tampoco cierra, y no deja estado pegado", async () => {
      const onClose = vi.fn();
      open({ onClose });
      await fireEvent.pointerDown(dialog());
      await fireEvent.click(screen.getByTestId("inside"));
      expect(onClose).not.toHaveBeenCalled();

      await fireEvent.click(dialog()); // un clic suelto, sin pulsación previa sobre el fondo
      expect(onClose).not.toHaveBeenCalled();
   });

   it("sin onClose no falla", async () => {
      open({ onClose: undefined });
      dialog().dispatchEvent(new Event("cancel", { cancelable: true }));
      await fireEvent.pointerDown(dialog());
      await fireEvent.click(dialog());
      expect(dialog()).toBeTruthy();
   });
});

describe("Modal: ciclo de vida y foco", () => {
   it("al desmontarse cierra el diálogo y devuelve el foco a quien lo abrió", () => {
      const opener = document.createElement("button");
      document.body.appendChild(opener);
      opener.focus();
      expect(document.activeElement).toBe(opener);

      const close = vi.spyOn(HTMLDialogElement.prototype, "close");
      const { unmount } = open();
      screen.getByRole("button", { name: "Aceptar" }).focus(); // el foco pasa al modal
      expect(document.activeElement).not.toBe(opener);

      unmount();
      expect(close).toHaveBeenCalled();
      expect(document.activeElement).toBe(opener);
   });
});
