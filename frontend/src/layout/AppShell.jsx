/**
 * Estructura de la aplicación autenticada: barra superior + sidebar izquierdo.
 *
 * Detalles que hacen que se sienta sólida:
 *  - El estado del sidebar se controla con un único atributo (`data-nav`) en el
 *    contenedor, y TODO el comportamiento responsive vive en CSS. No hay
 *    estilos en línea que peleen con los media queries.
 *  - El sidebar es un `<nav>` con encabezado propio; el ítem activo se marca
 *    con `aria-current="page"` (lo pone `NavLink`) además del color.
 *  - En móvil entra como panel deslizante con fondo oscurecido que se cierra con
 *    Escape o al tocar fuera, y el foco vuelve al botón que lo abrió.
 *  - El contenido arranca con `id="contenido"` para que el enlace de salto
 *    funcione desde el primer tabulador.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import Swal from 'sweetalert2'
import { useAuth } from '../auth/useAuth'
import Icon from '../components/Icon'
import { navItemsPara } from '../services/navigation'

/** Modo inicial del sidebar según el ancho de la ventana. */
function initialNavMode() {
  if (typeof window === 'undefined') return 'rail'
  return window.matchMedia('(min-width: 1200px)').matches ? 'expanded' : 'rail'
}

function initials(nombre) {
  return (nombre || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

export default function AppShell() {
  const { user, logout, esTalentoHumano } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const [navMode, setNavMode] = useState(initialNavMode)
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
    const query = window.matchMedia('(min-width: 1200px)')
    const handle = (event) => setNavMode(event.matches ? 'expanded' : 'rail')
    query.addEventListener('change', handle)
    return () => query.removeEventListener('change', handle)
  }, [userTouchedNav])

  const isDrawerOpen = navMode === 'open'

  const closeDrawer = useCallback((restoreFocus = false) => {
    setNavMode('rail')
    if (restoreFocus) burgerRef.current?.focus()
  }, [])

  /* Escape cierra el panel; el foco vuelve al botón que lo abrió. */
  useEffect(() => {
    if (!isDrawerOpen) return undefined
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        closeDrawer(true)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isDrawerOpen, closeDrawer])

  /* Al navegar desde el panel, se cierra solo. */
  const lastPath = useRef(location.pathname)
  useEffect(() => {
    if (lastPath.current === location.pathname) return
    lastPath.current = location.pathname
    setNavMode((mode) => (mode === 'open' ? 'rail' : mode))
  }, [location.pathname])

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
    setNavMode((mode) => (mode === 'open' ? 'rail' : mode === 'expanded' ? 'rail' : 'expanded'))
  }, [])

  const openDrawer = useCallback(() => {
    setUserTouchedNav(true)
    setNavMode('open')
  }, [])

  return (
    <div className="shell" data-nav={navMode}>
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>

      <header className="topbar">
        <button
          type="button"
          className="topbar__burger"
          onClick={isDrawerOpen ? () => closeDrawer(true) : openDrawer}
          aria-label={isDrawerOpen ? 'Cerrar el menú de navegación' : 'Abrir el menú de navegación'}
          aria-expanded={isDrawerOpen}
          aria-controls="menu-lateral"
          ref={burgerRef}
        >
          <Icon name="menu" size={22} />
        </button>

        <button
          type="button"
          className="topbar__burger topbar__collapse"
          onClick={toggleNav}
          aria-label={
            navMode === 'expanded' ? 'Contraer el menú lateral' : 'Expandir el menú lateral'
          }
          aria-expanded={navMode === 'expanded'}
          aria-controls="menu-lateral"
        >
          <Icon name="colapsar" size={22} />
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

      {isDrawerOpen ? (
        <button
          type="button"
          className="scrim"
          aria-label="Cerrar el menú de navegación"
          onClick={() => closeDrawer(true)}
        />
      ) : null}

      <nav className="sidebar" id="menu-lateral" aria-label="Navegación principal">
        <p className="sidebar__heading">Menú</p>

        <div className="sidebar__nav">
          {items.map((item) => (
            <NavLink
              key={item.id}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `sidebar__link${isActive ? ' is-active' : ''}`}
              title={item.label}
            >
              <Icon name={item.icon} size={20} />
              <span className="sidebar__label">{item.label}</span>
              {item.badge ? (
                <span className="sidebar__badge tabular" aria-hidden="true">
                  {item.badge}
                </span>
              ) : null}
            </NavLink>
          ))}
        </div>

        <div className="sidebar__foot">
          <p className="sidebar__foot-title">Sesión</p>
          <p className="sidebar__foot-line">
            {user?.cargo ? `Cargo: ${user.cargo}` : 'Sesión validada contra la base institucional.'}
          </p>
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
