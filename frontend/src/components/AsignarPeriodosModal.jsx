/**
 * Modal para asignar los tres períodos de vacaciones.
 *
 * Lo que resuelve:
 *  - Tres períodos con fecha de inicio y de fin. Un período se puede dejar
 *    vacío: no todo el mundo parte sus vacaciones en tres.
 *  - **Cálculo de días en vivo**, por período y en total. El total incluye
 *    ambos extremos de cada rango (del 1 al 5 son 5 días), que es la convención
 *    de una asignación de vacaciones.
 *  - Fecha de ingreso sugerida automáticamente como el día siguiente al último
 *    período, con un botón para aplicarla: se propone, no se impone.
 *  - Validación de rangos invertidos y de **períodos que se cruzan**, que es el
 *    error que de verdad descuadra el total y la nómina.
 *
 * Los días nunca se escriben a mano: se derivan de las fechas con
 * `calcularDias`, de modo que la pantalla, la tabla y el reporte siempre digan
 * lo mismo.
 */

import { useId, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import Modal from 'react-bootstrap/Modal'
import Icon from './Icon'
import { addDays, formatIsoDate, NUMERO } from '../utils/fechas'
import { resumirPeriodos, semaforoDiasAUsar, validarPeriodos } from '../utils/periodos'

/** Un decimal siempre, igual que en la tabla. */
const UN_DECIMAL = new Intl.NumberFormat('es-CO', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

/** Lleva los períodos guardados (con `null`) al formato del formulario (''). */
function aFormulario(periodos) {
  const normalizados = (periodos ?? []).slice(0, 3).map((periodo) => ({
    inicio: periodo?.inicio ?? '',
    fin: periodo?.fin ?? '',
  }))
  while (normalizados.length < 3) normalizados.push({ inicio: '', fin: '' })
  return normalizados
}

export default function AsignarPeriodosModal({ show, asignacion, onHide, onGuardar, saving = false }) {
  const baseId = useId()

  const [observaciones, setObservaciones] = useState(asignacion?.observaciones ?? '')
  const [errores, setErrores] = useState({})

  // El formulario se inicializa desde la asignación recibida, no con un efecto
  // que sincronice estado: quien abre el modal le pasa una `key` distinta por
  // radicado, así que React lo remonta y este `useState` vuelve a partir de los
  // datos correctos. Un efecto que llame a `setState` provoca un render en
  // cascada y es justo lo que la regla `set-state-in-effect` señala.
  const [periodos, setPeriodos] = useState(() => aFormulario(asignacion?.periodos))
  const [fechaIngreso, setFechaIngreso] = useState(asignacion?.fechaIngreso ?? '')

  const resumen = useMemo(() => resumirPeriodos(periodos), [periodos])

  /* Último día programado: base para sugerir la fecha de ingreso. */
  const ultimoDia = useMemo(() => {
    const fines = periodos.map((periodo) => periodo.fin).filter(Boolean).sort()
    return fines.length ? fines[fines.length - 1] : ''
  }, [periodos])

  const ingreso = ultimoDia ? addDays(ultimoDia, 1) : ''
  const ingresoDesactualizado = Boolean(ingreso && fechaIngreso !== ingreso)

  /* Días a usar = días a corte − días asignados, el mismo cálculo de la tabla.
     Aquí el corte ya viene de la vista, así que no hay que interpretarlo. */
  const corte = Number(asignacion?.diasACorte ?? 0) || 0
  const diasAUsar = useMemo(
    () => Math.round((corte - resumen.totalDias) * 10) / 10,
    [corte, resumen.totalDias],
  )

  function actualizarPeriodo(indice, campo, valor) {
    setPeriodos((previos) =>
      previos.map((periodo, i) => (i === indice ? { ...periodo, [campo]: valor } : periodo)),
    )
    // El error del período se limpia al tocarlo; se recalcula al guardar.
    setErrores((previos) => {
      const clave = `periodo${indice + 1}`
      if (!previos[clave]) return previos
      const copia = { ...previos }
      delete copia[clave]
      return copia
    })
  }

  function vaciarPeriodo(indice) {
    setPeriodos((previos) =>
      previos.map((periodo, i) => (i === indice ? { inicio: '', fin: '' } : periodo)),
    )
    setErrores((previos) => {
      const copia = { ...previos }
      delete copia[`periodo${indice + 1}`]
      return copia
    })
  }

  async function handleGuardar() {
    const nuevosErrores = validarPeriodos(periodos)

    if (resumen.periodosProgramados === 0) {
      nuevosErrores.general = 'Programa al menos un período antes de guardar.'
    }
    if (Object.keys(nuevosErrores).length > 0) {
      setErrores(nuevosErrores)
      // Se lleva el foco al primer período con problema, una sola vez.
      const primero = Object.keys(nuevosErrores)
        .filter((clave) => clave.startsWith('periodo'))
        .sort()[0]
      if (primero) {
        document.getElementById(`${baseId}-${primero}-inicio`)?.focus()
      }
      return
    }

    setErrores({})
    await onGuardar({
      periodos,
      fechaIngreso: fechaIngreso || ingreso,
      observaciones,
      totalDias: resumen.totalDias,
    })
  }

  if (!asignacion) return null

  return (
    <Modal show={show} onHide={onHide} centered size="xl" backdrop="static" keyboard>
      <Modal.Header closeButton>
        <Modal.Title>
          Asignar fechas de vacaciones
          <small>
            {asignacion.empleado} · Radicado {asignacion.id} · {asignacion.unes}
          </small>
        </Modal.Title>
      </Modal.Header>

      <Modal.Body>
        {errores.general ? (
          <Alert variant="danger" className="d-flex align-items-center gap-2" role="alert">
            <Icon name="error" size={18} />
            <span>{errores.general}</span>
          </Alert>
        ) : null}

        {/* Los tres períodos en una sola fila de columnas, con el total como
            cuarta columna. En pantalla estrecha las columnas se apilan solas
            (ver `.periodos` en modal.css). */}
        <div className="periodos">
          {periodos.map((periodo, indice) => {
            const clave = `periodo${indice + 1}`
            const error = errores[clave] ?? null
            const dias = resumen.dias[indice]
            const vacio = !periodo.inicio && !periodo.fin

            return (
              <fieldset
                key={clave}
                className={`periodo${error ? ' periodo--error' : ''}`}
                aria-describedby={error ? `${baseId}-${clave}-error` : undefined}
              >
                <legend className="visually-hidden">Período {indice + 1}</legend>

                <div className="periodo__head">
                  <span className="periodo__title">
                    <Icon name="editarFechas" size={16} />
                    Período {indice + 1}
                  </span>

                  <span className="periodo__dias tabular">
                    {dias === null
                      ? vacio
                        ? 'Sin programar'
                        : 'Incompleto'
                      : `${NUMERO.format(dias)} ${dias === 1 ? 'día' : 'días'}`}
                  </span>
                </div>

                <Form.Group controlId={`${baseId}-${clave}-inicio`}>
                  <Form.Label>Desde</Form.Label>
                  <Form.Control
                    type="date"
                    value={periodo.inicio}
                    onChange={(event) => actualizarPeriodo(indice, 'inicio', event.target.value)}
                    isInvalid={Boolean(error)}
                  />
                </Form.Group>

                <Form.Group controlId={`${baseId}-${clave}-fin`}>
                  <Form.Label>Hasta</Form.Label>
                  <Form.Control
                    type="date"
                    value={periodo.fin}
                    onChange={(event) => actualizarPeriodo(indice, 'fin', event.target.value)}
                    isInvalid={Boolean(error)}
                  />
                </Form.Group>

                {error ? (
                  <p className="invalid-feedback" id={`${baseId}-${clave}-error`} role="alert">
                    <Icon name="error" size={16} />
                    <span>{error}</span>
                  </p>
                ) : null}

                <Button
                  variant="link"
                  size="sm"
                  className="periodo__vaciar"
                  onClick={() => vaciarPeriodo(indice)}
                  disabled={vacio}
                >
                  Vaciar
                </Button>
              </fieldset>
            )
          })}

          <div className="resumen-calculo">
            <p className="resumen-calculo__etiqueta">Total asignado</p>
            <p className="resumen-calculo__total">
              <span className="resumen-calculo__valor tabular">{NUMERO.format(resumen.totalDias)}</span>
              <span className="resumen-calculo__unidad">
                {resumen.totalDias === 1 ? 'día' : 'días'}
              </span>
            </p>
            <p className="resumen-calculo__detalle">
              {resumen.periodosProgramados === 0
                ? 'Programa un período para calcular los días.'
                : `${resumen.periodosProgramados} de 3 períodos programados.`}
            </p>
            <p className="resumen-calculo__nota">Cuenta el día de inicio y el de fin.</p>

            {/* Mismo cálculo que la tabla y el modal de creación: días a corte
                menos días asignados. Al editar los períodos el número se mueve,
                así que verlo aquí evita tener que volver a la tabla. */}
            <p
              className={`dias-usar text-start dias-usar--${semaforoDiasAUsar(diasAUsar).tono}`}
              title={`${semaforoDiasAUsar(diasAUsar).etiqueta}: ${UN_DECIMAL.format(corte)} días a corte − ${UN_DECIMAL.format(resumen.totalDias)} asignados = ${UN_DECIMAL.format(diasAUsar)}`}
            >
              Días a usar <span className="tabular">{UN_DECIMAL.format(diasAUsar)}</span>
            </p>
            <p className="resumen-calculo__nota">
              {UN_DECIMAL.format(corte)} a corte − {UN_DECIMAL.format(resumen.totalDias)} asignados
            </p>
          </div>
        </div>

        <div className="bloque-cierre">
          <Form.Group controlId={`${baseId}-ingreso`}>
            <Form.Label>Fecha de ingreso</Form.Label>
            <Form.Control
              type="date"
              value={fechaIngreso}
              onChange={(event) => setFechaIngreso(event.target.value)}
              min={ultimoDia || undefined}
            />
            <Form.Text>
              {ingreso
                ? ingresoDesactualizado
                  ? `Según los períodos, el ingreso sería el ${formatIsoDate(ingreso, 'long')}.`
                  : 'Coincide con el día siguiente al último período.'
                : 'Se calcula al programar el primer período.'}
              {ingresoDesactualizado ? (
                <>
                  {' '}
                  <Button
                    variant="link"
                    size="sm"
                    className="p-0 align-baseline"
                    onClick={() => setFechaIngreso(ingreso)}
                  >
                    Usar esa fecha
                  </Button>
                </>
              ) : null}
            </Form.Text>
          </Form.Group>

          <Form.Group controlId={`${baseId}-observaciones`}>
            <Form.Label>
              Observaciones <span className="opcional">(opcional)</span>
            </Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              value={observaciones}
              onChange={(event) => setObservaciones(event.target.value)}
              maxLength={500}
              placeholder="Acuerdos con el líder de UNES, reemplazos, condiciones del turno…"
            />
            <Form.Text>{observaciones.length}/500 caracteres.</Form.Text>
          </Form.Group>
        </div>

        <div className="nota nota--warn" style={{ marginTop: 'var(--space-5)' }}>
          <Icon name="advertencia" size={18} />
          <span>
            Los días se calculan a partir de las fechas y no se pueden editar a mano. Al guardar se
            reemplazan los períodos de esta asignación.
          </span>
        </div>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="outline-secondary" onClick={onHide} disabled={saving}>
          Cancelar
        </Button>
        <Button variant="primary" onClick={handleGuardar} disabled={saving} aria-busy={saving || undefined}>
          {saving ? (
            <>
              <span className="btn__spinner" aria-hidden="true" />
              Guardando…
            </>
          ) : (
            <>
              <Icon name="aprobar" size={18} />
              Guardar períodos
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
