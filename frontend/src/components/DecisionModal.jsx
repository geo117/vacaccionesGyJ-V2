/**
 * Modal para aprobar o rechazar una asignación.
 *
 * Lo que resuelve:
 *  - La decisión se toma **período por período** desde el menú de tres puntos de
 *    la tabla. Cada clic se guarda en el acto en `aprobacion_rechazo_f1..f3`, sin
 *    esperar al botón general; el servidor recalcula el estado de la asignación.
 *  - **Aprobar la asignación** aprueba todos los períodos programados y la deja
 *    en «Aprobada».
 *  - Si **todos los períodos ya están rechazados**, se muestra además
 *    **«Aprobar todo»**, para revertir el rechazo y aprobar de una vez todas las
 *    asignaciones programadas.
 *  - **Rechazar todo** (nuevo) deja todos los períodos rechazados y activa el
 *    campo para escribir el motivo del rechazo completo. Está a la izquierda del
 *    botón principal, como pide el negocio.
 *  - Cuando se rechaza un período desde la tabla de acciones, se abre un
 *    **recuadro de rechazos**: una fila por período rechazado con su motivo. El
 *    recuadro muestra cuántos rechazos hay seleccionados; al guardar, los motivos
 *    se concatenan en `motivo_rechazo` (uno solo se guarda tal cual).
 *  - **Al rechazar, el motivo es obligatorio.** Un rechazo sin motivo obliga a
 *    la persona a preguntar por correo, que es justo el trámite que esta
 *    herramienta viene a quitar.
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

/** Posiciones de los períodos que están rechazados. */
function indicesRechazadosDe(decisiones) {
  return decisiones.reduce((salida, valor, indice) => {
    if (valor === 'rechazada') salida.push(indice)
    return salida
  }, [])
}

/**
 * Motivos iniciales por período.
 *
 * Cuando la asignación trae un motivo ya concatenado («Período 1: … | Período
 * 2: …») se reparte entre sus períodos para que al reabrir el modal no se pierda.
 * Si el motivo es anterior a este formato y hay varios rechazos, se coloca en el
 * primero: es preferible mostrarlo una vez que ocultarlo.
 */
function motivosIniciales(asignacion) {
  const indices = indicesRechazadosDe(decisionesIniciales(asignacion))
  const motivo = String(asignacion?.motivoRechazo ?? '').trim()
  const mapa = {}
  if (!motivo || indices.length === 0) return mapa
  if (indices.length === 1) {
    mapa[indices[0]] = motivo
    return mapa
  }

  let encontrado = false
  for (const indice of indices) {
    const patron = new RegExp(`Período ${indice + 1}:\\s*([^|]*)`, 'i')
    const coincidencia = motivo.match(patron)
    if (coincidencia) {
      mapa[indice] = coincidencia[1].trim()
      encontrado = true
    }
  }
  if (!encontrado) mapa[indices[0]] = motivo
  return mapa
}

/**
 * Motivo que se guarda en `motivo_rechazo`.
 *
 * Con un solo rechazo se guarda su texto; con varios se concatenan indicando el
 * período, para que la persona sepa a cuál corresponde cada explicación.
 */
function concatenarMotivos(motivos, indices) {
  const partes = indices
    .map((indice) => ({ indice, texto: String(motivos[indice] ?? '').trim() }))
    .filter((parte) => parte.texto)
  if (partes.length === 0) return ''
  if (partes.length === 1) return partes[0].texto
  return partes.map(({ indice, texto }) => `Período ${indice + 1}: ${texto}`).join(' | ')
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
  const [motivo, setMotivo] = useState(asignacion?.motivoRechazo ?? '')
  const [observaciones, setObservaciones] = useState(asignacion?.observaciones ?? '')
  const [errorMotivo, setErrorMotivo] = useState(null)
  const [decisionesPeriodo, setDecisionesPeriodo] = useState(() =>
    decisionesIniciales(asignacion),
  )
  const [motivosPeriodo, setMotivosPeriodo] = useState(() => motivosIniciales(asignacion))
  const [errorMotivos, setErrorMotivos] = useState(null)
  /* «Rechazar todo» está activo: el botón principal rechaza todos los períodos. */
  const [rechazoTodos, setRechazoTodos] = useState(
    () => asignacion?.estado === 'rechazada',
  )
  const [menuPeriodo, setMenuPeriodo] = useState(null)
  /* Período cuyo guardado está en curso y último error de guardado. */
  const [periodoSaving, setPeriodoSaving] = useState(null)
  const [errorPeriodo, setErrorPeriodo] = useState(null)

  // Días hábiles: la misma lista de fechas inactivas que usa el servidor y, si
  // el empleado de Colmena no trabaja sábados, los sábados también se descuentan.
  const resumen = useMemo(
    () =>
      resumirPeriodos(asignacion?.periodos ?? [], diasInhabiles, {
        sabadoHabil: asignacion?.sabadoHabil,
      }),
    [asignacion],
  )

  const indicesRechazados = useMemo(
    () => indicesRechazadosDe(decisionesPeriodo),
    [decisionesPeriodo],
  )
  const hayRechazos = indicesRechazados.length > 0
  /* Todos los períodos programados están rechazados: hay que ofrecer la vuelta
     a aprobados, porque el botón general estaría en modo rechazo. */
  const todasRechazadas =
    resumen.periodosProgramados > 0 &&
    indicesRechazados.length === resumen.periodosProgramados
  const motivoGeneralValido = motivo.trim().length > 0

  function enfocarMotivoGeneral() {
    requestAnimationFrame(() => document.getElementById(`${baseId}-motivo`)?.focus())
  }

  function enfocarMotivoPeriodo(indice) {
    requestAnimationFrame(() =>
      document.getElementById(`${baseId}-motivo-periodo-${indice + 1}`)?.focus(),
    )
  }

  /**
   * Activa el rechazo de todos los períodos. No guarda todavía: enciende el
   * campo del motivo para que la persona explique el rechazo completo y confirme
   * con el botón principal.
   */
  function activarRechazoTotal() {
    setErrorMotivo(null)
    setRechazoTodos(true)
    // Si ya había motivos por período, se ofrecen juntos para no reescribirlos.
    setMotivo((previo) => previo || concatenarMotivos(motivosPeriodo, indicesRechazados))
    enfocarMotivoGeneral()
  }

  /**
   * Marca un período concreto y **lo guarda de inmediato** en el servidor.
   *
   * La respuesta trae la asignación con las tres decisiones y el estado ya
   * recalculado (aprobada, rechazada, pendiente o en verificación). Al rechazar
   * se abre el recuadro con el motivo de ese período.
   */
  async function aplicarDecisionPeriodo(indice, valor) {
    if (resumen.dias[indice] === null || saving || periodoSaving !== null) return

    setMenuPeriodo(null)
    setErrorPeriodo(null)
    setRechazoTodos(false)
    setPeriodoSaving(indice)
    try {
      const actualizada = await onDecisionPeriodo(indice, valor)
      if (!actualizada) return

      setDecisionesPeriodo(decisionesIniciales(actualizada))
      setMotivo((previo) => actualizada.motivoRechazo ?? previo)
      setErrorMotivo(null)
      if (valor === 'rechazada') {
        setErrorMotivos(null)
        enfocarMotivoPeriodo(indice)
      }
    } catch (error) {
      setErrorPeriodo(mensajeDeError(error))
    } finally {
      setPeriodoSaving(null)
    }
  }

  async function handleConfirmar() {
    if (saving) return
    // Rechazo total: todos los períodos y un solo motivo.
    if (rechazoTodos) {
      if (!motivoGeneralValido) {
        setErrorMotivo('Escribe el motivo del rechazo de todos los períodos.')
        enfocarMotivoGeneral()
        return
      }
      setErrorMotivo(null)
      await onConfirmar({ decision: 'rechazada', motivo, observaciones })
      return
    }

    // Hay rechazos por período: se guardan sus motivos concatenados y se
    // conservan las decisiones que ya están en la base.
    if (hayRechazos) {
      const faltantes = indicesRechazados.filter(
        (indice) => !String(motivosPeriodo[indice] ?? '').trim(),
      )
      if (faltantes.length > 0) {
        const etiquetaPeriodos =
          faltantes.length === 1
            ? `del período ${faltantes[0] + 1}`
            : `de los períodos ${faltantes.map((indice) => indice + 1).join(', ')}`
        setErrorMotivos(`Escribe el motivo ${etiquetaPeriodos}.`)
        enfocarMotivoPeriodo(faltantes[0])
        return
      }
      setErrorMotivos(null)
      await onConfirmar({
        decision: 'rechazada',
        motivo: concatenarMotivos(motivosPeriodo, indicesRechazados),
        observaciones,
        decisionesPeriodos: decisionesPeriodo,
        guardarMotivos: true,
      })
      return
    }

    // Sin rechazos: aprobar todos los períodos programados.
    setErrorMotivo(null)
    await onConfirmar({ decision: 'aprobada', motivo: '', observaciones })
  }

  /**
   * Vuelve a aprobar todo cuando la asignación ya quedó rechazada por completo.
   * El servidor aplica la decisión uniforme y limpia el motivo del rechazo.
   */
  async function aprobarTodo() {
    if (saving) return
    setErrorMotivo(null)
    await onConfirmar({ decision: 'aprobada', motivo: '', observaciones })
  }

  if (!asignacion) return null

  const etiquetaPrincipal = rechazoTodos
    ? 'Rechazar asignación'
    : hayRechazos
      ? 'Guardar motivos del rechazo'
      : 'Aprobar asignación'
  const iconoPrincipal = rechazoTodos || hayRechazos ? 'rechazar' : 'aprobar'

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

        {/* Recuadro de rechazos por período: aparece en cuanto hay un rechazo
            individual y reúne una fila por período con su motivo. */}
        {!rechazoTodos && hayRechazos ? (
          <section
            className="rechazos"
            aria-labelledby={`${baseId}-rechazos-titulo`}
            aria-live="polite"
          >
            <div className="rechazos__cabecera">
              <div>
                <h3 className="card__title" id={`${baseId}-rechazos-titulo`}>
                  Motivos de los rechazos
                </h3>
                <p className="rechazos__ayuda">
                  Cada período rechazado necesita su motivo. Se guardan juntos en el motivo
                  del rechazo de la asignación.
                </p>
              </div>
              <span className="chip chip--danger">
                Rechazos seleccionados: {indicesRechazados.length}
              </span>
            </div>

            <div className="table-scroll">
              <Table className="data periodo-tabla" borderless responsive>
                <caption className="visually-hidden">
                  Períodos rechazados y el motivo que se guardará para cada uno.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Período</th>
                    <th scope="col">Motivo del rechazo</th>
                  </tr>
                </thead>
                <tbody>
                  {indicesRechazados.map((indice) => {
                    const valor = motivosPeriodo[indice] ?? ''
                    const invalido =
                      Boolean(errorMotivos) && String(valor).trim().length === 0
                    return (
                      <tr key={`motivo-rechazo-${indice + 1}`}>
                        <td>Período {indice + 1}</td>
                        <td>
                          <Form.Control
                            as="textarea"
                            rows={2}
                            id={`${baseId}-motivo-periodo-${indice + 1}`}
                            value={valor}
                            onChange={(event) => {
                              const texto = event.target.value
                              setMotivosPeriodo((previos) => ({ ...previos, [indice]: texto }))
                              if (errorMotivos) setErrorMotivos(null)
                            }}
                            isInvalid={invalido}
                            maxLength={500}
                            placeholder="Explica qué debe corregirse en este período…"
                            aria-label={`Motivo del rechazo del período ${indice + 1}`}
                          />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>
            </div>

            {errorMotivos ? (
              <p className="invalid-feedback d-flex" role="alert">
                <Icon name="error" size={16} />
                <span>{errorMotivos}</span>
              </p>
            ) : (
              <p className="rechazos__nota">
                {indicesRechazados.length > 1
                  ? `Se concatenarán ${indicesRechazados.length} motivos en la columna del motivo del rechazo.`
                  : 'Este motivo se guardará en la columna del motivo del rechazo.'}
              </p>
            )}
          </section>
        ) : null}

        {rechazoTodos ? (
          <Form.Group controlId={`${baseId}-motivo`} style={{ marginTop: 'var(--space-5)' }}>
            <Form.Label>Motivo del rechazo de todos los períodos</Form.Label>
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
              placeholder="Explica por qué se rechazan todos los períodos: fechas superpuestas, días insuficientes, cobertura del turno…"
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
        ) : !hayRechazos ? (
          <Alert variant="success" className="d-flex align-items-start gap-2 mt-4" role="status">
            <Icon name="aprobar" size={18} />
            <span>
              Todos los períodos programados quedarán <strong>aprobados</strong> y la asignación
              pasará a «Aprobada».
            </span>
          </Alert>
        ) : null}

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
        {todasRechazadas ? (
          <Button variant="primary" onClick={aprobarTodo} disabled={saving}>
            <Icon name="aprobar" size={18} />
            Aprobar todo
          </Button>
        ) : null}
        <Button
          variant="outline-danger"
          onClick={activarRechazoTotal}
          disabled={saving || resumen.periodosProgramados === 0}
          aria-pressed={rechazoTodos}
        >
          <Icon name="rechazar" size={18} />
          Rechazar todo
        </Button>
        <Button
          variant={rechazoTodos || hayRechazos ? 'danger' : 'primary'}
          onClick={handleConfirmar}
          disabled={saving}
          aria-busy={saving || undefined}
        >
          {saving ? (
            <>
              <span className="btn__spinner" aria-hidden="true" />
              Guardando…
            </>
          ) : (
            <>
              <Icon name={iconoPrincipal} size={18} />
              {etiquetaPrincipal}
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
