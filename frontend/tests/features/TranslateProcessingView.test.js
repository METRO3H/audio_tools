/**
 * Caracterización de TranslateProcessingView (progreso de Translate SRT).
 *
 * Fija lo que la vista HACE hoy, para poder partirla en componentes sin cambiar su comportamiento.
 * Los tests marcados "(comportamiento actual)" documentan cosas que parecen bugs: si un cambio
 * futuro las arregla a propósito, hay que actualizar el test, no es una regresión.
 */
import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

const bridge = vi.hoisted(() => {
   const fns = {};
   return new Proxy(fns, { get: (target, key) => (target[key] ??= vi.fn()) });
});
vi.mock("@shared/services/bridge.svelte.js", () => ({ bridge }));

import TranslateProcessingView from "@translate/srt/TranslateProcessingView.svelte";
import { progress } from "@shared/state/progress.svelte.js";

const FILES = [
   { path: "C:/s/a.srt", name: "a.srt", size_mb: 1, duration_seconds: 60 },
   { path: "C:/s/b.srt", name: "b.srt", size_mb: 2, duration_seconds: 90 },
];

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};
const emit = async (name, detail, prefix = "audiotools:translation:") => {
   window.dispatchEvent(new CustomEvent(`${prefix}${name}`, { detail }));
   await flush();
};
const click = async (el) => {
   await fireEvent.click(el);
   await flush();
};

let goHome, onCancel, onBack;
function mount() {
   goHome = vi.fn();
   onCancel = vi.fn();
   onBack = vi.fn();
   render(TranslateProcessingView, {
      props: { goHome, onCancel, onBack, fileInfos: FILES, outputPath: "C:/out" },
   });
}

// Botón `name` dentro del modal cuyo título coincide con `heading` (el checklist de la vista
// también tiene botones "Work info" / "Título", así que hay que acotar por modal).
function modalButton(heading, name) {
   let node = screen.getByRole("heading", { name: heading });
   while (node.parentElement) {
      node = node.parentElement;
      const found = within(node).queryAllByRole("button", { name });
      if (found.length) return found[0];
   }
   throw new Error(`no hay botón "${name}" en el modal "${heading}"`);
}
// El panel del modal (tanto el div a mano de hoy como el de Modal.svelte llevan rounded-2xl).
const modalOf = (heading) => screen.getByRole("heading", { name: heading }).closest(".rounded-2xl");

const BLOCKS_OUT = "═══ Bloque 1/2 ═══\n1: hola\n\n═══ Bloque 2/2 ═══\n2: chau";
const BLOCKS_IN =
   "═══ Bloque 1/2 ═══\n[Previous translated context]:\nCTX-IN\n\n[Block to translate]:\nBLK-IN";

beforeEach(() => {
   progress.reset();
   vi.resetAllMocks();
   mount();
});
afterEach(() => {
   cleanup();
   progress.reset();
});

describe("ciclo de vida", () => {
   it("al destruir la vista quita todos sus listeners de window", () => {
      const spy = vi.spyOn(window, "removeEventListener");
      cleanup();
      const removed = spy.mock.calls.map((c) => c[0]);
      for (const name of [
         "step", "work_info_stream", "title_stream", "work_info", "title", "lines",
         "queue_started", "block_stream", "block_input", "system_prompt",
      ]) {
         expect(removed).toContain(`audiotools:translation:${name}`);
      }
      expect(removed).toContain("audiotools:file");
      spy.mockRestore();
   });
});

describe("checklist de pasos y pestañas", () => {
   it("arranca en la pestaña Work info esperando al modelo", () => {
      expect(screen.getByPlaceholderText("Esperando al modelo...")).toBeTruthy();
   });

   it("un paso que pasa a active lleva la pestaña activa hasta él", async () => {
      await emit("step", { step: "title", status: "active" });
      expect(screen.getByPlaceholderText("Esperando al modelo...")).toBeTruthy();
      await emit("step", { step: "blocks", status: "active" });
      expect(screen.getByText(/líneas/)).toBeTruthy();
   });

   it("si el usuario eligió una pestaña, un paso nuevo ya no se la cambia", async () => {
      await click(screen.getByRole("button", { name: /Traducción/ }));
      await emit("step", { step: "title", status: "active" });
      expect(screen.getByText(/líneas/)).toBeTruthy();
   });

   it("un paso omitido muestra su aviso en vez del textarea", async () => {
      await emit("step", { step: "work_info", status: "skipped" });
      expect(screen.getByText(/paso omitido/)).toBeTruthy();
      await emit("step", { step: "title", status: "skipped" });
      await click(screen.getByRole("button", { name: /Título/ }));
      expect(screen.getByText(/No se dio título original/)).toBeTruthy();
   });

   it("al terminar el job, un paso que quedó activo pasa a done o cancelled", async () => {
      progress.running = true;
      await emit("step", { step: "work_info", status: "active" });
      progress.running = false;
      progress.success = false;
      await flush();
      const chip = screen.getByRole("button", { name: /Work info/ });
      expect(chip.textContent).toContain("✕");
   });
});

describe("texto en vivo", () => {
   it("work_info: el stream se muestra y el valor final lo reemplaza", async () => {
      await emit("work_info_stream", { text: "<think>x</think> crudo" });
      expect(screen.getByDisplayValue("<think>x</think> crudo")).toBeTruthy();
      await emit("work_info", { work_info: "limpio" });
      expect(screen.getByDisplayValue("limpio")).toBeTruthy();
   });

   it("título: stream y valor final", async () => {
      await click(screen.getByRole("button", { name: /Título/ }));
      await emit("title_stream", { text: "Tit crudo" });
      expect(screen.getByDisplayValue("Tit crudo")).toBeTruthy();
      await emit("title", { title: "Tit final" });
      expect(screen.getByDisplayValue("Tit final")).toBeTruthy();
   });

   it("ignora los nombres de evento anteriores (audiotools:translate:*)", async () => {
      await emit("work_info_stream", { text: "vieja" }, "audiotools:translate:");
      expect(screen.queryByDisplayValue("vieja")).toBeNull();
   });
});

describe("progreso por líneas y archivos", () => {
   beforeEach(async () => {
      await click(screen.getByRole("button", { name: /Traducción/ }));
   });

   it("muestra el porcentaje global y las líneas hechas/totales", async () => {
      await emit("lines", {
         file_index: 0, lines_done_file: 10, lines_total_file: 20,
         lines_done_global: 10, lines_total_global: 40,
      });
      expect(screen.getByText("25")).toBeTruthy();
      expect(screen.getByText(/10\/40 líneas/)).toBeTruthy();
   });

   it("el archivo actual no figura como hecho; los anteriores sí", async () => {
      const row = (name) => screen.getByText(name).closest('[role="button"]');
      const lines = (file_index) => ({
         file_index, lines_done_file: 1, lines_total_file: 5, lines_done_global: 1, lines_total_global: 10,
      });
      await emit("lines", lines(0));
      expect(row("a.srt").textContent).not.toContain("✓");
      expect(row("b.srt").textContent).not.toContain("✓");
      await emit("lines", lines(1));
      expect(row("a.srt").textContent).toContain("✓");
      expect(row("b.srt").textContent).not.toContain("✓");
   });

   it("sin líneas totales, el porcentaje es 0", () => {
      expect(screen.getByText(/0\/0 líneas/)).toBeTruthy();
   });

   it("lista los archivos de la cola", () => {
      expect(screen.getByText("a.srt")).toBeTruthy();
      expect(screen.getByText("b.srt")).toBeTruthy();
   });

   it("el tiempo de un archivo terminado sale de audiotools:file", async () => {
      // El tiempo solo se ve en filas hechas: el archivo 0 cuenta como hecho cuando el índice
      // actual (por el evento de líneas) ya es el 1.
      await emit("lines", {
         file_index: 1, lines_done_file: 0, lines_total_file: 5,
         lines_done_global: 5, lines_total_global: 10,
      });
      await emit("file", { index: 0, done: true, elapsed: 65 }, "audiotools:");
      expect(screen.getByText(/1:05/)).toBeTruthy();
   });
});

describe("cancelar y salir", () => {
   it("Cancelar llama a onCancel y pasa a 'Deteniendo...'", async () => {
      progress.running = true;
      await flush();
      await click(screen.getByRole("button", { name: "Cancelar" }));
      expect(onCancel).toHaveBeenCalledOnce();
      expect(screen.getByRole("button", { name: "Deteniendo..." }).disabled).toBe(true);
   });

   it("← Inicio sin job corriendo vuelve directo", async () => {
      await click(screen.getByRole("button", { name: /Inicio/ }));
      expect(goHome).toHaveBeenCalledOnce();
      expect(onCancel).not.toHaveBeenCalled();
   });

   it("← Inicio con el job corriendo pide confirmación; confirmar cancela y vuelve", async () => {
      progress.running = true;
      await flush();
      await click(screen.getByRole("button", { name: /Inicio/ }));
      expect(goHome).not.toHaveBeenCalled();
      await click(screen.getByRole("button", { name: "Cancelar y volver al inicio" }));
      expect(onCancel).toHaveBeenCalledOnce();
      expect(goHome).toHaveBeenCalledOnce();
   });

   it("← Inicio con el job corriendo: 'Seguir traduciendo' no hace nada", async () => {
      progress.running = true;
      await flush();
      await click(screen.getByRole("button", { name: /Inicio/ }));
      await click(screen.getByRole("button", { name: "Seguir traduciendo" }));
      expect(goHome).not.toHaveBeenCalled();
      expect(onCancel).not.toHaveBeenCalled();
   });
});

describe("botones de resultado", () => {
   it("no aparecen mientras corre", async () => {
      progress.running = true;
      await flush();
      expect(screen.queryByRole("button", { name: "Volver" })).toBeNull();
   });

   it("con éxito: Abrir carpeta y Volver", async () => {
      progress.running = false;
      progress.success = true;
      await flush();
      await click(screen.getByRole("button", { name: "Abrir carpeta" }));
      expect(bridge.open_folder).toHaveBeenCalledWith("C:/out");
      await click(screen.getByRole("button", { name: "Volver" }));
      expect(onBack).toHaveBeenCalledOnce();
   });

   it("con fallo: solo Volver", async () => {
      progress.running = false;
      progress.success = false;
      await flush();
      expect(screen.queryByRole("button", { name: "Abrir carpeta" })).toBeNull();
      expect(screen.getByRole("button", { name: "Volver" })).toBeTruthy();
   });
});

describe("modal de stream de un archivo", () => {
   beforeEach(async () => {
      await click(screen.getByRole("button", { name: /Traducción/ }));
      await emit("block_stream", { file_index: 0, text: BLOCKS_OUT });
      await emit("block_input", { file_index: 0, text: BLOCKS_IN });
      await click(screen.getByText("a.srt"));
   });

   it("se abre con el nombre del archivo y los bloques del output", () => {
      expect(screen.getByRole("heading", { name: "Stream — a.srt" })).toBeTruthy();
      const modal = modalOf("Stream — a.srt");
      expect(within(modal).getByRole("button", { name: "Bloque 1" })).toBeTruthy();
      expect(within(modal).getByRole("button", { name: "Bloque 2" })).toBeTruthy();
      expect(within(modal).getByText("1: hola")).toBeTruthy();
   });

   it("elegir otro bloque muestra su contenido", async () => {
      const modal = modalOf("Stream — a.srt");
      await click(within(modal).getByRole("button", { name: "Bloque 2" }));
      expect(within(modal).getByText("2: chau")).toBeTruthy();
   });

   it("si el log se acorta y el bloque elegido ya no existe, vuelve al primero", async () => {
      const modal = modalOf("Stream — a.srt");
      await click(within(modal).getByRole("button", { name: "Bloque 2" }));
      expect(within(modal).getByText("2: chau")).toBeTruthy();
      await emit("block_stream", { file_index: 0, text: "═══ Bloque 1/1 ═══\n1: hola" });
      expect(within(modal).getByText("1: hola")).toBeTruthy();
      expect(within(modal).getByRole("button", { name: "Bloque 1" }).className).toContain("bg-indigo-500/20");
   });

   it("la pestaña Input muestra lo enviado al modelo", async () => {
      const modal = modalOf("Stream — a.srt");
      await click(within(modal).getByRole("button", { name: "Input" }));
      expect(within(modal).getAllByRole("button", { name: /Bloque 1/ }).length).toBe(1);
      expect(modal.textContent).toContain("CTX-IN");
   });

   it("Ver raw alterna a la salida completa sin dividir en bloques", async () => {
      const modal = modalOf("Stream — a.srt");
      await click(within(modal).getByRole("button", { name: "Ver raw" }));
      expect(within(modal).queryByRole("button", { name: "Bloque 1" })).toBeNull();
      expect(modal.textContent).toContain("═══ Bloque 1/2 ═══");
      expect(within(modal).getByRole("button", { name: "Ver por bloques" })).toBeTruthy();
   });

   it("un archivo sin stream muestra que todavía no hay nada", async () => {
      await click(screen.getByRole("button", { name: "✕" }));
      await click(screen.getByText("b.srt"));
      expect(screen.getByText("Sin bloques")).toBeTruthy();
      expect(screen.getByText("Todavía no hay nada para este archivo.")).toBeTruthy();
   });

   it("✕ lo cierra", async () => {
      await click(screen.getByRole("button", { name: "✕" }));
      expect(screen.queryByRole("heading", { name: "Stream — a.srt" })).toBeNull();
   });

   it("Copiar todo copia el texto del output", async () => {
      const writeText = vi.fn().mockResolvedValue();
      Object.assign(navigator, { clipboard: { writeText } });
      await click(within(modalOf("Stream — a.srt")).getByRole("button", { name: "Copiar todo" }));
      expect(writeText).toHaveBeenCalledWith(BLOCKS_OUT);
   });
});

describe("modal de stream de todos los archivos", () => {
   beforeEach(async () => {
      await click(screen.getByRole("button", { name: /Traducción/ }));
      await emit("block_stream", { file_index: 0, text: BLOCKS_OUT });
      await emit("block_stream", { file_index: 1, text: "═══ Bloque 1/1 ═══\n1: otro" });
      await click(screen.getByTitle("Ver el stream del modelo para todos los archivos"));
   });

   it("lista los archivos y muestra los bloques del primero", () => {
      const modal = modalOf("Stream — todos los archivos");
      expect(within(modal).getByRole("button", { name: "a.srt" })).toBeTruthy();
      expect(within(modal).getByRole("button", { name: "b.srt" })).toBeTruthy();
      expect(within(modal).getByText("1: hola")).toBeTruthy();
   });

   it("elegir otro archivo muestra sus bloques", async () => {
      const modal = modalOf("Stream — todos los archivos");
      await click(within(modal).getByRole("button", { name: "b.srt" }));
      expect(within(modal).getByText("1: otro")).toBeTruthy();
   });

   it("cambiar de pestaña Input/Output vuelve al primer archivo y primer bloque", async () => {
      const modal = modalOf("Stream — todos los archivos");
      await click(within(modal).getByRole("button", { name: "b.srt" }));
      await click(within(modal).getByRole("button", { name: "Input" }));
      expect(within(modal).getByText("Este archivo no tiene bloques.")).toBeTruthy();
      await click(within(modal).getByRole("button", { name: "Output" }));
      expect(within(modal).getByText("1: hola")).toBeTruthy();
   });
});

describe("modal de prompt completo", () => {
   const SECTIONS = { base_prompt: "BASE", glossary: "GLOS", work_info: "WI", title: "TIT" };

   beforeEach(async () => {
      await emit("system_prompt", { text: "FULL", sections: SECTIONS });
      await click(screen.getByRole("button", { name: "Prompt" }));
   });

   it("abre en Instrucciones con el título del archivo y el bloque", () => {
      expect(screen.getByRole("heading", { name: /Prompt completo — a\.srt · Bloque 1/ })).toBeTruthy();
      expect(modalOf(/Prompt completo/).textContent).toContain("BASE");
   });

   it("cada pestaña muestra su sección", async () => {
      const H = /Prompt completo/;
      await click(modalButton(H, "Glossary"));
      expect(modalOf(H).textContent).toContain("GLOS");
      await click(modalButton(H, "Work info"));
      expect(modalOf(H).textContent).toContain("WI");
      await click(modalButton(H, "Título"));
      expect(modalOf(H).textContent).toContain("TIT");
   });

   it("una sección vacía muestra su aviso", async () => {
      cleanup();
      mount();
      await emit("system_prompt", { text: "F", sections: { base_prompt: "", glossary: "", work_info: "", title: "" } });
      await click(screen.getByRole("button", { name: "Prompt" }));
      expect(modalOf(/Prompt completo/).textContent).toContain("(No hay instrucciones)");
      await click(modalButton(/Prompt completo/, "Glossary"));
      expect(modalOf(/Prompt completo/).textContent).toContain("(No hay glossary)");
   });

   it("Ver raw muestra el prompt completo; Ver formateado vuelve", async () => {
      const H = /Prompt completo/;
      await click(modalButton(H, "Ver raw"));
      expect(modalOf(H).textContent).toContain("FULL");
      expect(modalButton(H, "Ver formateado")).toBeTruthy();
   });

   it("(comportamiento actual) la vista raw escribe \\n\\n como texto literal", async () => {
      const H = /Prompt completo/;
      await click(modalButton(H, "Ver raw"));
      expect(modalOf(H).textContent).toContain("FULL\\n\\n");
   });

   it("(comportamiento actual) Contexto y Bloque leen del log de la pestaña de stream, que arranca en Output", async () => {
      await emit("block_input", { file_index: 0, text: BLOCKS_IN });
      await emit("block_stream", { file_index: 0, text: BLOCKS_OUT });
      const H = /Prompt completo/;
      await click(modalButton(H, "Contexto"));
      expect(modalOf(H).textContent).toContain("(No hay contexto)");
      await click(modalButton(H, "Bloque"));
      expect(modalOf(H).textContent).toContain("═══ Bloque 1/2 ═══");
   });

   it("(comportamiento actual) tras elegir Input en un modal de stream, Contexto y Bloque leen el input", async () => {
      await emit("block_input", { file_index: 0, text: BLOCKS_IN });
      await click(modalButton(/Prompt completo/, "✕"));
      await click(screen.getByRole("button", { name: /Traducción/ }));
      await click(screen.getByText("a.srt"));
      await click(within(modalOf("Stream — a.srt")).getByRole("button", { name: "Input" }));
      await click(within(modalOf("Stream — a.srt")).getByRole("button", { name: "✕" }));
      await click(screen.getByRole("button", { name: "Prompt" }));
      const H = /Prompt completo/;
      await click(modalButton(H, "Contexto"));
      expect(modalOf(H).textContent).toContain("CTX-IN");
      await click(modalButton(H, "Bloque"));
      expect(modalOf(H).textContent).toContain("BLK-IN");
   });

   it("Copiar todo copia el prompt del sistema más el mensaje del usuario", async () => {
      const writeText = vi.fn().mockResolvedValue();
      Object.assign(navigator, { clipboard: { writeText } });
      await click(modalButton(/Prompt completo/, "Copiar todo"));
      expect(writeText).toHaveBeenCalledWith("FULL\n\n");
   });
});
