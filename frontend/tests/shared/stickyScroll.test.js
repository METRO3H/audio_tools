import { describe, it, expect, vi } from "vitest";
import { stickyScroll, STICK_THRESHOLD } from "@shared/ui/stickyScroll.js";

/** Un contenedor con medidas controladas (jsdom no calcula layout). */
function makeBox({ scrollHeight = 1000, clientHeight = 200 } = {}) {
   const node = document.createElement("div");
   let scrollTop = 0;
   Object.defineProperties(node, {
      scrollHeight: { get: () => box.scrollHeight },
      clientHeight: { get: () => box.clientHeight },
      scrollTop: { get: () => scrollTop, set: (v) => (scrollTop = v) },
   });
   const box = { node, scrollHeight, clientHeight };
   return box;
}
const userScrollsTo = (node, top) => {
   node.scrollTop = top;
   node.dispatchEvent(new Event("scroll"));
};

describe("stickyScroll", () => {
   it("al iniciar baja hasta el final", () => {
      const { node } = makeBox();
      stickyScroll(node, 0);
      expect(node.scrollTop).toBe(1000);
   });

   it("sigue el contenido nuevo mientras el usuario está al final", () => {
      const box = makeBox();
      const action = stickyScroll(box.node, 0);
      box.scrollHeight = 1400; // llegaron más líneas
      action.update(1);
      expect(box.node.scrollTop).toBe(1400);
   });

   it("si el usuario sube a leer, deja de moverlo", () => {
      const box = makeBox();
      const action = stickyScroll(box.node, 0);
      userScrollsTo(box.node, 100);
      box.scrollHeight = 1400;
      action.update(1);
      expect(box.node.scrollTop).toBe(100);
   });

   it("cuando el usuario vuelve al final, lo vuelve a seguir", () => {
      const box = makeBox();
      const action = stickyScroll(box.node, 0);
      userScrollsTo(box.node, 100);
      action.update(1);
      expect(box.node.scrollTop).toBe(100);

      userScrollsTo(box.node, 1000 - 200 - 10); // a 10 px del final
      box.scrollHeight = 1300;
      action.update(2);
      expect(box.node.scrollTop).toBe(1300);
   });

   it("el umbral es exacto: a STICK_THRESHOLD px sigue; un píxel más, no", () => {
      const a = makeBox();
      const actionA = stickyScroll(a.node, 0);
      userScrollsTo(a.node, 1000 - 200 - STICK_THRESHOLD);
      a.scrollHeight = 1100;
      actionA.update(1);
      expect(a.node.scrollTop).toBe(1100);

      const b = makeBox();
      const actionB = stickyScroll(b.node, 0);
      userScrollsTo(b.node, 1000 - 200 - STICK_THRESHOLD - 1);
      const before = b.node.scrollTop;
      b.scrollHeight = 1100;
      actionB.update(1);
      expect(b.node.scrollTop).toBe(before);
   });

   it("destroy() quita el listener", () => {
      const { node } = makeBox();
      const remove = vi.spyOn(node, "removeEventListener");
      stickyScroll(node, 0).destroy();
      expect(remove).toHaveBeenCalledWith("scroll", expect.any(Function));
   });
});
