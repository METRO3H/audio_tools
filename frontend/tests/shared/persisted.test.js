import { render, screen, cleanup } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import PersistedHarness from "./PersistedHarness.svelte";

const KEY = "test_config";
const DEFAULTS = { mediaType: "audio", intervalMins: 20, useSubfolder: true };

const stored = () => JSON.parse(localStorage.getItem(KEY));
const save = (value) => localStorage.setItem(KEY, JSON.stringify(value));
const rendered = () => JSON.parse(screen.getByTestId("json").textContent);

/** Monta el estado y devuelve el objeto reactivo para poder modificarlo. */
async function mount(defaults = DEFAULTS) {
   let cfg;
   render(PersistedHarness, { props: { storageKey: KEY, defaults, onready: (c) => (cfg = c) } });
   await tick();
   return cfg;
}

beforeEach(() => localStorage.clear());
afterEach(() => {
   cleanup();
   vi.restoreAllMocks();
});

describe("persisted: carga", () => {
   it("sin nada guardado usa los valores por defecto (y los guarda)", async () => {
      const cfg = await mount();
      expect({ ...cfg }).toEqual(DEFAULTS);
      expect(stored()).toEqual(DEFAULTS);
   });

   it("lo guardado reemplaza a los valores por defecto", async () => {
      save({ mediaType: "video", intervalMins: 7, useSubfolder: false });
      const cfg = await mount();
      expect({ ...cfg }).toEqual({ mediaType: "video", intervalMins: 7, useSubfolder: false });
   });

   it("lo guardado NO es pisado al montar (el bug de los tres efectos)", async () => {
      save({ mediaType: "audio", intervalMins: 7, useSubfolder: false });
      await mount();
      await tick();
      expect(stored()).toEqual({ mediaType: "audio", intervalMins: 7, useSubfolder: false });
   });

   it("las claves que faltan en lo guardado se completan con las de por defecto", async () => {
      save({ intervalMins: 45 });
      const cfg = await mount();
      expect({ ...cfg }).toEqual({ mediaType: "audio", intervalMins: 45, useSubfolder: true });
   });

   it("un valor de tipo equivocado se ignora clave por clave, sin invalidar el resto", async () => {
      save({ mediaType: 5, intervalMins: "20", useSubfolder: "sí" });
      expect({ ...(await mount()) }).toEqual(DEFAULTS);
      cleanup();
      localStorage.clear();

      save({ mediaType: "video", intervalMins: "abc", useSubfolder: false });
      expect({ ...(await mount()) }).toEqual({ mediaType: "video", intervalMins: 20, useSubfolder: false });
   });

   it("números no finitos y null no valen como número", async () => {
      localStorage.setItem(KEY, '{"intervalMins": null, "mediaType": "video"}');
      expect({ ...(await mount()) }).toEqual({ mediaType: "video", intervalMins: 20, useSubfolder: true });
   });

   it("las claves guardadas que ya no existen en los defaults se ignoran", async () => {
      save({ mediaType: "audio", segmentMode: "interval", intervalMins: 7, useSubfolder: false });
      const cfg = await mount();
      expect(cfg).not.toHaveProperty("segmentMode");
      expect(rendered()).toEqual({ mediaType: "audio", intervalMins: 7, useSubfolder: false });
   });

   it.each([["JSON corrupto", "{no es json"], ["un número", "5"], ["una lista", "[1,2]"], ["texto", '"hola"'], ["null", "null"]])(
      "si lo guardado es %s, usa los valores por defecto",
      async (_label, raw) => {
         localStorage.setItem(KEY, raw);
         expect({ ...(await mount()) }).toEqual(DEFAULTS);
      },
   );

   it("con un valor por defecto null se acepta cualquier valor guardado", async () => {
      save({ extra: { a: 1 } });
      const cfg = await mount({ extra: null });
      expect(cfg.extra).toEqual({ a: 1 });
   });

   it("las listas solo se aceptan si lo guardado también es una lista", async () => {
      save({ tags: "no soy lista" });
      expect([...(await mount({ tags: ["a"] })).tags]).toEqual(["a"]);
      cleanup();
      save({ tags: ["x", "y"] });
      expect([...(await mount({ tags: ["a"] })).tags]).toEqual(["x", "y"]);
   });
});

describe("persisted: guardado", () => {
   it("cada cambio se guarda", async () => {
      const cfg = await mount();
      cfg.intervalMins = 30;
      await tick();
      expect(stored().intervalMins).toBe(30);

      cfg.useSubfolder = false;
      await tick();
      expect(stored()).toEqual({ mediaType: "audio", intervalMins: 30, useSubfolder: false });
   });

   it("lo guardado solo contiene las claves de los defaults (limpia las obsoletas)", async () => {
      save({ mediaType: "audio", segmentMode: "interval", intervalMins: 7, useSubfolder: true });
      await mount();
      expect(Object.keys(stored()).sort()).toEqual(["intervalMins", "mediaType", "useSubfolder"]);
   });

   it("es reactivo: un cambio se refleja en lo que ve el componente", async () => {
      const cfg = await mount();
      cfg.mediaType = "video";
      await tick();
      expect(rendered().mediaType).toBe("video");
   });

   it("no comparte referencias con los defaults (modificar el estado no los altera)", async () => {
      const defaults = { tags: ["a"] };
      const cfg = await mount(defaults);
      cfg.tags.push("b");
      await tick();
      expect(defaults.tags).toEqual(["a"]);
      expect(stored().tags).toEqual(["a", "b"]);
   });

   it("si localStorage falla al guardar (cuota llena), no rompe la vista", async () => {
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
         throw new DOMException("cuota", "QuotaExceededError");
      });
      const cfg = await mount();
      expect(() => {
         cfg.intervalMins = 99;
      }).not.toThrow();
      await tick();
      expect(cfg.intervalMins).toBe(99);
   });

   it("dos estados con claves distintas no se pisan entre sí", async () => {
      render(PersistedHarness, { props: { storageKey: "a_config", defaults: { x: 1 } } });
      render(PersistedHarness, { props: { storageKey: "b_config", defaults: { y: 2 } } });
      await tick();
      expect(JSON.parse(localStorage.getItem("a_config"))).toEqual({ x: 1 });
      expect(JSON.parse(localStorage.getItem("b_config"))).toEqual({ y: 2 });
   });
});
