/**
 * Contexto de notificaciones.
 *
 * Vive en su propio módulo por la misma razón que el de sesión: el archivo del
 * proveedor exporta únicamente componentes (regla de Fast Refresh,
 * `react-refresh/only-export-components`).
 */

import { createContext } from 'react'

export const NotificacionesContext = createContext(null)
