/**
 * Proveedor de estado de sesión.
 *
 * Decisiones que importan para la seguridad:
 *  - `checking` es un estado real y visible. Mientras el servidor no confirme la
 *    sesión, la aplicación NO renderiza ninguna vista protegida: poseer un token
 *    en el navegador no equivale a estar autenticado.
 *  - Al montar, si hay token, se valida contra `/api/auth/session`. Si el
 *    servidor lo rechaza, se descarta y se vuelve al acceso.
 *  - El cierre de sesión revoca el token en el servidor; si esa llamada falla,
 *    igual se limpia el estado local (nunca se deja al usuario "a medias").
 *  - Un 401 con `SESSION_EXPIRED` en cualquier petición avisa una sola vez.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  authApi,
  clearToken,
  onSessionExpired,
  readToken,
  writeToken,
} from '../services/api'
import { AuthContext } from './context'

export default function AuthProvider({ children }) {
  const [status, setStatus] = useState('checking') // checking | authenticated | anonymous
  const [user, setUser] = useState(null)
  const [notice, setNotice] = useState(null)
  const expiryNotified = useRef(false)

  /* Verificación inicial contra el servidor. */
  useEffect(() => {
    let cancelled = false

    async function verify() {
      if (!readToken()) {
        if (!cancelled) setStatus('anonymous')
        return
      }
      try {
        const payload = await authApi.session()
        if (cancelled) return
        setUser(payload.usuario ?? null)
        setStatus('authenticated')
      } catch {
        if (cancelled) return
        clearToken()
        setUser(null)
        setStatus('anonymous')
      }
    }

    verify()
    return () => {
      cancelled = true
    }
  }, [])

  /* Un 401 en cualquier llamada devuelve al acceso, con un aviso único. */
  useEffect(() => {
    onSessionExpired(() => {
      setUser(null)
      setStatus('anonymous')
      if (!expiryNotified.current) {
        expiryNotified.current = true
        setNotice({
          code: 'SESSION_EXPIRED',
          message: 'Tu sesión expiró por inactividad. Vuelve a iniciar sesión para continuar.',
        })
      }
    })
    return () => onSessionExpired(null)
  }, [])

  const login = useCallback(async (correo, password, unes) => {
    // Un intento nuevo empieza sin token previo: no se reutiliza una sesión
    // anterior si el login falla.
    clearToken()
    const payload = await authApi.login(correo, password, unes)
    writeToken(payload.token)
    expiryNotified.current = false
    setNotice(null)
    setUser(payload.usuario ?? null)
    setStatus('authenticated')
    return payload.usuario ?? null
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch (error) {
      // 401 significa que el token ya no servía: es un cierre correcto. Cualquier
      // otro fallo se ignora a propósito, porque el usuario pidió salir y la
      // sesión local se destruye de todas formas.
      if (error instanceof ApiError && error.status !== 401) {
        // Se deja constancia sin exponer el token ni el cuerpo de la respuesta.
        console.warn('El cierre de sesión en el servidor no se pudo confirmar.')
      }
    } finally {
      clearToken()
      setUser(null)
      setNotice(null)
      expiryNotified.current = false
      setStatus('anonymous')
    }
  }, [])

  const clearNotice = useCallback(() => setNotice(null), [])

  /* El cargo viene del servidor (`usuario.esTalentoHumano`). La interfaz lo usa
     para mostrar u ocultar opciones, pero el control real está en el backend:
     ocultar un botón no impide llamar a la API. */
  const esTalentoHumano = Boolean(user?.esTalentoHumano)
  const puedeAprobar = Boolean(user?.puedeAprobar)
  /* UNES digitada al entrar. No vive en la base: es un dato de la sesión y la
     usan los listados para filtrar. */
  const unes = String(user?.unes ?? '')

  const value = useMemo(
    () => ({
      status,
      user,
      unes,
      notice,
      clearNotice,
      login,
      logout,
      esTalentoHumano,
      puedeAprobar,
    }),
    [status, user, unes, notice, clearNotice, login, logout, esTalentoHumano, puedeAprobar],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
