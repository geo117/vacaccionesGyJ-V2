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
