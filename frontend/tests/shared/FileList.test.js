import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import FileList from "@shared/components/FileList.svelte";

afterEach(() => cleanup());

const FILES = [
   { name: "a.mp3", size_mb: 12.5, path: "C:/x/a.mp3" },
   { name: "b.mp3", size_mb: 3, path: "C:/x/b.mp3" },
];

describe("FileList", () => {
   it("muestra la etiqueta con la cantidad y cada archivo con su peso", () => {
      render(FileList, { props: { fileInfos: FILES } });
      expect(screen.getByText("(2)")).toBeTruthy();
      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("12.5 MB")).toBeTruthy();
      expect(screen.getByText("3 MB")).toBeTruthy();
   });

   it("sin archivos muestra el texto vacío (por defecto o el indicado) y sin cantidad", () => {
      const { unmount } = render(FileList, { props: { fileInfos: [] } });
      expect(screen.getByText("Selecciona una carpeta base primero")).toBeTruthy();
      expect(screen.queryByText(/\(\d+\)/)).toBeNull();
      unmount();
      render(FileList, { props: { fileInfos: [], emptyText: "No se encontraron audios en ./audios" } });
      expect(screen.getByText("No se encontraron audios en ./audios")).toBeTruthy();
   });

   it("el peso 0 no se muestra", () => {
      render(FileList, { props: { fileInfos: [{ name: "x.mp3", size_mb: 0, path: "p" }] } });
      expect(screen.queryByText(/MB/)).toBeNull();
   });

   it("la etiqueta es configurable", () => {
      render(FileList, { props: { fileInfos: FILES, label: "Capítulos" } });
      expect(screen.getByText(/Capítulos/)).toBeTruthy();
   });

   it("el mensaje de estado es amarillo si empieza por ⚠ y verde en caso contrario", () => {
      const { unmount } = render(FileList, { props: { autoHint: "⚠ No existe la carpeta" } });
      expect(screen.getByText("⚠ No existe la carpeta").className).toContain("text-yellow-400");
      unmount();
      render(FileList, { props: { autoHint: "✓ 3 archivo(s) detectados" } });
      expect(screen.getByText("✓ 3 archivo(s) detectados").className).toContain("text-emerald-400");
   });

   it("sin mensaje no hay línea de estado", () => {
      render(FileList, { props: { fileInfos: FILES } });
      expect(document.querySelector(".text-emerald-400, .text-yellow-400")).toBeNull();
   });
});

describe("FileList: acciones", () => {
   it("«Seleccionar manualmente» solo aparece si hay callback, y lo llama", async () => {
      const { unmount } = render(FileList, { props: { fileInfos: [] } });
      expect(screen.queryByRole("button", { name: "Seleccionar manualmente" })).toBeNull();
      unmount();

      const onPickFiles = vi.fn();
      render(FileList, { props: { fileInfos: [], onPickFiles } });
      await fireEvent.click(screen.getByRole("button", { name: "Seleccionar manualmente" }));
      expect(onPickFiles).toHaveBeenCalledTimes(1);
   });

   it("cada ✕ tiene nombre accesible con el archivo, y llama a onRemove con su ruta", async () => {
      const onRemove = vi.fn();
      render(FileList, { props: { fileInfos: FILES, onRemove } });
      expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["Quitar a.mp3", "Quitar b.mp3"]);

      await fireEvent.click(screen.getByRole("button", { name: "Quitar b.mp3" }));
      expect(onRemove).toHaveBeenCalledWith("C:/x/b.mp3");
   });

   it("sin onRemove no hay botones de quitar", () => {
      render(FileList, { props: { fileInfos: FILES } });
      expect(screen.queryByRole("button")).toBeNull();
   });

   it("disabled se propaga a los botones", () => {
      render(FileList, { props: { fileInfos: FILES, onRemove: vi.fn(), onPickFiles: vi.fn(), disabled: true } });
      expect(screen.getAllByRole("button").every((b) => b.disabled)).toBe(true);
   });

   it("los botones son de tipo button (no envían formularios)", () => {
      render(FileList, { props: { fileInfos: FILES, onRemove: vi.fn(), onPickFiles: vi.fn() } });
      expect(screen.getAllByRole("button").every((b) => b.getAttribute("type") === "button")).toBe(true);
   });

   it("dos archivos con el mismo nombre pero distinta ruta se muestran los dos", () => {
      render(FileList, {
         props: {
            fileInfos: [
               { name: "x.mp3", size_mb: 1, path: "C:/a/x.mp3" },
               { name: "x.mp3", size_mb: 2, path: "C:/b/x.mp3" },
            ],
         },
      });
      expect(screen.getAllByText("x.mp3").length).toBe(2);
   });

   it("loading muestra «Cargando archivos...» en lugar de la lista y del texto vacío", () => {
      render(FileList, { props: { fileInfos: FILES, loading: true } });
      expect(screen.getByText("Cargando archivos...")).toBeTruthy();
      expect(screen.queryByText("a.mp3")).toBeNull();
   });

   it("sin loading (por defecto) no hay spinner", () => {
      render(FileList, { props: { fileInfos: FILES } });
      expect(screen.queryByText("Cargando archivos...")).toBeNull();
   });

   it("height=\"fixed\" reserva una caja de altura fija con la lista, el texto vacío y la carga dentro", () => {
      const { container, unmount } = render(FileList, { props: { fileInfos: FILES, height: "fixed" } });
      const box = container.querySelector(".h-44");
      expect(box).toBeTruthy();
      expect(box.textContent).toContain("a.mp3");
      expect(box.querySelector("ul").className).not.toContain("max-h-40");
      unmount();

      const empty = render(FileList, { props: { fileInfos: [], height: "fixed", emptyText: "Nada aún" } });
      expect(empty.container.querySelector(".h-44").textContent).toContain("Nada aún");
      empty.unmount();

      const loading = render(FileList, { props: { fileInfos: [], height: "fixed", loading: true } });
      expect(loading.container.querySelector(".h-44").textContent).toContain("Cargando archivos...");
   });

   it("el tamaño por defecto (auto) no cambia: lista con máximo de altura y sin caja fija", () => {
      const { container } = render(FileList, { props: { fileInfos: FILES } });
      expect(container.querySelector(".h-44")).toBeNull();
      expect(container.querySelector("ul").className).toContain("max-h-40");
   });
});

