/**
 * Comprobación del sidebar (mostrar/ocultar) y del contador de notificaciones.
 *
 * Se verifica sobre los archivos fuente y no montando los componentes: las
 * pruebas del proyecto corren con `node --test` sin DOM, y añadir jsdom sólo para
 * esto sería una dependencia nueva. Lo que se comprueba es lo que no puede
 * perderse en una edición descargada: que haya **una sola** hamburguesa en la
 * esquina superior izquierda, que el menú sea un offcanvas que arranca oculto y
 * se cierra al elegir una opción, que el contador salga del contexto compartido
 * y que la bandeja lo apague al abrirse.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const SHELL = new URL('../src/layout/AppShell.jsx', import.meta.url)
const CSS = new URL('../src/styles/layout.css', import.meta.url)
const PROVEEDOR = new URL('../src/notifications/NotificacionesProvider.jsx', import.meta.url)
const BANDEJA = new URL('../src/pages/NotificacionesPage.jsx', import.meta.url)
const MAIN = new URL('../src/main.jsx', import.meta.url)

test('el menú se abre con una sola hamburguesa y arranca oculto', async () => {
  const fuente = await readFile(SHELL, 'utf8')

  const hamburguesas = fuente.match(/className="topbar__burger"/g) ?? []
  assert.equal(hamburguesas.length, 1, 'debe haber una única hamburguesa')
  assert.ok(!fuente.includes('topbar__collapse'), 'el control duplicado de colapsar ya no existe')

  // El panel arranca cerrado: al iniciar sesión no hay nada abierto.
  assert.ok(fuente.includes('useState(false)'), 'el menú debe empezar oculto')
  assert.ok(fuente.includes('aria-expanded={navAbierto}'), 'la hamburguesa debe anunciar su estado')
  assert.ok(
    fuente.includes('aria-controls="menu-lateral"'),
    'la hamburguesa debe apuntar al panel que abre',
  )

  // Es un offcanvas de react-bootstrap, anclado a la izquierda.
  assert.ok(fuente.includes("from 'react-bootstrap/Offcanvas'"), 'el menú usa el Offcanvas')
  assert.ok(fuente.includes('placement="start"'), 'el panel entra desde la izquierda')

  // La hamburguesa es el primer botón de la barra: esquina superior izquierda.
  const topbar = fuente.indexOf('<header className="topbar">')
  const burger = fuente.indexOf('className="topbar__burger"')
  const identidad = fuente.indexOf('topbar__identity')
  assert.ok(topbar < burger && burger < identidad, 'la hamburguesa va antes que la identidad')
})

test('elegir una opción del menú lo cierra solo', async () => {
  const fuente = await readFile(SHELL, 'utf8')

  assert.ok(
    fuente.includes('onClick={handleNavClick}'),
    'cada enlace del menú debe cerrar el panel al pulsarlo',
  )
  assert.ok(
    /const handleNavClick = useCallback\(\(\) => \{[\s\S]*?setNavAbierto\(false\)/.test(fuente),
    'la navegación apaga el panel',
  )
  assert.ok(
    fuente.includes('onHide={cerrarNav}'),
    'react-bootstrap debe poder cerrar el panel (Escape, fondo, botón)',
  )
})

test('el CSS da al Offcanvas el aspecto del sistema', async () => {
  const css = await readFile(CSS, 'utf8')

  assert.ok(css.includes('.sidebar.offcanvas'), 'el panel tiene estilo propio')
  assert.ok(css.includes('--bs-offcanvas-width'), 'el ancho sale del token del sistema')
  assert.ok(css.includes('.sidebar .offcanvas-body'), 'el cuerpo del panel se estiliza')
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
