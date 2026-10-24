import { describe, it, expect, beforeEach } from "vitest";
import { progress } from "@shared/state/progress.svelte.js";

const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

beforeEach(() => {
   progress.reset();
   progress.jobId = "J1";
   progress.running = true;
});

describe("progress store: eventos del job actual", () => {
   it("start fija el total y el instante de inicio", () => {
      emit("audiotools:start", { job_id: "J1", tool: "diverge", total: 4 });
      expect(progress.total).toBe(4);
      expect(progress.startTime).toBeTruthy();
   });

   it("log y progress se aplican", () => {
      emit("audiotools:log", { job_id: "J1", message: "hola" });
      emit("audiotools:progress", { job_id: "J1", value: 0.25, file_index: 1, file_progress: 0.5, completed: 1, total: 4 });
      expect([...progress.logs]).toEqual(["hola"]);
      expect(progress.value).toBe(0.25);
      expect(progress.fileIndex).toBe(1);
      expect(progress.completed).toBe(1);
   });

   it("done con éxito: running=false, success=true, value=1, sin error ni cancelled", () => {
      emit("audiotools:done", { job_id: "J1", success: true, cancelled: false });
      expect(progress.running).toBe(false);
      expect(progress.success).toBe(true);
      expect(progress.value).toBe(1);
      expect(progress.error).toBeNull();
      expect(progress.cancelled).toBe(false);
   });

   it("done con error: success=false y mensaje en progress.error", () => {
      emit("audiotools:done", { job_id: "J1", success: false, cancelled: false, error: "No se pudo leer la duración" });
      expect(progress.success).toBe(false);
      expect(progress.error).toBe("No se pudo leer la duración");
      expect(progress.cancelled).toBe(false);
   });

   it("done cancelado: success=false, cancelled=true y sin error", () => {
      emit("audiotools:done", { job_id: "J1", success: false, cancelled: true });
      expect(progress.success).toBe(false);
      expect(progress.cancelled).toBe(true);
      expect(progress.error).toBeNull();
   });
});

describe("progress store: aviso (warning)", () => {
   it("un done con warning lo guarda, sin ser un error", () => {
      emit("audiotools:done", { job_id: "J1", success: true, cancelled: false, warning: "No se pudieron incrustar los capítulos" });
      expect(progress.success).toBe(true);
      expect(progress.warning).toBe("No se pudieron incrustar los capítulos");
      expect(progress.error).toBeNull();
   });

   it("un done sin warning lo deja en null", () => {
      emit("audiotools:done", { job_id: "J1", success: true });
      expect(progress.warning).toBeNull();
   });

   it("reset() lo limpia", () => {
      emit("audiotools:done", { job_id: "J1", success: true, warning: "algo" });
      progress.reset();
      expect(progress.warning).toBeNull();
   });

   it("el warning de OTRO job se descarta", () => {
      emit("audiotools:done", { job_id: "otro", success: true, warning: "viejo" });
      expect(progress.warning).toBeNull();
      expect(progress.running).toBe(true);
   });
});

describe("progress store: eventos de otro job", () => {
   it("se descartan log, progress y done", () => {
      emit("audiotools:log", { job_id: "otro", message: "rezagado" });
      emit("audiotools:progress", { job_id: "otro", value: 0.9, completed: 3, total: 4 });
      emit("audiotools:done", { job_id: "otro", success: false, cancelled: true, error: "viejo" });
      expect(progress.logs.length).toBe(0);
      expect(progress.value).toBe(0);
      expect(progress.running).toBe(true);
      expect(progress.success).toBeNull();
      expect(progress.error).toBeNull();
      expect(progress.cancelled).toBe(false);
   });

   it("con jobId=null (tras reset) un evento que trae job_id también se descarta", () => {
      progress.reset();
      progress.running = true;
      emit("audiotools:done", { job_id: "J1", success: false });
      expect(progress.running).toBe(true);
      expect(progress.success).toBeNull();
   });
});

describe("progress store: tools sin migrar (sin job_id)", () => {
   beforeEach(() => {
      progress.jobId = null;
   });

   it("log, progress y done se siguen aceptando", () => {
      emit("audiotools:log", { message: "legacy" });
      emit("audiotools:progress", { value: 0.5, file_index: 0, completed: 0, total: 2 });
      expect([...progress.logs]).toEqual(["legacy"]);
      expect(progress.value).toBe(0.5);
      emit("audiotools:done", { success: false });
      expect(progress.running).toBe(false);
      expect(progress.success).toBe(false);
      expect(progress.cancelled).toBe(false);
   });

   it("done con cancelled:true (transcripción/traducción) también se refleja", () => {
      emit("audiotools:done", { success: false, cancelled: true });
      expect(progress.cancelled).toBe(true);
   });
});

describe("progress.reset()", () => {
   it("limpia job_id, error y cancelled", () => {
      emit("audiotools:done", { job_id: "J1", success: false, cancelled: true, error: "x" });
      progress.reset();
      expect(progress.jobId).toBeNull();
      expect(progress.error).toBeNull();
      expect(progress.cancelled).toBe(false);
      expect(progress.success).toBeNull();
      expect(progress.running).toBe(false);
   });
});

describe("progress store: logs por archivo", () => {
   const fileLog = (detail) => window.dispatchEvent(new CustomEvent("audiotools:transcribe:file_log", { detail }));

   beforeEach(() => {
      progress.reset();
      progress.jobId = "J1";
   });

   it("acumula los mensajes de cada archivo por su índice", () => {
      fileLog({ job_id: "J1", file_index: 0, message: "a" });
      fileLog({ job_id: "J1", file_index: 1, message: "b" });
      fileLog({ job_id: "J1", file_index: 0, message: "c" });
      expect(progress.fileLogs).toEqual({ 0: ["a", "c"], 1: ["b"] });
   });

   it("descarta los de otro job (un job cancelado que sigue hablando)", () => {
      fileLog({ job_id: "OTRO", file_index: 0, message: "viejo" });
      expect(progress.fileLogs).toEqual({});
   });

   it("ignora un índice inválido", () => {
      fileLog({ job_id: "J1", file_index: -1, message: "x" });
      fileLog({ job_id: "J1", file_index: "0", message: "x" });
      fileLog({ job_id: "J1", message: "x" });
      expect(progress.fileLogs).toEqual({});
   });

   it("reset() los limpia", () => {
      fileLog({ job_id: "J1", file_index: 0, message: "a" });
      progress.reset();
      expect(progress.fileLogs).toEqual({});
   });
});

