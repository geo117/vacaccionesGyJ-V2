/**
 * Vista de acceso.
 *
 * Cómo se comporta y por qué:
 *  - Se envía una sola petición por envío; el botón queda `aria-busy` y
 *    deshabilitado mientras viaja, de modo que no se pueda martillar el
 *    endpoint ni crear varias sesiones con un doble clic.
 *  - El correo y la contraseña se validan siempre. La **UNES es opcional**:
 *    Talento Humano entra sólo con correo y contraseña y su tablero es la
 *    plantilla completa de la empresa. Para los demás cargos el servidor
 *    responde `UNES_REQUERIDA` tras comprobar las credenciales y es entonces
 *    cuando el campo se exige, sin delatar de antemano qué correos existen.
 *  - Un único mensaje para todos los fallos de credenciales. La respuesta del
 *    servidor ya es indistinguible entre "correo no existe", "contraseña
 *    incorrecta" y "cuenta sin acceso"; la interfaz no reintroduce la
 *    diferencia que el backend se cuidó de no revelar.
 *  - Cuando hay bloqueo por intentos, se dice cuánto falta. El límite es
 *    información del usuario; el catálogo de cuentas no lo es.
 *  - Tras un fallo se limpia la contraseña y el foco vuelve al primer campo con
 *    problema: no se deja la credencial escrita en pantalla ni al usuario
 *    perdido. La excepción es `UNES_REQUERIDA`: ahí las credenciales ya eran
 *    correctas y sólo falta la UNES, así que se conserva lo escrito.
 *  - La contraseña se muestra sólo si el usuario lo pide, con un control real de
 *    tipo `button` y su estado en `aria-pressed`.
 */

import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import Icon from '../components/Icon'
import Field from '../components/Field'
import { useAuth } from '../auth/useAuth'
import { ApiError } from '../services/api'
import { DEFAULT_ROUTE } from '../services/navigation'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Mensajes por código de error del backend. El texto lo decide el cliente. */
const MESSAGES = {
  INVALID_CREDENTIALS: 'El correo o la contraseña no son correctos.',
  TOO_MANY_ATTEMPTS:
    'Demasiados intentos fallidos. Por seguridad, espera unos minutos antes de volver a intentar.',
  UNES_REQUERIDA: 'Escribe la UNES con la que vas a trabajar.',
  UNES_INVALIDA: 'La UNES son tres dígitos, sin puntos ni guiones.',
  EMAIL_INVALID: 'Escribe tu correo corporativo completo (por ejemplo, nombre@gyj.com.co).',
  PASSWORD_INVALID: 'Escribe tu contraseña (mínimo 8 caracteres).',
  PASSWORD_WHITESPACE:
    'La contraseña empieza o termina con un espacio. Revisa que no se haya colado al pegarla.',
  PASSWORD_TOO_LONG: 'La contraseña supera los 128 caracteres permitidos.',
  DATABASE_UNAVAILABLE:
    'No pudimos validar tus credenciales en este momento. Intenta de nuevo en unos segundos.',
  NETWORK_ERROR:
    'No pudimos comunicarnos con el servidor. Verifica que el servicio esté en ejecución.',
  TIMEOUT: 'La operación tardó demasiado. Revisa tu conexión e intenta de nuevo.',
  INTERNAL_ERROR: 'Ocurrió un error inesperado. Intenta de nuevo o contacta a Soporte.',
  RATE_LIMITED: 'Demasiadas solicitudes seguidas. Espera un momento antes de reintentar.',
}

export default function LoginPage() {
  const { status, login, notice, clearNotice } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const emailId = useId()
  const unesId = useId()
  const passwordId = useId()

  const [correo, setCorreo] = useState('')
  const [unes, setUnes] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [emailError, setEmailError] = useState(null)
  const [unesError, setUnesError] = useState(null)
  const [passwordError, setPasswordError] = useState(null)
  const [formError, setFormError] = useState(null)

  const emailRef = useRef(null)
  const unesRef = useRef(null)
  const passwordRef = useRef(null)

  /* El aviso de sesión expirada pertenece a esta vista: se muestra una vez. */
  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(clearNotice, 12_000)
    return () => window.clearTimeout(timer)
  }, [notice, clearNotice])

  const redirectTo = location.state?.from?.pathname ?? DEFAULT_ROUTE

  const validate = useCallback(() => {
    let firstInvalid = null

    if (!correo.trim()) {
      setEmailError('Escribe tu correo corporativo.')
      firstInvalid = emailRef
    } else if (!EMAIL_PATTERN.test(correo.trim())) {
      setEmailError('El correo no tiene un formato válido (por ejemplo, nombre@gyj.com.co).')
      firstInvalid = emailRef
    } else {
      setEmailError(null)
    }

    if (!unes.trim()) {
      // Talento Humano entra sin UNES. Si el cargo no lo permite, el servidor
      // responde UNES_REQUERIDA y aquí se muestra el campo como pendiente.
      setUnesError(null)
    } else if (!/^\d{3}$/.test(unes.trim())) {
      setUnesError('La UNES son tres dígitos, sin puntos ni guiones.')
      firstInvalid = firstInvalid ?? unesRef
    } else {
      setUnesError(null)
    }

    if (!password) {
      setPasswordError('Escribe tu contraseña.')
      firstInvalid = firstInvalid ?? passwordRef
    } else if (password.length < 8) {
      setPasswordError('La contraseña debe tener al menos 8 caracteres.')
      firstInvalid = firstInvalid ?? passwordRef
    } else {
      setPasswordError(null)
    }

    return firstInvalid
  }, [correo, unes, password])

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting) return

    setFormError(null)
    const firstInvalid = validate()
    if (firstInvalid) {
      firstInvalid.current?.focus()
      return
    }

    setSubmitting(true)
    try {
      const usuario = await login(correo.trim().toLowerCase(), password, unes.trim())
      setPassword('')
      // Login correcto: se entra a la vista de inicio (o a la que se pedía).
      navigate(redirectTo, { replace: true, state: { usuario } })
    } catch (error) {
      const code = error instanceof ApiError ? error.code : 'INTERNAL_ERROR'
      const message = MESSAGES[code] ?? error?.message ?? MESSAGES.INTERNAL_ERROR

      if (code === 'UNES_REQUERIDA') {
        // Las credenciales eran correctas: sólo falta la UNES. No se borra la
        // contraseña ni se pinta el error general; se señala el campo.
        setUnesError(message)
        unesRef.current?.focus()
        return
      }

      // La contraseña no se queda escrita después de un fallo.
      setPassword('')
      setFormError({ code, message })
      passwordRef.current?.focus()
    } finally {
      setSubmitting(false)
    }
  }

  // Ya autenticado: esta vista no tiene nada que hacer.
  if (status === 'authenticated') {
    return <Navigate to={redirectTo} replace />
  }

  return (
    <div className="login">
      {/* Panel institucional: contexto, no adorno. Se oculta en móvil. */}
      <aside className="login__aside">
        <div className="login__brand">
          <span className="login__mark" aria-hidden="true">
            GJ
          </span>
          <span>
            <span className="login__brand-name">G&amp;J</span>
            <br />
            <span className="login__brand-sub">Gestión de Vacaciones</span>
          </span>
        </div>

        <div>
          <p className="login__pitch">
            Seguimiento de asignaciones de vacaciones para Talento Humano y líderes de UNES.
          </p>
          {/*<ul className="login__facts">
            <li>
              <Icon name="escudo" size={18} />
              <span>
                Las credenciales se validan contra la base institucional. No se guardan en el
                navegador.
              </span>
            </li>
            <li>
              <Icon name="bloqueo" size={18} />
              <span>
                La sesión se cierra sola por inactividad y queda registrada del lado del servidor.
              </span>
            </li>
          </ul>*/}
        </div>

        <p className="login__brand-sub">
          Acceso restringido · G&amp;J · {new Date().getFullYear()}
        </p>
      </aside>

      <main className="login__main" id="contenido">
        <div className="login__panel">
          <div className="login__panel-brand">
            <span className="login__mark" aria-hidden="true">
              GJ
            </span>
            <span>
              <span className="login__brand-name">Gestión de Vacaciones</span>
              <br />
              <span className="login__brand-sub">G&amp;J</span>
            </span>
          </div>

          <h1 className="login__title">Inicia sesión</h1>
          <p className="login__lead">
            Usa tu correo corporativo y tu contraseña institucional para entrar. Si tu perfil no es
            de Talento Humano, escribe además tu UNES.
          </p>

          {notice ? (
            <div className="alert alert--info login__form-error" role="status">
              <Icon name="alerta" size={18} />
              <span>{notice.message}</span>
            </div>
          ) : null}

          <form className="login__form" onSubmit={handleSubmit} noValidate>
            {formError ? (
              <div className="alert alert--danger login__form-error" role="alert">
                <Icon name="alerta" size={18} />
                <span>
                  <strong>No pudimos iniciar tu sesión.</strong> {formError.message}
                </span>
              </div>
            ) : null}

            <Field
              id={emailId}
              label="Correo corporativo"
              type="email"
              value={correo}
              onChange={(event) => {
                setCorreo(event.target.value)
                if (emailError) setEmailError(null)
                if (formError) setFormError(null)
              }}
              onBlur={() => {
                if (correo.trim() && !EMAIL_PATTERN.test(correo.trim())) {
                  setEmailError('El correo no tiene un formato válido.')
                }
              }}
              error={emailError}
              autoComplete="username"
              inputMode="email"
              placeholder="nombre@gyj.com.co"
              disabled={submitting}
              inputRef={emailRef}
              maxLength={150}
              required
            />

            {/* UNES y contraseña lado a lado: la UNES son tres dígitos y no
                necesita el ancho completo. Va a la izquierda de la contraseña. */}
            <div className="login__fila">
              <Field
                id={unesId}
                label="UNES"
                value={unes}
                onChange={(event) => {
                  // Sólo dígitos: la UNES es un número de tres cifras. Filtrar
                  // aquí evita que el usuario escriba algo que se va a rechazar.
                  setUnes(event.target.value.replace(/\D/g, '').slice(0, 3))
                  if (unesError) setUnesError(null)
                  if (formError) setFormError(null)
                }}
                onBlur={() => {
                  if (unes && unes.length !== 3) {
                    setUnesError('La UNES son tres dígitos (por ejemplo, 109).')
                  }
                }}
                error={unesError}
                inputMode="numeric"
                autoComplete="off"
                placeholder="109"
                disabled={submitting}
                inputRef={unesRef}
                maxLength={3}
              />

              <Field
                id={passwordId}
                label="Contraseña"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value)
                  if (passwordError) setPasswordError(null)
                  if (formError) setFormError(null)
                }}
                onKeyUp={(event) => {
                  if (typeof event.getModifierState === 'function') {
                    setCapsLock(event.getModifierState('CapsLock'))
                  }
                }}
                error={passwordError}
                hint={capsLock ? 'Bloq Mayús está activado.' : undefined}
                autoComplete="current-password"
                disabled={submitting}
                inputRef={passwordRef}
                maxLength={128}
                required
                action={
                  <button
                    type="button"
                    className="field__action"
                    onClick={() => setShowPassword((previous) => !previous)}
                    aria-pressed={showPassword}
                    aria-label={showPassword ? 'Ocultar la contraseña' : 'Mostrar la contraseña'}
                    disabled={submitting}
                  >
                    <Icon name={showPassword ? 'ocultar' : 'ver'} size={20} />
                  </button>
                }
              />
            </div>

            <button
              type="submit"
              className="btn btn--primary btn--block"
              disabled={submitting}
              aria-busy={submitting || undefined}
            >
              {submitting ? (
                <>
                  <span className="btn__spinner" aria-hidden="true" />
                  Validando…
                </>
              ) : (
                <>
                  <Icon name="playa" size={18} />
                  Entrar
                </>
              )}
            </button>

            <p className="field__hint">
              ¿No puedes entrar? Escribe a Talento Humano para verificar que tu cuenta esté activa
              en la base de datos.
            </p>
          </form>

          <p className="login__footer">
            Al entrar aceptas el uso institucional de la herramienta. Toda consulta queda
            registrada.
          </p>
        </div>
      </main>
    </div>
  )
}
