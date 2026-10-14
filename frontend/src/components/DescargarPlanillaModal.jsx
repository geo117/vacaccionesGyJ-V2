/**
 * Modal para descargar la planilla de vacaciones (PDF).
 *
 * Lo usa Talento Humano: elige la UNES en un desplegable y el PDF se genera para
 * esa unidad con la plantilla institucional. Los demás cargos descargan la suya
 * sin pasar por aquí —el servidor la limita a la UNES de la sesión—, así que este
 * modal siempre trabaja sobre una lista de UNES.
 *
 * El estado inicial sale de `unesInicial` (el filtro de la barra, si lo hay) y la
 * página lo remonta con una `key` al abrirlo, de modo que cada descarga parte de
 * datos frescos.
 */

import { useId, useState } from 'react'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import Modal from 'react-bootstrap/Modal'
import Icon from './Icon'

export default function DescargarPlanillaModal({
  show,
  opcionesUnes = [],
  unesInicial = '',
  descargando = false,
  onHide,
  onConfirmar,
}) {
  const baseId = useId()

  const sinOpciones = opcionesUnes.length === 0
  const [unes, setUnes] = useState(() => unesInicial || opcionesUnes[0]?.value || '')

  async function handleConfirmar() {
    if (sinOpciones || !unes) return
    await onConfirmar(unes)
  }

  return (
    <Modal show={show} onHide={onHide} centered backdrop="static" keyboard>
      <Modal.Header closeButton>
        <Modal.Title>
          Descargar planilla
          <small>Formato de vacaciones en PDF</small>
        </Modal.Title>
      </Modal.Header>

      <Modal.Body>
        <p>
          Se genera la planilla de vacaciones en PDF con la plantilla institucional, con los
          colaboradores y los períodos de la UNES elegida.
        </p>

        <Form.Group controlId={`${baseId}-unes`} style={{ marginTop: 'var(--space-5)' }}>
          <Form.Label>UNES</Form.Label>
          <Form.Select
            value={unes}
            onChange={(event) => setUnes(event.target.value)}
            disabled={sinOpciones || descargando}
          >
            {sinOpciones ? (
              <option value="">No hay UNES disponibles</option>
            ) : (
              opcionesUnes.map((opcion) => (
                <option key={opcion.value} value={opcion.value}>
                  {opcion.label}
                </option>
              ))
            )}
          </Form.Select>
          <Form.Text>
            {sinOpciones
              ? 'La tabla todavía no tiene colaboradores con UNES. Actualiza la vista e intenta de nuevo.'
              : 'Sólo se incluye la UNES seleccionada.'}
          </Form.Text>
        </Form.Group>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="outline-secondary" onClick={onHide} disabled={descargando}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          onClick={handleConfirmar}
          disabled={descargando || sinOpciones || !unes}
          aria-busy={descargando || undefined}
        >
          {descargando ? (
            <>
              <span className="btn__spinner" aria-hidden="true" />
              Generando…
            </>
          ) : (
            <>
              <Icon name="descargar" size={18} />
              Descargar planilla
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
