/**
 * Estructura de la aplicación autenticada: barra superior + menú lateral.
 *
 * El menú es un **offcanvas**: no ocupa una columna permanente, vive fuera de la
 * pantalla y entra deslizándose por encima del contenido cuando se pulsa la
 * hamburguesa. Por eso el contenido usa todo el ancho.
 *
 * Decisiones que sostienen el comportamiento:
 *  - **Arranca cerrado** (`useState(false)`): al iniciar sesión no hay panel
 *    abierto y la vista queda despejada.
 *  - Al elegir una opción el panel **se cierra solo** (el `onClick` de cada
 *    enlace apaga el estado): el menú no tapa la vista que la persona pidió.
 *  - Se usa el `Offcanvas` de react-bootstrap y no un panel propio porque trae
 *    el diálogo completo: `role="dialog"`, fondo oscurecido, cierre con Escape o
 *    al tocar fuera, foco atrapado y devuelto al disparador, y bloqueo del
 *    scroll de la página. La accesibilidad no se reimplementa.
 *  - El contador de notificaciones pendientes sale del contexto compartido, el
 *    mismo que usa la bandeja: el número del menú y lo que se ve al abrirlo no
 *    pueden discrepar.
 *  - El contenido arranca con `id="contenido"` para que el enlace de salto
 *    funcione desde el primer tabulador.
 */

import { useCallback, useMemo, useState } from 'react'
import Offcanvas from 'react-bootstrap/Offcanvas'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import Swal from 'sweetalert2'
import { useAuth } from '../auth/useAuth'
import Icon from '../components/Icon'
import { useNotificaciones } from '../notifications/useNotificaciones'
import { navItemsPara } from '../services/navigation'

function initials(nombre) {
  return (nombre || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

/** El contador se muestra corto; a partir de 100 no aporta precisión. */
function textoBadge(total) {
  return total > 99 ? '99+' : String(total)
}

export default function AppShell() {
  const { user, logout, esTalentoHumano } = useAuth()
  const { pendientes } = useNotificaciones()
  const location = useLocation()
  const navigate = useNavigate()

  /* El menú arranca cerrado: al entrar a la aplicación no hay nada abierto. */
  const [navAbierto, setNavAbierto] = useState(false)

  // El menú se arma con el cargo que confirmó el servidor: «Administración»
  // sólo existe en la lista para Talento Humano.
  const items = useMemo(() => navItemsPara(esTalentoHumano), [esTalentoHumano])
  const currentItem = useMemo(
    () => items.find((item) => location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)) ?? null,
    [items, location.pathname],
  )

  const abrirNav = useCallback(() => setNavAbierto(true), [])
  const cerrarNav = useCallback(() => setNavAbierto(false), [])

  /* Al navegar desde el panel, se cierra solo: la vista elegida queda a la vista
     y no tapada por el menú. */
  const handleNavClick = useCallback(() => {
    setNavAbierto(false)
  }, [])

  const handleLogout = useCallback(async () => {
    const confirmation = await Swal.fire({
      title: '¿Cerrar la sesión?',
      text: 'Tendrás que volver a autenticarte para entrar.',
      icon: 'question',
      showCancelButton: true,
      confirmButtonText: 'Cerrar sesión',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: '#003366',
      cancelButtonColor: '#5a6b7b',
      reverseButtons: true,
      focusCancel: true,
      customClass: { popup: 'gv-swal' },
    })

    if (!confirmation.isConfirmed) return

    await logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  return (
    <div className="shell">
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>

      <header className="topbar">
        <button
          type="button"
          className="topbar__burger"
          onClick={abrirNav}
          aria-label="Mostrar el menú de navegación"
          aria-expanded={navAbierto}
          aria-controls="menu-lateral"
        >
          <Icon name="menu" size={22} />
        </button>

        <div className="topbar__identity">
          <span className="topbar__mark" aria-hidden="true">
            GJ
          </span>
          <span className="topbar__titles">
            <span className="topbar__app">Gestión de Vacaciones</span>
            <br />
            <span className="topbar__view">{currentItem?.title ?? 'G&J'}</span>
          </span>
        </div>

        <div className="topbar__spacer" />

        <div className="topbar__user">
          <span className="topbar__user-text">
            <span className="topbar__user-name">{user?.nombre ?? 'Usuario'}</span>
            <br />
            <span className="topbar__user-mail">{user?.correo ?? ''}</span>
          </span>
          <span className="topbar__avatar" aria-hidden="true">
            {initials(user?.nombre)}
          </span>
        </div>

        <button type="button" className="topbar__logout" onClick={handleLogout}>
          <Icon name="salir" size={18} />
          <span className="topbar__logout-label">Salir</span>
        </button>
      </header>

      <Offcanvas
        id="menu-lateral"
        show={navAbierto}
        onHide={cerrarNav}
        placement="start"
        className="sidebar"
        aria-label="Menú de navegación"
      >
        <Offcanvas.Header closeButton closeLabel="Cerrar el menú de navegación">
          <Offcanvas.Title>Menú</Offcanvas.Title>
        </Offcanvas.Header>

        <Offcanvas.Body>
          <nav className="sidebar__nav" aria-label="Navegación principal">
            {items.map((item) => {
              const badge = item.id === 'notificaciones' ? pendientes : item.badge
              return (
                <NavLink
                  key={item.id}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `sidebar__link${isActive ? ' is-active' : ''}`}
                  title={item.label}
                  onClick={handleNavClick}
                >
                  <Icon name={item.icon} size={20} />
                  <span className="sidebar__label">{item.label}</span>
                  {badge ? (
                    <span className="sidebar__badge tabular" aria-hidden="true">
                      {textoBadge(badge)}
                    </span>
                  ) : null}
                  {item.id === 'notificaciones' && pendientes > 0 ? (
                    <span className="visually-hidden">
                      {`${pendientes} ${pendientes === 1 ? 'aviso pendiente' : 'avisos pendientes'} por revisar`}
                    </span>
                  ) : null}
                </NavLink>
              )
            })}
          </nav>

          <div className="sidebar__foot">
            <p className="sidebar__foot-title">Sesión</p>
            <p className="sidebar__foot-line">
              {user?.cargo ? `Cargo: ${user.cargo}` : 'Sesión validada contra la base institucional.'}
            </p>
            {esTalentoHumano ? (
              <p className="sidebar__foot-line">Plantilla completa de la empresa</p>
            ) : null}
            <p className="sidebar__foot-line">Versión 2.0</p>
          </div>
        </Offcanvas.Body>
      </Offcanvas>

      <main className="shell__content" id="contenido" tabIndex={-1}>
        <div className="shell__inner">
          <Outlet />
        </div>
      </main>

      <span className="visually-hidden" aria-live="polite">
        {currentItem ? `Sección actual: ${currentItem.title}` : ''}
      </span>
    </div>
  )
}
