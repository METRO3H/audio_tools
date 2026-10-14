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
});
