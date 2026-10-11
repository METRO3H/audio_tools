import { describe, it, expect, beforeEach, vi } from "vitest";

const bridgeMock = vi.hoisted(() => ({ run_x: vi.fn(), cancel: vi.fn() }));
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge: bridgeMock }));

import { useToolRun } from "@shared/state/useToolRun.svelte.js";
import { progress } from "@shared/state/progress.svelte.js";

const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

beforeEach(() => {
   progress.reset();
   bridgeMock.run_x.mockReset().mockResolvedValue(undefined);
   bridgeMock.cancel.mockReset();
});

describe("useToolRun", () => {
   it("start(): fija job_id, running y processing, y llama al bridge con las opciones + job_id", async () => {
      const job = useToolRun("run_x");
      await job.start({ file_path: "a.mp3" });

      expect(progress.jobId).toBeTruthy();
      expect(progress.running).toBe(true);
      expect(job.processing).toBe(true);
      expect(bridgeMock.run_x).toHaveBeenCalledWith({ file_path: "a.mp3", job_id: progress.jobId });
   });

   it("cada start() usa un job_id distinto y reinicia el estado anterior", async () => {
      const job = useToolRun("run_x");
      await job.start({});
      const first = progress.jobId;
      emit("audiotools:done", { job_id: first, success: false, error: "falló" });
      expect(progress.error).toBe("falló");

      await job.start({});
      expect(progress.jobId).not.toBe(first);
      expect(progress.error).toBeNull();
      expect(progress.success).toBeNull();
   });

   it("el done tardío de un job anterior NO corta el job nuevo", async () => {
      const job = useToolRun("run_x");
      await job.start({});
      const old = progress.jobId;
      job.back();
      await job.start({});

      emit("audiotools:done", { job_id: old, success: false, cancelled: true });
      expect(progress.running).toBe(true);
      expect(progress.success).toBeNull();
   });

   it("si el bridge lanza de forma síncrona (puente no listo) se muestra como error y no queda colgado", async () => {
      bridgeMock.run_x.mockImplementation(() => {
         throw new Error("[bridge] pywebview no está listo.");
      });
      const job = useToolRun("run_x");
      await job.start({});
      expect(progress.running).toBe(false);
      expect(progress.success).toBe(false);
      expect(progress.error).toMatch(/pywebview no está listo/);
   });

   it("si la llamada rechaza con un valor que no es Error, igual se muestra", async () => {
      bridgeMock.run_x.mockRejectedValue("fallo asíncrono");
      const job = useToolRun("run_x");
      await job.start({});
      expect(progress.success).toBe(false);
      expect(progress.error).toBe("fallo asíncrono");
   });

   it("back(): sale de la pantalla de proceso y limpia el estado", async () => {
      const job = useToolRun("run_x");
      await job.start({});
      job.back();
      expect(job.processing).toBe(false);
      expect(progress.jobId).toBeNull();
      expect(progress.running).toBe(false);
   });

   it("cancel() llama a bridge.cancel", () => {
      useToolRun("run_x").cancel();
      expect(bridgeMock.cancel).toHaveBeenCalledTimes(1);
   });
});
