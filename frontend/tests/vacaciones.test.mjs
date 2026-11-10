/**
 * Pruebas del plazo de vacaciones colectivas.
 *
 * Son funciones puras: se construyen fechas locales para que el resultado no
 * dependa de la zona horaria donde corra la prueba.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

import {
  debeDesactivarUsuarios,
  debeMostrarAviso,
  diasHastaLimite,
  textoCuentaRegresiva,
} from '../src/utils/vacaciones_colectivas.js'

const RESUMEN = new URL('../src/pages/ResumenPage.jsx', import.meta.url)

function fecha(anio, mes, dia) {
  return new Date(anio, mes - 1, dia, 12, 0, 0)
}

test('cuenta los días hasta el 1 de diciembre de 2026', () => {
  assert.equal(diasHastaLimite(fecha(2026, 11, 24)), 7)
  assert.equal(diasHastaLimite(fecha(2026, 11, 25)), 6)
  assert.equal(diasHastaLimite(fecha(2026, 11, 30)), 1)
  assert.equal(diasHastaLimite(fecha(2026, 12, 1)), 0)
  assert.equal(diasHastaLimite(fecha(2026, 12, 2)), -1)
})

test('el aviso se muestra desde 6 días antes y hasta el día límite', () => {
  assert.equal(debeMostrarAviso(fecha(2026, 11, 24)), false)
  assert.equal(debeMostrarAviso(fecha(2026, 11, 25)), true)
  assert.equal(debeMostrarAviso(fecha(2026, 11, 30)), true)
  assert.equal(debeMostrarAviso(fecha(2026, 12, 1)), true)
  assert.equal(debeMostrarAviso(fecha(2026, 12, 2)), false)
})

test('el corte de cuentas empieza el día siguiente al límite', () => {
  assert.equal(debeDesactivarUsuarios(fecha(2026, 12, 1)), false)
  assert.equal(debeDesactivarUsuarios(fecha(2026, 12, 2)), true)
})

test('el texto de la cuenta regresiva concuerda en singular y plural', () => {
  assert.equal(textoCuentaRegresiva(6), 'Quedan 6 días')
  assert.equal(textoCuentaRegresiva(1), 'Queda 1 día')
  assert.equal(textoCuentaRegresiva(0), 'Vence hoy')
})

test('el resumen muestra el aviso con SweetAlert2 y la cuenta regresiva', async () => {
  const fuente = await readFile(RESUMEN, 'utf8')

  assert.ok(fuente.includes('Swal.fire('), 'el aviso debe usar SweetAlert2')
  assert.ok(fuente.includes('debeMostrarAviso()'), 'debe respetar la ventana de 6 días')
  assert.ok(
    fuente.includes('textoCuentaRegresiva(dias)'),
    'el aviso debe incluir el contador de días',
  )
  assert.ok(
    fuente.includes('1 de diciembre de 2026'),
    'el texto debe indicar la fecha límite',
  )
})
