/**
 * Estructura de la aplicación autenticada: barra superior + sidebar izquierdo.
 *
 * Detalles que hacen que se sienta sólida:
 *  - El sidebar se muestra u oculta con **una sola hamburguesa**, en la esquina
 *    superior izquierda de la barra, a cualquier ancho de pantalla. El estado
 *    vive en un único atributo (`data-nav`) del contenedor y TODO el
 *    comportamiento responsive está en CSS: no hay estilos en línea que peleen
 *    con los media queries.
 *  - En móvil entra como panel deslizante con fondo oscurecido que se cierra con
 *    Escape o al tocar fuera, y el foco vuelve al botón que lo abrió. En pantalla
 *    ancha, ocultar el menú devuelve el ancho al contenido.
 *  - El sidebar es un `<nav>` con encabezado propio; el ítem activo se marca
 *    con `aria-current="page"` (lo pone `NavLink`) además del color.
 *  - El contador de notificaciones pendientes sale del contexto compartido, el
 *    mismo que usa la bandeja: el número del menú y lo que se ve al abrirlo no
 *    pueden discrepar.
 *  - El contenido arranca con `id="contenido"` para que el enlace de salto
 *    funcione desde el primer tabulador.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import Swal from 'sweetalert2'
import { useAuth } from '../auth/useAuth'
import Icon from '../components/Icon'
import { useNotificaciones } from '../notifications/useNotificaciones'
import { navItemsPara } from '../services/navigation'

/** Debajo de este ancho el sidebar es un panel deslizante, no una columna. */
const CONSULTA_MOVIL = '(max-width: 767.98px)'

/** Estado inicial del sidebar: visible en pantalla ancha, oculto en móvil. */
function initialNavAbierto() {
  if (typeof window === 'undefined') return true
  return !window.matchMedia(CONSULTA_MOVIL).matches
}

function enMovil() {
  if (typeof window === 'undefined') return false
  return window.matchMedia(CONSULTA_MOVIL).matches
}

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

  const [navAbierto, setNavAbierto] = useState(initialNavAbierto)
  /* Mientras el usuario no decida, el ancho de la ventana manda. */
  const [userTouchedNav, setUserTouchedNav] = useState(false)
  const burgerRef = useRef(null)

  // El menú se arma con el cargo que confirmó el servidor: «Administración»
  // sólo existe en la lista para Talento Humano.
  const items = useMemo(() => navItemsPara(esTalentoHumano), [esTalentoHumano])
  const currentItem = useMemo(
    () => items.find((item) => location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)) ?? null,
    [items, location.pathname],
  )

  /* Mantiene el modo coherente al cambiar de tamaño, salvo si el usuario ya
     decidió algo en esta pantalla. */
  useEffect(() => {
    if (userTouchedNav) return undefined
    const query = window.matchMedia(CONSULTA_MOVIL)
    const handle = (event) => setNavAbierto(!event.matches)
    query.addEventListener('change', handle)
    return () => query.removeEventListener('change', handle)
  }, [userTouchedNav])

  const cerrarNav = useCallback((restoreFocus = false) => {
    setNavAbierto(false)
    if (restoreFocus) burgerRef.current?.focus()
  }, [])

  /* Escape cierra el panel deslizante; el foco vuelve al botón que lo abrió. */
  useEffect(() => {
    if (!navAbierto || !enMovil()) return undefined
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        cerrarNav(true)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [navAbierto, cerrarNav])

  /* Al navegar desde el panel, se cierra solo. Se hace al pulsar el enlace —y no
     con un efecto sobre la ruta— porque el cierre sólo tiene sentido en móvil y
     ahí es donde está el panel abierto; en pantalla ancha el menú se queda como
     esté, que no es un diálogo que haya que cerrar. */
  const handleNavClick = useCallback(() => {
    if (enMovil()) setNavAbierto(false)
  }, [])

  const handleLogout = useCallback(async () => {
    const confirmation = await Swal.fire({
      title: '¿Cerrar la sesión?',
      text: 'Tendrás que volver a autenticarte para entrar.',
      icon: 'question',
      showCancelButton: true,
      confirmButtonText: 'Cerrar sesión',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: '#16456d',
      cancelButtonColor: '#5a6b7b',
      reverseButtons: true,
      focusCancel: true,
      customClass: { popup: 'gv-swal' },
    })

    if (!confirmation.isConfirmed) return

    await logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  const toggleNav = useCallback(() => {
    setUserTouchedNav(true)
    setNavAbierto((abierto) => !abierto)
  }, [])

  return (
    <div className="shell" data-nav={navAbierto ? 'abierto' : 'oculto'}>
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>

      <header className="topbar">
        <button
          type="button"
          className="topbar__burger"
          onClick={toggleNav}
          aria-label={navAbierto ? 'Ocultar el menú de navegación' : 'Mostrar el menú de navegación'}
          aria-expanded={navAbierto}
          aria-controls="menu-lateral"
          ref={burgerRef}
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

      {navAbierto ? (
        <button
          type="button"
          className="scrim"
          aria-label="Cerrar el menú de navegación"
          onClick={() => cerrarNav(true)}
        />
      ) : null}

      <nav className="sidebar" id="menu-lateral" aria-label="Navegación principal">
        <p className="sidebar__heading">Menú</p>

        <div className="sidebar__nav">
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
        </div>

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
      </nav>

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
