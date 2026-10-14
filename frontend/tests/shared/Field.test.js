import { render, screen, cleanup } from "@testing-library/svelte";
import { createRawSnippet } from "svelte";
import { describe, it, expect, afterEach } from "vitest";
import Field from "@shared/ui/Field.svelte";

afterEach(() => cleanup());

const inputSnippet = createRawSnippet(() => ({ render: () => `<input id="x" data-testid="control" />` }));
const mount = (props = {}) => render(Field, { props: { label: "Intervalo", children: inputSnippet, ...props } });

describe("Field", () => {
   it("muestra la etiqueta y su contenido", () => {
      mount();
      expect(screen.getByText("Intervalo")).toBeTruthy();
      expect(screen.getByTestId("control")).toBeTruthy();
   });

   it("con `for`, la etiqueta es un <label> asociado al control", () => {
      mount({ for: "x" });
      expect(screen.getByLabelText("Intervalo")).toBe(screen.getByTestId("control"));
      expect(screen.getByText("Intervalo").tagName).toBe("LABEL");
   });

   it("sin `for`, la etiqueta es un texto suelto (no un label huérfano)", () => {
      mount();
      expect(screen.getByText("Intervalo").tagName).toBe("SPAN");
      expect(document.querySelector("label")).toBeNull();
   });

   it("el icono de ayuda aparece solo si se da `help`", () => {
      mount();
      expect(screen.queryByRole("button", { name: "?" })).toBeNull();
      cleanup();
      mount({ help: "Una explicación" });
      expect(screen.getByRole("button", { name: "?" })).toBeTruthy();
   });

   it("estilo de etiqueta canónico y clases extra en el contenedor", () => {
      mount({ class: "mt-2" });
      expect(screen.getByText("Intervalo").className).toContain("text-xs text-white/40");
      expect(screen.getByText("Intervalo").closest(".flex-col").className).toContain("mt-2");
   });
});
