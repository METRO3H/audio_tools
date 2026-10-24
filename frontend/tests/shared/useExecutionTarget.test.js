import { describe, it, expect, vi } from "vitest";
import { useExecutionTarget } from "@shared/state/useExecutionTarget.svelte.js";

const MEDIATOR = { found: true, state: "idle", host: "10.0.0.5", port: 9000, models: ["medium", "large-v3"] };

function make(result = MEDIATOR) {
   const check = typeof result === "function" ? vi.fn(result) : vi.fn().mockResolvedValue(result);
   return { target: useExecutionTarget({ check }), check };
}

describe("useExecutionTarget", () => {
   it("empieza sin modo elegido ni destino", () => {
      const { target } = make();
      expect([target.mode, target.checking, target.error, target.remote, target.target]).toEqual([null, false, "", null, null]);
   });

   it("selectLocal: modo local, destino local, sin consultar al mediador", () => {
      const { target, check } = make();
      target.selectLocal();
      expect(target.mode).toBe("local");
      expect(target.target).toEqual({ mode: "local" });
      expect(check).not.toHaveBeenCalled();
   });

   it("selectRemote con el mediador libre: modo remoto, su información y el destino con host y puerto", async () => {
      const { target, check } = make();
      await target.selectRemote();
      expect(check).toHaveBeenCalledTimes(1);
      expect(target.mode).toBe("remote");
      expect(target.remote).toEqual(MEDIATOR);
      expect(target.target).toEqual({ mode: "remote", host: "10.0.0.5", port: 9000 });
      expect(target.error).toBe("");
      expect(target.checking).toBe(false);
   });

   it("mientras consulta, checking es true; y un segundo clic no lanza otra consulta", async () => {
      let finish;
      const { target, check } = make(() => new Promise((resolve) => (finish = resolve)));
      const first = target.selectRemote();
      expect(target.checking).toBe(true);
      await target.selectRemote();
      expect(check).toHaveBeenCalledTimes(1);
      finish(MEDIATOR);
      await first;
      expect(target.checking).toBe(false);
   });

   it("mediador no encontrado: se explica y se queda sin modo", async () => {
      const { target } = make({ found: false });
      await target.selectRemote();
      expect(target.mode).toBeNull();
      expect(target.error).toBe("No se encontró el server mediador en la red. ¿Está prendido?");
      expect(target.checking).toBe(false);
   });

   it.each(["busy", "loading"])("mediador %s: dice con qué modelo, y no pasa a remoto", async (state) => {
      const { target } = make({ found: true, state, busy_model: "large-v3" });
      await target.selectRemote();
      expect(target.mode).toBeNull();
      expect(target.error).toBe("El mediador está ocupado en este momento (modelo: large-v3). Inténtalo de nuevo en un rato.");
   });

   it("ocupado sin saber el modelo", async () => {
      const { target } = make({ found: true, state: "busy" });
      await target.selectRemote();
      expect(target.error).toContain("modelo: desconocido");
   });

   it("REGRESIÓN: si la consulta falla, no queda colgado en «buscando» y se explica", async () => {
      const { target } = make(() => Promise.reject(new Error("sin red")));
      await target.selectRemote();
      expect(target.checking).toBe(false);
      expect(target.mode).toBeNull();
      expect(target.error).toBe("No se pudo consultar el mediador (sin red).");
   });

   it("un error que no es Error también se muestra", async () => {
      const { target } = make(() => Promise.reject("boom"));
      await target.selectRemote();
      expect(target.error).toBe("No se pudo consultar el mediador (boom).");
   });

   it("un intento correcto borra el error del anterior", async () => {
      const results = [{ found: false }, MEDIATOR];
      const { target } = make(() => Promise.resolve(results.shift()));
      await target.selectRemote();
      expect(target.error).not.toBe("");
      await target.selectRemote();
      expect(target.error).toBe("");
      expect(target.mode).toBe("remote");
   });

   it("change(): vuelve a la elección, sin modo, sin destino y sin error", async () => {
      const { target } = make();
      await target.selectRemote();
      target.change();
      expect([target.mode, target.target, target.error]).toEqual([null, null, ""]);
   });

   it("change() también borra un error pendiente (el de un intento fallido anterior no debe verse al volver)", async () => {
      const { target } = make({ found: false });
      await target.selectRemote();
      expect(target.error).not.toBe("");
      target.change();
      expect(target.error).toBe("");
   });

   it("después de volver y elegir local, el destino es local aunque antes fuera remoto", async () => {
      const { target } = make();
      await target.selectRemote();
      target.change();
      target.selectLocal();
      expect(target.target).toEqual({ mode: "local" });
   });
});
