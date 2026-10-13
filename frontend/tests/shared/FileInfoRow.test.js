import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import FileInfoRow from "@shared/components/FileInfoRow.svelte";

afterEach(() => cleanup());
const row = () => screen.getByText("ep1.mp3").closest("div[class*='rounded-lg']");

describe("FileInfoRow: accesibilidad", () => {
   it("sin onRowClick es un bloque pasivo: sin rol ni tabindex", () => {
      render(FileInfoRow, { props: { name: "ep1.mp3" } });
      expect(screen.queryByRole("button")).toBeNull();
      expect(row().hasAttribute("tabindex")).toBe(false);
      expect(row().className).not.toContain("cursor-pointer");
   });

   it("con onRowClick es un botón alcanzable con teclado", async () => {
      const onRowClick = vi.fn();
      render(FileInfoRow, { props: { name: "ep1.mp3", onRowClick } });
      const button = screen.getByRole("button");
      expect(button.getAttribute("tabindex")).toBe("0");
      expect(button.className).toContain("cursor-pointer");

      await fireEvent.click(button);
      await fireEvent.keyDown(button, { key: "Enter" });
      await fireEvent.keyDown(button, { key: " " });
      await fireEvent.keyDown(button, { key: "a" });
      expect(onRowClick).toHaveBeenCalledTimes(3);
   });
});

describe("FileInfoRow: contenido", () => {
   it("muestra nombre, peso y duración formateada (con el formateador compartido)", () => {
      render(FileInfoRow, { props: { name: "ep1.mp3", sizeMb: 12, duration: 3725 } });
      expect(screen.getByText("12 MB")).toBeTruthy();
      expect(screen.getByText("1:02:05")).toBeTruthy();
   });

   it("sin peso (0) no lo muestra", () => {
      render(FileInfoRow, { props: { name: "ep1.mp3", sizeMb: 0, duration: 90 } });
      expect(screen.queryByText(/MB/)).toBeNull();
      expect(screen.getByText("1:30")).toBeTruthy();
   });

   it("en curso: porcentaje y barra; hecho: ✓ y sin barra", () => {
      const { unmount } = render(FileInfoRow, { props: { name: "ep1.mp3", active: true, progress: 0.42 } });
      expect(screen.getByText("42%")).toBeTruthy();
      expect(document.querySelector("[style*='width: 42%']")).toBeTruthy();
      unmount();

      render(FileInfoRow, { props: { name: "ep1.mp3", done: true, active: true, progress: 1, elapsedSeconds: 75 } });
      expect(screen.getByText("✓")).toBeTruthy();
      expect(screen.getByText("1:15")).toBeTruthy();
      expect(document.querySelector("[style*='width']")).toBeNull();
   });

   it("el color de la fila depende del estado", () => {
      render(FileInfoRow, { props: { name: "ep1.mp3", done: true } });
      expect(row().className).toContain("border-emerald-500/20");
      cleanup();
      render(FileInfoRow, { props: { name: "ep1.mp3", active: true } });
      expect(row().className).toContain("border-indigo-500/30");
   });
});
