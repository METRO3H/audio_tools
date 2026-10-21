import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

// Bridge falso: cualquier método sin configurar es un vi.fn() que devuelve undefined.
const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import MergeView from "@merge/MergeView.svelte";
import { appConfig } from "@shared/state/config.svelte.js";
import { progress } from "@shared/state/progress.svelte.js";

const AUDIO = ["mp3", "wav", "aac", "m4a", "ogg", "flac", "opus"];
const VIDEO = ["mp4", "mkv", "avi", "mov", "webm"];
const PATHS = ["C:/Proj/audios/a.mp3", "C:/Proj/audios/b.mp3"];

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};
const settle = async (ms = 250) => {
   await vi.advanceTimersByTimeAsync(ms);
   await flush();
};
const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

function planFor(paths = PATHS, extra = {}) {
   return {
      output_path: "C:\\Proj\\audios\\Proj.mp3",
      output_name: "Proj.mp3",
      files: paths.map((p, i) => ({
         index: i + 1, name: p.split("/").pop(), path: p, duration: 120, start: i * 120, end: (i + 1) * 120,
      })),
      excluded: [],
      total_duration: paths.length * 120,
      chapters: [],
      ...extra,
   };
}

const formatSelect = () => screen.getByLabelText("Formato de salida");
const runButton = () => screen.getByRole("button", { name: "Ejecutar merge" });
const mediaButton = (name) => screen.getByRole("button", { name });
const savedConfig = () => JSON.parse(localStorage.getItem("merge_config"));

async function mount(saved) {
   cleanup();
   localStorage.clear();
   if (saved) localStorage.setItem("merge_config", JSON.stringify(saved));
   render(MergeView, { props: { goHome: vi.fn() } });
   await flush();
}

/** Elige archivos a mano; los tamaños salen del file_info falso. */
async function pickFiles(paths = PATHS) {
   bridge.pick_files.mockResolvedValue(paths);
   bridge.get_file_info.mockImplementation(async (p) => ({ name: p.split("/").pop(), size_mb: 7, duration_seconds: 120 }));
   await fireEvent.click(screen.getByRole("button", { name: "Seleccionar manualmente" }));
   await flush();
   await flush();
}

beforeEach(async () => {
   vi.useFakeTimers();
   progress.reset();
   vi.resetAllMocks();
   appConfig.baseFolder = "C:/Proj";
   appConfig.mediaExtensions = { audio: [".mp3", ".wav"], video: [".mp4", ".mkv"] };
   appConfig.outputFormats = { audio: AUDIO, video: VIDEO };
   bridge.plan_merge.mockImplementation(async (options) => planFor(options.file_paths));
   await mount();
});
afterEach(() => {
   cleanup();
   vi.useRealTimers();
});

describe("MergeView: configuración recordada (bug verificado: el formato guardado se perdía en cada arranque)", () => {
   it("sin nada guardado: audio y mp3, y los formatos vienen del backend", async () => {
      expect(formatSelect().value).toBe("mp3");
      expect([...formatSelect().options].map((o) => o.value)).toEqual(AUDIO);
      expect(savedConfig()).toEqual({ mediaType: "audio", outputFormat: "mp3" });
   });

   it("REGRESIÓN: el formato guardado (wav) se respeta al montar y no se vuelve a pisar", async () => {
      await mount({ mediaType: "audio", outputFormat: "wav" });
      await settle();
      expect(formatSelect().value).toBe("wav");
      expect(savedConfig()).toEqual({ mediaType: "audio", outputFormat: "wav" });
   });

   it("un tipo y formato de video guardados se aplican", async () => {
      await mount({ mediaType: "video", outputFormat: "mkv" });
      expect(formatSelect().value).toBe("mkv");
      expect([...formatSelect().options].map((o) => o.value)).toEqual(VIDEO);
      expect(mediaButton(/Video/).className).toContain("bg-indigo-600");
   });

   it("un formato guardado que no vale para el tipo cae al primero, sin romper nada", async () => {
      await mount({ mediaType: "audio", outputFormat: "mp4" });
      expect(formatSelect().value).toBe("mp3");
   });

   it("elegir otro formato lo guarda", async () => {
      await fireEvent.change(formatSelect(), { target: { value: "flac" } });
      await flush();
      expect(savedConfig().outputFormat).toBe("flac");
   });

   it("cambiar el tipo restablece el formato al de por defecto y descarta los archivos", async () => {
      await mount({ mediaType: "audio", outputFormat: "wav" });
      await pickFiles();
      expect(screen.getByText("a.mp3")).toBeTruthy();

      await fireEvent.click(mediaButton(/Video/));
      await flush();
      expect(formatSelect().value).toBe("mp4");
      expect(screen.queryByText("a.mp3")).toBeNull();
      expect(savedConfig()).toEqual({ mediaType: "video", outputFormat: "mp4" });
   });

   it("pulsar el tipo ya activo no descarta nada", async () => {
      await pickFiles();
      await fireEvent.click(mediaButton(/Audio/));
      await flush();
      expect(screen.getByText("a.mp3")).toBeTruthy();
   });
});

describe("MergeView: plan desde el backend", () => {
   it("sin archivos (o con uno solo) no se pide plan y no se puede ejecutar", async () => {
      await settle();
      expect(bridge.plan_merge).not.toHaveBeenCalled();
      expect(runButton().disabled).toBe(true);

      await pickFiles([PATHS[0]]);
      await settle();
      expect(bridge.plan_merge).not.toHaveBeenCalled();
      expect(runButton().disabled).toBe(true);
   });

   it("con dos archivos pide el plan con las opciones exactas, incluidas las duraciones ya conocidas", async () => {
      await pickFiles();
      expect(bridge.plan_merge).not.toHaveBeenCalled(); // dentro del debounce
      await settle();
      expect(bridge.plan_merge).toHaveBeenCalledTimes(1);
      expect(bridge.plan_merge).toHaveBeenCalledWith({
         file_paths: PATHS,
         output_name: "Proj",
         output_format: "mp3",
         media_type: "audio",
         durations: [120, 120],
      });
   });

   it("una duración desconocida (0) se envía como null para que el backend la mida", async () => {
      bridge.pick_files.mockResolvedValue(PATHS);
      bridge.get_file_info.mockImplementation(async (p) => ({ name: p.split("/").pop(), size_mb: 1, duration_seconds: p.endsWith("a.mp3") ? 0 : 60 }));
      await fireEvent.click(screen.getByRole("button", { name: "Seleccionar manualmente" }));
      await flush();
      await flush();
      await settle();
      expect(bridge.plan_merge.mock.calls[0][0].durations).toEqual([null, 60]);
   });

   it("el botón Ejecutar se habilita solo cuando llega el plan", async () => {
      await pickFiles();
      expect(runButton().disabled).toBe(true); // plan pendiente
      await settle();
      expect(runButton().disabled).toBe(false);
   });

   it("muestra el nombre final que decide el backend", async () => {
      await pickFiles();
      await settle();
      expect(screen.getByText("→ Proj.mp3")).toBeTruthy();
   });

   it("el nombre de salida escrito por el usuario viaja en las opciones", async () => {
      await pickFiles();
      await settle();
      bridge.plan_merge.mockClear();
      await fireEvent.input(screen.getByPlaceholderText("Proj"), { target: { value: "Parte 1: Intro" } });
      await settle();
      expect(bridge.plan_merge).toHaveBeenCalledTimes(1);
      expect(bridge.plan_merge.mock.calls[0][0].output_name).toBe("Parte 1: Intro"); // el backend lo limpia
   });

   it("cambiar el formato vuelve a planificar con el nuevo formato", async () => {
      await pickFiles();
      await settle();
      bridge.plan_merge.mockClear();
      await fireEvent.change(formatSelect(), { target: { value: "wav" } });
      await settle();
      expect(bridge.plan_merge.mock.calls[0][0].output_format).toBe("wav");
   });

   it("REGRESIÓN: si el merge anterior está entre las entradas, avisa de que se excluirá", async () => {
      bridge.plan_merge.mockResolvedValue(
         planFor(PATHS, { excluded: ["C:/Proj/audios/Proj.mp3"] }),
      );
      await pickFiles([...PATHS, "C:/Proj/audios/Proj.mp3"]);
      await settle();
      expect(screen.getByText(/Se excluirá del merge: Proj\.mp3/)).toBeTruthy();
   });

   it("sin exclusiones no aparece ese aviso", async () => {
      await pickFiles();
      await settle();
      expect(screen.queryByText(/Se excluirá del merge/)).toBeNull();
   });

   it("si el backend devuelve un error: se muestra y no se puede ejecutar", async () => {
      bridge.plan_merge.mockResolvedValue({ error: "El formato «xyz» no es válido para audio." });
      await pickFiles();
      await settle();
      expect(screen.getByRole("alert").textContent).toContain("no es válido para audio");
      expect(runButton().disabled).toBe(true);
   });

   it("quitar un archivo hasta quedar con uno borra el plan", async () => {
      await pickFiles();
      await settle();
      expect(runButton().disabled).toBe(false);
      await fireEvent.click(screen.getAllByRole("button", { name: /^Quitar / })[0]);
      await settle();
      expect(runButton().disabled).toBe(true);
      expect(screen.queryByText("→ Proj.mp3")).toBeNull();
   });
});

const baseFolderButton = () => screen.getByText("C:/Proj").closest("button");
const nameInput = () => screen.getByLabelText("Nombre de salida");

describe("MergeView: archivos", () => {
   async function chooseBaseFolder(folder = "C:/Nuevo", scanResult = { files: PATHS, error: null }) {
      bridge.pick_folder.mockResolvedValue(folder);
      bridge.scan_media_folder.mockResolvedValue(scanResult);
      bridge.get_file_info.mockImplementation(async (p) => ({ name: p.split("/").pop(), size_mb: 7, duration_seconds: 120 }));
      await fireEvent.click(baseFolderButton());
      await flush();
      await flush();
   }

   it("al elegir la carpeta base detecta los archivos, avisa cuántos y propone el nombre de salida", async () => {
      await chooseBaseFolder();
      expect(bridge.scan_media_folder).toHaveBeenCalledWith("C:/Nuevo", "audio");
      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("b.mp3")).toBeTruthy();
      expect(screen.getByText("✓ 2 archivo(s) detectados").className).toContain("text-emerald-400");
      expect(appConfig.baseFolder).toBe("C:/Nuevo");
      expect(nameInput().value).toBe("Nuevo");
   });

   it("en modo video escanea videos", async () => {
      await fireEvent.click(mediaButton(/Video/));
      await flush();
      await chooseBaseFolder("C:/Nuevo", { files: ["C:/Nuevo/videos/a.mp4", "C:/Nuevo/videos/b.mp4"], error: null });
      expect(bridge.scan_media_folder).toHaveBeenCalledWith("C:/Nuevo", "video");
   });

   it("cancelar el diálogo de carpeta no cambia nada", async () => {
      bridge.pick_folder.mockResolvedValue(null);
      await fireEvent.click(baseFolderButton());
      await flush();
      expect(bridge.scan_media_folder).not.toHaveBeenCalled();
      expect(appConfig.baseFolder).toBe("C:/Proj");
   });

   it("un error del escaneo se muestra en amarillo y deja la lista vacía", async () => {
      await chooseBaseFolder("C:/Nuevo", { files: [], error: "No existe la carpeta ./audios" });
      expect(screen.getByText("⚠ No existe la carpeta ./audios").className).toContain("text-yellow-400");
      expect(screen.queryByText("a.mp3")).toBeNull();
   });

   it.each([
      ["audio", "⚠ No se encontraron archivos en ./audios"],
      ["video", "⚠ No se encontraron archivos en ./videos"],
   ])("si la carpeta no tiene %s, lo dice", async (type, message) => {
      if (type === "video") {
         await fireEvent.click(mediaButton(/Video/));
         await flush();
      }
      await chooseBaseFolder("C:/Nuevo", { files: [], error: null });
      expect(screen.getByText(message)).toBeTruthy();
   });

   it("REGRESIÓN: un archivo que desaparece entre el escaneo y la lectura ya no rompe la carga", async () => {
      bridge.pick_folder.mockResolvedValue("C:/Nuevo");
      bridge.scan_media_folder.mockResolvedValue({ files: [...PATHS, "C:/Proj/audios/c.mp3"], error: null });
      bridge.get_file_info.mockImplementation(async (p) => {
         if (p.endsWith("b.mp3")) throw new Error("[Errno 2] No such file or directory");
         return { name: p.split("/").pop(), size_mb: 7, duration_seconds: 120 };
      });
      await fireEvent.click(baseFolderButton());
      await flush();
      await flush();

      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("c.mp3")).toBeTruthy();
      expect(screen.queryByText("b.mp3")).toBeNull();
      expect(screen.getByText("⚠ 2 archivo(s) detectados; 1 no se pudieron leer").className).toContain("text-yellow-400");
   });

   it("la selección manual filtra por las extensiones del backend y parte de la carpeta base", async () => {
      await pickFiles();
      expect(bridge.pick_files).toHaveBeenCalledWith(["*.mp3", "*.wav"], "C:/Proj", "audio");
   });

   it("cancelar la selección manual conserva lo que ya había", async () => {
      await pickFiles();
      bridge.pick_files.mockResolvedValue(null);
      await fireEvent.click(screen.getByRole("button", { name: "Seleccionar manualmente" }));
      await flush();
      expect(screen.getByText("a.mp3")).toBeTruthy();
   });

   it("la selección manual propone el nombre de salida a partir de la carpeta base", async () => {
      await pickFiles();
      expect(nameInput().value).toBe("Proj");
   });

   it("el nombre que el usuario ya escribió no se pisa al cargar archivos", async () => {
      await fireEvent.input(nameInput(), { target: { value: "Mi merge" } });
      await pickFiles();
      expect(nameInput().value).toBe("Mi merge");
   });

   it("elegir otra carpeta base restablece el nombre de salida", async () => {
      await pickFiles();
      expect(nameInput().value).toBe("Proj");
      await chooseBaseFolder("C:/Otro");
      expect(nameInput().value).toBe("Otro");
   });

   it("quitar un archivo lo saca de la lista", async () => {
      await pickFiles();
      await fireEvent.click(screen.getByRole("button", { name: "Quitar a.mp3" }));
      expect(screen.queryByText("a.mp3")).toBeNull();
      expect(screen.getByText("b.mp3")).toBeTruthy();
   });
});

describe("MergeView: ejecución", () => {
   it("run_merge recibe las opciones del plan más el job_id, y ya no la ruta armada en el front", async () => {
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();

      expect(bridge.run_merge).toHaveBeenCalledTimes(1);
      const sent = bridge.run_merge.mock.calls[0][0];
      expect(sent).toEqual({
         file_paths: PATHS,
         output_name: "Proj",
         output_format: "mp3",
         media_type: "audio",
         durations: [120, 120],
         job_id: expect.any(String),
      });
      expect(sent).not.toHaveProperty("output_path");
      expect(sent).not.toHaveProperty("base_folder");
   });

   it("la pantalla de proceso muestra los archivos que SÍ se unen, con su tamaño, y la ruta de salida", async () => {
      bridge.plan_merge.mockResolvedValue(
         planFor(PATHS, { excluded: ["C:/Proj/audios/Proj.mp3"] }),   // el merge anterior no entra
      );
      await pickFiles([...PATHS, "C:/Proj/audios/Proj.mp3"]);
      await settle();
      await fireEvent.click(runButton());
      await flush();

      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("b.mp3")).toBeTruthy();
      expect(screen.queryByText("Proj.mp3")).toBeNull();     // excluido: no aparece como archivo a unir
      expect(screen.getAllByText("7 MB").length).toBe(2);     // el tamaño se conserva
      expect(progress.running).toBe(true);
   });

   it("no ejecuta mientras el plan está pendiente (aunque se fuerce el clic)", async () => {
      await pickFiles();
      await settle();
      bridge.plan_merge.mockClear();
      await fireEvent.input(screen.getByPlaceholderText("Proj"), { target: { value: "Otro" } }); // plan pendiente
      await flush();
      await fireEvent.click(runButton());
      await flush();
      expect(bridge.run_merge).not.toHaveBeenCalled();
   });

   it("un aviso del backend (capítulos) se muestra al terminar, sin ser un error", async () => {
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();
      emit("audiotools:done", {
         job_id: progress.jobId, success: true, cancelled: false,
         warning: "No se pudieron incrustar los capítulos: sin permiso",
      });
      await flush();
      expect(screen.getByRole("status").textContent).toContain("No se pudieron incrustar los capítulos");
      expect(screen.queryByRole("alert")).toBeNull();
   });

   it("un error del backend (opciones inválidas) se muestra en la pantalla de proceso", async () => {
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();
      emit("audiotools:done", { job_id: progress.jobId, success: false, cancelled: false, error: "El formato no es válido" });
      await flush();
      expect(screen.getByRole("alert").textContent).toContain("El formato no es válido");
   });
});
