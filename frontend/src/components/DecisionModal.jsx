/**
 * Modal para aprobar o rechazar una asignación.
 *
 * Lo que resuelve:
 *  - La decisión se toma **período por período** desde el menú de tres puntos de
 *    la tabla. Cada clic se guarda en el acto en `aprobacion_rechazo_f1..f3`, sin
 *    esperar al botón general; el servidor recalcula el estado de la asignación.
 *  - **Aprobar la asignación** aprueba todos los períodos programados y la deja
 *    en «Aprobada». **Rechazarla** los rechaza todos y exige el motivo.
 *  - **Al rechazar, el motivo es obligatorio.** Un rechazo sin motivo obliga a
 *    la persona a preguntar por correo, que es justo el trámite que esta
 *    herramienta viene a quitar. El foco se lleva al recuadro y no se guarda
 *    hasta que haya texto real (no sólo espacios).
 *  - Las observaciones son independientes del motivo: acompañan la decisión,
 *    sea cual sea.
 *
 * La decisión general se pide con confirmación de sweetalert2, mostrando el
 * efecto concreto: aprobar pasa la asignación a "Aprobada"; rechazar deja
 * constancia del motivo.
 */

import { useId, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import Modal from 'react-bootstrap/Modal'
import OverlayTrigger from 'react-bootstrap/OverlayTrigger'
import Popover from 'react-bootstrap/Popover'
import Table from 'react-bootstrap/Table'
import Icon from './Icon'
import StatusChip from './StatusChip'
import { diasInhabiles } from '../hooks/fechas_inactivas'
import { mensajeDeError } from '../hooks/useAsignaciones'
import { formatIsoDate, NUMERO } from '../utils/fechas'
import { resumirPeriodos } from '../utils/periodos'

/** Normaliza lo que venga de la base a los dos valores que usa la interfaz. */
function normalizarDecisionPeriodo(valor) {
  const texto = String(valor ?? '').trim().toLowerCase()
  if (texto.startsWith('aprob')) return 'aprobada'
  if (texto.startsWith('rechaz')) return 'rechazada'
  return null
}

/** Decisiones iniciales de los tres períodos, tomadas de la asignación. */
function decisionesIniciales(asignacion) {
  return [0, 1, 2].map((indice) => {
    const periodo = asignacion?.periodos?.[indice]
    const porColumna = asignacion?.[`aprobacionRechazoF${indice + 1}`]
    return normalizarDecisionPeriodo(periodo?.decision ?? porColumna)
  })
}

/** La decisión general no puede contradecir un período ya rechazado. */
function decisionInicial(asignacion) {
  if (asignacion?.estado === 'rechazada') return 'rechazada'
  return decisionesIniciales(asignacion).includes('rechazada') ? 'rechazada' : 'aprobada'
}

export default function DecisionModal({
  show,
  asignacion,
  onHide,
  onConfirmar,
  onDecisionPeriodo,
  saving = false,
}) {
  const baseId = useId()

  // Igual que en el modal de períodos: el estado inicial sale de la asignación
  // recibida y el remontaje por `key` lo reinicia al cambiar de radicado.
  // Se abre en la decisión que ya tiene la fila; si está pendiente, en aprobar.
  const [decision, setDecision] = useState(() => decisionInicial(asignacion))
  const [motivo, setMotivo] = useState(asignacion?.motivoRechazo ?? '')
  const [observaciones, setObservaciones] = useState(asignacion?.observaciones ?? '')
  const [errorMotivo, setErrorMotivo] = useState(null)
  const [decisionesPeriodo, setDecisionesPeriodo] = useState(() =>
    decisionesIniciales(asignacion),
  )
  const [menuPeriodo, setMenuPeriodo] = useState(null)
  /* Período cuyo guardado está en curso y último error de guardado. */
  const [periodoSaving, setPeriodoSaving] = useState(null)
  const [errorPeriodo, setErrorPeriodo] = useState(null)

  // Días hábiles: la misma lista de fechas inactivas que usa el servidor, para
  // que la decisión se tome sobre el total que quedó guardado.
  const resumen = useMemo(
    () => resumirPeriodos(asignacion?.periodos ?? [], diasInhabiles),
    [asignacion],
  )

  const motivoValido = motivo.trim().length > 0
  const puedeGuardar = decision === 'aprobada' || motivoValido

  /**
   * Marca un período concreto y **lo guarda de inmediato** en el servidor.
   *
   * La respuesta trae la asignación con las tres decisiones y el estado ya
   * recalculado (aprobada, rechazada, pendiente o en verificación). La decisión
   * general visible se ajusta con esa respuesta: si queda algún rechazo, el
   * botón general ofrece rechazar; si no, aprobar.
   */
  async function aplicarDecisionPeriodo(indice, valor) {
    if (resumen.dias[indice] === null || saving || periodoSaving !== null) return

    setMenuPeriodo(null)
    setErrorPeriodo(null)
    setPeriodoSaving(indice)
    try {
      const actualizada = await onDecisionPeriodo(indice, valor)
      if (!actualizada) return

      setDecisionesPeriodo(decisionesIniciales(actualizada))
      setDecision(decisionInicial(actualizada))
      setMotivo((previo) => actualizada.motivoRechazo ?? previo)
      setErrorMotivo(null)
    } catch (error) {
      setErrorPeriodo(mensajeDeError(error))
    } finally {
      setPeriodoSaving(null)
    }
  }

  async function handleConfirmar() {
    if (decision === 'rechazada' && !motivoValido) {
      setErrorMotivo('Escribe el motivo del rechazo antes de continuar.')
      document.getElementById(`${baseId}-motivo`)?.focus()
      return
    }
    setErrorMotivo(null)
    await onConfirmar({
      decision,
      motivo,
      observaciones,
      decisionesPeriodos: decisionesPeriodo,
    })
  }

  if (!asignacion) return null

  return (
    <Modal show={show} onHide={onHide} centered size="lg" backdrop="static" keyboard>
      <Modal.Header closeButton>
        <Modal.Title>
          Aprobar o rechazar la asignación
          <small>
            {asignacion.empleado} · Radicado {asignacion.id}
          </small>
        </Modal.Title>
        <StatusChip estado={asignacion.estado} />
      </Modal.Header>

      <Modal.Body>
        <div className="ficha" style={{ marginBottom: 'var(--space-5)' }}>
          <div className="ficha__campo">
            <p className="ficha__etiqueta">Días programados</p>
            <p className="ficha__valor tabular">
              {NUMERO.format(resumen.totalDias)} en {resumen.periodosProgramados}{' '}
              {resumen.periodosProgramados === 1 ? 'período' : 'períodos'}
            </p>
          </div>
          <div className="ficha__campo">
            <p className="ficha__etiqueta">Fecha de ingreso</p>
            <p className="ficha__valor">
              {formatIsoDate(asignacion.fechaReintegroLab, 'long') || '—'}
            </p>
          </div>
        </div>

        <h3 className="card__title" style={{ margin: 'var(--space-6) 0 var(--space-3)' }}>
          Períodos de vacaciones
        </h3>

        <div className="table-scroll">
          <Table className="data periodo-tabla" borderless responsive>
            <caption className="visually-hidden">
              Períodos programados con fecha de inicio, fecha de fin, días calculados y
              acciones para aprobar o rechazar cada período.
            </caption>
            <thead>
              <tr>
                <th scope="col">Período</th>
                <th scope="col">Desde</th>
                <th scope="col">Hasta</th>
                <th scope="col" className="numeric">
                  Días
                </th>
                <th scope="col" className="periodo-tabla__acciones">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody>
              {[0, 1, 2].map((indice) => {
                const periodo = asignacion.periodos?.[indice] ?? {}
                const dias = resumen.dias[indice]
                const programado = dias !== null

                return (
                  <tr key={`periodo-${indice + 1}`}>
                    <td>Período {indice + 1}</td>
                    <td>{formatIsoDate(periodo.inicio, 'long') || 'Sin programar'}</td>
                    <td>{formatIsoDate(periodo.fin, 'long') || 'Sin programar'}</td>
                    <td className="numeric tabular">
                      {dias === null ? '—' : NUMERO.format(dias)}
                    </td>
                    <td className="periodo-tabla__acciones">
                      <div className="periodo-tabla__decision">
                        {/* Mismo patrón de tres puntos que la tabla principal:
                            Popover dentro del contenedor con scroll. */}
                        <OverlayTrigger
                          trigger="click"
                          placement="left-start"
                          rootClose
                          show={menuPeriodo === indice}
                          onToggle={(next) => setMenuPeriodo(next ? indice : null)}
                          overlay={
                            <Popover
                              id={`${baseId}-acciones-periodo-${indice + 1}`}
                              className="acciones__popover"
                            >
                              <Popover.Body className="acciones__cuerpo">
                                <button
                                  type="button"
                                  className="acciones__item"
                                  disabled={saving || periodoSaving !== null}
                                  onClick={() => aplicarDecisionPeriodo(indice, 'aprobada')}
                                >
                                  <Icon name="aprobar" size={16} />
                                  Aprobar período
                                </button>
                                <button
                                  type="button"
                                  className="acciones__item acciones__item--peligro"
                                  disabled={saving || periodoSaving !== null}
                                  onClick={() => aplicarDecisionPeriodo(indice, 'rechazada')}
                                >
                                  <Icon name="rechazar" size={16} />
                                  Rechazar período
                                </button>
                              </Popover.Body>
                            </Popover>
                          }
                        >
                          <button
                            type="button"
                            className="acciones__toggle"
                            aria-label={`Acciones del período ${indice + 1}`}
                            aria-haspopup="menu"
                            aria-expanded={menuPeriodo === indice}
                            title={
                              !programado
                                ? 'Este período no está programado'
                                : periodoSaving === indice
                                  ? 'Guardando la decisión…'
                                  : `Acciones del período ${indice + 1}`
                            }
                            disabled={!programado || saving || periodoSaving !== null}
                            aria-busy={periodoSaving === indice || undefined}
                          >
                            {periodoSaving === indice ? (
                              <span className="btn__spinner" aria-hidden="true" />
                            ) : (
                              <Icon name="masOpciones" size={20} />
                            )}
                          </button>
                        </OverlayTrigger>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                <td colSpan={2}>
                  {resumen.periodosProgramados}{' '}
                  {resumen.periodosProgramados === 1
                    ? 'período programado'
                    : 'períodos programados'}
                </td>
                <td className="numeric tabular">
                  <strong>{NUMERO.format(resumen.totalDias)}</strong>
                </td>
                <td />
              </tr>
            </tfoot>
          </Table>
        </div>

        {errorPeriodo ? (
          <Alert variant="danger" className="d-flex align-items-start gap-2 mt-4" role="alert">
            <Icon name="error" size={18} />
            <span>{errorPeriodo}</span>
          </Alert>
        ) : null}

        {decision === 'rechazada' ? (
          <Form.Group controlId={`${baseId}-motivo`} style={{ marginTop: 'var(--space-5)' }}>
            <Form.Label>Motivo del rechazo</Form.Label>
            <Form.Control
              as="textarea"
              rows={4}
              value={motivo}
              onChange={(event) => {
                setMotivo(event.target.value)
                if (errorMotivo) setErrorMotivo(null)
              }}
              isInvalid={Boolean(errorMotivo)}
              maxLength={500}
              placeholder="Explica qué debe corregirse: fechas superpuestas, días insuficientes, cobertura del turno…"
              aria-describedby={`${baseId}-motivo-ayuda`}
            />
            {errorMotivo ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errorMotivo}</span>
              </p>
            ) : (
              <Form.Text id={`${baseId}-motivo-ayuda`}>
                Este texto es el que verá quien radicó la solicitud. {motivo.length}/500
                caracteres.
              </Form.Text>
            )}
          </Form.Group>
        ) : (
          <Alert variant="success" className="d-flex align-items-start gap-2 mt-4" role="status">
            <Icon name="aprobar" size={18} />
            <span>
              Todos los períodos programados quedarán <strong>aprobados</strong> y la asignación
              pasará a «Aprobada».
            </span>
          </Alert>
        )}

        <Form.Group
          controlId={`${baseId}-decision-observaciones`}
          style={{ marginTop: 'var(--space-5)' }}
        >
          <Form.Label>
            Observaciones <span className="opcional">(opcional)</span>
          </Form.Label>
          <Form.Control
            as="textarea"
            rows={3}
            value={observaciones}
            onChange={(event) => setObservaciones(event.target.value)}
            maxLength={500}
            placeholder="Notas internas para Talento Humano sobre esta decisión."
          />
          <Form.Text>Se guardan con la asignación. {observaciones.length}/500 caracteres.</Form.Text>
        </Form.Group>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="outline-secondary" onClick={onHide} disabled={saving}>
          Cancelar
        </Button>
        <Button
          variant={decision === 'rechazada' ? 'danger' : 'primary'}
          onClick={handleConfirmar}
          disabled={saving || !puedeGuardar}
          aria-busy={saving || undefined}
        >
          {saving ? (
            <>
              <span className="btn__spinner" aria-hidden="true" />
              Guardando…
            </>
          ) : (
            <>
              <Icon name={decision === 'rechazada' ? 'rechazar' : 'aprobar'} size={18} />
              {decision === 'rechazada' ? 'Rechazar asignación' : 'Aprobar asignación'}
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
