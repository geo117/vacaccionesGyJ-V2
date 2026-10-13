/**
 * Notificaciones.
 *
 * Los avisos los **redacta y guarda el servidor** cuando alguien programa
 * fechas, aprueba o rechaza. El navegador no los inventa: si el cliente mandara
 * el texto, cualquiera podría escribir el aviso que quisiera en la bandeja de
 * los demás.
 *
 * Qué ve cada quien lo decide el backend en el `WHERE` de la consulta:
 *  - Talento Humano ve todas.
 *  - Los demás ven las de su cargo y las dirigidas a Talento Humano.
 *
 * La tabla `dbo.notificaciones` no tiene columna de "leída", así que no se
 * ofrece marcarlas: sería un estado que se pierde al recargar y que la base no
 * respalda.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import EmptyState from '../components/EmptyState'
import Icon from '../components/Icon'
import { ApiError, notificacionesApi } from '../services/api'
import { useAuth } from '../auth/useAuth'
import { formatDateTime } from '../utils/fechas'

/** Deduce el tono del aviso a partir de lo que dice el servidor. */
function tonoDelAviso(mensaje) {
  const texto = mensaje.toLowerCase()
  if (texto.includes('rechaz')) return 'danger'
  if (texto.includes('aprob')) return 'ok'
  if (texto.includes('asign')) return 'info'
  return 'info'
}

const ETIQUETA_TONO = {
  danger: { chip: 'danger', texto: 'Rechazo', icono: 'rechazar' },
  ok: { chip: 'ok', texto: 'Aprobación', icono: 'aprobar' },
  info: { chip: 'info', texto: 'Asignación', icono: 'editarFechas' },
}

export default function NotificacionesPage() {
  const { esTalentoHumano } = useAuth()
  const [avisos, setAvisos] = useState([])
  const [mios, setMios] = useState([])
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState(null)
  const [filtro, setFiltro] = useState('todas')

  /**
   * Dos fuentes distintas, a propósito:
   *
   *  - `listar()` es la bandeja general. Los avisos de asignación, aprobación y
   *    rechazo son **sólo para Talento Humano**; para los demás cargos el
   *    servidor devuelve una lista vacía.
   *  - `mias()` son los avisos dirigidos a esta persona (`usuario_id`). Ahí
   *    llegan los que Talento Humano genera al modificar sus fechas, aprobarlas
   *    o rechazarlas.
   *
   * Se piden las dos en paralelo y se juntan sin repetir.
   */
  const traerAvisos = useCallback(async () => {
    try {
      const [generales, personales] = await Promise.all([
        notificacionesApi.listar(),
        notificacionesApi.mias(),
      ])
      const porId = new Map()
      for (const aviso of [...(generales.notificaciones ?? []), ...(personales.notificaciones ?? [])]) {
        porId.set(aviso.id, aviso)
      }
      const lista = [...porId.values()].sort(
        (a, b) => String(b.fechaRegistro ?? '').localeCompare(String(a.fechaRegistro ?? '')),
      )
      return { avisos: lista, mios: personales.notificaciones ?? [], error: null }
    } catch (error) {
      return {
        avisos: null,
        mios: [],
        error:
          error instanceof ApiError
            ? error.message
            : 'No pudimos cargar las notificaciones.',
      }
    }
  }, [])

  const recargar = useCallback(async () => {
    const { avisos: lista, mios: personales, error } = await traerAvisos()
    if (lista) {
      setAvisos(lista)
      setMios(personales)
    }
    setErrorCarga(error)
    setCargando(false)
  }, [traerAvisos])

  useEffect(() => {
    let vigente = true
    traerAvisos().then(({ avisos: lista, mios: personales, error }) => {
      if (!vigente) return
      if (lista) {
        setAvisos(lista)
        setMios(personales)
      }
      setErrorCarga(error)
      setCargando(false)
    })
    return () => {
      vigente = false
    }
  }, [traerAvisos])

  const idsMios = useMemo(() => new Set(mios.map((a) => a.id)), [mios])

  const filtrados = useMemo(
    () => (filtro === 'todas' ? avisos : avisos.filter((a) => tonoDelAviso(a.mensaje) === filtro)),
    [avisos, filtro],
  )

  const conteo = useMemo(() => {
    const base = { ok: 0, danger: 0, info: 0 }
    for (const aviso of avisos) base[tonoDelAviso(aviso.mensaje)] += 1
    return base
  }, [avisos])

  const FILTROS = [
    { value: 'todas', label: `Todas (${avisos.length})` },
    { value: 'info', label: `Asignaciones (${conteo.info})` },
    { value: 'ok', label: `Aprobaciones (${conteo.ok})` },
    { value: 'danger', label: `Rechazos (${conteo.danger})` },
  ]

  return (
    <>
      <header className="page__header">
        <div>
          <h1 className="page__title">Notificaciones</h1>
          <p className="page__lead">
            Avisos generados por las acciones sobre las asignaciones: fechas programadas,
            aprobaciones y rechazos.
          </p>
        </div>
        <div className="page__actions">
          <Button variant="outline-secondary" onClick={recargar} disabled={cargando}>
            <Icon name="buscar" size={18} />
            Actualizar
          </Button>
        </div>
      </header>

      {errorCarga ? (
        <Alert variant="danger" className="d-flex align-items-start gap-2" role="alert">
          <Icon name="error" size={18} />
          <span>{errorCarga}</span>
        </Alert>
      ) : null}

      <section className="card" aria-labelledby="bandeja-titulo">
        <header className="card__header">
          <div>
            <h2 className="card__title" id="bandeja-titulo">
              Bandeja de notificaciones
            </h2>
            <p className="card__subtitle">
              {cargando
                ? 'Consultando la base de datos…'
                : avisos.length === 0
                  ? esTalentoHumano
                    ? 'Todavía no hay avisos registrados.'
                    : 'No tienes avisos por ahora.'
                  : `${avisos.length} ${avisos.length === 1 ? 'aviso' : 'avisos'} · ${conteo.info} de asignación, ${conteo.ok} de aprobación y ${conteo.danger} de rechazo.`}
            </p>
          </div>
        </header>

        {avisos.length > 0 ? (
          <div className="card__body" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="filtros-chips" role="group" aria-label="Filtrar notificaciones">
              {FILTROS.map((opcion) => (
                <button
                  key={opcion.value}
                  type="button"
                  className="chip chip--neutral filtros-chips__boton"
                  aria-pressed={filtro === opcion.value}
                  onClick={() => setFiltro(opcion.value)}
                >
                  {opcion.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="card__body card__body--flush">
          {filtrados.length > 0 ? (
            <ul className="feed">
              {filtrados.map((aviso) => {
                const tono = tonoDelAviso(aviso.mensaje)
                const meta = ETIQUETA_TONO[tono]
                return (
                  <li className="feed__item" key={aviso.id}>
                    <span className={`feed__icon feed__icon--${tono}`} aria-hidden="true">
                      <Icon name={meta.icono} size={18} />
                    </span>

                    <div className="feed__body">
                      <p className="feed__title">
                        <span className={`chip chip--${meta.chip}`}>{meta.texto}</span>
                        {aviso.unes ? (
                          <span className="chip chip--neutral">{aviso.unes}</span>
                        ) : null}
                        {idsMios.has(aviso.id) ? (
                          <span className="chip chip--info">Para ti</span>
                        ) : null}
                      </p>
                      <p className="feed__text">{aviso.mensaje}</p>
                      <p className="feed__meta">
                        {formatDateTime(aviso.fechaRegistro)} · Aviso #{aviso.id}
                        {aviso.fechaUpdate && aviso.fechaUpdate !== aviso.fechaRegistro
                          ? ` · actualizado ${formatDateTime(aviso.fechaUpdate)}`
                          : ''}
                      </p>
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            <EmptyState
              icon="notificaciones"
              title={
                cargando
                  ? 'Consultando las notificaciones…'
                  : avisos.length === 0
                    ? 'Sin notificaciones por ahora'
                    : 'Ningún aviso de ese tipo'
              }
              text={
                cargando
                  ? 'Un momento.'
                  : avisos.length === 0
                    ? esTalentoHumano
                      ? 'Cada vez que se programen fechas, se apruebe o se rechace una asignación, el aviso aparecerá aquí.'
                      : 'Aquí verás los avisos que Talento Humano genere al modificar tus fechas, aprobarlas o rechazarlas.'
                    : 'Prueba con otro filtro para ver el resto de los avisos.'
              }
              action={
                avisos.length > 0 && filtro !== 'todas' ? (
                  <Button variant="outline-secondary" onClick={() => setFiltro('todas')}>
                    Ver todas
                  </Button>
                ) : null
              }
            />
          )}
        </div>
      </section>

      <p className="field__hint" style={{ marginTop: 'var(--space-4)' }}>
        <Icon name="info" size={14} /> Los avisos los genera el servidor en{' '}
        <code>dbo.notificaciones</code> y se filtran según tu cargo.
      </p>
    </>
  )
}
