/**
 * Utilidades de fecha y número para las vistas de asignaciones.
 *
 * Todo el cálculo de días se hace en UTC a propósito: si se sumaran milisegundos
 * entre dos fechas locales, el cambio de horario de verano introduciría o
 * quitaría un día en algunos países. Aquí las fechas son días de calendario, no
 * instantes, así que se cuentan como tales.
 */

const FECHA_CORTA = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' })
const FECHA_LARGA = new Intl.DateTimeFormat('es-CO', { dateStyle: 'long' })
const NUMERO = new Intl.NumberFormat('es-CO')
const MS_POR_DIA = 86_400_000

export { FECHA_CORTA, FECHA_LARGA, NUMERO }

/** Normaliza un `<input type="date">` (`aaaa-mm-dd`) a fecha UTC. */
export function parseIsoDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null // Fecha imposible como 2026-02-31.
  }
  return date
}

/** Fecha UTC → `aaaa-mm-dd`, el formato que entiende el input. */
export function toIsoDate(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return ''
  return date.toISOString().slice(0, 10)
}

/**
 * Días calendario entre dos fechas, contando ambos extremos.
 *
 * Es la convención de una asignación de vacaciones: del 1 al 5 de marzo son
 * 5 días, no 4.
 */
export function daysInclusive(startIso, endIso) {
  const start = parseIsoDate(startIso)
  const end = parseIsoDate(endIso)
  if (!start || !end) return null
  const diff = Math.round((end.getTime() - start.getTime()) / MS_POR_DIA)
  if (diff < 0) return null // Fin antes del inicio: no es un rango válido.
  return diff + 1
}

/** Suma días de calendario a una fecha ISO. */
export function addDays(startIso, days) {
  const start = parseIsoDate(startIso)
  if (!start) return ''
  return toIsoDate(new Date(start.getTime() + days * MS_POR_DIA))
}

/** Etiqueta legible de una fecha ISO; si no se puede leer, devuelve el original. */
export function formatIsoDate(value, style = 'short') {
  const parsed = parseIsoDate(value)
  if (!parsed) return value ?? ''
  return (style === 'long' ? FECHA_LARGA : FECHA_CORTA).format(parsed)
}

/** Fecha con hora (notificaciones, marcas de tiempo). */
export function formatDateTime(value) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(parsed)
}
