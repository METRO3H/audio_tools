import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import SwitchHarness from "./SwitchHarness.svelte";

afterEach(() => cleanup());
const toggle = () => screen.getByRole("switch");
const state = () => screen.getByTestId("state").textContent;

describe("Switch", () => {
   it("es un interruptor con nombre accesible (aunque no tenga texto visible)", () => {
      render(SwitchHarness, { props: { label: "VAD filter" } });
      expect(screen.getByRole("switch", { name: "VAD filter" })).toBeTruthy();
      expect(toggle().textContent.trim()).toBe("");
   });

   it("aria-checked refleja el estado, y el aspecto cambia con él", () => {
      render(SwitchHarness, { props: { initial: false } });
      expect(toggle().getAttribute("aria-checked")).toBe("false");
      expect(toggle().className).toContain("bg-white/10");
      expect(toggle().firstElementChild.className).toContain("translate-x-0");
      cleanup();

      render(SwitchHarness, { props: { initial: true } });
      expect(toggle().getAttribute("aria-checked")).toBe("true");
      expect(toggle().className).toContain("bg-indigo-600");
      expect(toggle().firstElementChild.className).toContain("translate-x-4");
   });

   it("al pulsarlo alterna y actualiza el valor enlazado del padre", async () => {
      render(SwitchHarness, { props: { initial: false } });
      await fireEvent.click(toggle());
      expect(state()).toBe("true");
      expect(toggle().getAttribute("aria-checked")).toBe("true");
      await fireEvent.click(toggle());
      expect(state()).toBe("false");
   });

   it("onchange recibe el nuevo valor en cada alternancia", async () => {
      const onchange = vi.fn();
      render(SwitchHarness, { props: { initial: false, onchange } });
      await fireEvent.click(toggle());
      await fireEvent.click(toggle());
      expect(onchange.mock.calls).toEqual([[true], [false]]);
   });

   it("deshabilitado: el botón queda deshabilitado", () => {
      render(SwitchHarness, { props: { disabled: true } });
      expect(toggle().disabled).toBe(true);
   });

   it("es un botón de tipo button (no envía formularios)", () => {
      render(SwitchHarness);
      expect(toggle().getAttribute("type")).toBe("button");
   });
});
