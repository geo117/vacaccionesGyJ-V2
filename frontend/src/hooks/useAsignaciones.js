/**
 * Datos de las asignaciones: carga y escritura contra la API.
 *
 * Antes esta vista trabajaba sobre `mock/`. Ahora el origen es
 * `dbo.asignacion_vacaciones` y **el servidor es el que calcula**: los días, el
 * total y la fecha de regreso se derivan de las fechas en el backend y vuelven
 * calculados. La interfaz los muestra, no los inventa.
 *
 * Por eso este hook no lleva estado de períodos en el cliente: tras guardar, se
 * reemplaza la fila con la que devolvió el servidor. Si se "adivinara" el
 * resultado en el navegador, la pantalla y la base podrían discrepar.
 */

import { useCallback, useEffect, useState } from 'react'
import { ApiError, asignacionesApi } from '../services/api'

/** Mensajes para la persona, por código de error del backend. */
export const MENSAJES_ASIGNACIONES = {
  PERIODOS_CRUZADOS: 'Dos períodos se cruzan. Revisa las fechas antes de guardar.',
  RANGO_INVERTIDO: 'La fecha de fin de un período es anterior a la de inicio.',
  PERIODO_INCOMPLETO: 'Cada período necesita fecha de inicio y de fin.',
  SIN_PERIODOS: 'Programa al menos un período de vacaciones.',
  MOTIVO_REQUERIDO: 'Escribe el motivo del rechazo antes de continuar.',
  DECISION_INVALIDA: 'La decisión debe ser aprobar o rechazar.',
  ASIGNACION_NO_EXISTE: 'La asignación ya no existe. Actualiza la lista.',
  FORBIDDEN_ROLE: 'Aprobar o rechazar es exclusivo de Talento Humano.',
  CAMPO_LARGO: 'Uno de los textos supera el largo permitido.',
  CAMPO_REQUERIDO: 'Falta un dato obligatorio.',
  FECHA_INVALIDA: 'Una de las fechas no es válida.',
  DATABASE_UNAVAILABLE: 'La base de datos no respondió. Intenta de nuevo en unos segundos.',
  NETWORK_ERROR: 'No pudimos comunicarnos con el servidor. Verifica que esté en ejecución.',
}

/** Traduce un error de la API al mensaje que ve la persona. */
export function mensajeDeError(error) {
  if (error instanceof ApiError) {
    return MENSAJES_ASIGNACIONES[error.code] ?? error.message
  }
  return 'Ocurrió un error inesperado. Intenta de nuevo.'
}

export default function useAsignaciones() {
  const [filas, setFilas] = useState([])
  const [origen, setOrigen] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState(null)

  /** Trae la lista sin tocar el estado (ver AdministracionPage). */
  const traerAsignaciones = useCallback(async () => {
    try {
      const datos = await asignacionesApi.listar()
      return {
        filas: datos.asignaciones ?? [],
        // "vista" = plantilla de la UNES desde el servidor corporativo;
        // "local" = sólo las asignaciones registradas, porque la vista no
        // respondió. La pantalla avisa cuando es "local".
        origen: datos.origen ?? null,
        error: null,
      }
    } catch (error) {
      return { filas: null, origen: null, error: mensajeDeError(error) }
    }
  }, [])

  const recargar = useCallback(async () => {
    const { filas: lista, origen: nuevoOrigen, error } = await traerAsignaciones()
    if (lista) {
      setFilas(lista)
      setOrigen(nuevoOrigen)
    }
    setErrorCarga(error)
    setCargando(false)
  }, [traerAsignaciones])

  useEffect(() => {
    let vigente = true
    traerAsignaciones().then(({ filas: lista, origen: nuevoOrigen, error }) => {
      if (!vigente) return
      if (lista) {
        setFilas(lista)
        setOrigen(nuevoOrigen)
      }
      setErrorCarga(error)
      setCargando(false)
    })
    return () => {
      vigente = false
    }
  }, [traerAsignaciones])

  /**
   * Guarda los períodos de una asignación.
   *
   * La fila se reemplaza con lo que devolvió el servidor: si el cálculo del
   * navegador y el de la base no coincidieran, gana el de la base.
   */
  const guardarPeriodos = useCallback(async (id, datos) => {
    const respuesta = await asignacionesApi.guardarPeriodos(id, datos)
    const actualizada = respuesta.asignacion
    if (actualizada) {
      setFilas((previas) => previas.map((fila) => (fila.id === id ? actualizada : fila)))
    }
    return actualizada
  }, [])

  /** Registra la decisión y devuelve la asignación actualizada. */
  const registrarDecision = useCallback(async (id, datos) => {
    const respuesta = await asignacionesApi.decidir(id, datos)
    const actualizada = respuesta.asignacion
    if (actualizada) {
      setFilas((previas) => previas.map((fila) => (fila.id === id ? actualizada : fila)))
    }
    return actualizada
  }, [])

  /** Crea una asignación nueva y la agrega al principio de la lista. */
  const crearAsignacion = useCallback(async (datos) => {
    const respuesta = await asignacionesApi.crear(datos)
    const creada = respuesta.asignacion
    if (creada) setFilas((previas) => [creada, ...previas])
    return creada
  }, [])

  return {
    filas,
    origen,
    cargando,
    errorCarga,
    recargar,
    guardarPeriodos,
    registrarDecision,
    crearAsignacion,
  }
}
