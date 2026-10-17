import { render, screen, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import UsePlanHarness from "./UsePlanHarness.svelte";

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};
const settle = async (ms = 250) => {
   await vi.advanceTimersByTimeAsync(ms);
   await flush();
};
const state = () => JSON.parse(screen.getByTestId("state").textContent);

let api;
function mount(fetchPlan, props = {}) {
   render(UsePlanHarness, { props: { fetchPlan, onready: (a) => (api = a), ...props } });
   return flush();
}
const change = async (options) => {
   api.setOptions(options);
   await flush();
};
const deferred = () => {
   let resolve;
   const promise = new Promise((r) => (resolve = r));
   return { promise, resolve };
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
   cleanup();
   vi.useRealTimers();
});

describe("usePlan: consulta", () => {
   it("sin opciones no consulta y no hay plan ni error", async () => {
      const fetchPlan = vi.fn();
      await mount(fetchPlan);
      await settle();
      expect(fetchPlan).not.toHaveBeenCalled();
      expect(state()).toEqual({ value: null, error: "", pending: false });
   });

   it("con opciones iniciales consulta tras el debounce y entrega el plan", async () => {
      const fetchPlan = vi.fn().mockResolvedValue({ files: [1, 2] });
      await mount(fetchPlan, { initial: { a: 1 } });
      expect(fetchPlan).not.toHaveBeenCalled(); // aún dentro del debounce
      expect(state().pending).toBe(true);

      await settle();
      expect(fetchPlan).toHaveBeenCalledTimes(1);
      expect(fetchPlan).toHaveBeenCalledWith({ a: 1 });
      expect(state()).toEqual({ value: { files: [1, 2] }, error: "", pending: false });
   });

   it("pending es true mientras la consulta está en vuelo", async () => {
      const d = deferred();
      await mount(() => d.promise, { initial: { a: 1 } });
      await settle();
      expect(state().pending).toBe(true); // ya salió, pero no ha vuelto

      d.resolve({ ok: true });
      await flush();
      expect(state().pending).toBe(false);
   });

   it("varios cambios seguidos producen UNA sola consulta, con el último valor", async () => {
      const fetchPlan = vi.fn().mockResolvedValue({ ok: true });
      await mount(fetchPlan, { initial: { n: 0 } });
      await settle();
      fetchPlan.mockClear();

      await change({ n: 1 });
      await vi.advanceTimersByTimeAsync(100);
      await change({ n: 2 });
      await vi.advanceTimersByTimeAsync(100);
      await change({ n: 3 });
      await settle();

      expect(fetchPlan).toHaveBeenCalledTimes(1);
      expect(fetchPlan).toHaveBeenCalledWith({ n: 3 });
   });

   it("el debounce es configurable", async () => {
      const fetchPlan = vi.fn().mockResolvedValue({});
      await mount(fetchPlan, { initial: { a: 1 }, debounceMs: 1000 });
      await vi.advanceTimersByTimeAsync(900);
      expect(fetchPlan).not.toHaveBeenCalled();
      await settle(150);
      expect(fetchPlan).toHaveBeenCalledTimes(1);
   });

   it("pasar a null borra el plan y el error, y cancela una consulta en espera", async () => {
      const fetchPlan = vi.fn().mockResolvedValue({ files: [1] });
      await mount(fetchPlan, { initial: { a: 1 } });
      await settle();
      expect(state().value).toEqual({ files: [1] });

      await change(null);
      expect(state()).toEqual({ value: null, error: "", pending: false });

      fetchPlan.mockClear();
      await change({ a: 2 });
      await vi.advanceTimersByTimeAsync(100);
      await change(null); // antes de que salga
      await settle();
      expect(fetchPlan).not.toHaveBeenCalled();
   });
});

describe("usePlan: respuestas", () => {
   it("una respuesta que llega tarde NO pisa a la más reciente", async () => {
      const old = deferred();
      const fresh = deferred();
      const fetchPlan = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
      await mount(fetchPlan, { initial: { n: 1 } });
      await settle(); // sale la consulta 1 (queda pendiente)
      await change({ n: 2 });
      await settle(); // sale la consulta 2 (queda pendiente)

      fresh.resolve({ from: "nueva" });
      await flush();
      expect(state().value).toEqual({ from: "nueva" });

      old.resolve({ from: "vieja" });
      await flush();
      expect(state().value).toEqual({ from: "nueva" });
      expect(state().pending).toBe(false);
   });

   it("una respuesta que llega cuando ya no hay opciones se descarta", async () => {
      const d = deferred();
      await mount(() => d.promise, { initial: { n: 1 } });
      await settle();
      await change(null);
      d.resolve({ from: "tarde" });
      await flush();
      expect(state()).toEqual({ value: null, error: "", pending: false });
   });

   it("un { error } devuelto por el backend se muestra y borra el plan", async () => {
      const fetchPlan = vi.fn().mockResolvedValueOnce({ ok: 1 }).mockResolvedValueOnce({ error: "Se necesitan al menos 2 archivos." });
      await mount(fetchPlan, { initial: { n: 1 } });
      await settle();
      expect(state().value).toEqual({ ok: 1 });

      await change({ n: 2 });
      await settle();
      expect(state()).toEqual({ value: null, error: "Se necesitan al menos 2 archivos.", pending: false });
   });

   it("tras un error, una respuesta buena lo limpia", async () => {
      const fetchPlan = vi.fn().mockResolvedValueOnce({ error: "mal" }).mockResolvedValueOnce({ ok: 1 });
      await mount(fetchPlan, { initial: { n: 1 } });
      await settle();
      await change({ n: 2 });
      await settle();
      expect(state()).toEqual({ value: { ok: 1 }, error: "", pending: false });
   });

   it("si la llamada rechaza, se muestra su mensaje", async () => {
      await mount(() => Promise.reject(new Error("puente caído")), { initial: { n: 1 } });
      await settle();
      expect(state()).toEqual({ value: null, error: "puente caído", pending: false });
   });

   it("si la llamada lanza de forma síncrona (puente no listo), también se muestra", async () => {
      await mount(
         () => {
            throw new Error("[bridge] pywebview no está listo.");
         },
         { initial: { n: 1 } },
      );
      await settle();
      expect(state().error).toMatch(/pywebview no está listo/);
      expect(state().pending).toBe(false);
   });

   it("un rechazo que no es un Error también se muestra", async () => {
      await mount(() => Promise.reject("fallo"), { initial: { n: 1 } });
      await settle();
      expect(state().error).toBe("fallo");
   });
});

describe("usePlan: ciclo de vida", () => {
   it("al desmontarse no consulta ni deja temporizadores", async () => {
      const fetchPlan = vi.fn().mockResolvedValue({});
      await mount(fetchPlan, { initial: { n: 1 } });
      cleanup();
      expect(vi.getTimerCount()).toBe(0);
      await settle();
      expect(fetchPlan).not.toHaveBeenCalled();
   });
});
