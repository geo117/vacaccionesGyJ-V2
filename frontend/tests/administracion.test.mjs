/**
 * Comprobaciones de la administración de usuarios y del alcance de Colmena.
 *
 * Igual que el resto de pruebas del proyecto, se verifica sobre el archivo
 * fuente: no hay DOM. Lo que se protege es lo que no puede perderse en una
 * edición descuidada: la tabla paginada de a 10, los anchos en caracteres y el
 * login sin UNES de los jefes de Colmena.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const ADMIN = new URL('../src/pages/AdministracionPage.jsx', import.meta.url)
const LOGIN = new URL('../src/pages/LoginPage.jsx', import.meta.url)
const ASIGNACIONES = new URL('../src/pages/AsignacionesPage.jsx', import.meta.url)

test('la tabla de usuarios se pagina de a 10 con los cuatro controles', async () => {
  const fuente = await readFile(ADMIN, 'utf8')

  assert.ok(fuente.includes('const POR_PAGINA = 10'), 'la página debe ser de 10 usuarios')
  assert.ok(fuente.includes('visibles.slice('), 'se pagina sobre lo ya filtrado')
  assert.ok(fuente.includes('visiblesPagina'), 'la tabla debe pintar sólo la página actual')
  assert.ok(fuente.includes('tabla-paginador__info'), 'falta el texto de cuántos se ven')
  assert.ok(fuente.includes('Mostrando '), 'el texto debe decir cuántos se ven de la totalidad')
  assert.ok(fuente.includes("'usuario' : 'usuarios'"), 'el texto debe concordar en singular y plural')

  for (const control of ['Pagination.First', 'Pagination.Prev', 'Pagination.Next', 'Pagination.Last']) {
    assert.ok(fuente.includes(`<${control}`), `falta el control ${control}`)
  }

  assert.ok(
    fuente.indexOf('</Table>') < fuente.indexOf('tabla-paginador'),
    'el paginador va debajo de la tabla',
  )
})

test('la tabla de usuarios identifica las columnas Usuario y Cargo', async () => {
  const pagina = await readFile(ADMIN, 'utf8')

  assert.ok(pagina.includes('className="data admin-tabla"'), 'falta la clase de la tabla de usuarios')
  assert.ok(pagina.includes('col-usuario'), 'falta la columna Usuario')
  assert.ok(pagina.includes('col-cargo'), 'falta la columna Cargo')
})

test('el login de los jefes de Colmena no valida la UNES en el cliente', async () => {
  const fuente = await readFile(LOGIN, 'utf8')

  assert.ok(
    !fuente.includes('/^\\d{3}$/.test(unes.trim())'),
    'la UNES la valida el servidor, no el formulario',
  )
  assert.ok(fuente.includes('UNES_INVALIDA'), 'el error de UNES inválida debe señalar el campo')
  assert.ok(fuente.includes('jefes de Colmena'), 'el texto debe explicar que pueden entrar sin UNES')
})

test('la vista de asignaciones muestra el alcance de Colmena', async () => {
  const fuente = await readFile(ASIGNACIONES, 'utf8')

  assert.ok(fuente.includes('alcanceColmena'), 'la vista debe leer el alcance del servidor')
  assert.ok(fuente.includes('Plantilla de tu equipo'), 'falta el título para el jefe de equipo')
  assert.ok(
    fuente.includes('Plantilla de tu conjunto (Colmena y filial)'),
    'falta el título del alcance de dirección',
  )
  assert.ok(
    fuente.includes('archivos de Colmena y filial'),
    'la dirección debe ver sólo las cédulas de los dos archivos',
  )
  assert.ok(
    fuente.includes('jefe de equipo de Colmena'),
    'la vista debe explicar por qué sólo ve su equipo',
  )
})
