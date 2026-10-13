import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import CopyButton from "@shared/ui/CopyButton.svelte";

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};
let writeText;

beforeEach(() => {
   vi.useFakeTimers();
   writeText = vi.fn().mockResolvedValue();
   Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => {
   cleanup();
   vi.useRealTimers();
   delete document.execCommand;
});

const button = () => screen.getByRole("button");

describe("CopyButton", () => {
   it("copia el texto y muestra la confirmación; luego vuelve a la etiqueta original", async () => {
      render(CopyButton, { props: { text: "hola mundo" } });
      expect(button().textContent.trim()).toBe("Copiar todo");

      await fireEvent.click(button());
      await flush();
      expect(writeText).toHaveBeenCalledWith("hola mundo");
      expect(button().textContent.trim()).toBe("✓ Copiado");

      await vi.advanceTimersByTimeAsync(2000);
      await flush();
      expect(button().textContent.trim()).toBe("Copiar todo");
   });

   it("con una función, el texto se calcula solo al pulsar", async () => {
      const text = vi.fn(() => "calculado");
      render(CopyButton, { props: { text } });
      expect(text).not.toHaveBeenCalled();

      await fireEvent.click(button());
      await flush();
      expect(text).toHaveBeenCalledTimes(1);
      expect(writeText).toHaveBeenCalledWith("calculado");
   });

   it("si el texto está vacío no copia ni confirma", async () => {
      render(CopyButton, { props: { text: () => "" } });
      await fireEvent.click(button());
      await flush();
      expect(writeText).not.toHaveBeenCalled();
      expect(button().textContent.trim()).toBe("Copiar todo");
   });

   it("deshabilitado: el botón queda deshabilitado", () => {
      // Un navegador no entrega clics a un botón disabled (jsdom sí despacha los sintéticos),
      // así que basta con comprobar el atributo.
      render(CopyButton, { props: { text: "x", disabled: true } });
      expect(button().disabled).toBe(true);
   });

   it("etiquetas personalizadas", async () => {
      render(CopyButton, { props: { text: "x", label: "Copiar log", copiedLabel: "¡Listo!" } });
      expect(button().textContent.trim()).toBe("Copiar log");
      await fireEvent.click(button());
      await flush();
      expect(button().textContent.trim()).toBe("¡Listo!");
   });

   it("`class` reemplaza el estilo por defecto", () => {
      const { unmount } = render(CopyButton, { props: { text: "x" } });
      expect(button().className).toContain("border-white/10");
      unmount();
      render(CopyButton, { props: { text: "x", class: "mi-clase" } });
      expect(button().className).toBe("mi-clase");
   });

   it("si no se logra copiar de ninguna forma, no muestra la confirmación", async () => {
      writeText.mockRejectedValue(new Error("denegado"));
      document.execCommand = vi.fn().mockReturnValue(false);
      render(CopyButton, { props: { text: "x" } });
      await fireEvent.click(button());
      await flush();
      expect(button().textContent.trim()).toBe("Copiar todo");
   });

   it("pulsar dos veces seguidas reinicia el temporizador de la confirmación", async () => {
      render(CopyButton, { props: { text: "x" } });
      await fireEvent.click(button());
      await flush();
      await vi.advanceTimersByTimeAsync(1500);
      await fireEvent.click(button());
      await flush();
      await vi.advanceTimersByTimeAsync(1500); // 3000 desde el primero, 1500 desde el segundo
      await flush();
      expect(button().textContent.trim()).toBe("✓ Copiado");
      await vi.advanceTimersByTimeAsync(600);
      await flush();
      expect(button().textContent.trim()).toBe("Copiar todo");
   });

   it("al desmontarse no deja temporizadores pendientes", async () => {
      const { unmount } = render(CopyButton, { props: { text: "x" } });
      await fireEvent.click(button());
      await flush();
      expect(vi.getTimerCount()).toBe(1);
      unmount();
      expect(vi.getTimerCount()).toBe(0);
   });
});
