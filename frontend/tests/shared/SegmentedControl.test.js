import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import SegmentedHarness from "./SegmentedHarness.svelte";

afterEach(() => cleanup());
const OPTIONS = [
   { value: "audio", label: "🎵 Audio" },
   { value: "video", label: "🎬 Video" },
];
const mount = (props = {}) => render(SegmentedHarness, { props: { options: OPTIONS, initial: "audio", ...props } });
const button = (name) => screen.getByRole("button", { name });
const value = () => screen.getByTestId("value").textContent;

describe("SegmentedControl", () => {
   it("es un grupo con nombre accesible y un botón por opción", () => {
      mount({ label: "Tipo" });
      expect(screen.getByRole("group", { name: "Tipo" })).toBeTruthy();
      expect(screen.getAllByRole("button").length).toBe(2);
   });

   it("marca la opción seleccionada con aria-pressed y con su aspecto", () => {
      mount();
      expect(button(/Audio/).getAttribute("aria-pressed")).toBe("true");
      expect(button(/Video/).getAttribute("aria-pressed")).toBe("false");
      expect(button(/Audio/).className).toContain("bg-indigo-600 text-white");
      expect(button(/Video/).className).toContain("border border-white/10 bg-white/5 text-white/50");
   });

   it("al pulsar otra opción cambia el valor enlazado y el aspecto", async () => {
      mount();
      await fireEvent.click(button(/Video/));
      expect(value()).toBe("video");
      expect(button(/Video/).getAttribute("aria-pressed")).toBe("true");
      expect(button(/Audio/).getAttribute("aria-pressed")).toBe("false");
   });

   it("onchange se llama una vez con el nuevo valor, y no al pulsar la opción ya seleccionada", async () => {
      const onchange = vi.fn();
      mount({ onchange });
      await fireEvent.click(button(/Audio/)); // ya seleccionada
      expect(onchange).not.toHaveBeenCalled();
      await fireEvent.click(button(/Video/));
      expect(onchange).toHaveBeenCalledTimes(1);
      expect(onchange).toHaveBeenCalledWith("video");
   });

   it("`fill` reparte el ancho (flex-1); sin él, los botones tienen su propio padding", () => {
      mount({ fill: true });
      expect(button(/Audio/).className).toContain("flex-1");
      cleanup();
      mount();
      expect(button(/Audio/).className).not.toContain("flex-1");
      expect(button(/Audio/).className).toContain("px-4");
   });

   it("admite valores que no son texto", async () => {
      mount({ options: [{ value: 1, label: "Uno" }, { value: 2, label: "Dos" }], initial: 1 });
      await fireEvent.click(button("Dos"));
      expect(value()).toBe("2");
   });

   it("los botones son de tipo button (no envían formularios)", () => {
      mount();
      expect(screen.getAllByRole("button").every((b) => b.getAttribute("type") === "button")).toBe(true);
   });

   it("`size=\"sm\"` da botones compactos; el tamaño por defecto no cambia", () => {
      mount();
      expect(button(/Audio/).className).toContain("rounded-lg py-2");
      cleanup();
      mount({ size: "sm" });
      expect(button(/Audio/).className).toContain("rounded-md px-3 py-1.5");
      expect(button(/Audio/).className).not.toContain("px-4");
   });

   it("`wrap` deja que los botones pasen a la línea siguiente; sin él, no", () => {
      mount({ wrap: true });
      expect(screen.getByRole("group").className).toContain("flex-wrap");
      cleanup();
      mount();
      expect(screen.getByRole("group").className).not.toContain("flex-wrap");
   });

   it("una opción `disabled` no se puede elegir: ni cambia el valor ni llama a onchange, y se ve atenuada", async () => {
      const onchange = vi.fn();
      mount({ onchange, options: [OPTIONS[0], { ...OPTIONS[1], disabled: true }] });
      expect(button(/Video/).disabled).toBe(true);
      expect(button(/Video/).className).toContain("opacity-30");
      expect(button(/Audio/).disabled).toBe(false);
      await fireEvent.click(button(/Video/));
      expect(value()).toBe("audio");
      expect(onchange).not.toHaveBeenCalled();
   });

   it("una opción `disabled` que es el valor seleccionado se sigue viendo seleccionada", () => {
      mount({ initial: "video", options: [OPTIONS[0], { ...OPTIONS[1], disabled: true }] });
      expect(button(/Video/).getAttribute("aria-pressed")).toBe("true");
      expect(button(/Video/).className).toContain("bg-indigo-600 text-white");
      expect(button(/Video/).className).not.toContain("opacity-30");
   });

   it("admite valores booleanos", async () => {
      mount({ options: [{ value: true, label: "Sí" }, { value: false, label: "No" }], initial: true });
      await fireEvent.click(button("No"));
      expect(value()).toBe("false");
      expect(button("No").getAttribute("aria-pressed")).toBe("true");
   });
});
