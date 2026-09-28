/**
 * bridge.svelte.js
 * ─────────────────
 * Wrapper reactivo sobre window.pywebview.api.
 *
 * Problema: pywebview inyecta window.pywebview de forma asíncrona.
 * Solución: esperamos el evento 'pywebviewready' antes de marcar
 *           el bridge como listo, y exponemos un $state reactivo
 *           que los componentes pueden observar.
 *
 * Uso:
 *   import { bridge, bridgeReady } from '$lib/stores/bridge.svelte.js'
 *
 *   if (bridgeReady.value) {
 *     const files = await bridge.pick_files(['*.mp3'])
 *   }
 */

// ── Estado ─────────────────────────────────────────────────────────────────────

export const bridgeReady = $state({ value: false })

/** @type {Window['pywebview']['api'] | null} */
let _api = null

// ── Inicialización ─────────────────────────────────────────────────────────────

if (typeof window !== 'undefined') {
  window.addEventListener('pywebviewready', () => {
    _api = window.pywebview.api
    bridgeReady.value = true
  })
}

// ── Proxy seguro ───────────────────────────────────────────────────────────────

/**
 * Proxy que lanza un error claro si se llama antes de que
 * pywebview esté listo, en lugar de fallar silenciosamente.
 */
export const bridge = new Proxy(
  {},
  {
    get(_, method) {
      return (...args) => {
        if (!_api) {
          throw new Error(
            `[bridge] pywebview no está listo. ` +
            `Espera a que bridgeReady.value sea true antes de llamar a "${String(method)}".`
          )
        }
        return _api[method](...args)
      }
    },
  }
)