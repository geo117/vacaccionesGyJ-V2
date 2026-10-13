/**
 * Generación y descarga del reporte de asignaciones.
 *
 * Por qué CSV y no un PDF generado en el cliente:
 *  - Lo abre cualquier persona en Excel, que es donde Talento Humano sigue
 *    trabajando, y no añade una dependencia de cientos de kB al bundle.
 *  - No hay plantilla binaria que se desincronice de la tabla.
 *
 * Dos detalles que sí importan:
 *  - Se añade BOM UTF-8 para que Excel en Windows no rompa las tildes ni la ñ.
 *  - Se neutralizan las fórmulas. Un campo que empiece por `=`, `+`, `-` o `@`
 *    lo interpreta Excel como fórmula: un nombre con `=cmd|...` es una vía de
 *    ejecución al abrir el archivo (CSV injection). Se prefija con apóstrofo.
 */

import { formatIsoDate } from './fechas.js'

const BOM = '\uFEFF'
const RIESGO_FORMULA = /^[=+\-@\t\r]/

/** Escapa un valor para CSV y neutraliza fórmulas. */
function celda(value) {
  const texto = value === null || value === undefined ? '' : String(value)
  const seguro = RIESGO_FORMULA.test(texto) ? `'${texto}` : texto
  // Comillas dobles dentro del campo se duplican, según RFC 4180.
  return `"${seguro.replace(/"/g, '""')}"`
}

function fila(valores) {
  return valores.map(celda).join(',')
}

/**
 * Encabezados del reporte. Es una función y no una constante para que el orden
 * de las columnas viva junto a la función que las rellena: si se añade una
 * columna, ambas cambian en el mismo lugar.
 */
function columnas() {
  return [
    'Radicado',
    'Desc. Unes',
    'Colaborador',
    'Identificación',
    'UNES',
    'Cargo',
    'Estado',
    'Días a corte',
    'Días asignados',
    'Días a usar',
    'Período 1 desde',
    'Período 1 hasta',
    'Días P1',
    'Período 2 desde',
    'Período 2 hasta',
    'Días P2',
    'Período 3 desde',
    'Período 3 hasta',
    'Días P3',
    'Total de días',
    'Fecha de ingreso',
    'Observaciones',
    'Motivo de rechazo',
  ]
}

/** Un decimal, para que el CSV y la pantalla muestren el mismo número. */
function unDecimal(valor) {
  const numero = Number(valor)
  return Number.isFinite(numero) ? numero.toFixed(1) : ''
}

function filaDeAsignacion(row) {
  const periodos = row.periodos ?? []
  const dias = periodos.map((p) => p.dias ?? '')

  return [
    // Sin asignación todavía, el radicado va vacío: no existe.
    row.id ?? '',
    row.descUnes ?? '',
    row.empleado,
    row.identificacion,
    row.unes,
    row.cargo,
    row.estado,
    unDecimal(row.diasACorte ?? 0),
    unDecimal(row.diasAsignados ?? row.totalDias ?? 0),
    unDecimal(row.diasAUsar ?? 0),
    formatIsoDate(periodos[0]?.inicio),
    formatIsoDate(periodos[0]?.fin),
    dias[0],
    formatIsoDate(periodos[1]?.inicio),
    formatIsoDate(periodos[1]?.fin),
    dias[1],
    formatIsoDate(periodos[2]?.inicio),
    formatIsoDate(periodos[2]?.fin),
    dias[2],
    unDecimal(row.totalDias ?? 0),
    formatIsoDate(row.fechaIngreso),
    row.observaciones ?? '',
    row.motivoRechazo ?? '',
  ]
}

/**
 * Construye el CSV de las asignaciones recibidas.
 *
 * @param {Array} asignaciones filas ya filtradas: el reporte refleja lo que la
 *   persona está viendo, no todo el conjunto.
 */
export function buildAssignmentsCsv(asignaciones) {
  const lineas = [
    fila(columnas()),
    ...asignaciones.map((row) => fila(filaDeAsignacion(row))),
  ]
  return BOM + lineas.join('\r\n') + '\r\n'
}

/** Nombre de archivo con la fecha del día, sin caracteres problemáticos. */
export function buildReportFilename(extension = 'csv') {
  const hoy = new Date()
  const sello = [
    hoy.getFullYear(),
    String(hoy.getMonth() + 1).padStart(2, '0'),
    String(hoy.getDate()).padStart(2, '0'),
  ].join('-')
  return `asignaciones-vacaciones-${sello}.${extension}`
}

/**
 * Dispara la descarga en el navegador.
 *
 * Se usa un Blob y `URL.revokeObjectURL` para no dejar el archivo retenido en
 * memoria, y se retira el `<a>` del documento después de hacer clic.
 */
export function downloadCsv(filename, contenido) {
  const blob = new Blob([contenido], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = filename
  enlace.rel = 'noopener'
  document.body.appendChild(enlace)
  enlace.click()
  document.body.removeChild(enlace)
  // Se libera en el siguiente ciclo: revocar antes puede cancelar la descarga.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  return { filename, bytes: blob.size }
}
