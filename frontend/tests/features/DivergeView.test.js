import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

// Bridge falso: cualquier método sin configurar es un vi.fn() que devuelve undefined.
const bridge = vi.hoisted(
   () => {
      const fns = {};
      return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
   },
);
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import DivergeView from "@diverge/DivergeView.svelte";
import { appConfig } from "@shared/state/config.svelte.js";
import { progress } from "@shared/state/progress.svelte.js";

const FILE = "C:/Proj/audios/show.mp3";
const CHAPTERS = [
   { index: 1, title: "Intro", start: 0, end: 12.5 },
   { index: 2, title: "Main", start: 12.5, end: 99 },
];

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};
/** Deja pasar el debounce del plan y resuelve las promesas pendientes. */
const settle = async (ms = 250) => {
   await vi.advanceTimersByTimeAsync(ms);
   await flush();
};

function plan(names, { outputDir = "C:\\Proj\\audios\\parts" } = {}) {
   return {
      output_dir: outputDir,
      segments: names.map((name, i) => ({
         index: i + 1, name, start: i * 10, end: (i + 1) * 10, duration: 10, output: `${outputDir}\\${name}`,
      })),
   };
}

const runButton = () => screen.getByRole("button", { name: "Ejecutar diverge" });
const countText = () => screen.queryByText(/^\d+ segmentos$/)?.textContent.trim() ?? null;

/** Elige un archivo a mano y deja listo el plan inicial. */
async function loadFile({ chapters = CHAPTERS, duration = 3600 } = {}) {
   bridge.pick_files.mockResolvedValue([FILE]);
   bridge.get_file_info.mockResolvedValue({ name: "show.mp3", size_mb: 10, duration_seconds: duration });
   bridge.get_chapters_for_file.mockResolvedValue(chapters);
   screen.getByRole("button", { name: "Seleccionar manualmente" }).click();
   await flush();
   await flush();
}

beforeEach(() => {
   vi.useFakeTimers();
   localStorage.clear();
   progress.reset();
   appConfig.baseFolder = "C:/Proj";
   appConfig.mediaExtensions = { audio: [".mp3"], video: [".mp4"] };
   vi.resetAllMocks();
   bridge.plan_diverge.mockResolvedValue(plan(["[1] Proj - Intro.mp3", "[2] Proj - Main.mp3"]));
   render(DivergeView, { props: { goHome: vi.fn() } });
});

afterEach(() => {
   cleanup();
   vi.useRealTimers();
});

describe("DivergeView: plan desde el backend", () => {
   it("sin archivo no se pide plan y no se puede ejecutar", async () => {
      await settle();
      expect(bridge.plan_diverge).not.toHaveBeenCalled();
      expect(runButton().disabled).toBe(true);
   });

   it("con capítulos: pide el plan en modo chapters con la duración ya conocida", async () => {
      await loadFile();
      expect(bridge.plan_diverge).not.toHaveBeenCalled(); // aún dentro del debounce
      await settle();
      expect(bridge.plan_diverge).toHaveBeenCalledTimes(1);
      expect(bridge.plan_diverge).toHaveBeenCalledWith({
         file_path: FILE,
         base_folder: "C:/Proj",
         segment_mode: "chapters",
         interval_seconds: null,
         output_folder: null,
         media_type: "audio",
         use_subfolder: true,
         duration_seconds: 3600,
      });
   });

   it("el botón Ejecutar se habilita solo cuando llega el plan", async () => {
      await loadFile();
      expect(runButton().disabled).toBe(true); // plan pendiente
      await settle();
      expect(runButton().disabled).toBe(false);
   });

   it("muestra la carpeta de salida que decide el backend", async () => {
      await loadFile();
      await settle();
      expect(screen.getByText("C:\\Proj\\audios\\parts")).toBeTruthy();
   });

   it("modo intervalo: muestra el número de segmentos del plan (exacto, sin '≈')", async () => {
      bridge.plan_diverge.mockResolvedValue(plan(["[1] Proj.mp3", "[2] Proj.mp3", "[3] Proj.mp3"]));
      await loadFile({ chapters: [] }); // sin capítulos: arranca en intervalo
      await settle();
      expect(bridge.plan_diverge).toHaveBeenCalledWith(
         expect.objectContaining({ segment_mode: "interval", interval_seconds: 1200 }),
      );
      expect(countText()).toBe("3 segmentos");
   });

   it("varios cambios seguidos del intervalo producen UNA sola consulta, con el último valor", async () => {
      await loadFile({ chapters: [] });
      await settle();
      bridge.plan_diverge.mockClear();

      const input = screen.getByLabelText("Intervalo (minutos)");
      await fireEvent.input(input, { target: { value: "5" } });
      await vi.advanceTimersByTimeAsync(100);
      await fireEvent.input(input, { target: { value: "50" } });
      await vi.advanceTimersByTimeAsync(100);
      await fireEvent.input(input, { target: { value: "15" } });
      await settle();

      expect(bridge.plan_diverge).toHaveBeenCalledTimes(1);
      expect(bridge.plan_diverge).toHaveBeenCalledWith(expect.objectContaining({ interval_seconds: 900 }));
   });

   it("un intervalo inválido (vacío) borra el plan y deshabilita Ejecutar", async () => {
      await loadFile({ chapters: [] });
      await settle();
      expect(runButton().disabled).toBe(false);

      await fireEvent.input(screen.getByLabelText("Intervalo (minutos)"), { target: { value: "" } });
      await settle();
      expect(countText()).toBeNull();
      expect(runButton().disabled).toBe(true);
   });

   it("una respuesta que llega tarde NO pisa a la más reciente", async () => {
      await loadFile({ chapters: [] });
      await settle();
      bridge.plan_diverge.mockReset();

      let resolveOld, resolveNew;
      bridge.plan_diverge
         .mockImplementationOnce(() => new Promise((r) => (resolveOld = r)))
         .mockImplementationOnce(() => new Promise((r) => (resolveNew = r)));

      const input = screen.getByLabelText("Intervalo (minutos)");
      await fireEvent.input(input, { target: { value: "10" } });
      await settle(); // sale la consulta 1 (queda pendiente)
      await fireEvent.input(input, { target: { value: "30" } });
      await settle(); // sale la consulta 2 (queda pendiente)

      resolveNew(plan(["[1] Proj.mp3", "[2] Proj.mp3"]));
      await flush();
      expect(countText()).toBe("2 segmentos");

      resolveOld(plan(["a", "b", "c", "d", "e"])); // la vieja llega después
      await flush();
      expect(countText()).toBe("2 segmentos");
      expect(runButton().disabled).toBe(false);
   });

   it("si el backend devuelve un error: se muestra y no se puede ejecutar", async () => {
      bridge.plan_diverge.mockResolvedValue({ error: "No se pudo leer la duración de «show.mp3»." });
      await loadFile();
      await settle();
      expect(screen.getByRole("alert").textContent).toContain("No se pudo leer la duración");
      expect(runButton().disabled).toBe(true);
   });

   it("si la llamada al plan rechaza, también se muestra como error", async () => {
      bridge.plan_diverge.mockRejectedValue(new Error("puente caído"));
      await loadFile();
      await settle();
      expect(screen.getByRole("alert").textContent).toContain("puente caído");
      expect(runButton().disabled).toBe(true);
   });

   it("con subcarpeta activa NUNCA envía output_folder, aunque haya una carpeta de salida recordada", async () => {
      // Elegir una carpeta base deja recordada la carpeta de salida (outputFolder = esa carpeta).
      bridge.pick_folder.mockResolvedValue("C:/Otra");
      bridge.get_file_for_diverge.mockResolvedValue({
         name: "x.mp3", path: "C:/Otra/audios/x.mp3", size_mb: 1, duration_seconds: 60,
      });
      bridge.get_chapters_for_file.mockResolvedValue([]);
      screen.getByText("C:/Proj").closest("button").click();
      await flush();
      await flush();
      await settle();

      expect(bridge.plan_diverge).toHaveBeenLastCalledWith(
         expect.objectContaining({ base_folder: "C:/Otra", use_subfolder: true, output_folder: null }),
      );
   });

   it("sin subcarpeta: no se planifica hasta elegir carpeta de salida, y luego se envía", async () => {
      await loadFile();
      await settle();
      bridge.plan_diverge.mockClear();

      screen.getByRole("switch").click(); // desactiva la subcarpeta
      await settle();
      expect(bridge.plan_diverge).not.toHaveBeenCalled();
      expect(runButton().disabled).toBe(true);

      bridge.pick_folder.mockResolvedValue("C:/salida");
      screen.getByText("Sin seleccionar").closest("button").click();
      await flush();
      await settle();
      expect(bridge.plan_diverge).toHaveBeenCalledWith(
         expect.objectContaining({ use_subfolder: false, output_folder: "C:/salida" }),
      );
   });
});

describe("DivergeView: modo video", () => {
   it("envía media_type video, en intervalo, y deja que el backend deduzca la carpeta de salida", async () => {
      screen.getByRole("button", { name: /Video/ }).click();
      await flush();
      await settle();

      bridge.pick_files.mockResolvedValue(["C:/videos/clip.mp4"]);
      bridge.get_file_info.mockResolvedValue({ name: "clip.mp4", size_mb: 5, duration_seconds: 600 });
      screen.getByRole("button", { name: "Seleccionar archivo" }).click();
      await flush();
      await flush();
      await settle();

      expect(bridge.get_chapters_for_file).not.toHaveBeenCalled(); // en video no hay capítulos
      expect(bridge.plan_diverge).toHaveBeenLastCalledWith({
         file_path: "C:/videos/clip.mp4",
         base_folder: "C:/Proj",
         segment_mode: "interval",
         interval_seconds: 1200,
         output_folder: null,
         media_type: "video",
         use_subfolder: true,
         duration_seconds: 600,
      });
   });
});

describe("DivergeView: ejecución", () => {
   it("run_diverge recibe las opciones del plan (sin capítulos, sin formato, sin duración) más el job_id", async () => {
      await loadFile();
      await settle();
      runButton().click();
      await flush();

      expect(bridge.run_diverge).toHaveBeenCalledTimes(1);
      const sent = bridge.run_diverge.mock.calls[0][0];
      expect(sent).toEqual({
         file_path: FILE,
         base_folder: "C:/Proj",
         segment_mode: "chapters",
         interval_seconds: null,
         output_folder: null,
         media_type: "audio",
         use_subfolder: true,
         job_id: expect.any(String),
      });
      expect(sent).not.toHaveProperty("chapters");
      expect(sent).not.toHaveProperty("output_format");
      expect(sent).not.toHaveProperty("duration_seconds");
   });

   it("la pantalla de proceso muestra los nombres del plan y su carpeta de salida", async () => {
      await loadFile();
      await settle();
      runButton().click();
      await flush();

      expect(screen.getByText("[1] Proj - Intro.mp3")).toBeTruthy();
      expect(screen.getByText("[2] Proj - Main.mp3")).toBeTruthy();
      expect(progress.running).toBe(true);
   });

   it("no ejecuta mientras el plan está pendiente (aunque se fuerce el clic)", async () => {
      await loadFile();
      await settle();
      const input = screen.getByLabelText("Chapters (2)", { exact: false });
      expect(input).toBeTruthy();
      screen.getByLabelText("Intervalo fijo").click(); // cambia de modo => nuevo plan pendiente
      await flush();
      runButton().click();
      await flush();
      expect(bridge.run_diverge).not.toHaveBeenCalled();
   });
});
