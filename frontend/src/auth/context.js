/**
 * Contexto de sesión.
 *
 * Vive en su propio módulo para que el archivo del proveedor exporte
 * únicamente componentes (regla de Fast Refresh: `react-refresh/only-export-components`).
 *
 * Nota de portabilidad: el nombre de este archivo y el del proveedor
 * (`AuthProvider.jsx`) no pueden diferir sólo en mayúsculas. Windows y macOS
 * resuelven las rutas sin distinguir mayúsculas, así que dos archivos como
 * `authContext.js` y `AuthContext.jsx` colisionan y el import se resuelve al
 * archivo equivocado.
 */

import { createContext } from 'react'

export const AuthContext = createContext(null)
