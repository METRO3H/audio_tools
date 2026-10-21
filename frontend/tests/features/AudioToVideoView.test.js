import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

// Bridge falso: cualquier método sin configurar es un vi.fn() que devuelve undefined.
const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import AudioToVideoView from "@audio-to-video/AudioToVideoView.svelte";
import { appConfig } from "@shared/state/config.svelte.js";
import { progress } from "@shared/state/progress.svelte.js";

const CAPS = {
   encoders: [
      { id: "cpu", label: "CPU (libx264)" },
      { id: "nvidia", label: "NVIDIA (nvenc)" },
      { id: "amd", label: "AMD (amf)" },
      { id: "intel", label: "Intel (qsv)" },
   ],
   encoder_priority: ["nvidia", "amd", "intel", "cpu"],
   presets: {
      cpu: ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"],
      nvidia: ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
      amd: ["fast", "medium", "slow"],
      intel: ["fast", "medium", "slow"],
   },
   default_presets: { cpu: "medium", nvidia: "p4", amd: "medium", intel: "medium" },
   fps: [1, 24, 30, 60],
   resolutions: ["1280x720", "1920x1080", "3840x2160"],
   quality_range: [0, 51],
};
const ALL_GPUS = { cpu: true, nvidia: true, amd: true, intel: true };
const ONLY_CPU = { cpu: true, nvidia: false, amd: false, intel: false };
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

function planFor(options, extra = {}) {
   return {
      output_dir: "C:\\Proj\\videos",
      files: options.file_paths.map((p, i) => ({
         index: i, name: p.split("/").pop(), path: p, duration: 120,
         output: `C:\\Proj\\videos\\${p.split("/").pop().replace(/\.\w+$/, "")}.mp4`,
         output_name: `${p.split("/").pop().replace(/\.\w+$/, "")}.mp4`, exists: false,
      })),
      total_duration: options.file_paths.length * 120,
      ...extra,
   };
}

const encoderButton = (label) => screen.getByRole("button", { name: label });
const runButton = () => screen.getByRole("button", { name: "Ejecutar Audio → Video" });
const savedConfig = () => JSON.parse(localStorage.getItem("audio_to_video_config"));
const isSelected = (button) => button.className.includes("bg-indigo-600");

async function mount({ saved, detected = ALL_GPUS } = {}) {
   cleanup();
   localStorage.clear();
   if (saved) localStorage.setItem("audio_to_video_config", JSON.stringify(saved));
   bridge.detect_encoders.mockResolvedValue(detected);
   render(AudioToVideoView, { props: { goHome: vi.fn() } });
   await flush();
   await flush();
}

/** Elige audios a mano; los tamaños y duraciones salen del file_info falso. */
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
   appConfig.videoEncoding = CAPS;
   appConfig.mediaExtensions = { audio: [".mp3", ".wav"], video: [".mp4"] };
   bridge.get_file_info.mockImplementation(async (p) => ({ name: p.split("/").pop(), size_mb: 7, duration_seconds: 120 }));
   bridge.plan_audio_to_video.mockImplementation(async (options) => planFor(options));
});
afterEach(() => {
   cleanup();
   vi.useRealTimers();
});

describe("AudioToVideoView: encoder (bug verificado: la detección pisaba el encoder guardado)", () => {
   it("sin nada guardado: el mejor disponible, con su preset por defecto, y no guarda esa elección", async () => {
      await mount();
      expect(isSelected(encoderButton("NVIDIA (nvenc)"))).toBe(true);
      expect(isSelected(encoderButton("CPU (libx264)"))).toBe(false);
      expect(savedConfig().encoder).toBeNull(); // "automático": solo se guarda lo que el usuario elige
   });

   it("REGRESIÓN: cpu guardado se respeta aunque haya NVIDIA, y el preset guardado (fast) no se pisa con p4", async () => {
      await mount({ saved: { encoder: "cpu", preset: "fast", fps: 1, crf: 23, resolution: "1280x720", copyAudio: true, showAdvanced: true } });
      await settle();
      expect(isSelected(encoderButton("CPU (libx264)"))).toBe(true);
      expect(isSelected(encoderButton("NVIDIA (nvenc)"))).toBe(false);
      expect(isSelected(screen.getByRole("button", { name: "fast" }))).toBe(true);
      expect(savedConfig()).toMatchObject({ encoder: "cpu", preset: "fast" });
   });

   it("un encoder guardado que ya no está disponible cae al mejor disponible SIN borrar lo guardado", async () => {
      await mount({ saved: { encoder: "nvidia", showAdvanced: true }, detected: { cpu: true, nvidia: false, amd: true, intel: false } });
      expect(isSelected(encoderButton("AMD (amf)"))).toBe(true);
      expect(savedConfig().encoder).toBe("nvidia"); // si vuelve la GPU, vuelve la elección
   });

   it("sin ningún encoder por hardware, queda CPU", async () => {
      await mount({ detected: ONLY_CPU });
      expect(isSelected(encoderButton("CPU (libx264)"))).toBe(true);
      expect(encoderButton("NVIDIA (nvenc)").disabled).toBe(true);
   });

   it("un encoder guardado inválido (config manipulada) se ignora", async () => {
      await mount({ saved: { encoder: "quantum" } });
      expect(isSelected(encoderButton("NVIDIA (nvenc)"))).toBe(true);
   });

   it("mientras se detecta se muestra lo guardado y no se puede ejecutar; después sí", async () => {
      let finish;
      cleanup();
      localStorage.clear();
      localStorage.setItem("audio_to_video_config", JSON.stringify({ encoder: "nvidia" }));
      bridge.detect_encoders.mockReturnValue(new Promise((resolve) => (finish = resolve)));
      render(AudioToVideoView, { props: { goHome: vi.fn() } });
      await flush();
      await pickFiles();
      await settle();

      expect(screen.getByText("Detectando...")).toBeTruthy();
      expect(isSelected(encoderButton("NVIDIA (nvenc)"))).toBe(true);
      expect(runButton().disabled).toBe(true);

      finish(ALL_GPUS);
      await settle();
      expect(screen.queryByText("Detectando...")).toBeNull();
      expect(runButton().disabled).toBe(false);
   });

   it("REGRESIÓN: si la detección falla, el spinner se va y se avisa (antes quedaba «Detectando...» para siempre)", async () => {
      cleanup();
      bridge.detect_encoders.mockRejectedValue(new Error("puente caído"));
      render(AudioToVideoView, { props: { goHome: vi.fn() } });
      await flush();
      await flush();
      expect(screen.queryByText("Detectando...")).toBeNull();
      expect(screen.getByRole("alert").textContent).toContain("puente caído");
      expect(isSelected(encoderButton("CPU (libx264)"))).toBe(true);
   });

   it("elegir un encoder lo guarda", async () => {
      await mount();
      await fireEvent.click(encoderButton("CPU (libx264)"));
      await flush();
      expect(savedConfig().encoder).toBe("cpu");
   });
});

describe("AudioToVideoView: presets y valores guardados", () => {
   it("cada encoder ofrece sus presets y arranca en el suyo por defecto (cpu medium, nvidia p4)", async () => {
      await mount({ saved: { showAdvanced: true } }); // automático → nvidia
      expect(isSelected(screen.getByRole("button", { name: "p4" }))).toBe(true);
      expect(screen.queryByRole("button", { name: "medium" })).toBeNull();

      await fireEvent.click(encoderButton("CPU (libx264)"));
      await flush();
      expect(isSelected(screen.getByRole("button", { name: "medium" }))).toBe(true); // antes caía en «faster»
      expect(screen.queryByRole("button", { name: "p4" })).toBeNull();
   });

   it("el preset elegido para un encoder vuelve al volver a él", async () => {
      await mount({ saved: { showAdvanced: true } });
      await fireEvent.click(screen.getByRole("button", { name: "p6" }));
      await fireEvent.click(encoderButton("CPU (libx264)"));
      await fireEvent.click(encoderButton("NVIDIA (nvenc)"));
      await flush();
      expect(isSelected(screen.getByRole("button", { name: "p6" }))).toBe(true);
   });

   it("valores guardados fuera de lo permitido se corrigen en lo que se envía, sin romper nada", async () => {
      await mount({ saved: { encoder: "cpu", fps: 25, crf: 99, resolution: "800x600", preset: "p4" } });
      await pickFiles();
      await settle();
      const sent = bridge.plan_audio_to_video.mock.calls.at(-1)[0];
      expect(sent).toMatchObject({ encoder: "cpu", fps: 1, crf: 51, resolution: "1280x720", preset: "medium" });
   });

   it("los fps, las resoluciones y el rango de calidad vienen del backend", async () => {
      await mount({ saved: { showAdvanced: true } });
      for (const f of ["1", "24", "30", "60"]) expect(screen.getByRole("button", { name: f })).toBeTruthy();
      for (const r of CAPS.resolutions) expect(screen.getByRole("button", { name: r })).toBeTruthy();
      const slider = screen.getByLabelText(/Calidad/);
      expect([slider.min, slider.max]).toEqual(["0", "51"]);
   });

   it("el texto del fondo negro sigue a la resolución elegida (antes decía siempre 1280×720)", async () => {
      await mount({ saved: { showAdvanced: true } });
      expect(screen.getByText("Fondo negro 1280×720")).toBeTruthy();
      await fireEvent.click(screen.getByRole("button", { name: "1920x1080" }));
      await flush();
      expect(screen.getByText("Fondo negro 1920×1080")).toBeTruthy();
   });
});

describe("AudioToVideoView: plan y ejecución", () => {
   it("el plan recibe todas las opciones (con las duraciones ya conocidas) y no se pide sin archivos", async () => {
      await mount();
      await settle();
      expect(bridge.plan_audio_to_video).not.toHaveBeenCalled();

      await pickFiles();
      await settle();
      expect(bridge.plan_audio_to_video).toHaveBeenCalledTimes(1);
      expect(bridge.plan_audio_to_video.mock.calls[0][0]).toEqual({
         file_paths: PATHS,
         base_folder: "C:/Proj",
         background_image: null,
         encoder: "nvidia",
         fps: 1,
         crf: 23,
         preset: "p4",
         resolution: "1280x720",
         copy_audio: true,
         durations: [120, 120],
      });
   });

   it("run_audio_to_video recibe UN objeto con las opciones del plan y el job_id (no 9 argumentos)", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();

      expect(bridge.run_audio_to_video).toHaveBeenCalledTimes(1);
      const call = bridge.run_audio_to_video.mock.calls[0];
      expect(call).toHaveLength(1);
      expect(call[0]).toMatchObject({ file_paths: PATHS, base_folder: "C:/Proj", encoder: "nvidia", copy_audio: true });
      expect(call[0].job_id).toEqual(expect.any(String));
      expect(progress.running).toBe(true);
   });

   it("la pantalla de proceso muestra los archivos del plan, con su tamaño", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();
      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("b.mp3")).toBeTruthy();
      expect(screen.getAllByText("7 MB").length).toBe(2);
   });

   it("no ejecuta con el plan pendiente (aunque se fuerce el clic)", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(screen.getByRole("button", { name: "CPU (libx264)" })); // cambia las opciones → plan pendiente
      await flush();
      await fireEvent.click(runButton());
      await flush();
      expect(bridge.run_audio_to_video).not.toHaveBeenCalled();
   });

   it("un error del plan (nombres repetidos, carpeta inexistente...) se muestra y bloquea el botón", async () => {
      bridge.plan_audio_to_video.mockResolvedValue({ error: "«a.mp3» y «a.wav» darían el mismo video («a.mp4»)." });
      await mount();
      await pickFiles();
      await settle();
      expect(screen.getByRole("alert").textContent).toContain("darían el mismo video");
      expect(runButton().disabled).toBe(true);
   });

   it("avisa de los videos que ya existen y se sobrescribirán, pero deja ejecutar", async () => {
      bridge.plan_audio_to_video.mockImplementation(async (o) => {
         const plan = planFor(o);
         plan.files[0].exists = true;
         return plan;
      });
      await mount();
      await pickFiles();
      await settle();
      expect(screen.getByText(/se sobrescribirán: a\.mp4/)).toBeTruthy();
      expect(runButton().disabled).toBe(false);
   });

   it("muestra dónde quedarán los videos, según el plan", async () => {
      await mount();
      await pickFiles();
      await settle();
      expect(screen.getByText("→ C:\\Proj\\videos")).toBeTruthy();
   });

   it("un error del backend al ejecutar se muestra en la pantalla de proceso", async () => {
      await mount();
      await pickFiles();
      await settle();
      await fireEvent.click(runButton());
      await flush();
      window.dispatchEvent(new CustomEvent("audiotools:done", {
         detail: { job_id: progress.jobId, success: false, cancelled: false, error: "La carpeta base no existe" },
      }));
      await flush();
      expect(screen.getByRole("alert").textContent).toContain("La carpeta base no existe");
   });
});

describe("AudioToVideoView: carpeta, archivos e imagen", () => {
   it("elegir la carpeta base detecta los audios (con su origen) y la imagen", async () => {
      bridge.pick_folder.mockResolvedValue("C:/Otra");
      bridge.scan_audio_parts_or_audios.mockResolvedValue({ files: PATHS, source: "./audios/parts", error: null });
      bridge.scan_images_folder.mockResolvedValue({ path: "C:/Otra/images/bg_opt.jpg", name: "bg_opt.jpg", optimized: true });
      await mount();
      await fireEvent.click(screen.getByText("C:/Proj"));
      await flush();
      await flush();
      expect(screen.getByText("✓ 2 audio(s) detectados desde ./audios/parts")).toBeTruthy();
      expect(screen.getByText("✓ Imagen optimizada: bg_opt.jpg")).toBeTruthy();
      expect(appConfig.baseFolder).toBe("C:/Otra");
   });

   it("REGRESIÓN: elegir una imagen a mano NO vuelve a escanear la carpeta (el escaneo optimiza imágenes)", async () => {
      bridge.pick_image.mockResolvedValue("C:/fotos/portada.png");
      await mount();
      await fireEvent.click(screen.getByRole("button", { name: "Cambiar" }));
      await flush();
      expect(bridge.scan_images_folder).not.toHaveBeenCalled();
      expect(screen.getByText("✓ Imagen seleccionada: portada.png")).toBeTruthy();

      await pickFiles();
      await settle();
      expect(bridge.plan_audio_to_video.mock.calls.at(-1)[0].background_image).toBe("C:/fotos/portada.png");
   });

   it("quitar la imagen vuelve al fondo negro", async () => {
      bridge.pick_image.mockResolvedValue("C:/fotos/portada.png");
      await mount();
      await fireEvent.click(screen.getByRole("button", { name: "Cambiar" }));
      await flush();
      await fireEvent.click(screen.getByRole("button", { name: "Quitar" }));
      await flush();
      expect(screen.getByText("Fondo negro 1280×720")).toBeTruthy();
   });

   it("REGRESIÓN: una detección de imagen lenta de una carpeta anterior no pisa la elección manual", async () => {
      let late;
      bridge.pick_folder.mockResolvedValue("C:/Otra");
      bridge.scan_audio_parts_or_audios.mockResolvedValue({ files: PATHS, source: "./audios", error: null });
      bridge.scan_images_folder.mockReturnValue(new Promise((resolve) => (late = resolve)));
      bridge.pick_image.mockResolvedValue("C:/fotos/portada.png");
      await mount();
      await fireEvent.click(screen.getByText("C:/Proj"));
      await flush();
      await fireEvent.click(screen.getByRole("button", { name: "Cambiar" }));
      await flush();

      late({ path: "C:/Otra/images/vieja.jpg", name: "vieja.jpg", optimized: false });
      await flush();
      expect(screen.getByText("✓ Imagen seleccionada: portada.png")).toBeTruthy();
      expect(screen.queryByText(/vieja\.jpg/)).toBeNull();
   });

   it("quitar un archivo lo saca de la lista", async () => {
      await mount();
      await pickFiles();
      await fireEvent.click(screen.getByRole("button", { name: "Quitar a.mp3" }));
      expect(screen.queryByText("a.mp3")).toBeNull();
      expect(screen.getByText("b.mp3")).toBeTruthy();
   });
});

describe("AudioToVideoView: selección de audios (useFileSelection)", () => {
   it("la selección manual usa las extensiones que da el backend, no una lista propia (antes duplicada en el front)", async () => {
      await mount();
      await pickFiles();
      expect(bridge.pick_files).toHaveBeenCalledWith(["*.mp3", "*.wav"], "C:/Proj", "audio");
   });

   it("una carpeta sin audios avisa con ⚠", async () => {
      bridge.pick_folder.mockResolvedValue("C:/Vacia");
      bridge.scan_audio_parts_or_audios.mockResolvedValue({ files: [], source: "./audios", error: null });
      await mount();
      await fireEvent.click(screen.getByText("C:/Proj"));
      await flush();
      await flush();
      expect(screen.getByText("⚠ No se encontraron audios")).toBeTruthy();
   });

   it("un error del escaneo se muestra y vacía la lista", async () => {
      bridge.pick_folder.mockResolvedValue("C:/Mala");
      bridge.scan_audio_parts_or_audios.mockResolvedValue({ files: [], source: null, error: "La carpeta no existe" });
      await mount();
      await fireEvent.click(screen.getByText("C:/Proj"));
      await flush();
      await flush();
      expect(screen.getByText("⚠ La carpeta no existe")).toBeTruthy();
   });

   it("un audio ilegible se omite y se avisa, en vez de romper toda la carga", async () => {
      bridge.get_file_info.mockImplementation(async (p) => {
         if (p.includes("b.mp3")) throw new Error("ffprobe falló");
         return { name: "a.mp3", size_mb: 7, duration_seconds: 120 };
      });
      await mount();
      await pickFiles();
      await settle();
      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("⚠ 1 archivo(s) detectados; 1 no se pudieron leer")).toBeTruthy();
      expect(bridge.plan_audio_to_video.mock.calls.at(-1)[0].file_paths).toEqual(["C:/Proj/audios/a.mp3"]);
   });

   it("cancelar el diálogo de selección no cambia la lista", async () => {
      await mount();
      await pickFiles();
      bridge.pick_files.mockResolvedValue([]);
      await fireEvent.click(screen.getByRole("button", { name: "Seleccionar manualmente" }));
      await flush();
      expect(screen.getByText("a.mp3")).toBeTruthy();
      expect(screen.getByText("b.mp3")).toBeTruthy();
   });

   it("si se cambia de carpeta mientras otra se escanea, solo cuenta la última", async () => {
      let slow;
      bridge.pick_folder.mockResolvedValueOnce("C:/Lenta").mockResolvedValueOnce("C:/Rapida");
      bridge.scan_images_folder.mockResolvedValue(null);
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
});

describe("AudioToVideoView: selectores (SegmentedControl)", () => {
   it("el encoder es un grupo con nombre: el elegido está pulsado y los no disponibles, deshabilitados", async () => {
      await mount({ detected: { cpu: true, nvidia: true, amd: false, intel: false } });
      const group = screen.getByRole("group", { name: "Encoder" });
      expect(group.className).toContain("flex-wrap");
      expect(encoderButton("NVIDIA (nvenc)").getAttribute("aria-pressed")).toBe("true");
      expect(encoderButton("AMD (amf)").disabled).toBe(true);
      expect(encoderButton("Intel (qsv)").disabled).toBe(true);
      expect(encoderButton("CPU (libx264)").disabled).toBe(false);
   });

   it("fps y audio también son grupos con nombre y estado", async () => {
      await mount({ saved: { showAdvanced: true, fps: 30, copyAudio: false } });
      expect(screen.getByRole("group", { name: "FPS" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "30" }).getAttribute("aria-pressed")).toBe("true");
      expect(screen.getByRole("button", { name: "AAC 192k" }).getAttribute("aria-pressed")).toBe("true");
      expect(screen.getByRole("button", { name: /Copy/ }).getAttribute("aria-pressed")).toBe("false");
   });

   it("elegir audio Copy / AAC, fps y resolución los guarda", async () => {
      await mount({ saved: { showAdvanced: true } });
      await fireEvent.click(screen.getByRole("button", { name: "AAC 192k" }));
      await fireEvent.click(screen.getByRole("button", { name: "24" }));
      await fireEvent.click(screen.getByRole("button", { name: "3840x2160" }));
      await flush();
      expect(savedConfig()).toMatchObject({ copyAudio: false, fps: 24, resolution: "3840x2160" });
   });

   it("la etiqueta de la calidad queda asociada a su control", async () => {
      await mount({ saved: { showAdvanced: true, crf: 30 } });
      expect(screen.getByLabelText(/Calidad/).value).toBe("30");
   });
});
