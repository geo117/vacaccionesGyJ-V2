/**
 * Cliente HTTP de la API.
 *
 * Reglas de seguridad que se cumplen aquí:
 *  - La URL base sale de una variable de entorno de Vite, nunca de la URL ni de
 *    un parámetro; no hay forma de que un enlace redirija las credenciales a
 *    otro host (open redirect / SSRF desde el navegador).
 *  - El token vive en `sessionStorage`, no en `localStorage`: muere al cerrar
 *    la pestaña y no queda disponible para otro documento del mismo origen
 *    durante semanas.
 *  - Nunca se registra el token, la contraseña ni el cuerpo de la petición.
 *  - Una respuesta 401 con `SESSION_EXPIRED` dispara un único manejador global
 *    (registrado por el proveedor de autenticación) en lugar de dejar la UI en
 *    un estado a medias.
 *  - No se usan cookies: sin `credentials`, sin CSRF.
 */

const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const API_BASE = RAW_BASE.replace(/\/+$/, '')

const TOKEN_STORAGE_KEY = 'gv.session.token'
const REQUEST_TIMEOUT_MS = 12_000

/** Error de transporte o de negocio, ya normalizado. */
export class ApiError extends Error {
  constructor({ code, message, status, details }) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details ?? null
  }
}

/* -- almacenamiento del token --------------------------------------------- */

let memoryToken = null

export function readToken() {
  if (memoryToken) return memoryToken
  try {
    memoryToken = window.sessionStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    // Modo privado o almacenamiento bloqueado: la sesión vive sólo en memoria.
    memoryToken = null
  }
  return memoryToken
}

export function writeToken(token) {
  memoryToken = token || null
  try {
    if (token) window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
    else window.sessionStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    /* sin almacenamiento persistente, la sesión sigue en memoria */
  }
}

export function clearToken() {
  writeToken(null)
}

/* -- manejador global de sesión expirada ---------------------------------- */

let sessionExpiredHandler = null

export function onSessionExpired(handler) {
  sessionExpiredHandler = typeof handler === 'function' ? handler : null
}

function notifySessionExpired() {
  if (sessionExpiredHandler) sessionExpiredHandler()
}

/* -- petición -------------------------------------------------------------- */

async function request(path, { method = 'GET', body, auth = false, timeoutMs = REQUEST_TIMEOUT_MS } = {}) {
  const url = `${API_BASE}${path}`
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  if (auth) {
    const token = readToken()
    if (!token) {
      throw new ApiError({
        code: 'SESSION_REQUIRED',
        message: 'Tu sesión no está activa. Inicia sesión para continuar.',
        status: 401,
      })
    }
    headers.Authorization = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
    })
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new ApiError({
        code: 'TIMEOUT',
        message: 'La operación tardó demasiado. Revisa tu conexión e intenta de nuevo.',
        status: 0,
      })
    }
    throw new ApiError({
      code: 'NETWORK_ERROR',
      message: 'No pudimos comunicarnos con el servidor. Verifica que el backend esté en ejecución.',
      status: 0,
    })
  } finally {
    window.clearTimeout(timer)
  }

  let payload = null
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
  }

  if (response.ok) return payload ?? {}

  const code = payload?.code || `HTTP_${response.status}`
  const message = payload?.message || 'No pudimos completar la operación. Intenta de nuevo.'

  if (response.status === 401 && code !== 'INVALID_CREDENTIALS') {
    clearToken()
    notifySessionExpired()
  }

  throw new ApiError({ code, message, status: response.status, details: payload?.details ?? null })
}

/* -- API ------------------------------------------------------------------ */

export const authApi = {
  /**
   * Inicia sesión. Devuelve `{ token, expires_in, usuario }`.
   *
   * La UNES se digita en el formulario y viaja en el cuerpo: el servidor la
   * guarda en la sesión (no en la tabla de usuarios) y la usa para filtrar los
   * listados de esa UNES.
   *
   * Es **opcional**: Talento Humano entra sólo con correo y contraseña y su
   * tablero es la plantilla completa. Si el cargo la necesita y no se envió, el
   * servidor responde 400 con `UNES_REQUERIDA` y la vista vuelve a pedirla.
   */
  login(correo, password, unes) {
    return request('/api/auth/login', {
      method: 'POST',
      body: { correo, password, unes },
      auth: false,
      timeoutMs: 15_000,
    })
  },

  /** Cierra la sesión en el servidor y revoca el token. */
  logout() {
    return request('/api/auth/logout', { method: 'POST', auth: true })
  },

  /** Confirma con el servidor que la sesión sigue siendo válida. */
  session() {
    return request('/api/auth/session', { auth: true })
  },
}

export const usuariosApi = {
  listar() {
    return request('/api/usuarios', { auth: true })
  },
  crear(datos) {
    return request('/api/usuarios', { method: 'POST', body: datos, auth: true })
  },
  actualizar(id, datos) {
    return request(`/api/usuarios/${id}`, { method: 'PUT', body: datos, auth: true })
  },
  /**
   * Activa o desactiva la cuenta.
   *
   * El servidor cierra las sesiones abiertas al desactivar, así que el efecto
   * es inmediato y no hay que esperar a que caduque el token.
   */
  cambiarActivo(id, activo) {
    return request(`/api/usuarios/${id}/activo`, {
      method: 'PATCH',
      body: { activo },
      auth: true,
    })
  },
  eliminar(id) {
    return request(`/api/usuarios/${id}`, { method: 'DELETE', auth: true })
  },
}

export const asignacionesApi = {
  /**
   * Tablero de la UNES de la sesión.
   *
   * El servidor decide el origen: si la vista corporativa responde, devuelve los
   * colaboradores de esa UNES con la asignación que tengan; si no, sólo las
   * asignaciones registradas. `origen` dice cuál de los dos se usó.
   */
  listar() {
    return request('/api/asignaciones', { auth: true })
  },
  obtener(id) {
    return request(`/api/asignaciones/${id}`, { auth: true })
  },
  crear(datos) {
    return request('/api/asignaciones', { method: 'POST', body: datos, auth: true })
  },
  guardarPeriodos(id, datos) {
    return request(`/api/asignaciones/${id}/periodos`, { method: 'PUT', body: datos, auth: true })
  },
  /**
   * Aprobar o rechazar. El servidor exige el cargo de Talento Humano: si el
   * usuario no lo tiene, responde 403 aunque la interfaz no ofrezca la opción.
   */
  decidir(id, datos) {
    return request(`/api/asignaciones/${id}/decision`, { method: 'POST', body: datos, auth: true })
  },
}

export const notificacionesApi = {
  /** Bandeja general: sólo Talento Humano recibe avisos. */
  listar() {
    return request('/api/notificaciones', { auth: true })
  },
  /** Avisos dirigidos a la persona que consulta (`usuario_id`). */
  mias() {
    return request('/api/notificaciones/mias', { auth: true })
  },
}

export const resumenApi = {
  obtener() {
    return request('/api/resumen', { auth: true })
  },
}

export const healthApi = {
  check() {
    return request('/api/health', { timeoutMs: 5_000 })
  },
}
