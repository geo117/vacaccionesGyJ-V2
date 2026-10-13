/**
 * Ruta no encontrada.
 *
 * Se ofrece una salida concreta en lugar de dejar al usuario en un callejón.
 */

import { Link, useLocation } from 'react-router-dom'
import Icon from '../components/Icon'
import { DEFAULT_ROUTE } from '../services/navigation'

export default function NotFoundPage() {
  const location = useLocation()

  return (
    <div className="empty" role="region" aria-labelledby="no-encontrada">
      <span className="empty__icon" aria-hidden="true">
        <Icon name="alerta" size={24} />
      </span>
      <h1 className="empty__title" id="no-encontrada">
        No encontramos esta página
      </h1>
      <p className="empty__text">
        La dirección <code>{location.pathname}</code> no corresponde a ninguna sección de la
        herramienta.
      </p>
      <Link className="btn btn--primary" to={DEFAULT_ROUTE}>
        Ir al resumen
      </Link>
    </div>
  )
}
