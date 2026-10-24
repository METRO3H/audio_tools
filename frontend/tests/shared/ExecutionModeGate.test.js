import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import ExecutionModeGate from "@shared/components/ExecutionModeGate.svelte";
import { useExecutionTarget } from "@shared/state/useExecutionTarget.svelte.js";

afterEach(() => cleanup());

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};

function mount(check = vi.fn().mockResolvedValue({ found: true, state: "idle", host: "h", port: 1, models: [] })) {
   const target = useExecutionTarget({ check });
   render(ExecutionModeGate, {
      props: {
         title: "Transcribe",
         goHome: vi.fn(),
         target,
         remoteTitle: "Transcribir en remoto",
         remoteDescription: "Usa el server mediador.",
         localTitle: "Transcribir en esta PC",
         localDescription: "Carga el modelo localmente.",
      },
   });
   return { target, check };
}

describe("ExecutionModeGate", () => {
   it("muestra el título y las dos tarjetas con los textos que se le dan", () => {
      mount();
      expect(screen.getByText("Transcribe")).toBeTruthy();
      expect(screen.getByRole("button", { name: /Transcribir en remoto/ })).toBeTruthy();
      expect(screen.getByText("Usa el server mediador.")).toBeTruthy();
      expect(screen.getByRole("button", { name: /Transcribir en esta PC/ })).toBeTruthy();
      expect(screen.getByText("Carga el modelo localmente.")).toBeTruthy();
   });

   it("elegir local pone el modo local", async () => {
      const { target } = mount();
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en esta PC/ }));
      expect(target.mode).toBe("local");
   });

   it("elegir remoto consulta al mediador y, si está libre, pone el modo remoto", async () => {
      const { target, check } = mount();
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en remoto/ }));
      await flush();
      expect(check).toHaveBeenCalledTimes(1);
      expect(target.mode).toBe("remote");
   });

   it("mientras busca, la tarjeta remota muestra el spinner y se deshabilita", async () => {
      let finish;
      mount(() => new Promise((resolve) => (finish = resolve)));
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en remoto/ }));
      await flush();
      expect(screen.getByText("Buscando mediador en la red...")).toBeTruthy();
      expect(screen.getByRole("button", { name: /Buscando mediador/ }).disabled).toBe(true);
      finish({ found: false });
      await flush();
      expect(screen.queryByText("Buscando mediador en la red...")).toBeNull();
   });

   it("un fallo se anuncia como alerta bajo la tarjeta remota", async () => {
      mount(vi.fn().mockResolvedValue({ found: false }));
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en remoto/ }));
      await flush();
      expect(screen.getByRole("alert").textContent).toContain("No se encontró el server mediador");
   });
});
