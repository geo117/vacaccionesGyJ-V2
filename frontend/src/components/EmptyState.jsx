/**
 * Estado vacío.
 *
 * Un "No hay datos" en gris no dice nada. Aquí el vacío explica qué aparecería
 * en la vista y, cuando corresponde, ofrece la acción que lo llena.
 */

import Icon from './Icon'

export default function EmptyState({ icon = 'vacio', title, text, action = null }) {
  return (
    <div className="empty">
      <span className="empty__icon" aria-hidden="true">
        <Icon name={icon} size={24} />
      </span>
      <p className="empty__title">{title}</p>
      {text ? <p className="empty__text">{text}</p> : null}
      {action}
    </div>
  )
}
