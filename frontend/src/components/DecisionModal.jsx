/**
 * Modal para aprobar o rechazar una asignación.
 *
 * Lo que resuelve:
 *  - La decisión se elige en un grupo de dos botones con `aria-pressed`, no en un
 *    desplegable: son dos opciones y verlas juntas evita un clic de más.
 *  - **Al rechazar, el motivo es obligatorio.** Un rechazo sin motivo obliga a
 *    la persona a preguntar por correo, que es justo el trámite que esta
 *    herramienta viene a quitar. El foco se lleva al recuadro y no se guarda
 *    hasta que haya texto real (no sólo espacios).
 *  - Las observaciones son independientes del motivo: acompañan la decisión,
 *    sea cual sea.
 *
 * Antes de guardar se pide confirmación con sweetalert2, mostrando el efecto
 * concreto: aprobar pasa la asignación a "Aprobada"; rechazar deja constancia
 * del motivo.
 */

import { useId, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import Modal from 'react-bootstrap/Modal'
import Icon from './Icon'
import StatusChip from './StatusChip'
import { formatIsoDate, NUMERO } from '../utils/fechas'
import { resumirPeriodos } from '../utils/periodos'

const DECISIONES = [
  { valor: 'aprobada', etiqueta: 'Aprobar', icono: 'aprobar', tono: 'ok' },
  { valor: 'rechazada', etiqueta: 'Rechazar', icono: 'rechazar', tono: 'danger' },
]

export default function DecisionModal({ show, asignacion, onHide, onConfirmar, saving = false }) {
  const baseId = useId()

  // Igual que en el modal de períodos: el estado inicial sale de la asignación
  // recibida y el remontaje por `key` lo reinicia al cambiar de radicado.
  // Se abre en la decisión que ya tiene la fila; si está pendiente, en aprobar.
  const [decision, setDecision] = useState(
    asignacion?.estado === 'rechazada' ? 'rechazada' : 'aprobada',
  )
  const [motivo, setMotivo] = useState(asignacion?.motivoRechazo ?? '')
  const [observaciones, setObservaciones] = useState(asignacion?.observaciones ?? '')
  const [errorMotivo, setErrorMotivo] = useState(null)

  const resumen = useMemo(() => resumirPeriodos(asignacion?.periodos ?? []), [asignacion])

  const motivoValido = motivo.trim().length > 0
  const puedeGuardar = decision === 'aprobada' || motivoValido

  async function handleConfirmar() {
    if (decision === 'rechazada' && !motivoValido) {
      setErrorMotivo('Escribe el motivo del rechazo antes de continuar.')
      document.getElementById(`${baseId}-motivo`)?.focus()
      return
    }
    setErrorMotivo(null)
    await onConfirmar({ decision, motivo, observaciones })
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
            <p className="ficha__valor">{formatIsoDate(asignacion.fechaIngreso, 'long') || '—'}</p>
          </div>
        </div>

        <Form.Group controlId={`${baseId}-decision`}>
          <Form.Label>Decisión</Form.Label>
          <div className="decision" role="group" aria-labelledby={`${baseId}-decision`}>
            {DECISIONES.map((opcion) => (
              <button
                key={opcion.valor}
                type="button"
                className="decision__opcion"
                data-decision={opcion.valor}
                aria-pressed={decision === opcion.valor}
                onClick={() => {
                  setDecision(opcion.valor)
                  if (opcion.valor === 'aprobada') setErrorMotivo(null)
                }}
              >
                <Icon name={opcion.icono} size={18} />
                {opcion.etiqueta}
              </button>
            ))}
          </div>
        </Form.Group>

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
                Este texto es el que verá quien radicó la solicitud. {motivo.length}/500 caracteres.
              </Form.Text>
            )}
          </Form.Group>
        ) : (
          <Alert variant="success" className="d-flex align-items-start gap-2 mt-4" role="status">
            <Icon name="aprobar" size={18} />
            <span>
              La asignación quedará <strong>aprobada</strong> con los períodos programados.
            </span>
          </Alert>
        )}

        <Form.Group controlId={`${baseId}-decision-observaciones`} style={{ marginTop: 'var(--space-5)' }}>
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
