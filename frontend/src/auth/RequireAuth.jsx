/**
 * Guarda de rutas protegidas.
 *
 * Mientras el servidor no confirme la sesión, no se renderiza ninguna vista
 * interna: se muestra una pantalla de verificación. Poseer un token en el
 * navegador no autentica a nadie; la decisión la toma el backend.
 */

import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'

export default function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'checking') {
    return (
      <div className="boot" role="status" aria-live="polite">
        <span className="boot__spinner" aria-hidden="true" />
        <p>Verificando tu sesión…</p>
      </div>
    )
  }

  if (status === 'anonymous') {
    // Se recuerda a dónde quería llegar, para devolverlo allí tras entrar.
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}
