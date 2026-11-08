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

test('la decisión por período se lee de la asignación y se guarda de inmediato', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes('periodo?.decision'), 'la decisión debe leerse de cada período')
  assert.ok(
    fuente.includes('aprobacionRechazoF${indice + 1}'),
    'también debe aceptar las columnas planas aprobacion_rechazo_f1..f3',
  )
  assert.ok(
    fuente.includes('onDecisionPeriodo(indice, valor)'),
    'cada clic de período debe llamar al guardado inmediato',
  )
  assert.ok(
    fuente.includes('decisionesPeriodos: decisionesPeriodo'),
    'la decisión general conserva el contexto de los períodos',
  )
})

test('la página guarda cada período sin esperar la confirmación general', async () => {
  const fuente = await readFile(PAGINA, 'utf8')

  assert.ok(
    fuente.includes('registrarDecisionPeriodo(fila.id, indice + 1, decision)'),
    'el clic del período debe llegar al hook que llama a la API',
  )
  assert.ok(
    fuente.includes('onDecisionPeriodo={handleDecisionPeriodo}'),
    'el modal debe recibir el manejador de la decisión por período',
  )
  assert.ok(
    fuente.includes('decisionesPeriodos') && fuente.includes('registrarDecision(fila.id, {'),
    'la decisión general sigue llegando al hook que llama a la API',
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

test('el modal ofrece «Rechazar todo» a la izquierda del botón principal', async () => {
  const fuente = await readFile(MODAL, 'utf8')
  const pie = fuente.slice(fuente.indexOf('<Modal.Footer>'))

  assert.ok(pie.includes('activarRechazoTotal'), 'falta el manejador del rechazo total')
  assert.ok(pie.includes('Rechazar todo'), 'falta el botón «Rechazar todo»')
  assert.ok(
    pie.indexOf('Rechazar todo') < pie.indexOf('{etiquetaPrincipal}'),
    '«Rechazar todo» debe ir antes del botón principal (a su izquierda)',
  )
  assert.ok(
    fuente.includes("asignacion?.estado === 'rechazada'"),
    'una asignación ya rechazada debe abrir el modo de rechazo total',
  )
})

test('cada rechazo por período abre su recuadro de motivos', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes('Rechazos seleccionados:'), 'falta el contador de rechazos')
  assert.ok(fuente.includes('Motivos de los rechazos'), 'falta el recuadro de motivos')
  assert.ok(fuente.includes('motivo-periodo-'), 'falta el campo de motivo por período')
  assert.ok(
    fuente.includes('concatenarMotivos(motivosPeriodo, indicesRechazados)'),
    'los motivos deben concatenarse antes de enviarse',
  )
  assert.ok(
    fuente.includes("Período ${indice + 1}: ${texto}") && fuente.includes("join(' | ')"),
    'con varios rechazos, cada motivo debe indicar su período y unirse en un solo texto',
  )
  assert.ok(
    fuente.includes('guardarMotivos: true'),
    'guardar los motivos no debe confundirse con rechazar todos los períodos',
  )
})

test('cuando todo está rechazado el modal ofrece aprobar todo', async () => {
  const fuente = await readFile(MODAL, 'utf8')

  assert.ok(fuente.includes('const todasRechazadas'), 'falta detectar el rechazo total')
  assert.ok(
    fuente.includes('indicesRechazados.length === resumen.periodosProgramados'),
    'el estado debe comparar todos los períodos programados',
  )
  assert.ok(fuente.includes('async function aprobarTodo'), 'falta la acción de aprobar todo')
  assert.ok(fuente.includes('Aprobar todo'), 'falta el botón «Aprobar todo»')
  assert.ok(fuente.includes('{todasRechazadas ? ('), 'el botón debe aparecer sólo en rechazo total')
  assert.ok(
    /async function aprobarTodo[\s\S]*?onConfirmar\(\{ decision: 'aprobada', motivo: '', observaciones \}\)/.test(
      fuente,
    ),
    'aprobar todo debe enviar la decisión uniforme de aprobación',
  )
})

test('el recuadro de rechazos tiene estilo propio', async () => {
  const css = await readFile(CSS, 'utf8')

  assert.ok(css.includes('.rechazos'), 'falta el estilo del recuadro de rechazos')
  assert.ok(css.includes('.rechazos__cabecera'), 'falta la cabecera con el contador')
  assert.ok(css.includes('.rechazos__nota'), 'falta la nota de concatenación')
})

