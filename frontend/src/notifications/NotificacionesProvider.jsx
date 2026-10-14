/**
 * Estado compartido de las notificaciones.
 *
 * Existe por una razón concreta: el contador del sidebar y la bandeja de
 * `NotificacionesPage` tienen que ser **el mismo dato**. Si cada uno pidiera la
 * lista por su cuenta, el número del menú y lo que se ve al abrirlo podrían
 * discrepar.
 *
 * Qué se considera «pendiente»
 * ---------------------------
 * `dbo.notificaciones` **no tiene columna de leída**, y añadir estado de lectura
 * en el navegador es una decisión consciente: se guarda en `localStorage`, con
 * una clave por usuario, el conjunto de ids que esa persona ya vio. El contador
 * son los avisos que no están en ese conjunto. No es una verdad del servidor y
 * no se pretende que lo sea: si la persona entra desde otro equipo, vuelve a
 * verlos como pendientes. La alternativa —inventar una columna en la base— es
 * una decisión de esquema que no corresponde tomar aquí.
 *
 * Por qué hay dos componentes
 * ---------------------------
 * El estado depende de **quién** entró, así que el componente que lo guarda se
 * monta con `key={userId}`: al cambiar de usuario React lo desmonta y lo vuelve a
 * crear con el estado en cero. Es la forma de reiniciar estado por un cambio de
 * identidad sin un efecto que llame a `setState` y provoque un render de más.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, notificacionesApi } from '../services/api'
import { useAuth } from '../auth/useAuth'
import { NotificacionesContext } from './context'

/** Prefijo de la clave por usuario en `localStorage`. */
const CLAVE_VISTAS = 'gv.notificaciones.vistas'

/** Techo de ids recordados por usuario: evita que la clave crezca sin fin. */
const MAX_VISTAS = 500

function leerVistas(userId) {
  if (!userId) return new Set()
  try {
    const crudo = window.localStorage.getItem(`${CLAVE_VISTAS}.${userId}`)
    const lista = crudo ? JSON.parse(crudo) : []
    if (!Array.isArray(lista)) return new Set()
    return new Set(lista.map((valor) => Number(valor)).filter(Number.isFinite))
  } catch {
    // Modo privado o almacenamiento bloqueado: todo vuelve a contar como
    // pendiente, que es la lectura segura.
    return new Set()
  }
}

function guardarVistas(userId, ids) {
  if (!userId) return
  try {
    window.localStorage.setItem(
      `${CLAVE_VISTAS}.${userId}`,
      JSON.stringify([...ids].slice(-MAX_VISTAS)),
    )
  } catch {
    /* sin almacenamiento, el contador se reinicia en la próxima recarga */
  }
}

/** Une la bandeja general y los avisos propios, sin repetir y del más nuevo. */
function mezclarAvisos(generales, personales) {
  const porId = new Map()
  for (const aviso of [
    ...(generales?.notificaciones ?? []),
    ...(personales?.notificaciones ?? []),
  ]) {
    porId.set(aviso.id, aviso)
  }
  return [...porId.values()].sort((a, b) =>
    String(b.fechaRegistro ?? '').localeCompare(String(a.fechaRegistro ?? '')),
  )
}

/** Pide las dos bandejas y devuelve la lista ya mezclada. No toca el estado. */
async function pedirAvisos() {
  const [generales, personales] = await Promise.all([
    notificacionesApi.listar(),
    notificacionesApi.mias(),
  ])
  return {
    avisos: mezclarAvisos(generales, personales),
    mios: personales?.notificaciones ?? [],
  }
}

/**
 * Estado de las notificaciones de **una** sesión.
 *
 * Se monta con `key={userId}`, así que `userId` no cambia mientras vive: es lo
 * que permite inicializar el estado con `useState` y no tener que reiniciarlo.
 */
function NotificacionesDeSesion({ userId, activo, children }) {
  const [avisos, setAvisos] = useState([])
  const [mios, setMios] = useState([])
  const [vistas, setVistas] = useState(() => leerVistas(userId))
  /* Nace en `true` cuando hay sesión: el efecto ya va a pedir los avisos, así que
     no hace falta encender el indicador con un `setState` dentro del efecto. */
  const [cargando, setCargando] = useState(activo)
  const [errorCarga, setErrorCarga] = useState(null)

  const avisosRef = useRef([])
  // Número de la última petición lanzada: una respuesta vieja no puede pisar a
  // una nueva ni dejar el estado a medias.
  const peticionRef = useRef(0)

  const aplicar = useCallback((datos) => {
    avisosRef.current = datos.avisos
    setAvisos(datos.avisos)
    setMios(datos.mios)
    setErrorCarga(null)
  }, [])

  const anotarError = useCallback((error) => {
    setErrorCarga(
      error instanceof ApiError ? error.message : 'No pudimos cargar las notificaciones.',
    )
  }, [])

  /** Recarga pedida por la interfaz (el botón «Actualizar»). */
  const recargar = useCallback(async () => {
    if (!activo || !userId) return null

    const numero = peticionRef.current + 1
    peticionRef.current = numero
    setCargando(true)
    try {
      const datos = await pedirAvisos()
      if (numero !== peticionRef.current) return null
      aplicar(datos)
      return datos.avisos
    } catch (error) {
      if (numero === peticionRef.current) anotarError(error)
      return null
    } finally {
      if (numero === peticionRef.current) setCargando(false)
    }
  }, [activo, userId, aplicar, anotarError])

  /* Carga inicial: todo lo que escribe estado vive en los callbacks de la
     promesa, no en el cuerpo del efecto, para no encadenar renders. */
  useEffect(() => {
    if (!activo) return undefined

    let vigente = true
    const numero = peticionRef.current + 1
    peticionRef.current = numero

    pedirAvisos()
      .then((datos) => {
        if (vigente && numero === peticionRef.current) aplicar(datos)
      })
      .catch((error) => {
        if (vigente && numero === peticionRef.current) anotarError(error)
      })
      .finally(() => {
        if (vigente && numero === peticionRef.current) setCargando(false)
      })

    return () => {
      // Lo que llegue tarde ya no interesa: este componente puede estar
      // desmontado porque la persona cambió de usuario.
      vigente = false
      peticionRef.current += 1
    }
  }, [activo, aplicar, anotarError])

  /* Marca como vistas todas las que están cargadas: es lo que apaga el contador
     al abrir la bandeja. */
  const marcarVistas = useCallback(() => {
    const ids = avisosRef.current.map((aviso) => aviso.id)
    if (ids.length === 0) return
    setVistas((previas) => {
      if (ids.every((valor) => previas.has(valor))) return previas
      const siguientes = new Set(previas)
      for (const valor of ids) siguientes.add(valor)
      guardarVistas(userId, siguientes)
      return siguientes
    })
  }, [userId])

  const idsMios = useMemo(() => new Set(mios.map((aviso) => aviso.id)), [mios])

  const pendientes = useMemo(
    () => avisos.reduce((total, aviso) => (vistas.has(aviso.id) ? total : total + 1), 0),
    [avisos, vistas],
  )

  const value = useMemo(
    () => ({
      avisos,
      mios,
      idsMios,
      cargando,
      errorCarga,
      pendientes,
      recargar,
      marcarVistas,
    }),
    [avisos, mios, idsMios, cargando, errorCarga, pendientes, recargar, marcarVistas],
  )

  return <NotificacionesContext.Provider value={value}>{children}</NotificacionesContext.Provider>
}

export default function NotificacionesProvider({ children }) {
  const { status, user } = useAuth()
  const userId = user?.id ?? null

  return (
    <NotificacionesDeSesion
      // Cambiar de identidad reinicia el estado: no queda nada del usuario
      // anterior, ni la lista ni el contador.
      key={userId ?? 'anonimo'}
      userId={userId}
      activo={status === 'authenticated' && Boolean(userId)}
    >
      {children}
    </NotificacionesDeSesion>
  )
}
