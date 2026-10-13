/**
 * Pruebas de la lógica de períodos de vacaciones y del reporte.
 *
 * Son funciones puras, así que se prueban directamente con Node: no hace falta
 * montar un componente ni abrir un navegador.
 *
 *   cd frontend
 *   node tests/periodos.test.mjs
 *
 * Salen con código 1 si algo falla, para poder encadenarlas en CI.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { addDays, daysInclusive, parseIsoDate, toIsoDate } from '../src/utils/fechas.js'
import { buildAssignmentsCsv, buildReportFilename } from '../src/utils/reporte.js'
import {
  calcularDias,
  resumirPeriodos,
  semaforoDiasAUsar,
  ultimoDiaProgramado,
  validarPeriodos,
} from '../src/utils/periodos.js'

/* -- Días ------------------------------------------------------------------ */

test('cuenta ambos extremos del rango', () => {
  assert.equal(daysInclusive('2026-03-01', '2026-03-01'), 1)
  assert.equal(daysInclusive('2026-03-01', '2026-03-05'), 5)
  assert.equal(daysInclusive('2026-10-01', '2026-10-31'), 31)
})

test('atraviesa meses y años sin perder días', () => {
  assert.equal(daysInclusive('2026-10-28', '2026-11-02'), 6)
  assert.equal(daysInclusive('2026-12-28', '2027-01-04'), 8)
  // Febrero de 2028 es bisiesto: 29 días.
  assert.equal(daysInclusive('2028-02-01', '2028-02-29'), 29)
})

test('rechaza rangos invertidos y fechas imposibles', () => {
  assert.equal(daysInclusive('2026-03-05', '2026-03-01'), null)
  assert.equal(daysInclusive('2026-02-30', '2026-03-01'), null)
  assert.equal(daysInclusive('', '2026-03-01'), null)
  assert.equal(daysInclusive('2026-03-01', null), null)
})

test('suma días para la fecha de ingreso', () => {
  assert.equal(addDays('2026-03-05', 1), '2026-03-06')
  assert.equal(addDays('2026-10-31', 1), '2026-11-01')
  assert.equal(addDays('2026-12-31', 1), '2027-01-01')
})

test('convierte ISO en ambos sentidos', () => {
  assert.equal(toIsoDate(parseIsoDate('2026-07-09')), '2026-07-09')
})

/* -- Resumen de los tres períodos ------------------------------------------ */

const TRES_PERIODOS = [
  { inicio: '2026-11-02', fin: '2026-11-06' },
  { inicio: '2026-11-09', fin: '2026-11-13' },
  { inicio: '2026-11-16', fin: '2026-11-19' },
]

test('suma los días de los tres períodos', () => {
  const resumen = resumirPeriodos(TRES_PERIODOS)
  assert.equal(resumen.totalDias, 14)
  assert.equal(resumen.periodosProgramados, 3)
  assert.deepEqual(resumen.dias, [5, 5, 4])
})

test('un período programado no cuenta los vacíos', () => {
  const resumen = resumirPeriodos([
    { inicio: '2026-10-20', fin: '2026-10-24' },
    { inicio: null, fin: null },
    { inicio: null, fin: null },
  ])
  assert.equal(resumen.totalDias, 5)
  assert.equal(resumen.periodosProgramados, 1)
})

test('sin períodos el total es 0, no null', () => {
  assert.equal(resumirPeriodos([]).totalDias, 0)
})

test('un período a medias es "sin calcular", no 0 días', () => {
  // Distinguir "no programado" de "cero días" evita un total creíble pero falso.
  assert.equal(calcularDias({ inicio: '2026-11-02', fin: null }), null)
  assert.equal(calcularDias({ inicio: null, fin: '2026-11-02' }), null)
})

test('el último día programado ignora los períodos vacíos', () => {
  assert.equal(ultimoDiaProgramado(TRES_PERIODOS), '2026-11-19')
  assert.equal(ultimoDiaProgramado([]), '')
})

/* -- Validación ------------------------------------------------------------ */

test('tres períodos correctos no producen errores', () => {
  assert.deepEqual(validarPeriodos(TRES_PERIODOS), {})
})

test('detecta la fecha de fin anterior al inicio', () => {
  const errores = validarPeriodos([{ inicio: '2026-11-10', fin: '2026-11-01' }])
  assert.ok(errores.periodo1)
})

test('detecta períodos que se cruzan y cada uno nombra a su contraparte', () => {
  const errores = validarPeriodos([
    { inicio: '2026-11-02', fin: '2026-11-06' },
    { inicio: '2026-11-05', fin: '2026-11-10' },
  ])
  // El período 2 debe decir "con el 1" y el 1 "con el 2": nunca consigo mismo.
  assert.equal(errores.periodo1, 'Se cruza con el período 2.')
  assert.equal(errores.periodo2, 'Se cruza con el período 1.')
})

test('un período que choca con dos nombra a ambos', () => {
  const errores = validarPeriodos([
    { inicio: '2026-11-02', fin: '2026-11-10' },
    { inicio: '2026-11-03', fin: '2026-11-04' },
    { inicio: '2026-11-08', fin: '2026-11-12' },
  ])
  assert.equal(errores.periodo1, 'Se cruza con los períodos 2 y 3.')
  assert.equal(errores.periodo2, 'Se cruza con el período 1.')
  assert.equal(errores.periodo3, 'Se cruza con el período 1.')
})

test('períodos contiguos no se consideran cruzados', () => {
  // Uno termina el 6 y el otro empieza el 7: son consecutivos, no solapados.
  assert.deepEqual(
    validarPeriodos([
      { inicio: '2026-11-02', fin: '2026-11-06' },
      { inicio: '2026-11-07', fin: '2026-11-10' },
    ]),
    {},
  )
})

test('un período sin fechas es válido; uno a medias no', () => {
  assert.deepEqual(validarPeriodos([{ inicio: '', fin: '' }]), {})
  assert.ok(validarPeriodos([{ inicio: '2026-11-02', fin: '' }]).periodo1)
  assert.ok(validarPeriodos([{ inicio: '', fin: '2026-11-02' }]).periodo1)
})

/* -- Semáforo de días a usar -----------------------------------------------
   El valor es «días a corte − días asignados»: positivo si le quedan días por
   disfrutar, negativo si programó más de los que tiene.                        */

test('un valor muy negativo significa que programó más días de los que tiene', () => {
  assert.equal(semaforoDiasAUsar(-17).tono, 'danger')
  assert.equal(semaforoDiasAUsar(-3.1).tono, 'danger')
  assert.equal(semaforoDiasAUsar(-17).etiqueta, 'Más días de los que tiene')
})

test('exactamente −3 ya no es rojo, es amarillo', () => {
  // El umbral es exclusivo hacia el rojo: −3 queda en amarillo.
  assert.equal(semaforoDiasAUsar(-3).tono, 'warn')
  assert.equal(semaforoDiasAUsar(0).tono, 'warn')
  assert.equal(semaforoDiasAUsar(0).etiqueta, 'Ajustado')
})

test('exactamente 10 sigue siendo amarillo', () => {
  assert.equal(semaforoDiasAUsar(10).tono, 'warn')
})

test('más de 10 es verde: le quedan días', () => {
  assert.equal(semaforoDiasAUsar(10.1).tono, 'ok')
  assert.equal(semaforoDiasAUsar(25).tono, 'ok')
  assert.equal(semaforoDiasAUsar(25).etiqueta, 'Le quedan días')
})

test('un valor no numérico no se colorea como bueno', () => {
  assert.equal(semaforoDiasAUsar(null).tono, 'neutral')
  assert.equal(semaforoDiasAUsar(undefined).tono, 'neutral')
  assert.equal(semaforoDiasAUsar('x').tono, 'neutral')
})

test('el signo acompaña el orden «corte − asignados»', () => {
  // 7,2 días a corte y ninguna fecha programada: le quedan 7,2 por disfrutar,
  // que es amarillo (ajustado), no rojo.
  const sinFechas = 7.2 - 0
  assert.equal(semaforoDiasAUsar(sinFechas).tono, 'warn')
  // 5 a corte y 20 programados: programó 15 días de más, rojo.
  const excedido = 5 - 20
  assert.equal(semaforoDiasAUsar(excedido).tono, 'danger')
  // 30 a corte y 5 programados: le quedan 25, verde.
  assert.equal(semaforoDiasAUsar(30 - 5).tono, 'ok')
})

/* -- Reporte --------------------------------------------------------------- */

const FILA = {
  id: 'ACT-3041',
  empleado: 'Ana María Restrepo',
  identificacion: '10245871',
  unes: 'UNES 120',
  cargo: 'Auxiliar administrativo',
  estado: 'aprobada',
  periodos: [{ inicio: '2026-10-20', fin: '2026-10-24' }, { inicio: null, fin: null }, { inicio: null, fin: null }],
  totalDias: 5,
  fechaIngreso: '2026-10-25',
  observaciones: 'Nota con "comillas" y ; punto y coma',
  motivoRechazo: null,
}

test('el CSV lleva BOM para que Excel no rompa las tildes', () => {
  assert.equal(buildAssignmentsCsv([FILA]).charCodeAt(0), 0xfeff)
})

test('el CSV tiene encabezado y una fila por asignación', () => {
  const lineas = buildAssignmentsCsv([FILA, { ...FILA, id: 'ACT-3042' }]).trim().split('\r\n')
  assert.equal(lineas.length, 3)
})

test('escapa comillas y comas según RFC 4180', () => {
  assert.ok(buildAssignmentsCsv([FILA]).includes('""comillas""'))
  assert.ok(buildAssignmentsCsv([{ ...FILA, empleado: 'Pérez, Juan' }]).includes('"Pérez, Juan"'))
})

test('neutraliza fórmulas para evitar ejecución al abrir el archivo', () => {
  const csv = buildAssignmentsCsv([{ ...FILA, empleado: "=cmd|'/c calc'!A1" }])
  assert.ok(csv.includes("\"'=cmd"), 'el valor debe quedar prefijado con apóstrofo')
})

test('el nombre del archivo incluye la fecha del día', () => {
  assert.match(buildReportFilename(), /^asignaciones-vacaciones-\d{4}-\d{2}-\d{2}\.csv$/)
})
