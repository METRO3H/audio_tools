import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { vi, describe, it, expect, afterEach } from "vitest";
import PromptEditorModal from "@shared/components/PromptEditorModal.svelte";

afterEach(() => cleanup());

function mount(props = {}) {
   return render(PromptEditorModal, {
      props: {
         title: "Prompt",
         languages: ["japanese", "chinese"],
         selectedLanguage: "japanese",
         onSelectLanguage: vi.fn(),
         value: "contenido",
         dirty: false,
         onInput: vi.fn(),
         onSave: vi.fn(),
         onClose: vi.fn(),
         ...props,
      },
   });
}

it("muestra el título y el contenido", () => {
   mount();
   expect(screen.getByText("Prompt")).toBeTruthy();
   expect(screen.getByDisplayValue("contenido")).toBeTruthy();
});

it('sin dirty no muestra "· sin guardar"', () => {
   mount({ dirty: false });
   expect(screen.queryByText(/sin guardar/)).toBeNull();
});

it('con dirty muestra "· sin guardar"', () => {
   mount({ dirty: true });
   expect(screen.getByText(/sin guardar/)).toBeTruthy();
});

it("muestra description solo si se pasa", () => {
   mount({ description: "" });
   expect(screen.queryByText(/compartidos entre/)).toBeNull();
   cleanup();
   mount({ description: "Términos fijos compartidos entre tools." });
   expect(screen.getByText("Términos fijos compartidos entre tools.")).toBeTruthy();
});

it("lista los idiomas en el combo, capitalizados", () => {
   mount({ languages: ["japanese", "chinese"] });
   const select = screen.getByRole("combobox");
   const options = [...select.querySelectorAll("option")].map((o) => o.textContent);
   expect(options).toEqual(["Japanese", "Chinese"]);
});

it("onSelectLanguage se llama con el idioma elegido", async () => {
   const onSelectLanguage = vi.fn();
   mount({ onSelectLanguage });
   await fireEvent.change(screen.getByRole("combobox"), { target: { value: "chinese" } });
   expect(onSelectLanguage).toHaveBeenCalledWith("chinese");
});

it("onInput se llama al escribir en el textarea", async () => {
   const onInput = vi.fn();
   mount({ onInput });
   await fireEvent.input(screen.getByDisplayValue("contenido"), { target: { value: "nuevo texto" } });
   expect(onInput).toHaveBeenCalled();
});

it("onSave se llama al tocar guardar", async () => {
   const onSave = vi.fn();
   mount({ onSave });
   await fireEvent.click(screen.getByTitle("Guardar"));
   expect(onSave).toHaveBeenCalled();
});

it("onClose se llama al tocar la cruz", async () => {
   const onClose = vi.fn();
   mount({ onClose });
   await fireEvent.click(screen.getByText("✕"));
   expect(onClose).toHaveBeenCalled();
});
