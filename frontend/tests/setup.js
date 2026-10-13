// jsdom implementa el elemento <dialog> pero no show()/showModal()/close().
// Se simulan lo justo para poder probar los modales. Lo que NO se puede verificar aquí
// (foco atrapado, Escape real, capa superior) lo aporta el navegador de verdad.
if (typeof HTMLDialogElement !== "undefined" && !HTMLDialogElement.prototype.showModal) {
   HTMLDialogElement.prototype.show = function show() {
      this.setAttribute("open", "");
   };
   HTMLDialogElement.prototype.showModal = function showModal() {
      this.setAttribute("open", "");
      this.setAttribute("data-modal", "true");
   };
   HTMLDialogElement.prototype.close = function close() {
      if (!this.hasAttribute("open")) return;
      this.removeAttribute("open");
      this.removeAttribute("data-modal");
      this.dispatchEvent(new Event("close"));
   };
}
