/**
 * Comprobación del sidebar (mostrar/ocultar) y del contador de notificaciones.
 *
 * Se verifica sobre los archivos fuente y no montando los componentes: las
 * pruebas del proyecto corren con `node --test` sin DOM, y añadir jsdom sólo para
 * esto sería una dependencia nueva. Lo que se comprueba es lo que no puede
 * perderse en una edición descargada: que haya **una sola** hamburguesa en la
 * esquina superior izquierda, que su estado llegue al CSS por `data-nav`, que el
 * contador salga del contexto compartido y que la bandeja lo apague al abrirse.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const SHELL = new URL('../src/layout/AppShell.jsx', import.meta.url)
const CSS = new URL('../src/styles/layout.css', import.meta.url)
const PROVEEDOR = new URL('../src/notifications/NotificacionesProvider.jsx', import.meta.url)
const BANDEJA = new URL('../src/pages/NotificacionesPage.jsx', import.meta.url)
const MAIN = new URL('../src/main.jsx', import.meta.url)

test('el sidebar se muestra y se oculta con una sola hamburguesa', async () => {
  const fuente = await readFile(SHELL, 'utf8')

  const hamburguesas = fuente.match(/className="topbar__burger"/g) ?? []
  assert.equal(hamburguesas.length, 1, 'debe haber una única hamburguesa')
  assert.ok(!fuente.includes('topbar__collapse'), 'el control duplicado de colapsar ya no existe')

  // El estado vive en un atributo del contenedor: el comportamiento responsive
  // está en CSS, no en estilos en línea.
  assert.ok(
    fuente.includes('data-nav={navAbierto ? \'abierto\' : \'oculto\'}'),
    'el estado del menú debe viajar en data-nav',
  )
  assert.ok(fuente.includes('aria-expanded={navAbierto}'), 'la hamburguesa debe anunciar su estado')

  // La hamburguesa es el primer botón de la barra: esquina superior izquierda.
  const topbar = fuente.indexOf('<header className="topbar">')
  const burger = fuente.indexOf('className="topbar__burger"')
  const identidad = fuente.indexOf('topbar__identity')
  assert.ok(topbar < burger && burger < identidad, 'la hamburguesa va antes que la identidad')
})

test('el CSS define los dos estados en todos los tamaños', async () => {
  const css = await readFile(CSS, 'utf8')

  assert.ok(
    css.includes(".shell[data-nav='oculto'] .sidebar"),
    'en pantalla ancha, «oculto» debe sacar el sidebar de la vista',
  )
  assert.ok(
    css.includes(".shell[data-nav='oculto'] .shell__content"),
    'al ocultarlo, el contenido debe recuperar el ancho',
  )
  assert.ok(
    css.includes(".shell[data-nav='abierto'] .sidebar"),
    'en móvil, «abierto» debe mostrar el panel deslizante',
  )
  // El badge del riel se superpone al icono; en ancho completo vuelve al flujo.
  assert.ok(css.includes('.sidebar__badge'), 'el contador debe tener estilo propio')
})

test('el contador de pendientes sale del contexto compartido', async () => {
  const shell = await readFile(SHELL, 'utf8')
  const proveedor = await readFile(PROVEEDOR, 'utf8')
  const main = await readFile(MAIN, 'utf8')

  assert.ok(shell.includes('useNotificaciones()'), 'el sidebar debe leer el contador del contexto')
  assert.ok(
    /const badge = item\.id === 'notificaciones' \? pendientes : item\.badge/.test(shell),
    'el contador va en la opción de notificaciones',
  )
  assert.ok(
    proveedor.includes('pendientes'),
    'el proveedor debe exponer el número de avisos sin revisar',
  )
  assert.ok(
    proveedor.includes('gv.notificaciones.vistas'),
    'lo ya visto se recuerda por usuario, porque la tabla no tiene columna de leída',
  )
  assert.ok(
    proveedor.includes('key={userId ?? \'anonimo\'}'),
    'cambiar de usuario debe reiniciar el estado, no arrastrarlo',
  )
  assert.ok(
    main.includes('<NotificacionesProvider>'),
    'el proveedor debe envolver la aplicación',
  )
})

test('abrir la bandeja apaga el contador', async () => {
  const bandeja = await readFile(BANDEJA, 'utf8')

  assert.ok(bandeja.includes('useNotificaciones()'), 'la bandeja comparte el estado del contador')
  assert.ok(
    /if \(!cargando\) marcarVistas\(\)/.test(bandeja),
    'al terminar la carga, los avisos quedan marcados como vistos',
  )
  assert.ok(
    !bandeja.includes('notificacionesApi'),
    'la bandeja no debe pedir su propia copia: el dato es el del contexto',
  )
})
