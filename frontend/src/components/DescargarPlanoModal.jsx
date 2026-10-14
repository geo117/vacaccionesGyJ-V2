/**
 * Modal para descargar el plano UNOEE (Excel).
 *
 * Dos alcances excluyentes:
 *  - **General**: toda la plantilla.
 *  - **Por UNES**: una unidad concreta, elegida en un desplegable que aparece al
 *    marcar esa opción.
 *
 * Las opciones son botones con `aria-pressed` y no radios: el sistema ya agrupa
 * así lo excluyente (ver `.opciones` en modal.css) y deja las dos a la vista. La
 * descarga la ejecuta quien abre el modal (`onConfirmar`); este componente no
 * conoce la API.
 */

import { useId, useState } from 'react'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import Modal from 'react-bootstrap/Modal'
import Icon from './Icon'

const ALCANCES = [
  { valor: 'general', etiqueta: 'Plano general', icono: 'plano' },
  { valor: 'unes', etiqueta: 'Plano por UNES', icono: 'buscar' },
]

export default function DescargarPlanoModal({
  show,
  opcionesUnes = [],
  unesInicial = '',
  descargando = false,
  onHide,
  onConfirmar,
}) {
  const baseId = useId()

  const sinOpciones = opcionesUnes.length === 0
  const [alcance, setAlcance] = useState('general')
  const [unes, setUnes] = useState(() => unesInicial || opcionesUnes[0]?.value || '')

  const faltaUnes = alcance === 'unes' && (sinOpciones || !unes)

  async function handleConfirmar() {
    if (faltaUnes) return
    await onConfirmar({ unes: alcance === 'unes' ? unes : '' })
  }

  return (
    <Modal show={show} onHide={onHide} centered backdrop="static" keyboard>
      <Modal.Header closeButton>
        <Modal.Title>
          Descargar plano UNOEE
          <small>Formato oficial en Excel</small>
        </Modal.Title>
      </Modal.Header>

      <Modal.Body>
        <p>
          Se genera el plano en Excel sobre la plantilla oficial, listo para la importación.
        </p>

        <Form.Group style={{ marginTop: 'var(--space-5)' }}>
          <Form.Label id={`${baseId}-alcance-label`}>Alcance</Form.Label>
          <div className="opciones" role="group" aria-labelledby={`${baseId}-alcance-label`}>
            {ALCANCES.map((opcion) => (
              <button
                key={opcion.valor}
                type="button"
                className="opciones__item"
                aria-pressed={alcance === opcion.valor}
                onClick={() => setAlcance(opcion.valor)}
              >
                <Icon name={opcion.icono} size={18} />
                {opcion.etiqueta}
              </button>
            ))}
          </div>
          <Form.Text>
            {alcance === 'general'
              ? 'Incluye a toda la plantilla.'
              : 'Incluye sólo la UNES seleccionada.'}
          </Form.Text>
        </Form.Group>

        {alcance === 'unes' ? (
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
            {sinOpciones ? (
              <Form.Text>
                La tabla todavía no tiene colaboradores con UNES. Actualiza la vista e intenta de
                nuevo.
              </Form.Text>
            ) : null}
          </Form.Group>
        ) : null}
      </Modal.Body>

      <Modal.Footer>
        <Button variant="outline-secondary" onClick={onHide} disabled={descargando}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          onClick={handleConfirmar}
          disabled={descargando || faltaUnes}
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
              Descargar plano
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
