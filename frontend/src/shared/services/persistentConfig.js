/**
 * Almacenamiento persistente en localStorage para configuraciones de usuario.
 * Cada clave guarda un objeto JSON.
 */
export const persistentConfig = {
  get(key, defaultValue = null) {
    try {
      const raw = localStorage.getItem(key)
      if (!raw) return defaultValue
      return JSON.parse(raw)
    } catch {
      return defaultValue
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // ignore
    }
  }
}
