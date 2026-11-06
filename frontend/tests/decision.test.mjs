/**
 * Comprobación del modal de decisión.
 *
 * Se verifica sobre el archivo fuente porque las pruebas del proyecto corren
 * con `node --test` sin DOM. Lo que no puede perderse en una edición descuidada:
 * que la tabla de períodos tenga el menú de acciones por fila y que las
 * decisiones viajen al servidor junto con la decisión general.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const MODAL = new URL('../src/components/DecisionModal.jsx', import.meta.url)
const PAGINA = new URL('../src/pages/AsignacionesPage.jsx', import.meta.url)
const CSS = new URL('../src/styles/modal.css', import.meta.url)

test('la tabla de períodos tiene la columna de acciones y las dos decisiones', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes('Períodos de vacaciones'), 'falta la tabla de períodos')
  assert.ok(fuente.includes('periodo-tabla__acciones'), 'falta la columna «Acciones»')
  assert.ok(fuente.includes('Aprobar período'), 'falta la opción de aprobar el período')
  assert.ok(fuente.includes('Rechazar período'), 'falta la opción de rechazar el período')
  assert.ok(fuente.includes('masOpciones'), 'el disparador debe ser el icono de tres puntos')
})

test('la decisión por período se toma de la asignación y viaja al guardar', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes('periodo?.decision'), 'la decisión debe leerse de cada período')
  assert.ok(
    fuente.includes('aprobacionRechazoF${indice + 1}'),
    'también debe aceptar las columnas planas aprobacion_rechazo_f1..f3',
  )
  assert.ok(
    fuente.includes('decisionesPeriodos: decisionesPeriodo'),
    'el payload debe incluir las decisiones por período',
  )
})

test('la página no descarta las decisiones por período al confirmar', async () => {
  const fuente = await readFile(PAGINA, 'utf8')

  assert.ok(
    fuente.includes('decisionesPeriodos') && fuente.includes('registrarDecision(fila.id, {'),
    'la decisión por período debe llegar al hook que llama a la API',
  )
})

test('la columna de acciones tiene el botón de tres puntos centrado', async () => {
  const css = await readFile(CSS, 'utf8')

  assert.ok(css.includes('.periodo-tabla__acciones'), 'falta el estilo de la columna de acciones')
  assert.ok(css.includes('.periodo-tabla__decision'), 'falta el estilo de la celda de decisión')
  assert.ok(
    /\.periodo-tabla__decision\s*\{[^}]*justify-content:\s*center/s.test(css),
    'el botón de acciones debe quedar centrado',
  )
  assert.ok(
    !css.includes('.periodo-tabla__sin-decision'),
    'la etiqueta «Sin decisión» ya no se muestra en la columna de acciones',
  )
})
