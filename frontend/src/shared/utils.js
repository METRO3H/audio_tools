/**
 * utils.js
 * ─────────
 * Funciones utilitarias compartidas entre vistas.
 */

export function basename(path) {
  return path?.split(/[\\/]/).pop() ?? ''
}

export function folderName(path) {
  return path?.split(/[\\/]/).pop() ?? ''
}

export function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function formatElapsed(seconds) {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}
