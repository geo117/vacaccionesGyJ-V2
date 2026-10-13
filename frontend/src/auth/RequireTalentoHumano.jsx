/**
 * Guarda de rutas exclusivas de Talento Humano.
 *
 * Igual que `RequireAuth`, no decide a partir de lo que el navegador tenga
 * guardado: usa el cargo que el servidor devolvió al confirmar la sesión. Y aun
 * así esto es sólo la puerta de la interfaz — el backend vuelve a comprobar el
 * cargo en cada endpoint de administración, porque a la API se le puede llamar
 * sin pasar por aquí.
 */

import { Link, Outlet } from 'react-router-dom'
import { useAuth } from './useAuth'
import { DEFAULT_ROUTE } from '../services/navigation'

export default function RequireTalentoHumano() {
  const { esTalentoHumano } = useAuth()

  if (!esTalentoHumano) {
    return (
      <div className="empty" role="region" aria-labelledby="sin-permiso">
        <h1 className="empty__title" id="sin-permiso">
          Esta sección es de Talento Humano
        </h1>
        <p className="empty__text">
          Tu usuario no tiene el cargo necesario para administrar las cuentas. Si crees que es un
          error, escribe a Talento Humano para que revisen tu cargo en la base de datos.
        </p>
        <Link className="btn btn--primary" to={DEFAULT_ROUTE}>
          Volver al resumen
        </Link>
      </div>
    )
  }

  return <Outlet />
}
