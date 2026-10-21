/**
 * Comprobación del modal de edición de períodos («Asignar fechas»).
 *
 * Igual que las demás pruebas de interfaz del proyecto, se verifica sobre el
 * archivo fuente: no hay DOM en las pruebas y añadir jsdom sólo para esto sería
 * una dependencia nueva. Lo que se comprueba es lo que una edición descuidada
 * podría romper: de qué columna sale la fecha de ingreso y qué se envía al
 * guardar.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const MODAL = new URL('../src/components/AsignarPeriodosModal.jsx', import.meta.url)

test('la «Fecha de ingreso» se precarga desde fecha_reintegro_lab', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(
    fuente.includes('asignacion?.fechaReintegroLab'),
    'la fecha de ingreso debe venir de la columna fecha_reintegro_lab',
  )
  assert.ok(
    !fuente.includes('asignacion?.fechaIngreso'),
    'no debe precargarse con fecha_regreso (`fechaIngreso` en el JSON)',
  )
})

test('al guardar se manda fechaReintegroLab y la fecha de regreso calculada', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(
    fuente.includes('fechaReintegroLab: fechaIngreso'),
    'el campo de la pantalla se persiste en fecha_reintegro_lab',
  )
  assert.ok(
    fuente.includes('fechaIngreso: ingreso'),
    'fecha_regreso sigue siendo el día siguiente al último período',
  )
})

test('el recuadro «Total asignado» muestra el día de reintegro a labores', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes('Reintegro a labores:'), 'debe estar el mensaje del reintegro')
  assert.ok(
    fuente.includes("formatIsoDate(fechaIngreso, 'long')"),
    'la fecha se muestra larga («9 de noviembre de 2026»)',
  )
})
