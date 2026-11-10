/**
 * Plazo de las vacaciones colectivas.
 *
 * La fecha límite es el **1 de diciembre de 2026**. El aviso de Resumen se
 * muestra desde seis días antes y el backend aplica el corte de cuentas cuando
 * ya pasó ese día. Este módulo es puro para poder probarlo con Node.
 */

export const FECHA_LIMITE = '2026-12-01'
export const DIAS_AVISO = 6

const MS_POR_DIA = 86_400_000

/** Medianoche UTC del día local: evita que el cambio de horario mueva la cuenta. */
function aUtcMedianoche(fecha) {
  return Date.UTC(fecha.getFullYear(), fecha.getMonth(), fecha.getDate())
}

/** Días de calendario hasta la fecha límite; negativo si ya pasó. */
export function diasHastaLimite(hoy = new Date()) {
  const [anio, mes, dia] = FECHA_LIMITE.split('-').map(Number)
  return Math.round((Date.UTC(anio, mes - 1, dia) - aUtcMedianoche(hoy)) / MS_POR_DIA)
}

/** La ventana de aviso va del 25 de noviembre al 1 de diciembre de 2026. */
export function debeMostrarAviso(hoy = new Date()) {
  const dias = diasHastaLimite(hoy)
  return dias >= 0 && dias <= DIAS_AVISO
}

/** Desde el 2 de diciembre de 2026 ya se aplica el corte de cuentas. */
export function debeDesactivarUsuarios(hoy = new Date()) {
  return diasHastaLimite(hoy) < 0
}

/** Texto de la cuenta regresiva que acompaña al aviso. */
export function textoCuentaRegresiva(dias) {
  if (dias <= 0) return 'Vence hoy'
  if (dias === 1) return 'Queda 1 día'
  return `Quedan ${dias} días`
}
