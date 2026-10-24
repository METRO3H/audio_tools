import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

vi.mock("@shared/services/bridge.svelte.js", () => ({
   bridge: new Proxy({}, { get: () => vi.fn() }),
}));

import ProcessingView from "@shared/components/ProcessingView.svelte";
import { progress } from "@shared/state/progress.svelte.js";

const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));
const flush = async () => { await tick(); await Promise.resolve(); await tick(); };

function mount(overrides = {}) {
   const props = {
      title: "Dividir audio",
      goHome: vi.fn(),
      fileInfos: [{ name: "a.mp3", size_mb: 1, duration_seconds: 60 }],
      outputPath: "C:/out",
      onCancel: vi.fn(),
      onBack: vi.fn(),
      ...overrides,
   };
   render(ProcessingView, { props });
   return props;
}

const cancelButton = () => screen.getByRole("button", { name: /^(Cancelar|Cancelando\.\.\.)$/ });
const statusSpan = (text) => screen.getAllByText(text).find((el) => el.className.includes("text-sm font-medium"));

beforeEach(() => {
   progress.reset();
   progress.jobId = "J1";
   progress.running = true;
});
afterEach(() => cleanup());

describe("ProcessingView: cancelación", () => {
   it("en curso: botón Cancelar habilitado y estado Procesando", () => {
      mount();
      expect(cancelButton().textContent.trim()).toBe("Cancelar");
      expect(cancelButton().disabled).toBe(false);
      expect(screen.getAllByText("Procesando...").length).toBeGreaterThan(0);
   });

   it("al pulsar Cancelar: llama a onCancel y muestra Cancelando... (botón, estado y barra) con el botón deshabilitado", async () => {
      const { onCancel } = mount();
      cancelButton().click();
      await flush();
      expect(onCancel).toHaveBeenCalledTimes(1);
      expect(cancelButton().textContent.trim()).toBe("Cancelando...");
      expect(cancelButton().disabled).toBe(true);
      // botón + estado global + etiqueta de la barra
      expect(screen.getAllByText("Cancelando...").length).toBe(3);
      expect(screen.queryByText("Procesando...")).toBeNull();
   });

   it("un segundo clic no vuelve a llamar a onCancel", async () => {
      const { onCancel } = mount();
      cancelButton().click();
      await flush();
      cancelButton().click();
      await flush();
      expect(onCancel).toHaveBeenCalledTimes(1);
   });

   it("done{cancelled:true}: se muestra Cancelado en ámbar, sin recuadro de error, y aparece Volver", async () => {
      mount();
      cancelButton().click();
      await flush();
      emit("audiotools:done", { job_id: "J1", success: false, cancelled: true });
      await flush();

      expect(statusSpan("Cancelado").className).toContain("text-amber-400");
      expect(screen.getAllByText("Cancelado").length).toBe(2); // estado + barra
      expect(screen.queryByText("Error")).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
      expect(screen.queryByRole("button", { name: /Cancel/ })).toBeNull(); // ya no hay botón Cancelar
      expect(screen.getByRole("button", { name: "Volver" })).toBeTruthy();
   });

   it("done{success:false} sin cancelled: sigue siendo Error en rojo", async () => {
      mount();
      emit("audiotools:done", { job_id: "J1", success: false, cancelled: false, error: "No se pudo leer la duración" });
      await flush();
      expect(statusSpan("Error").className).toContain("text-red-400");
      expect(screen.queryByText("Cancelado")).toBeNull();
      expect(screen.getByRole("alert").textContent).toContain("No se pudo leer la duración");
   });

   it("done{success:true}: Completado en verde", async () => {
      mount();
      emit("audiotools:done", { job_id: "J1", success: true, cancelled: false });
      await flush();
      expect(statusSpan("Completado").className).toContain("text-emerald-400");
   });

   it("done con warning: el job se ve Completado y el aviso aparece en ámbar, no como error", async () => {
      mount();
      emit("audiotools:done", {
         job_id: "J1", success: true, cancelled: false,
         warning: "No se pudieron incrustar los capítulos: sin permiso",
      });
      await flush();

      expect(statusSpan("Completado").className).toContain("text-emerald-400");
      const warning = screen.getByRole("status");
      expect(warning.textContent).toContain("No se pudieron incrustar los capítulos");
      expect(warning.className).toContain("text-amber-300");
      expect(screen.queryByRole("alert")).toBeNull();
   });

   it("sin warning no hay recuadro de aviso", async () => {
      mount();
      emit("audiotools:done", { job_id: "J1", success: true, cancelled: false });
      await flush();
      expect(screen.queryByRole("status")).toBeNull();
   });

   it("el job termina bien aunque se haya pulsado Cancelar: no queda como cancelado", async () => {
      mount();
      cancelButton().click();
      await flush();
      emit("audiotools:done", { job_id: "J1", success: true, cancelled: false });
      await flush();
      expect(statusSpan("Completado")).toBeTruthy();
      expect(screen.queryByText("Cancelando...")).toBeNull();
   });

   it("si onCancel falla (puente caído) el botón se reactiva para reintentar", async () => {
      mount({ onCancel: vi.fn().mockRejectedValue(new Error("bridge caído")) });
      cancelButton().click();
      await flush();
      await flush();
      expect(cancelButton().textContent.trim()).toBe("Cancelar");
      expect(cancelButton().disabled).toBe(false);
   });

   it("tras cancelar y terminar, un job NUEVO sobre la misma instancia arranca con el botón Cancelar activo", async () => {
      mount();
      cancelButton().click();
      await flush();
      emit("audiotools:done", { job_id: "J1", success: false, cancelled: true });
      await flush();

      progress.reset();
      progress.jobId = "J2";
      progress.running = true;
      await flush();

      expect(cancelButton().textContent.trim()).toBe("Cancelar");
      expect(cancelButton().disabled).toBe(false);
      expect(screen.queryByText("Cancelando...")).toBeNull();
   });

   it("un done de OTRO job no cambia nada (sigue en curso)", async () => {
      mount();
      emit("audiotools:done", { job_id: "viejo", success: false, cancelled: true });
      await flush();
      expect(cancelButton().textContent.trim()).toBe("Cancelar");
      expect(screen.queryByText("Cancelado")).toBeNull();
   });

   it("tools sin migrar (done sin job_id ni cancelled) se muestran como antes: Error", async () => {
      progress.jobId = null;
      mount();
      emit("audiotools:done", { success: false });
      await flush();
      expect(statusSpan("Error").className).toContain("text-red-400");
   });

   it("transcripción local/remota: done con cancelled:true y sin job_id también se ve como Cancelado", async () => {
      progress.jobId = null;
      mount();
      emit("audiotools:done", { success: false, cancelled: true });
      await flush();
      expect(statusSpan("Cancelado").className).toContain("text-amber-400");
   });
});

describe("ProcessingView: logs por archivo", () => {
   const fileLog = (index, message) =>
      emit("audiotools:transcribe:file_log", { job_id: "J1", file_index: index, message });

   it("con enableFileLogs, pulsar un archivo abre sus logs, tomados del store", async () => {
      mount({ enableFileLogs: true });
      fileLog(0, "[0.00s -> 1.00s] hola");
      fileLog(1, "no es de este archivo");
      await flush();

      await fireEvent.click(screen.getByText("a.mp3"));
      await flush();
      expect(screen.getByText("[0.00s -> 1.00s] hola")).toBeTruthy();
      expect(screen.queryByText("no es de este archivo")).toBeNull();
   });

   it("sin enableFileLogs, pulsar un archivo no abre nada", async () => {
      mount();
      fileLog(0, "[0.00s -> 1.00s] hola");
      await flush();
      await fireEvent.click(screen.getByText("a.mp3"));
      await flush();
      expect(screen.queryByText("[0.00s -> 1.00s] hola")).toBeNull();
   });
});

