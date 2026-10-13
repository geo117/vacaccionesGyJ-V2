/**
 * Resumen general.
 *
 * Dos indicadores y el consolidado **de todos los empleados** con sus datos
 * actuales: la totalidad de las cuentas registradas en `dbo.Usuarios`, cruzadas
 * con las asignaciones de cada una.
 *
 * Todo lo que se ve sale de `GET /api/resumen`, que resuelve el cruce con un
 * `LEFT JOIN` en la base. Quien no tiene asignaciones aparece igual, con ceros:
 * son justamente a quienes hay que mirar.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Table from 'react-bootstrap/Table'
import EmptyState from '../components/EmptyState'
import Icon from '../components/Icon'
import StatusChip from '../components/StatusChip'
import { ApiError, resumenApi } from '../services/api'
import { formatDateTime, NUMERO } from '../utils/fechas'

const CARGO_TALENTO_HUMANO = 'talento humano'

function esTalentoHumano(empleado) {
  return String(empleado?.cargo || '').trim().toLowerCase() === CARGO_TALENTO_HUMANO
}

export default function ResumenPage() {
  const [datos, setDatos] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState(null)
  const [busqueda, setBusqueda] = useState('')

  const traerResumen = useCallback(async () => {
    try {
      return { datos: await resumenApi.obtener(), error: null }
    } catch (error) {
      return {
        datos: null,
        error:
          error instanceof ApiError ? error.message : 'No pudimos cargar el resumen.',
      }
    }
  }, [])

  const recargar = useCallback(async () => {
    const { datos: nuevos, error } = await traerResumen()
    if (nuevos) setDatos(nuevos)
    setErrorCarga(error)
    setCargando(false)
  }, [traerResumen])

  useEffect(() => {
    let vigente = true
    traerResumen().then(({ datos: nuevos, error }) => {
      if (!vigente) return
      if (nuevos) setDatos(nuevos)
      setErrorCarga(error)
      setCargando(false)
    })
    return () => {
      vigente = false
    }
  }, [traerResumen])

  const totales = datos?.totales ?? {}
  const empleados = useMemo(() => datos?.empleados ?? [], [datos])

  const visibles = useMemo(() => {
    const needle = busqueda.trim().toLowerCase()
    if (!needle) return empleados
    return empleados.filter(
      (e) =>
        e.nombre.toLowerCase().includes(needle) ||
        e.correo.toLowerCase().includes(needle) ||
        (e.cargo || '').toLowerCase().includes(needle),
    )
  }, [empleados, busqueda])

  const indicadores = [
    {
      id: 'usuarios',
      label: 'Usuarios registrados',
      value: totales.usuarios ?? 0,
      tone: 'info',
      icon: 'empleado',
      foot: `${empleados.filter(esTalentoHumano).length} con cargo de Talento Humano`,
    },
    {
      id: 'asignaciones',
      label: 'Asignaciones registradas',
      value: totales.asignaciones ?? 0,
      tone: 'info',
      icon: 'asignaciones',
      foot: `${NUMERO.format(totales.diasProgramados ?? 0)} días programados en total`,
    },
    {
      id: 'pendientes',
      label: 'Pendientes de revisión',
      value: totales.pendientes ?? 0,
      tone: 'warn',
      icon: 'pendiente',
      foot: 'Requieren una decisión de Talento Humano',
    },
    {
      id: 'aprobadas',
      label: 'Aprobadas',
      value: totales.aprobadas ?? 0,
      tone: 'ok',
      icon: 'aprobada',
      foot: `${NUMERO.format(totales.rechazadas ?? 0)} rechazadas`,
    },
  ]

  return (
    <>
      <header className="page__header">
        <div>
          <h1 className="page__title">Resumen general</h1>
          <p className="page__lead">
            Estado de las asignaciones y consolidado de todos los empleados registrados, con sus
            datos actuales.
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

      <section aria-labelledby="kpis-titulo" className="grid grid--kpi">
        <h2 className="visually-hidden" id="kpis-titulo">
          Indicadores generales
        </h2>
        {indicadores.map((kpi) => (
          <article className={`kpi kpi--${kpi.tone}`} key={kpi.id}>
            <p className="kpi__label">
              <Icon name={kpi.icon} size={16} />
              {kpi.label}
            </p>
            <p className="kpi__value tabular">
              {cargando ? '—' : NUMERO.format(kpi.value)}
            </p>
            <p className="kpi__foot">{kpi.foot}</p>
          </article>
        ))}
      </section>

      <section className="card" style={{ marginTop: 'var(--space-6)' }} aria-labelledby="empleados-titulo">
        <header className="card__header">
          <div>
            <h2 className="card__title" id="empleados-titulo">
              Consolidado por empleado
            </h2>
            <p className="card__subtitle">
              {cargando
                ? 'Consultando la base de datos…'
                : `${NUMERO.format(visibles.length)} de ${NUMERO.format(empleados.length)} empleados con sus asignaciones.`}
            </p>
          </div>
          <div className="toolbar__field" style={{ minWidth: 260 }}>
            <label className="visually-hidden" htmlFor="buscar-empleado">
              Buscar empleado
            </label>
            <div className="field__control">
              <input
                id="buscar-empleado"
                className="field__input"
                type="search"
                value={busqueda}
                onChange={(event) => setBusqueda(event.target.value)}
                placeholder="Nombre, correo o cargo"
                autoComplete="off"
              />
              <span
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  right: 'var(--space-4)',
                  display: 'inline-flex',
                  color: 'var(--ink-muted)',
                }}
              >
                <Icon name="buscarPersona" size={18} />
              </span>
            </div>
          </div>
        </header>

        <div className="card__body card__body--flush">
          {visibles.length > 0 ? (
            <Table className="data" borderless responsive>
              <caption className="visually-hidden">
                Empleados registrados con su correo, cargo, número de asignaciones, días totales y
                estado de sus solicitudes.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Empleado</th>
                  <th scope="col">Correo</th>
                  <th scope="col">Cargo</th>
                  <th scope="col" className="numeric">
                    Asignaciones
                  </th>
                  <th scope="col" className="numeric">
                    Días totales
                  </th>
                  <th scope="col">Estado</th>
                  <th scope="col">Última actualización</th>
                </tr>
              </thead>
              <tbody>
                {visibles.map((empleado) => (
                  <tr key={empleado.usuarioId}>
                    <td>{empleado.nombre}</td>
                    <td>{empleado.correo}</td>
                    <td>
                      {esTalentoHumano(empleado) ? (
                        <StatusChip estado="ok" label={empleado.cargo} />
                      ) : (
                        empleado.cargo || '—'
                      )}
                    </td>
                    <td className="numeric tabular">{NUMERO.format(empleado.asignaciones)}</td>
                    <td className="numeric tabular">{NUMERO.format(empleado.diasTotales)}</td>
                    <td>
                      {empleado.asignaciones === 0 ? (
                        <span className="chip chip--neutral">Sin asignaciones</span>
                      ) : (
                        <div className="d-flex align-items-center gap-2">
                          {empleado.pendientes > 0 ? (
                            <StatusChip estado="pendiente" label={`${empleado.pendientes} pend.`} />
                          ) : null}
                          {empleado.aprobadas > 0 ? (
                            <StatusChip estado="aprobada" label={`${empleado.aprobadas} aprob.`} />
                          ) : null}
                          {empleado.rechazadas > 0 ? (
                            <StatusChip estado="rechazada" label={`${empleado.rechazadas} rech.`} />
                          ) : null}
                        </div>
                      )}
                    </td>
                    <td>
                      {empleado.ultimaActualizacion
                        ? formatDateTime(empleado.ultimaActualizacion)
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState
              icon="empleado"
              title={cargando ? 'Consultando los empleados…' : 'Ningún empleado coincide'}
              text={
                cargando
                  ? 'Un momento.'
                  : busqueda.trim()
                    ? 'Prueba con otro nombre, correo o cargo.'
                    : 'Todavía no hay usuarios registrados en la base de datos.'
              }
              action={
                busqueda.trim() ? (
                  <Button variant="outline-secondary" onClick={() => setBusqueda('')}>
                    Limpiar búsqueda
                  </Button>
                ) : null
              }
            />
          )}
        </div>
      </section>
    </>
  )
}
