/**
 * Comprobación de la ficha del colaborador (modal «ver empleado»).
 *
 * Igual que el resto de pruebas de interfaz del proyecto, se verifica sobre el
 * archivo fuente: no hay DOM en las pruebas y añadir jsdom sólo para esto sería
 * una dependencia nueva. Lo que se comprueba es lo que una edición descuidada
 * podría llevarse por delante: que los dos campos deducidos sigan ahí, que la
 * etiqueta del responsable dependa del estado y que el botón que se quitó no
 * vuelva.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const MODAL = new URL('../src/components/EmpleadoDetalleModal.jsx', import.meta.url)
const CSS = new URL('../src/styles/modal.css', import.meta.url)

test('la ficha cambia «Fecha de registro» por «Aplica licencia»', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes('etiqueta="Aplica licencia"'), 'debe estar el campo «Aplica licencia»')
  assert.ok(
    !fuente.includes('Fecha de registro'),
    '«Fecha de registro» ya no se muestra en la ficha',
  )
  assert.ok(
    !fuente.includes('fechaRegistro'),
    'el modal ya no lee fechaRegistro: ese dato salió de la ficha',
  )
})

test('«Aplica licencia» se deduce del semáforo, no de un valor inventado', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(
    fuente.includes("semaforoDiasAUsar(diasAUsar).tono === 'danger'"),
    'el umbral debe ser el mismo rojo del semáforo (días a usar < −3)',
  )
  assert.ok(fuente.includes("'Licencia no remunerada'"), 'el mensaje del caso en contra')
  assert.ok(fuente.includes("'No aplica'"), 'el mensaje del caso normal')
  assert.ok(
    /return \{ texto: 'No aplica', tono: 'ok' \}/.test(fuente),
    '«No aplica» va en verde: tono ok',
  )
})

test('«Aprobado por» y «Rechazado por» dependen del estado', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes("etiqueta: 'Aprobado por'"), 'falta la etiqueta de aprobación')
  assert.ok(fuente.includes("etiqueta: 'Rechazado por'"), 'falta la etiqueta de rechazo')
  assert.ok(
    fuente.includes("etiqueta: 'Pendiente de aprobación'"),
    'una asignación pendiente no tiene responsable de la decisión todavía',
  )
  assert.ok(
    !fuente.includes('Registrado por'),
    '«Registrado por» ya no se usa en la ficha',
  )
})

test('el botón «Vaciar períodos» se eliminó', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(!fuente.includes('Vaciar períodos'), 'el botón ya no debe existir')
  assert.ok(
    !fuente.includes('onLimpiar'),
    'tampoco su prop: se pasaba sin usarse y no hacía nada',
  )
})

test('«Fecha de ingreso» sale de fecha_reintegro_lab, no de fecha_regreso', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(
    fuente.includes('asignacion.fechaReintegroLab'),
    'la fecha de ingreso debe leerse de fecha_reintegro_lab',
  )
  assert.ok(
    !fuente.includes('asignacion.fechaIngreso'),
    'fecha_regreso (`fechaIngreso` en el JSON) ya no es la fecha de ingreso de la ficha',
  )
})

test('el tono del campo tiene estilo propio', async () => {
  const css = await readFile(CSS, 'utf8')

  assert.ok(css.includes('.ficha__valor--ok'), 'el verde de «No aplica» necesita su clase')
  assert.ok(css.includes('.ficha__valor--danger'), 'el rojo de «Licencia no remunerada» también')
})
