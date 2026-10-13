/**
 * Asignaciones de vacaciones.
 *
 * La tabla es **la plantilla de la UNES**: una fila por colaborador de la vista
 * corporativa `PBI_Colaborador_Vacaciones`, con la asignación que tenga (o
 * ninguna). Los que todavía no tienen fechas aparecen igual, porque son
 * justamente a quienes hay que programárselas.
 *
 * Columnas y de dónde sale cada dato:
 *   Desc. Unes     ← DescCO
 *   Colaborador    ← Empleado
 *   Identificación ← cedula
 *   UNES           ← IDCia_CO
 *   Cargo          ← Cargo
 *   Estado         ← pendiente hasta que se apruebe o rechace
 *   Días a corte   ← dias_vacaciones_corteDic
 *   Días asignados ← el total de los períodos programados
 *   Días a usar    ← días asignados − días a corte, con semáforo
 *
 * El filtro por UNES lo aplica el **servidor** con la UNES de la sesión: aquí no
 * llega la plantilla de otras UNES, así que no hay nada que filtrar en el
 * navegador.
 *
 * Si la vista corporativa no responde, el servidor degrada al listado local de
 * asignaciones y lo dice en `origen`; la pantalla lo avisa.
 */

import { useDeferredValue, useId, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import OverlayTrigger from 'react-bootstrap/OverlayTrigger'
import Popover from 'react-bootstrap/Popover'
import Table from 'react-bootstrap/Table'
import Swal from 'sweetalert2'
import AsignarPeriodosModal from '../components/AsignarPeriodosModal'
import DecisionModal from '../components/DecisionModal'
import EmpleadoDetalleModal from '../components/EmpleadoDetalleModal'
import EmptyState from '../components/EmptyState'
import Icon from '../components/Icon'
import NuevaAsignacionModal from '../components/NuevaAsignacionModal'
import StatusChip from '../components/StatusChip'
import { useAuth } from '../auth/useAuth'
import useAsignaciones, { mensajeDeError } from '../hooks/useAsignaciones'
import { NUMERO } from '../utils/fechas'
import { semaforoDiasAUsar } from '../utils/periodos'
import { buildAssignmentsCsv, buildReportFilename, downloadCsv } from '../utils/reporte'

const ESTADOS = [
  { value: 'todas', label: 'Todos los estados' },
  { value: 'pendiente', label: 'Pendientes' },
  { value: 'aprobada', label: 'Aprobadas' },
  { value: 'rechazada', label: 'Rechazadas' },
]

const SWAL_BASE = {
  confirmButtonColor: '#16456d',
  cancelButtonColor: '#5a6b7b',
  customClass: { popup: 'gv-swal' },
}

/** Un decimal siempre, incluso en 0: `0.0` y no `0`. */
const UN_DECIMAL = new Intl.NumberFormat('es-CO', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

/**
 * Celda de «Días a usar».
 *
 * El valor llega ya calculado por el servidor (días a corte − días asignados).
 * Aquí sólo se pinta. El color no es la única señal: lleva la etiqueta del
 * semáforo para lectores de pantalla y un `title` con la operación que produjo
 * el número, para que el dato sea interpretable sin depender del color.
 */
function CeldaDiasAUsar({ valor, asignados, corte }) {
  const { tono, etiqueta } = semaforoDiasAUsar(valor)
  const titulo = `${etiqueta}: ${UN_DECIMAL.format(corte)} días a corte − ${UN_DECIMAL.format(asignados)} asignados = ${UN_DECIMAL.format(valor)}`
  return (
    <span className={`dias-usar dias-usar--${tono} tabular`} title={titulo}>
      <span className="visually-hidden">{etiqueta}: </span>
      {UN_DECIMAL.format(valor)}
    </span>
  )
}

/** Cuerpo de la alerta del motivo, con nodos de texto (nunca HTML interpolado). */
function construirCuerpoMotivo(motivo, fila) {
  const contenedor = document.createElement('div')
  contenedor.style.textAlign = 'left'

  const texto = document.createElement('p')
  texto.textContent = motivo
  texto.style.margin = '0'

  const pie = document.createElement('p')
  pie.textContent = `${fila.empleado}${fila.id ? ` · Radicado ${fila.id}` : ''}`
  pie.style.margin = 'var(--space-3) 0 0'
  pie.style.fontSize = 'var(--text-xs)'
  pie.style.color = 'var(--ink-muted)'

  contenedor.append(texto, pie)
  return contenedor
}

export default function AsignacionesPage() {
  const searchId = useId()
  const stateId = useId()
  const unesId = useId()

  const { puedeAprobar, unes } = useAuth()
  const {
    filas,
    origen,
    cargando,
    errorCarga,
    recargar,
    guardarPeriodos,
    registrarDecision,
    crearAsignacion,
  } = useAsignaciones()

  const [query, setQuery] = useState('')
  const [estado, setEstado] = useState('todas')
  const [filtroUnes, setFiltroUnes] = useState('todas')

  const [empleadoAbierto, setEmpleadoAbierto] = useState(null)
  const [fechasAbiertas, setFechasAbiertas] = useState(null)
  const [decisionAbierta, setDecisionAbierta] = useState(null)
  const [nuevaAbierta, setNuevaAbierta] = useState(false)
  const [nuevaInicial, setNuevaInicial] = useState(null)
  const [guardando, setGuardando] = useState(false)
  const [menuAbierto, setMenuAbierto] = useState(null)

  const deferredQuery = useDeferredValue(query)

  const unesDisponibles = useMemo(() => {
    const set = new Set(filas.map((row) => row.unes).filter(Boolean))
    return [...set].sort((a, b) => a.localeCompare(b, 'es'))
  }, [filas])

  const filtradas = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    return filas.filter((row) => {
      if (estado !== 'todas' && row.estado !== estado) return false
      if (filtroUnes !== 'todas' && row.unes !== filtroUnes) return false
      if (!needle) return true
      return (
        String(row.empleado || '').toLowerCase().includes(needle) ||
        String(row.identificacion || '').includes(needle) ||
        String(row.id ?? '').includes(needle) ||
        String(row.cargo || '').toLowerCase().includes(needle) ||
        String(row.descUnes || '').toLowerCase().includes(needle)
      )
    })
  }, [filas, deferredQuery, estado, filtroUnes])

  const hayFiltros = query.trim() !== '' || estado !== 'todas' || filtroUnes !== 'todas'

  const resumen = useMemo(() => {
    const conAsignacion = filtradas.filter((f) => !f.sinAsignacion)
    return {
      total: filtradas.length,
      conAsignacion: conAsignacion.length,
      sinAsignacion: filtradas.length - conAsignacion.length,
      enContra: filtradas.filter((f) => Number(f.diasAUsar) < -3).length,
    }
  }, [filtradas])

  function limpiarFiltros() {
    setQuery('')
    setEstado('todas')
    setFiltroUnes('todas')
  }

  /* -- Reporte ------------------------------------------------------------- */

  async function handleDescargar() {
    if (filtradas.length === 0) {
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'info',
        title: 'No hay registros que exportar',
        text: 'Ajusta la búsqueda o los filtros para que la tabla tenga filas.',
        confirmButtonText: 'Entendido',
      })
      return
    }

    const confirmacion = await Swal.fire({
      ...SWAL_BASE,
      icon: 'question',
      title: 'Descargar el reporte',
      html: `Se exportarán <strong>${NUMERO.format(filtradas.length)}</strong> ${filtradas.length === 1 ? 'colaborador' : 'colaboradores'
        }${hayFiltros ? ' (con los filtros aplicados)' : ''}, con sus períodos y días calculados.`,
      showCancelButton: true,
      confirmButtonText: 'Descargar CSV',
      cancelButtonText: 'Cancelar',
      reverseButtons: true,
      focusCancel: true,
    })
    if (!confirmacion.isConfirmed) return

    Swal.fire({
      ...SWAL_BASE,
      title: 'Generando el reporte…',
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    })

    try {
      const { filename, bytes } = downloadCsv(
        buildReportFilename('csv'),
        buildAssignmentsCsv(filtradas),
      )
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: 'Reporte descargado',
        html: `<strong>${filename}</strong><br /><span style="color:#5a6b7b">${NUMERO.format(
          Math.max(1, Math.round(bytes / 1024)),
        )} kB · ábrelo con Excel o Google Sheets</span>`,
        confirmButtonText: 'Listo',
      })
    } catch {
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudo generar el reporte',
        text: 'Intenta de nuevo. Si el problema sigue, contacta a Soporte.',
        confirmButtonText: 'Entendido',
      })
    }
  }

  /* -- Acciones ------------------------------------------------------------ */

  /** Abre el modal de fechas: programa sobre la asignación, o crea una nueva. */
  function abrirFechas(fila) {
    if (fila.sinAsignacion) {
      // Colaborador de la UNES sin asignación: el modal de creación arranca con
      // sus datos de la vista, así no hay que volver a teclearlos.
      setNuevaInicial(fila)
      setNuevaAbierta(true)
      return
    }
    setFechasAbiertas(fila)
  }

  async function handleCrear(datos) {
    setGuardando(true)
    try {
      const creada = await crearAsignacion(datos)
      setNuevaAbierta(false)
      setNuevaInicial(null)
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: 'Asignación registrada',
        html: `Se registraron <strong>${UN_DECIMAL.format(creada?.totalDias ?? 0)}</strong> días para <strong>${creada?.empleado ?? ''}</strong>.<br /><span style="color:#5a6b7b">Queda pendiente y se generó la notificación.</span>`,
        confirmButtonText: 'Listo',
        timer: 4500,
        timerProgressBar: true,
      })
      await recargar()
    } catch (error) {
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudo registrar la asignación',
        text: mensajeDeError(error),
        confirmButtonText: 'Entendido',
      })
    } finally {
      setGuardando(false)
    }
  }

  async function handleGuardarPeriodos(datos) {
    setGuardando(true)
    try {
      const actualizada = await guardarPeriodos(fechasAbiertas.id, datos)
      setFechasAbiertas(null)
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: 'Períodos guardados',
        html: `Se asignaron <strong>${UN_DECIMAL.format(actualizada?.totalDias ?? 0)}</strong> días de vacaciones.<br /><span style="color:#5a6b7b">La asignación vuelve a pendiente y se notificó al colaborador.</span>`,
        confirmButtonText: 'Listo',
        timer: 4500,
        timerProgressBar: true,
      })
      await recargar()
    } catch (error) {
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudieron guardar los períodos',
        text: mensajeDeError(error),
        confirmButtonText: 'Entendido',
      })
    } finally {
      setGuardando(false)
    }
  }

  async function handleConfirmarDecision({ decision, motivo, observaciones }) {
    const fila = decisionAbierta
    const aprobando = decision === 'aprobada'

    const confirmacion = await Swal.fire({
      ...SWAL_BASE,
      icon: aprobando ? 'question' : 'warning',
      title: aprobando ? '¿Aprobar la asignación?' : '¿Rechazar la asignación?',
      html: aprobando
        ? `<strong>${fila.empleado}</strong> quedará con la asignación aprobada y se le notificará.`
        : `<strong>${fila.empleado}</strong> quedará rechazada y se le notificará el motivo.`,
      showCancelButton: true,
      confirmButtonText: aprobando ? 'Sí, aprobar' : 'Sí, rechazar',
      cancelButtonText: 'Volver',
      confirmButtonColor: aprobando ? '#16456d' : '#a81f2b',
      reverseButtons: true,
      focusCancel: true,
    })
    if (!confirmacion.isConfirmed) return

    setGuardando(true)
    try {
      await registrarDecision(fila.id, { decision, motivo, observaciones })
      setDecisionAbierta(null)
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: aprobando ? 'Asignación aprobada' : 'Asignación rechazada',
        text: 'La decisión quedó registrada y se generó la notificación.',
        confirmButtonText: 'Listo',
        timer: 4500,
        timerProgressBar: true,
      })
      await recargar()
    } catch (error) {
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudo registrar la decisión',
        text: mensajeDeError(error),
        confirmButtonText: 'Entendido',
      })
    } finally {
      setGuardando(false)
    }
  }

  return (
    <>
      <header className="page__header">
        <div>
          <h1 className="page__title">Asignaciones de vacaciones</h1>
          <p className="page__lead">
            {unes
              ? `Colaboradores de la UNES ${unes} con sus días de vacaciones.`
              : 'Colaboradores con sus días de vacaciones.'}{' '}
            {puedeAprobar ? 'Registra aquí la decisión de Talento Humano.' : ''}
          </p>
        </div>
        <div className="page__actions">
          <Button variant="outline-secondary" onClick={recargar} disabled={cargando}>
            <Icon name="buscar" size={18} />
            Actualizar
          </Button>
          <Button variant="outline-secondary" onClick={limpiarFiltros} disabled={!hayFiltros}>
            Limpiar filtros
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              setNuevaInicial(null)
              setNuevaAbierta(true)
            }}
          >
            <Icon name="crear" size={18} />
            Nueva asignación
          </Button>
          <Button variant="outline-secondary" onClick={handleDescargar}>
            <Icon name="descargar" size={18} />
            Descargar reporte
          </Button>
        </div>
      </header>

      {errorCarga ? (
        <Alert variant="danger" className="d-flex align-items-start gap-2" role="alert">
          <Icon name="error" size={18} />
          <span>{errorCarga}</span>
        </Alert>
      ) : null}

      {origen === 'local' && !cargando ? (
        <Alert variant="warning" className="d-flex align-items-start gap-2" role="note">
          <Icon name="advertencia" size={18} />
          <span>
            No se pudo consultar la vista de colaboradores, así que se muestran sólo las
            asignaciones registradas. Avísale a Soporte si el problema continúa.
          </span>
        </Alert>
      ) : null}

      {!puedeAprobar ? (
        <Alert variant="info" className="d-flex align-items-start gap-2" role="note">
          <Icon name="info" size={18} />
          <span>
            Tu cargo permite <strong>consultar</strong> y programar períodos. Aprobar o rechazar es
            exclusivo de Talento Humano.
          </span>
        </Alert>
      ) : null}

      <section className="card" aria-labelledby="tabla-titulo">
        <header className="card__header">
          <div>
            <h2 className="card__title" id="tabla-titulo">
              Plantilla de la UNES
            </h2>
            <p className="card__subtitle">
              {cargando
                ? 'Consultando la vista de colaboradores…'
                : `${NUMERO.format(resumen.total)} colaboradores · ${NUMERO.format(resumen.conAsignacion)} con fechas programadas · ${NUMERO.format(resumen.sinAsignacion)} sin programar${resumen.enContra > 0 ? ` · ${NUMERO.format(resumen.enContra)} con saldo en contra` : ''
                }`}
            </p>
          </div>
        </header>

        <div className="card__body" style={{ borderBottom: '1px solid var(--line)' }}>
          <div className="toolbar">
            <div className="toolbar__field toolbar__field--grow">
              <Form.Label htmlFor={searchId}>Buscar colaborador</Form.Label>
              <div className="field__control">
                <Form.Control
                  id={searchId}
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Nombre, identificación, cargo o radicado"
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
                  <Icon name="buscar" size={18} />
                </span>
              </div>
            </div>

            <div className="toolbar__field">
              <Form.Label htmlFor={stateId}>Estado</Form.Label>
              <Form.Select
                id={stateId}
                value={estado}
                onChange={(event) => setEstado(event.target.value)}
              >
                {ESTADOS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Form.Select>
            </div>

            {unesDisponibles.length > 1 ? (
              <div className="toolbar__field">
                <Form.Label htmlFor={unesId}>UNES</Form.Label>
                <Form.Select
                  id={unesId}
                  value={filtroUnes}
                  onChange={(event) => setFiltroUnes(event.target.value)}
                >
                  <option value="todas">Todas las UNES</option>
                  {unesDisponibles.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Form.Select>
              </div>
            ) : null}
          </div>
        </div>

        <div className="card__body card__body--flush">
          {filtradas.length > 0 ? (
            /* El contenedor lleva el desplazamiento horizontal y `min-width: 0`
               para que la tabla se desplace dentro de la tarjeta en lugar de
               estirar la página entera. */
            <div className="table-scroll table-scroll--ajustado">
              <Table className="data data--tablero" borderless>
                <caption className="visually-hidden">
                  Colaboradores de la UNES con su descripción, identificación, cargo, estado de la
                  asignación, días a corte, días asignados y días a usar.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Desc. Unes</th>
                    <th scope="col">Colaborador</th>
                    <th scope="col">Identificación</th>
                    <th scope="col">UNES</th>
                    <th scope="col">Cargo</th>
                    <th scope="col">Estado</th>
                    <th scope="col" className="numeric" title="Días a corte">
                      Corte
                    </th>
                    <th scope="col" className="numeric" title="Días asignados">
                      Asignados
                    </th>
                    <th scope="col" className="numeric" title="Días a usar">
                      A usar
                    </th>
                    <th scope="col">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filtradas.map((fila) => (
                    <tr
                      key={`${fila.identificacion}-${fila.id ?? 'sin'}`}
                      data-sin-asignacion={fila.sinAsignacion ? 'si' : undefined}
                    >
                      <td title={fila.descUnes || undefined}>{fila.descUnes || '—'}</td>
                      <td title={fila.empleado || undefined}>{fila.empleado}</td>
                      <td className="tabular">{fila.identificacion || '—'}</td>
                      <td>{fila.unes || '—'}</td>
                      <td title={fila.cargo || undefined}>{fila.cargo || '—'}</td>
                      <td>
                        <div className="d-flex align-items-center gap-2">
                          <StatusChip estado={fila.estado} />
                          {fila.motivoRechazo ? (
                            <OverlayTrigger
                              trigger={['hover', 'focus']}
                              placement="left"
                              overlay={
                                <Popover id={`motivo-${fila.identificacion}`}>
                                  <Popover.Header as="h3">Motivo del rechazo</Popover.Header>
                                  <Popover.Body>{fila.motivoRechazo}</Popover.Body>
                                </Popover>
                              }
                            >
                              <button
                                type="button"
                                className="chip chip--danger"
                                aria-label={`Ver el motivo del rechazo de ${fila.empleado}`}
                              >
                                <Icon name="info" size={14} />
                                Motivo
                              </button>
                            </OverlayTrigger>
                          ) : null}
                        </div>
                      </td>
                      <td className="numeric tabular">{UN_DECIMAL.format(fila.diasACorte ?? 0)}</td>
                      <td className="numeric tabular">
                        {UN_DECIMAL.format(fila.diasAsignados ?? 0)}
                      </td>
                      <td className="numeric">
                        <CeldaDiasAUsar
                          valor={fila.diasAUsar ?? 0}
                          asignados={fila.diasAsignados ?? 0}
                          corte={fila.diasACorte ?? 0}
                        />
                      </td>
                      <td>
                        {/* Menú de tres puntos. Se arma con `OverlayTrigger` +
                          `Popover`: el `Dropdown` de react-bootstrap aplica
                          modificadores de Popper que competían entre sí y
                          dejaban el menú descentrado dentro de una tabla con
                          desplazamiento horizontal. */}
                        <OverlayTrigger
                          trigger="click"
                          placement="left-start"
                          rootClose
                          show={menuAbierto === fila.identificacion}
                          onToggle={(next) => setMenuAbierto(next ? fila.identificacion : null)}
                          overlay={
                            <Popover
                              id={`acciones-${fila.identificacion}`}
                              className="acciones__popover"
                            >
                              <Popover.Body className="acciones__cuerpo">
                                <button
                                  type="button"
                                  className="acciones__item"
                                  onClick={() => {
                                    setMenuAbierto(null)
                                    setEmpleadoAbierto(fila)
                                  }}
                                >
                                  <Icon name="empleado" size={16} />
                                  Ver empleado
                                </button>

                                <button
                                  type="button"
                                  className="acciones__item"
                                  onClick={() => {
                                    setMenuAbierto(null)
                                    abrirFechas(fila)
                                  }}
                                >
                                  <Icon name="editarFechas" size={16} />
                                  {fila.sinAsignacion ? 'Asignar fechas' : 'Editar fechas'}
                                </button>

                                {/* Sólo Talento Humano puede aprobar o rechazar.
                                  El backend responde 403 si otro cargo lo llama. */}
                                {puedeAprobar ? (
                                  <button
                                    type="button"
                                    className="acciones__item"
                                    disabled={fila.sinAsignacion}
                                    title={
                                      fila.sinAsignacion
                                        ? 'Primero programa las fechas de este colaborador'
                                        : 'Aprobar o rechazar la asignación'
                                    }
                                    onClick={() => {
                                      setMenuAbierto(null)
                                      setDecisionAbierta(fila)
                                    }}
                                  >
                                    <Icon name="aprobar" size={16} />
                                    Aprobar / rechazar
                                  </button>
                                ) : null}

                                {fila.motivoRechazo ? (
                                  <>
                                    <hr className="acciones__separador" />
                                    <button
                                      type="button"
                                      className="acciones__item"
                                      onClick={() => {
                                        setMenuAbierto(null)
                                        Swal.fire({
                                          ...SWAL_BASE,
                                          icon: 'info',
                                          title: 'Motivo del rechazo',
                                          html: construirCuerpoMotivo(fila.motivoRechazo, fila),
                                          confirmButtonText: 'Entendido',
                                        })
                                      }}
                                    >
                                      <Icon name="info" size={16} />
                                      Ver motivo del rechazo
                                    </button>
                                  </>
                                ) : null}
                              </Popover.Body>
                            </Popover>
                          }
                        >
                          <button
                            type="button"
                            className="acciones__toggle"
                            aria-label={`Acciones para ${fila.empleado}`}
                            aria-haspopup="menu"
                            aria-expanded={menuAbierto === fila.identificacion}
                            title="Acciones"
                          >
                            <Icon name="masOpciones" size={20} />
                          </button>
                        </OverlayTrigger>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon="buscarPersona"
              title={
                cargando
                  ? 'Consultando los colaboradores…'
                  : filas.length === 0
                    ? 'No hay colaboradores para esta UNES'
                    : 'Ningún colaborador coincide con la búsqueda'
              }
              text={
                cargando
                  ? 'Un momento.'
                  : filas.length === 0
                    ? `La vista no devolvió colaboradores para la UNES ${unes || 'indicada'}. Revisa el número o consulta con Soporte.`
                    : 'Prueba con otro nombre, identificación o cargo, o quita los filtros.'
              }
              action={
                hayFiltros ? (
                  <Button variant="outline-secondary" onClick={limpiarFiltros}>
                    Limpiar filtros
                  </Button>
                ) : null
              }
            />
          )}
        </div>
      </section>

      <EmpleadoDetalleModal
        show={Boolean(empleadoAbierto)}
        asignacion={empleadoAbierto}
        onHide={() => setEmpleadoAbierto(null)}
        onAsignar={(fila) => {
          setEmpleadoAbierto(null)
          abrirFechas(fila)
        }}
      />

      <AsignarPeriodosModal
        key={fechasAbiertas?.id ?? 'sin-fechas'}
        show={Boolean(fechasAbiertas)}
        asignacion={fechasAbiertas}
        saving={guardando}
        onHide={() => setFechasAbiertas(null)}
        onGuardar={handleGuardarPeriodos}
      />

      {puedeAprobar ? (
        <DecisionModal
          key={decisionAbierta?.id ?? 'sin-decision'}
          show={Boolean(decisionAbierta)}
          asignacion={decisionAbierta}
          saving={guardando}
          onHide={() => setDecisionAbierta(null)}
          onConfirmar={handleConfirmarDecision}
        />
      ) : null}

      <NuevaAsignacionModal
        key={nuevaAbierta ? `nueva-${nuevaInicial?.identificacion ?? 'libre'}` : 'nueva-cerrada'}
        show={nuevaAbierta}
        inicial={nuevaInicial}
        saving={guardando}
        onHide={() => {
          setNuevaAbierta(false)
          setNuevaInicial(null)
        }}
        onCrear={handleCrear}
      />
    </>
  )
}
