/**
 * Acceso al contexto de notificaciones.
 *
 * Falla de forma explícita si se usa fuera del proveedor: un `null` silencioso
 * dejaría el contador del sidebar en cero sin decir por qué.
 */

import { useContext } from 'react'
import { NotificacionesContext } from './context'

export function useNotificaciones() {
  const context = useContext(NotificacionesContext)
  if (!context) {
    throw new Error('useNotificaciones debe usarse dentro de <NotificacionesProvider>.')
  }
  return context
}
