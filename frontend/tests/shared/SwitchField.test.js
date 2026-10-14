import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import SwitchFieldHarness from "./SwitchFieldHarness.svelte";

afterEach(() => cleanup());
const help = () => screen.queryByRole("button", { name: "?" });

describe("SwitchField", () => {
   it("muestra la etiqueta y el interruptor se llama igual", () => {
      render(SwitchFieldHarness, { props: { label: "Word timestamps" } });
      expect(screen.getByText("Word timestamps")).toBeTruthy();
      expect(screen.getByRole("switch", { name: "Word timestamps" })).toBeTruthy();
   });

   it("alterna y refleja el valor enlazado", async () => {
      render(SwitchFieldHarness, { props: { label: "Opción", initial: true } });
      expect(screen.getByTestId("state").textContent).toBe("true");
      await fireEvent.click(screen.getByRole("switch"));
      expect(screen.getByTestId("state").textContent).toBe("false");
   });

   it("muestra el icono de ayuda solo si se da `help`", () => {
      render(SwitchFieldHarness, { props: { label: "A" } });
      expect(help()).toBeNull();
      cleanup();
      render(SwitchFieldHarness, { props: { label: "A", help: "Explicación" } });
      expect(help()).toBeTruthy();
   });

   it("muestra la descripción bajo la etiqueta solo si se da", () => {
      render(SwitchFieldHarness, { props: { label: "A", description: "C:\\salida\\parts" } });
      expect(screen.getByText("C:\\salida\\parts").className).toContain("truncate");
      cleanup();
      render(SwitchFieldHarness, { props: { label: "A" } });
      expect(document.querySelector(".truncate")).toBeNull();
   });

   it("con contenido hijo, ese reemplaza a la etiqueta visible pero el nombre accesible sigue siendo `label`", () => {
      render(SwitchFieldHarness, { props: { label: "Guardar en subcarpeta", rich: true } });
      expect(screen.getByText("con formato").tagName).toBe("CODE");
      expect(screen.queryByText("Guardar en subcarpeta")).toBeNull();
      expect(screen.getByRole("switch", { name: "Guardar en subcarpeta" })).toBeTruthy();
   });

   it("el tamaño del texto de la etiqueta: md = text-sm, sm = text-xs", () => {
      render(SwitchFieldHarness, { props: { label: "A" } });
      expect(screen.getByText("A").className).toContain("text-sm");
      cleanup();
      render(SwitchFieldHarness, { props: { label: "A", size: "sm" } });
      expect(screen.getByText("A").className).toContain("text-xs");
   });

   it("las clases extra se aplican a la fila", () => {
      render(SwitchFieldHarness, { props: { label: "A", class: "rounded-lg border px-3" } });
      const row = screen.getByRole("switch").parentElement;
      expect(row.className).toContain("justify-between");
      expect(row.className).toContain("rounded-lg border px-3");
   });

   it("deshabilitado se propaga al interruptor", () => {
      render(SwitchFieldHarness, { props: { label: "A", disabled: true } });
      expect(screen.getByRole("switch").disabled).toBe(true);
   });
});
