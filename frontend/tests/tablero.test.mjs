/**
 * Comprobación del HTML de la celda de «Días a usar».
 *
 * Se verifica sobre el archivo fuente y no montando el componente: no hay
 * entorno de DOM en las pruebas del proyecto (corren con `node --test` sin
 * jsdom) y añadir jsdom sólo para esto sería una dependencia nueva. Lo que se
 * comprueba aquí es que la celda lleve el título y la etiqueta accesible, que es
 * lo que no puede perderse en una edición descuidada.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const RUTA = new URL('../src/pages/AsignacionesPage.jsx', import.meta.url)

test('la celda de días a usar lleva la operación en el title', async () => {
  const fuente = await readFile(RUTA, 'utf8')
  // El orden importa y es el que pidió el negocio: días a corte − asignados.
  assert.ok(
    fuente.includes('días a corte −'),
    'el title debe mostrar la operación en el orden «corte − asignados»',
  )
  assert.ok(fuente.includes('className={`dias-usar dias-usar--${tono} tabular`}'))
})

test('la celda de días a usar lleva etiqueta para lectores de pantalla', async () => {
  const fuente = await readFile(RUTA, 'utf8')
  assert.ok(
    fuente.includes('visually-hidden">{etiqueta}'),
    'el color no puede ser la única señal: hace falta la etiqueta',
  )
})

test('las columnas que pidió el negocio están en la tabla', async () => {
  const fuente = await readFile(RUTA, 'utf8')
  // Los encabezados numéricos van cortos ("Corte", "Asignados", "A usar") para
  // que quepan en su columna; el nombre completo va en el `title` y se
  // comprueba aquí para que no se pierda al editar.
  for (const columna of [
    'Desc. Unes',
    'Colaborador',
    'Identificación',
    'UNES',
    'Cargo',
    'Estado',
    'Corte',
    'Asignados',
    'A usar',
  ]) {
    // El JSX parte los encabezados en varias líneas, así que la comparación
    // tiene que tolerar saltos y espacios.
    const patron = new RegExp(`>\\s*${columna.replace('.', '\\.')}\\s*<`)
    assert.ok(patron.test(fuente), `falta la columna ${columna}`)
  }
  for (const completo of ['Días a corte', 'Días asignados', 'Días a usar']) {
    assert.ok(fuente.includes(`title="${completo}"`), `falta el title ${completo}`)
  }
})

test('la tabla lleva el contenedor con desplazamiento propio', async () => {
  const fuente = await readFile(RUTA, 'utf8')
  assert.ok(
    fuente.includes('table-scroll--ajustado'),
    'la tabla debe ir dentro de su contenedor con scroll para no estirar la página',
  )
  assert.ok(fuente.includes('data--tablero'), 'la tabla debe llevar la clase de anchos por columna')
})

test('el botón de motivo va debajo del estado, no al lado', async () => {
  const fuente = await readFile(RUTA, 'utf8')

  // En fila, el chip y el botón juntos (unos 180px) desbordaban la columna
  // «Estado» y se montaban encima del dato de «Corte». Apilados, el ancho que
  // necesita la celda es el del más ancho de los dos.
  const celda = fuente.match(
    /<div className="d-flex flex-column align-items-start gap-2">[\s\S]*?<\/div>/,
  )
  assert.ok(celda, 'el estado y el botón de motivo deben apilarse en columna')
  assert.ok(celda[0].includes('<StatusChip estado={fila.estado} />'), 'falta el chip de estado')
  assert.ok(celda[0].includes('Motivo'), 'falta el botón de motivo dentro del mismo bloque')
  assert.ok(
    celda[0].indexOf('<StatusChip') < celda[0].indexOf('Motivo'),
    'el motivo va después del estado, es decir, debajo',
  )
})

test('la tabla se pagina de a 20 con los controles de react-bootstrap', async () => {
  const fuente = await readFile(RUTA, 'utf8')

  assert.ok(
    fuente.includes("from 'react-bootstrap/Pagination'"),
    'el paginador debe ser el componente Pagination de react-bootstrap',
  )
  assert.ok(fuente.includes('const POR_PAGINA = 20'), 'la página debe ser de 20 registros')
  assert.ok(
    fuente.includes('filtradas.slice('),
    'se pagina sobre lo ya filtrado, no sobre la lista completa',
  )

  // Los cuatro controles que pidió el negocio: ir al comienzo, retroceder,
  // avanzar e ir al final.
  for (const control of ['Pagination.First', 'Pagination.Prev', 'Pagination.Next', 'Pagination.Last']) {
    assert.ok(fuente.includes(`<${control}`), `falta el control ${control}`)
  }

  assert.ok(
    fuente.indexOf('className="tabla-paginador"') > fuente.indexOf('</Table>'),
    'el paginador va debajo de la tabla, no encima',
  )
})
