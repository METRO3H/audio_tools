import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import TranslationSettings from "@shared/components/TranslationSettings.svelte";
import { useExecutionTarget } from "@shared/state/useExecutionTarget.svelte.js";

const flush = async () => {
   await tick();
   await Promise.resolve();
   await tick();
};

beforeEach(() => localStorage.clear());
afterEach(() => cleanup());

/** target real (useExecutionTarget), igual que hace ExecutionModeGate.test.js. */
function makeTarget(remoteModels = ["remote-a.gguf", "remote-b.gguf"]) {
   return useExecutionTarget({
      check: vi.fn().mockResolvedValue({ found: true, state: "idle", host: "h", port: 1, models: remoteModels }),
   });
}

function mount(props = {}) {
   const target = props.target ?? makeTarget();
   const result = render(TranslationSettings, {
      props: {
         target,
         models: ["a.gguf", "b.gguf"],
         storageKey: "test_translate",
         noModelsLabel: "Sin modelos",
         ...props,
      },
   });
   return { ...result, target };
}

describe("TranslationSettings: sin modo elegido", () => {
   it("no renderiza nada hasta que target.mode tiene un valor", () => {
      mount({ target: makeTarget() });
      expect(screen.queryByRole("combobox")).toBeNull();
      expect(screen.queryByLabelText("GPU layers")).toBeNull();
   });
});

describe("TranslationSettings: modo local", () => {
   it("sin nada guardado, usa los defaults de local (nGpuLayers 20) y el primer modelo", async () => {
      const target = makeTarget();
      target.selectLocal();
      mount({ target });
      await flush();
      expect(screen.getByLabelText("GPU layers").value).toBe("20");
      expect(screen.getByLabelText("Contexto").value).toBe("4096");
      expect(screen.getByLabelText("Temperatura").value).toBe("0.3");
      expect(screen.getAllByRole("combobox")[0].value).toBe("a.gguf");
   });

   it("editar un campo lo guarda bajo <storageKey>_local_config, sin tocar el de remoto", async () => {
      const target = makeTarget();
      target.selectLocal();
      mount({ target });
      await flush();
      await fireEvent.input(screen.getByLabelText("GPU layers"), { target: { value: "35" } });
      await flush();
      expect(JSON.parse(localStorage.getItem("test_translate_local_config")).nGpuLayers).toBe(35);
      // Los dos persisted() existen desde que el componente monta (ver el porqué en el
      // componente), así que el de remoto también está en localStorage — pero con SUS propios
      // defaults, sin nada del 35 que se escribió en local.
      expect(JSON.parse(localStorage.getItem("test_translate_remote_config")).nGpuLayers).toBe(0);
   });

   it("carga un valor ya guardado en localStorage al montar", async () => {
      localStorage.setItem(
         "test_translate_local_config",
         JSON.stringify({ selectedModel: "b.gguf", nGpuLayers: 12, nCtx: 8192, temperature: 0.7 }),
      );
      const target = makeTarget();
      target.selectLocal();
      mount({ target });
      await flush();
      expect(screen.getByLabelText("GPU layers").value).toBe("12");
      expect(screen.getAllByRole("combobox")[0].value).toBe("b.gguf");
   });

   it("si el modelo guardado ya no está en la lista, cae al primero disponible", async () => {
      localStorage.setItem(
         "test_translate_local_config",
         JSON.stringify({ selectedModel: "ya-no-existe.gguf", nGpuLayers: 20, nCtx: 4096, temperature: 0.3 }),
      );
      const target = makeTarget();
      target.selectLocal();
      mount({ target });
      await flush();
      expect(screen.getAllByRole("combobox")[0].value).toBe("a.gguf");
   });
});

describe("TranslationSettings: modo remoto", () => {
   it("sin nada guardado, usa los defaults de remoto (nGpuLayers 0) y los modelos de target.remote", async () => {
      const target = makeTarget(["remote-a.gguf", "remote-b.gguf"]);
      await target.selectRemote();
      mount({ target, models: target.remote.models });
      await flush();
      expect(screen.getByLabelText("GPU layers").value).toBe("0");
      expect(screen.getAllByRole("combobox")[0].value).toBe("remote-a.gguf");
   });

   it("editar un campo lo guarda bajo <storageKey>_remote_config, sin tocar el de local", async () => {
      const target = makeTarget();
      await target.selectRemote();
      mount({ target, models: target.remote.models });
      await flush();
      await fireEvent.input(screen.getByLabelText("Temperatura"), { target: { value: "1.1" } });
      await flush();
      expect(JSON.parse(localStorage.getItem("test_translate_remote_config")).temperature).toBe(1.1);
      expect(JSON.parse(localStorage.getItem("test_translate_local_config")).temperature).toBe(0.3);
   });

   it("muestra remoteNoModelsHint cuando el mediador no tiene modelos", async () => {
      const target = makeTarget([]);
      await target.selectRemote();
      mount({ target, models: [], remoteNoModelsHint: "sin .gguf en el mediador" });
      await flush();
      expect(screen.getByText("sin .gguf en el mediador")).toBeTruthy();
   });
});

describe("TranslationSettings: local y remoto no se pisan", () => {
   it("un valor puesto en local no aparece al pasar a remoto, y viceversa", async () => {
      const target = makeTarget();
      target.selectLocal();
      const { unmount } = mount({ target });
      await flush();
      await fireEvent.input(screen.getByLabelText("GPU layers"), { target: { value: "99" } });
      await flush();
      unmount();

      target.change();
      await target.selectRemote();
      mount({ target, models: target.remote.models });
      await flush();
      expect(screen.getByLabelText("GPU layers").value).toBe("0"); // default de remoto, no el 99 de local
   });
});
