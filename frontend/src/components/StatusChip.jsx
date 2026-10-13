/**
 * Estado de asignación / notificación.
 *
 * El estado se comunica con tres señales a la vez —color, glifo y palabra—
 * porque el color por sí solo no es accesible para daltonismo ni para lectores
 * de pantalla.
 */

import Icon from './Icon'
import { estadoMeta } from './iconNames'

export default function StatusChip({ estado, label }) {
  const meta = estadoMeta(estado)

  return (
    <span className={`chip chip--${meta.tone}`}>
      <Icon name={meta.icon} size={14} />
      {label ?? meta.label}
    </span>
  )
}
