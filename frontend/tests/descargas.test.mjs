/**
 * Comprobación del nombre de archivo que propone el servidor al descargar.
 *
 * Se verifica sobre la función pura y no montando nada: `node --test` sin jsdom,
 * y lo que importa aquí —que el nombre con tildes de `filename*` no se pierda—
 * no necesita DOM.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { nombreDeArchivoDesdeCabecera } from '../src/utils/descargas.js'

test('lee el nombre del `filename*` con codificación UTF-8', () => {
  const cabecera = "attachment; filename=\"2-109_vacaciones.pdf\"; filename*=UTF-8''2-109_vacaciones.pdf"
  assert.equal(nombreDeArchivoDesdeCabecera(cabecera), '2-109_vacaciones.pdf')
})

test('decodifica tildes y la ñ del `filename*`', () => {
  const cabecera = "attachment; filename*=UTF-8''plano%20de%20a%C3%B1o.xlsx"
  assert.equal(nombreDeArchivoDesdeCabecera(cabecera), 'plano de año.xlsx')
})

test('cae al `filename` simple cuando no hay `filename*`', () => {
  assert.equal(
    nombreDeArchivoDesdeCabecera('attachment; filename="plano_vacaciones_general.xlsx"'),
    'plano_vacaciones_general.xlsx',
  )
})

test('acepta un `filename` sin comillas', () => {
  assert.equal(
    nombreDeArchivoDesdeCabecera('attachment; filename=2-109_vacaciones.pdf'),
    '2-109_vacaciones.pdf',
  )
})

test('devuelve null cuando la cabecera no trae nombre', () => {
  assert.equal(nombreDeArchivoDesdeCabecera('attachment'), null)
  assert.equal(nombreDeArchivoDesdeCabecera(''), null)
  assert.equal(nombreDeArchivoDesdeCabecera(undefined), null)
})
