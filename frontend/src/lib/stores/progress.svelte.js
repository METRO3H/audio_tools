/**
 * progress.svelte.js
 * ───────────────────
 * Estado global de progreso para cualquier operación en curso.
 *
 * Escucha los CustomEvents que api.py emite via evaluate_js():
 *   audiotools:progress  { value: float 0..1 }
 *   audiotools:log       { message: string }
 *   audiotools:file      { index: int, done: bool }
 *   audiotools:done      { success: bool }
 *
 * Uso:
 *   import { progress } from '$lib/stores/progress.svelte.js'
 *
 *   progress.value      // 0..1
 *   progress.running    // bool
 *   progress.logs       // string[]
 *   progress.success    // bool | null (null = en curso)
 *   progress.files      // { index: int, done: bool }[]
 *   progress.reset()    // limpia para una nueva operación
 */

// ── Estado ─────────────────────────────────────────────────────────────────────

export const progress = $state({
  value:   0,
  running: false,
  logs:    /** @type {string[]} */ ([]),
  success: /** @type {boolean | null} */ (null),
  files:   /** @type {{ index: number, done: boolean }[]} */ ([]),

  /** Prepara el store para una nueva operación. */
  reset() {
    this.value   = 0
    this.running = true
    this.logs    = []
    this.success = null
    this.files   = []
  },
})

// ── Listeners ──────────────────────────────────────────────────────────────────

if (typeof window !== 'undefined') {

  window.addEventListener('audiotools:progress', (/** @type {CustomEvent} */ e) => {
    progress.value = e.detail.value
  })

  window.addEventListener('audiotools:log', (/** @type {CustomEvent} */ e) => {
    progress.logs = [...progress.logs, e.detail.message]
  })

  window.addEventListener('audiotools:file', (/** @type {CustomEvent} */ e) => {
    const { index, done } = e.detail
    const updated = [...progress.files]
    updated[index] = { index, done }
    progress.files = updated
  })

  window.addEventListener('audiotools:done', (/** @type {CustomEvent} */ e) => {
    progress.running = false
    progress.success = e.detail.success
    progress.value   = e.detail.success ? 1 : progress.value
  })
}