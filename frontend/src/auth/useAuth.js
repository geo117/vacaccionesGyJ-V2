/**
 * Acceso al contexto de sesión.
 *
 * Falla de forma explícita si se usa fuera del proveedor: un `null` silencioso
 * produciría pantallas en blanco difíciles de diagnosticar.
 */

import { useContext } from 'react'
import { AuthContext } from './context'

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>.')
  }
  return context
}
