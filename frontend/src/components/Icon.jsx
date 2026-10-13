/**
 * Componente de icono.
 *
 * Se expone `<Icon name="..." />` en lugar de devolver el componente desde una
 * función: crear un componente durante el render reinicia su estado en cada
 * pasada y React lo reporta como error (`react-hooks/static-components`).
 *
 * Todo icono es decorativo por defecto (`aria-hidden`): la señal siempre es el
 * texto que lo acompaña, nunca el dibujo solo.
 */

import { ICONS } from './iconNames'

export default function Icon({ name, size = 18, ...rest }) {
  const Component = ICONS[name] ?? ICONS.porDefecto
  return <Component size={size} aria-hidden="true" focusable="false" {...rest} />
}
