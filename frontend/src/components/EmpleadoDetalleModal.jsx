/**
 * Modal de detalle del empleado.
 *
 * Es una vista de consulta: no modifica nada. Muestra los tres períodos con los
 * días ya calculados y, cuando la asignación fue rechazada, el motivo en un
 * recuadro para que no se pierda entre los datos.
 *
 * Dos campos son **deducidos, no guardados**:
 *
 *  - «Aplica licencia». No hay columna para esto en la base y no hace falta: es
 *    una consecuencia del saldo. Se decide con el **mismo umbral del semáforo**
 *    (`semaforoDiasAUsar`), así que si algún día cambia el rojo, cambia también
 *    aquí y los dos números no pueden contradecirse. Por debajo del rojo el
 *    colaborador programó más días de los que tiene y el exceso va sin pago.
 *  - «Aprobado por» / «Rechazado por». `th_asignacion` guarda el nombre de quien
 *    tocó la asignación por última vez, así que la **etiqueta** la decide el
 *    estado: aprobada, rechazada o todavía pendiente.
 *
 * `Modal` de react-bootstrap aporta el comportamiento del diálogo (foco
 * atrapado, `aria-modal`, Escape, fondo) y `Table`/`Badge` el del contenido.
 */

import Modal from 'react-bootstrap/Modal'
import Table from 'react-bootstrap/Table'
import Button from 'react-bootstrap/Button'
import Icon from './Icon'
import StatusChip from './StatusChip'
import { formatIsoDate, NUMERO } from '../utils/fechas'
import { calcularDias, semaforoDiasAUsar } from '../utils/periodos'

const ETIQUETA_ESTADO = {
  pendiente: { texto: 'Pendiente de revisión', tone: 'warn' },
  aprobada: { texto: 'Aprobada', tone: 'ok' },
  rechazada: { texto: 'Rechazada', tone: 'danger' },
}

/**
 * Quién responde por la asignación, según en qué punto esté.
 *
 * Pendiente no es «aprobado por nadie»: simplemente todavía no hay decisión, y
 * el campo se muestra vacío en lugar de atribuirle a alguien algo que no hizo.
 */
function responsableDe(estado, thAsignacion) {
  if (estado === 'aprobada') return { etiqueta: 'Aprobado por', valor: thAsignacion }
  if (estado === 'rechazada') return { etiqueta: 'Rechazado por', valor: thAsignacion }
  return { etiqueta: 'Pendiente de aprobación', valor: null }
}

/** «Aplica licencia»: el exceso de días programados se paga como licencia. */
function licenciaDe(diasAUsar) {
  if (semaforoDiasAUsar(diasAUsar).tono === 'danger') {
    return { texto: 'Licencia no remunerada', tono: 'danger' }
  }
  return { texto: 'No aplica', tono: 'ok' }
}

function Campo({ etiqueta, valor, tono }) {
  return (
    <div className="ficha__campo">
      <p className="ficha__etiqueta">{etiqueta}</p>
      <p className={`ficha__valor${tono ? ` ficha__valor--${tono}` : ''}`}>{valor || '—'}</p>
    </div>
  )
}

export default function EmpleadoDetalleModal({ show, asignacion, onHide, onAsignar }) {
  if (!asignacion) return null

  const estado = ETIQUETA_ESTADO[asignacion.estado] ?? ETIQUETA_ESTADO.pendiente
  const periodos = asignacion.periodos ?? []
  const totalDias = periodos.reduce((suma, periodo) => suma + (calcularDias(periodo) ?? 0), 0)
  const programados = periodos.filter((periodo) => calcularDias(periodo) !== null).length
  const responsable = responsableDe(asignacion.estado, asignacion.thAsignacion)
  const licencia = licenciaDe(asignacion.diasAUsar)

  return (
    <Modal show={show} onHide={onHide} centered size="lg" backdrop="static" keyboard>
      <Modal.Header closeButton>
        <Modal.Title>
          {asignacion.empleado}
          <small>
            Radicado {asignacion.id} · {asignacion.unes}
          </small>
        </Modal.Title>
        <StatusChip estado={asignacion.estado} label={estado.texto} />
      </Modal.Header>

      <Modal.Body>
        <div className="ficha">
          <Campo etiqueta="Identificación" valor={asignacion.identificacion} />
          <Campo etiqueta="Cargo" valor={asignacion.cargo} />
          <Campo etiqueta="Centro de operación" valor={asignacion.unes} />
          <Campo etiqueta={responsable.etiqueta} valor={responsable.valor} />
          <Campo etiqueta="Aplica licencia" valor={licencia.texto} tono={licencia.tono} />
          <Campo etiqueta="Fecha de ingreso" valor={formatIsoDate(asignacion.fechaIngreso, 'long')} />
        </div>

        <h3 className="card__title" style={{ margin: 'var(--space-6) 0 var(--space-3)' }}>
          Períodos de vacaciones
        </h3>

        <div className="table-scroll">
          <Table className="data periodo-tabla" borderless responsive>
            <caption className="visually-hidden">
              Períodos programados con fecha de inicio, fecha de fin y días calculados.
            </caption>
            <thead>
              <tr>
                <th scope="col">Período</th>
                <th scope="col">Desde</th>
                <th scope="col">Hasta</th>
                <th scope="col" className="numeric">
                  Días
                </th>
              </tr>
            </thead>
            <tbody>
              {periodos.map((periodo, indice) => {
                const dias = calcularDias(periodo)
                return (
                  <tr key={`periodo-${indice + 1}`}>
                    <td>Período {indice + 1}</td>
                    <td>{formatIsoDate(periodo.inicio, 'long') || 'Sin programar'}</td>
                    <td>{formatIsoDate(periodo.fin, 'long') || 'Sin programar'}</td>
                    <td className="numeric tabular">{dias === null ? '—' : NUMERO.format(dias)}</td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                <td colSpan={2}>
                  {programados} {programados === 1 ? 'período programado' : 'períodos programados'}
                </td>
                <td className="numeric tabular">
                  <strong>{NUMERO.format(totalDias)}</strong>
                </td>
              </tr>
            </tfoot>
          </Table>
        </div>

        {asignacion.observaciones ? (
          <div className="nota nota--info" style={{ marginTop: 'var(--space-5)' }}>
            <Icon name="info" size={18} />
            <span>
              <strong>Observaciones.</strong> {asignacion.observaciones}
            </span>
          </div>
        ) : null}

        {asignacion.motivoRechazo ? (
          <div className="nota nota--danger" style={{ marginTop: 'var(--space-4)' }}>
            <Icon name="rechazar" size={18} />
            <span>
              <strong>Motivo del rechazo.</strong> {asignacion.motivoRechazo}
            </span>
          </div>
        ) : null}
      </Modal.Body>

      <Modal.Footer>
        <Button variant="outline-secondary" onClick={onHide}>
          Cerrar
        </Button>
        <Button variant="primary" onClick={() => onAsignar(asignacion)}>
          <Icon name="editarFechas" size={18} />
          Asignar fechas
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
