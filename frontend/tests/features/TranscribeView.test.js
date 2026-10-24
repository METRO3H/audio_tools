import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import TranscribeView from "@transcribe/TranscribeView.svelte";
import { appConfig } from "@shared/state/config.svelte.js";
import { progress } from "@shared/state/progress.svelte.js";
import { TRANSCRIBE_CAPS } from "./transcribeCaps.js";

const PATHS = ["C:/Proj/audios/a.mp3", "C:/Proj/audios/b.mp3"];
const MEDIATOR = { found: true, state: "idle", host: "10.0.0.5", port: 9000, models: ["medium", "large-v3-turbo"] };

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};
const settle = async (ms = 250) => {
   await vi.advanceTimersByTimeAsync(ms);
   await flush();
};

function planFor(options, extra = {}) {
   const names = options.file_paths.map((p) => p.split("/").pop());
   return {
      output_dir: "C:\\Proj\\transcriptions\\japanese",
      files: options.file_paths.map((p, i) => ({
         index: i, name: names[i], path: p, duration: 120,
         output: `C:\\Proj\\transcriptions\\japanese\\${names[i].replace(/\.\w+$/, "")}.srt`,
         output_name: `${names[i].replace(/\.\w+$/, "")}.srt`, exists: false,
      })),
      total_duration: options.file_paths.length * 120,
      ...extra,
   };
}

const select = (label) => screen.getByLabelText(label);
const runButton = () => screen.getByRole("button", { name: "Ejecutar transcripción" });
const savedConfig = () => JSON.parse(localStorage.getItem("transcribe_config"));
const lastPlanOptions = () => bridge.plan_transcribe.mock.calls.at(-1)[0];
const isSelected = (button) => button.className.includes("bg-indigo-600");

async function mount({ saved, mode = "local" } = {}) {
   cleanup();
   localStorage.clear();
   if (saved) localStorage.setItem("transcribe_config", JSON.stringify(saved));
   render(TranscribeView, { props: { goHome: vi.fn() } });
   await flush();
   if (mode === "local") await fireEvent.click(screen.getByRole("button", { name: /Transcribir en esta PC/ }));
   if (mode === "remote") {
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en remoto/ }));
      await flush();
      await flush();
   }
   await flush();
}

async function pickFiles(paths = PATHS) {
   bridge.pick_files.mockResolvedValue(paths);
   await fireEvent.click(screen.getByRole("button", { name: "Seleccionar manualmente" }));
   await flush();
   await flush();
}

beforeEach(() => {
   vi.useFakeTimers();
   progress.reset();
   vi.resetAllMocks();
   appConfig.baseFolder = "C:/Proj";
   appConfig.transcription = TRANSCRIBE_CAPS;
   appConfig.mediaExtensions = { audio: [".mp3", ".wav"], video: [".mp4"] };
   bridge.check_remote_server.mockResolvedValue(MEDIATOR);
   bridge.get_file_info.mockImplementation(async (p) => ({ name: p.split("/").pop(), size_mb: 7, duration_seconds: 120 }));
   bridge.plan_transcribe.mockImplementation(async (options) => planFor(options));
});
afterEach(() => {
   cleanup();
   vi.useRealTimers();
});

describe("TranscribeView: valores y configuración guardada", () => {
   it("sin nada guardado, todo sale de los valores por defecto del backend", async () => {
      await mount();
      expect(isSelected(screen.getByRole("button", { name: "CUDA" }))).toBe(true);
      expect(select("Modelo").value).toBe("large-v3");
      expect(select("Compute type").value).toBe("int8_float16");
      expect(select("Beam size").value).toBe("5");
      expect(select("Idioma").value).toBe("ja");
      expect(select("Formato de salida").value).toBe("srt");
      await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByRole("switch", { name: "VAD filter" }).getAttribute("aria-checked")).toBe("true");
      expect(within(dialog).getByRole("switch", { name: "Condition on previous text" }).getAttribute("aria-checked")).toBe("false");
      expect(within(dialog).getByLabelText("Initial prompt").value).toBe("prompt de config");
   });

   it("los idiomas se ven con su nombre completo, nunca abreviados", async () => {
      await mount();
      const options = within(select("Idioma")).getAllByRole("option").map((o) => o.textContent);
      expect(options).toEqual(["japanese", "chinese"]);
   });

   it("no congela los valores por defecto: lo no tocado se guarda como null", async () => {
      await mount();
      await fireEvent.change(select("Beam size"), { target: { value: "7" } });
      await flush();
      expect(savedConfig()).toMatchObject({ beamSize: 7, modelSize: null, device: null, initialPrompt: null, outputSubfolder: "" });
   });

   it("respeta lo guardado", async () => {
      await mount({
         saved: { modelSize: "small", device: "cpu", computeType: "int8", beamSize: 3, language: "zh", outputFormat: "vtt",
                  vadFilter: false, conditionOnPrev: true, wordTimestamps: false, initialPrompt: "mi glosario", outputSubfolder: "serie" },
      });
      expect(isSelected(screen.getByRole("button", { name: "CPU" }))).toBe(true);
      expect(select("Modelo").value).toBe("small");
      expect(select("Compute type").value).toBe("int8");
      expect(select("Beam size").value).toBe("3");
      expect(select("Idioma").value).toBe("zh");
      expect(select("Formato de salida").value).toBe("vtt");
      expect(select("Subcarpeta de salida").value).toBe("serie");
      await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByRole("switch", { name: "VAD filter" }).getAttribute("aria-checked")).toBe("false");
      expect(within(dialog).getByRole("switch", { name: "Condition on previous text" }).getAttribute("aria-checked")).toBe("true");
      expect(within(dialog).getByLabelText("Initial prompt").value).toBe("mi glosario");
   });

   it("un prompt vacío guardado es «sin prompt»; solo null significa «el de config.py»", async () => {
      await mount({ saved: { initialPrompt: "" } });
      await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
      expect(within(screen.getByRole("dialog")).getByLabelText("Initial prompt").value).toBe("");

      appConfig.transcription = { ...TRANSCRIBE_CAPS, defaults: { ...TRANSCRIBE_CAPS.defaults, initial_prompt: "otro de config" } };
      await mount({ saved: { initialPrompt: null } });
      await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
      expect(within(screen.getByRole("dialog")).getByLabelText("Initial prompt").value).toBe("otro de config");
   });

   it("el idioma guardado por versiones viejas con su nombre («chinese») sigue valiendo", async () => {
      await mount({ saved: { language: "chinese" } });
      expect(select("Idioma").value).toBe("zh");
   });

   it("una subcarpeta guardada que era «la del idioma» (japanese con zh) no arrastra la carpeta del otro idioma", async () => {
      await mount({ saved: { language: "zh", outputSubfolder: "japanese" } });
      expect(select("Subcarpeta de salida").value).toBe("");
      expect(select("Subcarpeta de salida").placeholder).toBe("chinese");
      await pickFiles();
      await settle();
      expect(lastPlanOptions()).toMatchObject({ language: "zh", output_subfolder: null });
   });

   it("valores guardados inválidos se corrigen sin romper nada", async () => {
      await mount({ saved: { device: "tpu", beamSize: 99, outputFormat: "xyz", computeType: "float32", language: "klingon", modelSize: "gigante" } });
      await pickFiles();
      await settle();
      expect(lastPlanOptions()).toMatchObject({
         device: "cuda", beam_size: 5, output_format: "srt", compute_type: "int8_float16", language: "ja", model_size: "large-v3",
      });
   });

   it("cambiar de dispositivo muestra un compute type válido, y al volver reaparece el elegido", async () => {
      await mount();
      await fireEvent.click(screen.getByRole("button", { name: "CPU" }));
      await flush();
      expect(select("Compute type").value).toBe("float32");
      expect(within(select("Compute type")).getAllByRole("option").map((o) => o.value)).toEqual(["float32", "int8"]);
      await fireEvent.click(screen.getByRole("button", { name: "CUDA" }));
      await flush();
      expect(select("Compute type").value).toBe("int8_float16");
   });

   it("cambiar el idioma devuelve la subcarpeta a la del idioma", async () => {
      await mount({ saved: { outputSubfolder: "mi carpeta" } });
      expect(select("Subcarpeta de salida").value).toBe("mi carpeta");
      await fireEvent.change(select("Idioma"), { target: { value: "zh" } });
      await flush();
      expect(select("Subcarpeta de salida").value).toBe("");
      expect(select("Subcarpeta de salida").placeholder).toBe("chinese");
      expect(screen.getByText("→ transcriptions/chinese/")).toBeTruthy();
   });

   it("lo que se escribe en la subcarpeta se guarda y se ve en la ruta", async () => {
      await mount();
      await fireEvent.input(select("Subcarpeta de salida"), { target: { value: "serie 1" } });
      await flush();
      expect(savedConfig().outputSubfolder).toBe("serie 1");
      expect(screen.getByText("→ transcriptions/serie 1/")).toBeTruthy();
   });
});

describe("TranscribeView: destino remoto", () => {
   it("la lista de modelos es la del mediador, y un modelo guardado que no está se reemplaza SIN pisar lo guardado", async () => {
      await mount({ saved: { modelSize: "small" }, mode: "remote" });
      expect(within(select("Modelo")).getAllByRole("option").map((o) => o.value)).toEqual(["medium", "large-v3-turbo"]);
      expect(select("Modelo").value).toBe("medium");
      expect(savedConfig().modelSize).toBe("small"); // antes se persistía "medium" y contaminaba el uso local

      await fireEvent.click(screen.getByRole("button", { name: /Cambiar modo/ }));
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en esta PC/ }));
      await flush();
      expect(select("Modelo").value).toBe("small");
   });

   it("un modelo guardado que el mediador también tiene se conserva", async () => {
      await mount({ saved: { modelSize: "large-v3-turbo" }, mode: "remote" });
      expect(select("Modelo").value).toBe("large-v3-turbo");
   });

   it("el plan y la ejecución llevan el destino remoto", async () => {
      await mount({ mode: "remote" });
      await pickFiles();
      await settle();
      expect(lastPlanOptions().target).toEqual({ mode: "remote", host: "10.0.0.5", port: 9000 });
      expect(lastPlanOptions().model_size).toBe("medium");
   });

   it("mediador no encontrado, ocupado, o que falla: se explica y no queda colgado el spinner", async () => {
      bridge.check_remote_server.mockResolvedValue({ found: false });
      await mount({ mode: "remote" });
      expect(screen.getByText(/No se encontró el server mediador/)).toBeTruthy();

      bridge.check_remote_server.mockResolvedValue({ found: true, state: "busy", busy_model: "large-v3" });
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en remoto/ }));
      await flush();
      expect(screen.getByText(/ocupado en este momento \(modelo: large-v3\)/)).toBeTruthy();

      bridge.check_remote_server.mockRejectedValue(new Error("sin red"));
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en remoto/ }));
      await flush();
      expect(screen.getByText("No se pudo consultar el mediador (sin red).")).toBeTruthy();
      expect(screen.queryByText(/Buscando mediador/)).toBeNull();
      expect(screen.getByRole("button", { name: /Transcribir en remoto/ }).disabled).toBe(false);
   });
});

describe("TranscribeView: plan y ejecución", () => {
   it("el plan recibe todas las opciones (con las duraciones conocidas) y no se pide sin archivos", async () => {
      await mount();
      await settle();
      expect(bridge.plan_transcribe).not.toHaveBeenCalled();

      await pickFiles();
      await settle();
      expect(bridge.plan_transcribe).toHaveBeenCalledTimes(1);
      expect(lastPlanOptions()).toEqual({
         file_paths: PATHS, base_folder: "C:/Proj", model_size: "large-v3", device: "cuda", compute_type: "int8_float16",
         beam_size: 5, language: "ja", vad_filter: true, condition_on_previous_text: false, word_timestamps: true,
         output_format: "srt", output_subfolder: null, target: { mode: "local" }, durations: [120, 120],
      });
   });

   it("escribir el prompt no vuelve a pedir el plan", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(screen.getByRole("button", { name: "Opciones adicionales" }));
      await fireEvent.input(within(screen.getByRole("dialog")).getByLabelText("Initial prompt"), { target: { value: "hola" } });
      await settle();
      expect(bridge.plan_transcribe).toHaveBeenCalledTimes(1);
   });

   it("run_transcribe recibe UN objeto con las opciones del plan, el prompt y el job_id (no 15 argumentos)", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();

      expect(bridge.run_transcribe).toHaveBeenCalledTimes(1);
      const call = bridge.run_transcribe.mock.calls[0];
      expect(call).toHaveLength(1);
      expect(call[0]).toMatchObject({ file_paths: PATHS, base_folder: "C:/Proj", model_size: "large-v3", target: { mode: "local" },
                                      initial_prompt: "prompt de config" });
      expect(call[0].job_id).toEqual(expect.any(String));
      expect(progress.running).toBe(true);
   });

   it("un error del plan (subcarpeta con ruta, nombres repetidos...) se muestra y bloquea el botón", async () => {
      bridge.plan_transcribe.mockResolvedValue({ error: "La subcarpeta debe ser un solo nombre de carpeta, sin rutas (por ejemplo «japanese»)." });
      await mount();
      await pickFiles();
      await settle();
      expect(screen.getByRole("alert").textContent).toContain("un solo nombre de carpeta");
      expect(runButton().disabled).toBe(true);
   });

   it("avisa de las transcripciones que ya existen y se sobrescribirán, pero deja ejecutar", async () => {
      bridge.plan_transcribe.mockImplementation(async (o) => {
         const plan = planFor(o);
         plan.files[1].exists = true;
         return plan;
      });
      await mount();
      await pickFiles();
      await settle();
      expect(screen.getByText(/se sobrescribirán: b\.srt/)).toBeTruthy();
      expect(runButton().disabled).toBe(false);
   });

   it("no ejecuta con el plan pendiente (aunque se fuerce el clic)", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.change(select("Beam size"), { target: { value: "8" } });
      await flush();
      await fireEvent.click(runButton());
      await flush();
      expect(bridge.run_transcribe).not.toHaveBeenCalled();
   });

   it("la pantalla de proceso muestra los archivos del plan y sus logs por archivo, tomados del store", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();

      const jobId = progress.jobId;
      window.dispatchEvent(new CustomEvent("audiotools:transcribe:file_log", { detail: { job_id: jobId, file_index: 1, message: "[0.00s -> 1.00s] hola b" } }));
      window.dispatchEvent(new CustomEvent("audiotools:transcribe:file_log", { detail: { job_id: "OTRO", file_index: 1, message: "de otro job" } }));
      await flush();

      await fireEvent.click(screen.getByText("b.mp3"));
      await flush();
      expect(screen.getByText("[0.00s -> 1.00s] hola b")).toBeTruthy();
      expect(screen.queryByText("de otro job")).toBeNull();
   });

   it("un error del backend al ejecutar se muestra en la pantalla de proceso", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();
      window.dispatchEvent(new CustomEvent("audiotools:done", {
         detail: { job_id: progress.jobId, success: false, cancelled: false, error: "RuntimeError: CUDA no disponible" },
      }));
      await flush();
      expect(screen.getByRole("alert").textContent).toContain("CUDA no disponible");
   });
});

describe("TranscribeView: archivos", () => {
   it("la selección manual usa las extensiones del backend", async () => {
      await mount();
      await pickFiles();
      expect(bridge.pick_files).toHaveBeenCalledWith(["*.mp3", "*.wav"], "C:/Proj", "audio");
   });

   it("quitar un archivo lo saca de la lista y del plan", async () => {
      await mount();
      await pickFiles();
      await fireEvent.click(screen.getAllByText("✕")[0]);
      await settle();
      expect(lastPlanOptions().file_paths).toEqual([PATHS[1]]);
   });
});

describe("TranscribeView: carpeta y selección de audios (useFileSelection / FileList)", () => {
   it("elegir la carpeta base detecta los audios y dice de dónde salen", async () => {
      bridge.pick_folder.mockResolvedValue("C:/Otra");
      bridge.scan_audio_parts_or_audios.mockResolvedValue({ files: PATHS, source: "./audios/parts", error: null });
      await mount();
      await fireEvent.click(screen.getByText("C:/Proj"));
      await flush();
      await flush();
      expect(screen.getByText("✓ 2 archivo(s) detectados desde ./audios/parts")).toBeTruthy();
      expect(appConfig.baseFolder).toBe("C:/Otra");
      await settle();
      expect(lastPlanOptions().base_folder).toBe("C:/Otra");
   });

   it("una carpeta sin audios y un error del escaneo avisan con ⚠", async () => {
      bridge.pick_folder.mockResolvedValue("C:/Vacia");
      bridge.scan_audio_parts_or_audios.mockResolvedValueOnce({ files: [], source: "./audios", error: null });
      await mount();
      await fireEvent.click(screen.getByText("C:/Proj"));
      await flush();
      await flush();
      expect(screen.getByText("⚠ No se encontraron audios")).toBeTruthy();

      bridge.scan_audio_parts_or_audios.mockResolvedValueOnce({ files: [], source: null, error: "La carpeta no existe" });
      await fireEvent.click(screen.getByText("C:/Vacia"));
      await flush();
      await flush();
      expect(screen.getByText("⚠ La carpeta no existe")).toBeTruthy();
   });

   it("un audio ilegible se omite y se avisa, en vez de romper toda la carga (antes se perdían todos)", async () => {
      bridge.get_file_info.mockImplementation(async (p) => {
         if (p.includes("b.mp3")) throw new Error("ffprobe falló");
         return { name: "a.mp3", size_mb: 7, duration_seconds: 120 };
      });
      await mount();
      await pickFiles();
      await settle();
      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("⚠ 1 archivo(s) detectados; 1 no se pudieron leer")).toBeTruthy();
      expect(lastPlanOptions().file_paths).toEqual(["C:/Proj/audios/a.mp3"]);
   });

   it("mientras se leen los archivos, la caja de altura fija muestra «Cargando archivos...»", async () => {
      let finish;
      bridge.get_file_info.mockImplementation(() => new Promise((resolve) => (finish = resolve)));
      bridge.pick_files.mockResolvedValue([PATHS[0]]);
      await mount();
      await fireEvent.click(screen.getByRole("button", { name: "Seleccionar manualmente" }));
      await flush();
      expect(screen.getByText("Cargando archivos...")).toBeTruthy();
      expect(screen.getByText("Cargando archivos...").closest(".h-44")).toBeTruthy();

      finish({ name: "a.mp3", size_mb: 7, duration_seconds: 120 });
      await flush();
      await flush();
      expect(screen.queryByText("Cargando archivos...")).toBeNull();
      expect(screen.getByText("a.mp3")).toBeTruthy();
   });

   it("si se cambia de carpeta mientras otra se escanea, solo cuenta la última", async () => {
      let slow;
      bridge.pick_folder.mockResolvedValueOnce("C:/Lenta").mockResolvedValueOnce("C:/Rapida");
      bridge.scan_audio_parts_or_audios
         .mockReturnValueOnce(new Promise((resolve) => (slow = resolve)))
         .mockResolvedValueOnce({ files: ["C:/Rapida/audios/z.mp3"], source: "./audios", error: null });
      await mount();
      await fireEvent.click(screen.getByText("C:/Proj"));
      await flush();
      await fireEvent.click(screen.getByText("C:/Lenta"));
      await flush();
      await flush();

      slow({ files: ["C:/Lenta/audios/vieja.mp3"], source: "./audios", error: null });
      await flush();
      await flush();
      expect(screen.getByText("z.mp3")).toBeTruthy();
      expect(screen.queryByText("vieja.mp3")).toBeNull();
   });

   it("cada archivo se quita con un botón que lo nombra", async () => {
      await mount();
      await pickFiles();
      await fireEvent.click(screen.getByRole("button", { name: "Quitar a.mp3" }));
      expect(screen.queryByText("a.mp3")).toBeNull();
      expect(screen.getByText("b.mp3")).toBeTruthy();
   });
});

describe("TranscribeView: elección de destino (ExecutionModeGate)", () => {
   it("al abrir pide elegir, con los textos de Transcribe, y no muestra aún las opciones", async () => {
      cleanup();
      render(TranscribeView, { props: { goHome: vi.fn() } });
      await flush();
      expect(screen.getByRole("button", { name: /Transcribir en remoto/ })).toBeTruthy();
      expect(screen.getByText("Usa el server mediador de la red para transcribir sin cargar el modelo en esta PC.")).toBeTruthy();
      expect(screen.getByText("Carga el modelo localmente, como siempre.")).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Ejecutar transcripción" })).toBeNull();
   });

   it("«Cambiar modo» vuelve a la elección y los archivos elegidos se conservan", async () => {
      await mount();
      await pickFiles();
      await fireEvent.click(screen.getByRole("button", { name: /Cambiar modo/ }));
      await flush();
      expect(screen.getByRole("button", { name: /Transcribir en esta PC/ })).toBeTruthy();
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en esta PC/ }));
      await flush();
      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("(2)")).toBeTruthy();
   });

   it("el título dice «(remoto)» solo en modo remoto", async () => {
      await mount({ mode: "remote" });
      expect(screen.getByText("Transcribe (remoto)")).toBeTruthy();
      await fireEvent.click(screen.getByRole("button", { name: /Cambiar modo/ }));
      await fireEvent.click(screen.getByRole("button", { name: /Transcribir en esta PC/ }));
      await flush();
      expect(screen.queryByText("Transcribe (remoto)")).toBeNull();
   });
});

describe("TranscribeView: campos (Field / SegmentedControl)", () => {
   it("el dispositivo es un grupo con nombre: el elegido está pulsado", async () => {
      await mount();
      expect(screen.getByRole("group", { name: "Device" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "CUDA" }).getAttribute("aria-pressed")).toBe("true");
      expect(screen.getByRole("button", { name: "CPU" }).getAttribute("aria-pressed")).toBe("false");
      await fireEvent.click(screen.getByRole("button", { name: "CPU" }));
      expect(savedConfig().device).toBe("cpu");
   });

   it("cada campo tiene su ayuda (7) y su etiqueta asociada al control", async () => {
      await mount();
      expect(screen.getAllByRole("button", { name: "?" }).length).toBe(7);
      for (const label of ["Modelo", "Idioma", "Compute type", "Beam size", "Formato de salida", "Subcarpeta de salida"]) {
         expect(screen.getByLabelText(label)).toBeTruthy();
      }
   });
});

