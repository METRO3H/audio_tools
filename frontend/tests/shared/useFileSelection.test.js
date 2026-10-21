import { vi, describe, it, expect, beforeEach } from "vitest";

const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import { useFileSelection } from "@shared/state/useFileSelection.svelte.js";

const deferred = () => {
   let resolve;
   const promise = new Promise((r) => (resolve = r));
   return { promise, resolve };
};
const name = (path) => path.split("/").pop();
const info = (path) => ({ name: name(path), size_mb: 5, duration_seconds: 60 });

const A = "C:/Proj/audios/a.mp3";
const B = "C:/Proj/audios/b.mp3";
const C = "C:/Proj/audios/c.mp3";

beforeEach(() => {
   vi.resetAllMocks();
   bridge.get_file_info.mockImplementation(async (path) => info(path));
});

function make(overrides = {}) {
   const options = {
      scan: vi.fn().mockResolvedValue({ files: [A, B], error: null }),
      pick: vi.fn().mockResolvedValue([A, B]),
      onLoaded: vi.fn(),
      ...overrides,
   };
   return { selection: useFileSelection(options), ...options };
}

describe("useFileSelection: cargar desde una carpeta", () => {
   it("detecta los archivos, lee su información y dice cuántos son", async () => {
      const { selection, scan, onLoaded } = make();
      await selection.loadFromFolder("C:/Proj");

      expect(scan).toHaveBeenCalledWith("C:/Proj");
      expect(selection.files).toEqual([
         { name: "a.mp3", size_mb: 5, duration_seconds: 60, path: A },
         { name: "b.mp3", size_mb: 5, duration_seconds: 60, path: B },
      ]);
      expect(selection.hint).toBe("✓ 2 archivo(s) detectados");
      expect(selection.loading).toBe(false);
      expect(onLoaded).toHaveBeenCalledTimes(1);
      expect(onLoaded).toHaveBeenCalledWith(selection.files, "folder");
   });

   it("el mensaje de éxito es configurable y recibe el resultado del escaneo", async () => {
      const { selection } = make({
         scan: vi.fn().mockResolvedValue({ files: [A], error: null, source: "audios" }),
         formatDetected: (n, result) => `✓ ${n} archivo(s) detectados desde ${result.source}`,
      });
      await selection.loadFromFolder("C:/Proj");
      expect(selection.hint).toBe("✓ 1 archivo(s) detectados desde audios");
   });

   it("un error del escaneo vacía la lista y lo muestra con ⚠", async () => {
      const { selection, onLoaded } = make({
         scan: vi.fn().mockResolvedValue({ files: [], error: "No existe la carpeta ./audios" }),
      });
      await selection.loadFromFolder("C:/Proj");
      expect(selection.files).toEqual([]);
      expect(selection.hint).toBe("⚠ No existe la carpeta ./audios");
      expect(onLoaded).not.toHaveBeenCalled();
   });

   it("si no encuentra nada, usa el texto indicado (fijo o calculado al momento)", async () => {
      const empty = { scan: vi.fn().mockResolvedValue({ files: [], error: null }) };
      const fixed = make({ ...empty, emptyHint: "No se encontraron audios en ./audios" });
      await fixed.selection.loadFromFolder("C:/Proj");
      expect(fixed.selection.hint).toBe("⚠ No se encontraron audios en ./audios");

      let kind = "audios";
      const lazy = make({ ...empty, emptyHint: () => `No se encontraron ${kind}` });
      kind = "videos";
      await lazy.selection.loadFromFolder("C:/Proj");
      expect(lazy.selection.hint).toBe("⚠ No se encontraron videos");
   });

   it("el texto por defecto cuando no encuentra nada", async () => {
      const { selection } = make({ scan: vi.fn().mockResolvedValue({ files: [], error: null }) });
      await selection.loadFromFolder("C:/Proj");
      expect(selection.hint).toBe("⚠ No se encontraron archivos");
   });

   it("si el escaneo lanza (puente caído), no rechaza: vacía la lista y lo muestra", async () => {
      const { selection } = make({ scan: vi.fn().mockRejectedValue(new Error("[bridge] pywebview no está listo.")) });
      await selection.loadFromFolder("C:/Proj");
      expect(selection.files).toEqual([]);
      expect(selection.hint).toBe("⚠ [bridge] pywebview no está listo.");
      expect(selection.loading).toBe(false);
   });

   it("una carga reemplaza a la anterior, no se acumula", async () => {
      const scan = vi.fn().mockResolvedValueOnce({ files: [A, B], error: null }).mockResolvedValueOnce({ files: [C], error: null });
      const { selection } = make({ scan });
      await selection.loadFromFolder("x");
      await selection.loadFromFolder("y");
      expect(selection.files.map((f) => f.path)).toEqual([C]);
   });

   it("loading es true mientras escanea y lee información", async () => {
      const d = deferred();
      const { selection } = make({ scan: vi.fn().mockReturnValue(d.promise) });
      const loading = selection.loadFromFolder("x");
      expect(selection.loading).toBe(true);
      d.resolve({ files: [A], error: null });
      await loading;
      expect(selection.loading).toBe(false);
   });
});

describe("useFileSelection: archivos que no se pueden leer", () => {
   it("REGRESIÓN: un archivo ilegible ya no hace fallar toda la carga; se omite y se avisa", async () => {
      // get_file_info lanza si el archivo desapareció entre el escaneo y la lectura
      bridge.get_file_info.mockImplementation(async (path) => {
         if (path === B) throw new Error("[Errno 2] No such file or directory");
         return info(path);
      });
      const { selection, onLoaded } = make({ scan: vi.fn().mockResolvedValue({ files: [A, B, C], error: null }) });
      await selection.loadFromFolder("x");

      expect(selection.files.map((f) => f.path)).toEqual([A, C]);
      expect(selection.hint).toBe("⚠ 2 archivo(s) detectados; 1 no se pudieron leer");
      expect(onLoaded).toHaveBeenCalledWith(selection.files, "folder");
   });

   it("si no se puede leer ninguno, lista vacía y aviso, sin llamar a onLoaded", async () => {
      bridge.get_file_info.mockRejectedValue(new Error("boom"));
      const { selection, onLoaded } = make();
      await selection.loadFromFolder("x");
      expect(selection.files).toEqual([]);
      expect(selection.hint).toBe("⚠ No se pudo leer ninguno de los archivos");
      expect(onLoaded).not.toHaveBeenCalled();
   });

   it("lo mismo en la selección manual", async () => {
      bridge.get_file_info.mockImplementation(async (path) => {
         if (path === A) throw new Error("boom");
         return info(path);
      });
      const { selection } = make();
      await selection.pickFiles();
      expect(selection.files.map((f) => f.path)).toEqual([B]);
      expect(selection.hint).toBe("⚠ 1 archivo(s) detectados; 1 no se pudieron leer");
   });
});

describe("useFileSelection: cargas que se pisan", () => {
   it("REGRESIÓN: una respuesta vieja que llega tarde NO pisa a la más reciente", async () => {
      const slow = deferred();
      const scan = vi.fn().mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ files: [C], error: null });
      const { selection, onLoaded } = make({ scan });

      const first = selection.loadFromFolder("vieja");
      await selection.loadFromFolder("nueva");
      expect(selection.files.map((f) => f.path)).toEqual([C]);

      slow.resolve({ files: [A, B], error: null }); // llega tarde
      await first;
      expect(selection.files.map((f) => f.path)).toEqual([C]);
      expect(selection.hint).toBe("✓ 1 archivo(s) detectados");
      expect(onLoaded).toHaveBeenCalledTimes(1);
      expect(selection.loading).toBe(false);
   });

   it.each([
      ["con error", { files: [], error: "No existe la carpeta ./audios" }],
      ["vacía", { files: [], error: null }],
   ])("REGRESIÓN: un escaneo viejo que termina %s tampoco pisa el estado nuevo", async (_label, staleResult) => {
      const slow = deferred();
      const scan = vi.fn().mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ files: [C], error: null });
      const { selection } = make({ scan });

      const first = selection.loadFromFolder("vieja");
      await selection.loadFromFolder("nueva");
      slow.resolve(staleResult);
      await first;

      expect(selection.files.map((f) => f.path)).toEqual([C]);
      expect(selection.hint).toBe("✓ 1 archivo(s) detectados");
   });

   it("un escaneo viejo que LANZA tampoco pisa el estado nuevo", async () => {
      const slow = deferred();
      const scan = vi.fn().mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ files: [C], error: null });
      const { selection } = make({ scan });

      const first = selection.loadFromFolder("vieja");
      await selection.loadFromFolder("nueva");
      slow.resolve(Promise.reject(new Error("tarde")));
      await first;

      expect(selection.files.map((f) => f.path)).toEqual([C]);
      expect(selection.hint).toBe("✓ 1 archivo(s) detectados");
   });

   it("loading sigue siendo true mientras la carga MÁS RECIENTE no termina", async () => {
      const slowOld = deferred();
      const slowNew = deferred();
      const scan = vi.fn().mockReturnValueOnce(slowOld.promise).mockReturnValueOnce(slowNew.promise);
      const { selection } = make({ scan });

      const first = selection.loadFromFolder("vieja");
      const second = selection.loadFromFolder("nueva");
      slowOld.resolve({ files: [A], error: null });
      await first;
      expect(selection.loading).toBe(true); // la vieja terminó, la nueva no

      slowNew.resolve({ files: [B], error: null });
      await second;
      expect(selection.loading).toBe(false);
   });

   it("una selección manual posterior descarta una carga de carpeta en curso", async () => {
      const slow = deferred();
      const { selection } = make({ scan: vi.fn().mockReturnValue(slow.promise), pick: vi.fn().mockResolvedValue([C]) });
      const folderLoad = selection.loadFromFolder("x");
      await selection.pickFiles();
      slow.resolve({ files: [A, B], error: null });
      await folderLoad;
      expect(selection.files.map((f) => f.path)).toEqual([C]);
   });
});

describe("useFileSelection: selección manual", () => {
   it("carga los archivos elegidos y borra el mensaje anterior", async () => {
      const { selection, onLoaded } = make();
      await selection.loadFromFolder("x");
      expect(selection.hint).not.toBe("");

      await selection.pickFiles();
      expect(selection.files.map((f) => f.path)).toEqual([A, B]);
      expect(selection.hint).toBe("");
      expect(onLoaded).toHaveBeenLastCalledWith(selection.files, "manual");
   });

   it.each([[null], [undefined], [[]]])("cancelar el diálogo (%j) no cambia nada", async (cancelled) => {
      const { selection, onLoaded } = make({ pick: vi.fn().mockResolvedValue(cancelled) });
      await selection.loadFromFolder("x");
      const before = [...selection.files];
      const hint = selection.hint;
      onLoaded.mockClear();

      await selection.pickFiles();
      expect(selection.files).toEqual(before);
      expect(selection.hint).toBe(hint);
      expect(onLoaded).not.toHaveBeenCalled();
   });

   it("cancelar el diálogo NO interrumpe una carga de carpeta que sigue en curso", async () => {
      const slow = deferred();
      const { selection } = make({ scan: vi.fn().mockReturnValue(slow.promise), pick: vi.fn().mockResolvedValue(null) });
      const folderLoad = selection.loadFromFolder("x");
      await selection.pickFiles(); // el usuario abre el diálogo y lo cancela
      slow.resolve({ files: [A, B], error: null });
      await folderLoad;
      expect(selection.files.map((f) => f.path)).toEqual([A, B]);
   });

   it("si el diálogo falla (puente caído), muestra el aviso y conserva los archivos", async () => {
      const { selection } = make({ pick: vi.fn().mockRejectedValue(new Error("sin puente")) });
      await selection.loadFromFolder("x");
      await selection.pickFiles();
      expect(selection.hint).toBe("⚠ sin puente");
      expect(selection.files.length).toBe(2);
   });
});

describe("useFileSelection: quitar y limpiar", () => {
   it("remove quita solo el archivo indicado y deja el mensaje", async () => {
      const { selection } = make();
      await selection.loadFromFolder("x");
      selection.remove(A);
      expect(selection.files.map((f) => f.path)).toEqual([B]);
      expect(selection.hint).toBe("✓ 2 archivo(s) detectados");
   });

   it("quitar una ruta que no está no hace nada", async () => {
      const { selection } = make();
      await selection.loadFromFolder("x");
      selection.remove("otra");
      expect(selection.files.length).toBe(2);
   });

   it("clear vacía lista y mensaje", async () => {
      const { selection } = make();
      await selection.loadFromFolder("x");
      selection.clear();
      expect(selection.files).toEqual([]);
      expect(selection.hint).toBe("");
      expect(selection.loading).toBe(false);
   });

   it("clear descarta una carga en curso: su resultado no aparece después", async () => {
      const slow = deferred();
      const { selection, onLoaded } = make({ scan: vi.fn().mockReturnValue(slow.promise) });
      const pending = selection.loadFromFolder("x");
      selection.clear();
      slow.resolve({ files: [A, B], error: null });
      await pending;
      expect(selection.files).toEqual([]);
      expect(selection.hint).toBe("");
      expect(onLoaded).not.toHaveBeenCalled();
   });
});
