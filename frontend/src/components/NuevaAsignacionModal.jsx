/**
 * Modal para registrar una asignación nueva.
 *
 * Pide los datos del colaborador y sus tres períodos. Reutiliza el mismo
 * componente de períodos que la edición, así que el cálculo de días y la
 * validación de cruces son idénticos en los dos caminos: no hay dos reglas que
 * puedan divergir.
 *
 * Con `inicial` se precargan los datos que ya vienen de la vista de
 * colaboradores (UNES, nombre, identificación, cargo, correo y días a corte):
 * si la persona está en la plantilla, no tiene sentido volver a teclearlos.
 *
 * El servidor vuelve a calcular los días y el total; lo que se ve aquí es una
 * previsualización, no el dato que se guarda.
 */

import { useId, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import Modal from 'react-bootstrap/Modal'
import Icon from './Icon'
import { addDays, formatIsoDate, NUMERO } from '../utils/fechas'
import { resumirPeriodos, semaforoDiasAUsar, validarPeriodos } from '../utils/periodos'

const CAMPOS_VACIOS = {
  identificacion: '',
  empleado: '',
  cargo: '',
  descUnes: '',
  unes: '',
  correo: '',
  // Los días a corte no se editan aquí: vienen de la vista del colaborador (o de
  // la asignación, si ya existe) y sólo alimentan el cálculo de «Días a usar».
  diasACorte: '',
  observaciones: '',
  // Fecha de reintegro a labores: se elige a mano y se guarda en
  // `fecha_reintegro_lab`. No se deriva de los períodos.
  fechaReintegroLab: '',
}

const PERIODOS_VACIOS = [
  { inicio: '', fin: '' },
  { inicio: '', fin: '' },
  { inicio: '', fin: '' },
]

/** Lleva una fila de la vista (o de una asignación) a los campos del formulario. */
function aFormulario(inicial) {
  if (!inicial) return CAMPOS_VACIOS
  const corte = inicial.diasACorte
  return {
    identificacion: String(inicial.identificacion ?? ''),
    empleado: String(inicial.empleado ?? ''),
    cargo: String(inicial.cargo ?? ''),
    descUnes: String(inicial.descUnes ?? ''),
    unes: String(inicial.unes ?? ''),
    correo: String(inicial.correo ?? ''),
    // El campo del formulario es texto; un 0 se muestra como "0", no vacío.
    diasACorte: corte === undefined || corte === null ? '' : String(corte),
    observaciones: '',
    fechaReintegroLab: String(inicial.fechaReintegroLab ?? ''),
  }
}

/** Un decimal siempre, para que el cálculo y la tabla muestren lo mismo. */
const UN_DECIMAL = new Intl.NumberFormat('es-CO', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

export default function NuevaAsignacionModal({
  show,
  inicial = null,
  saving = false,
  onHide,
  onCrear,
}) {
  const baseId = useId()
  const precargado = Boolean(inicial)

  // El estado inicial sale de la fila recibida y el remontaje por `key` lo
  // reinicia; así no hace falta un efecto de sincronización.
  const [datos, setDatos] = useState(() => aFormulario(inicial))
  const [periodos, setPeriodos] = useState(PERIODOS_VACIOS)
  const [errores, setErrores] = useState({})

  const resumen = useMemo(() => resumirPeriodos(periodos), [periodos])

  const ultimoDia = useMemo(() => {
    const fines = periodos.map((p) => p.fin).filter(Boolean).sort()
    return fines.length ? fines[fines.length - 1] : ''
  }, [periodos])

  /* Día siguiente al último período: es la fecha de regreso que se guarda en
     `fecha_regreso`. El reintegro a labores de `fecha_reintegro_lab` es otro
     dato, se elige a mano y no se deriva de aquí. */
  const ingreso = ultimoDia ? addDays(ultimoDia, 1) : ''

  /* Días a usar = días a corte − días asignados, en ese orden.
     Los días a corte llegan de la vista del colaborador. Si no vinieran (p. ej.
     una fila de una asignación antigua sin ese dato), el cálculo daría «0 −
     asignados» y mostraría un número que no significa nada: en ese caso se dice
     que no está disponible en lugar de inventarlo. */
  const diasACorteNumero = useMemo(() => {
    const numero = Number(String(datos.diasACorte).trim())
    return Number.isFinite(numero) ? numero : 0
  }, [datos.diasACorte])

  const hayCorte = String(datos.diasACorte).trim() !== ''

  const diasAUsar = useMemo(
    () => Math.round((diasACorteNumero - resumen.totalDias) * 10) / 10,
    [diasACorteNumero, resumen.totalDias],
  )

  function actualizar(campo, valor) {
    setDatos((previos) => ({ ...previos, [campo]: valor }))
    setErrores((previos) => {
      if (!previos[campo]) return previos
      const copia = { ...previos }
      delete copia[campo]
      return copia
    })
  }

  function actualizarPeriodo(indice, campo, valor) {
    setPeriodos((previos) =>
      previos.map((periodo, i) => (i === indice ? { ...periodo, [campo]: valor } : periodo)),
    )
    setErrores((previos) => {
      const clave = `periodo${indice + 1}`
      if (!previos[clave]) return previos
      const copia = { ...previos }
      delete copia[clave]
      return copia
    })
  }

  function validar() {
    const nuevos = { ...validarPeriodos(periodos) }

    if (!datos.identificacion.trim()) nuevos.identificacion = 'Escribe la identificación.'
    else if (datos.identificacion.trim().length > 50) nuevos.identificacion = 'Máximo 50 caracteres.'

    if (!datos.empleado.trim()) nuevos.empleado = 'Escribe el nombre del colaborador.'
    else if (datos.empleado.trim().length > 150) nuevos.empleado = 'Máximo 150 caracteres.'

    if (datos.cargo.trim().length > 100) nuevos.cargo = 'Máximo 100 caracteres.'
    if (datos.descUnes.trim().length > 255) nuevos.descUnes = 'Máximo 255 caracteres.'
    if (datos.unes.trim().length > 10) nuevos.unes = 'Máximo 10 caracteres.'

    if (datos.correo.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(datos.correo.trim())) {
      nuevos.correo = 'El correo no tiene un formato válido.'
    }
    if (datos.correo.trim().length > 150) nuevos.correo = 'Máximo 150 caracteres.'

    /* El reintegro a labores no puede caer dentro de las vacaciones: si coincide
       con el último día programado (o es anterior), la persona seguiría de
       vacaciones ese día. */
    if (datos.fechaReintegroLab && ultimoDia && datos.fechaReintegroLab <= ultimoDia) {
      nuevos.fechaReintegroLab = 'Debe ser posterior al último día de vacaciones.'
    }

    if (resumen.periodosProgramados === 0) {
      nuevos.general = 'Programa al menos un período de vacaciones.'
    }

    return nuevos
  }

  async function handleCrear() {
    const nuevos = validar()
    if (Object.keys(nuevos).length > 0) {
      setErrores(nuevos)
      const orden = [
        'identificacion',
        'empleado',
        'fechaReintegroLab',
        'periodo1',
        'periodo2',
        'periodo3',
      ]
      const primero = orden.find((clave) => nuevos[clave])
      if (primero) {
        const sufijo = primero.startsWith('periodo') ? '-inicio' : ''
        document.getElementById(`${baseId}-${primero}${sufijo}`)?.focus()
      }
      return
    }
    setErrores({})

    await onCrear({
      identificacion: datos.identificacion.trim(),
      empleado: datos.empleado.trim(),
      cargo: datos.cargo.trim(),
      descUnes: datos.descUnes.trim(),
      unes: datos.unes.trim(),
      correo: datos.correo.trim().toLowerCase() || null,
      diasACorte: datos.diasACorte === '' ? 0 : Number(datos.diasACorte),
      observaciones: datos.observaciones.trim() || null,
      fechaReintegroLab: datos.fechaReintegroLab || null,
      periodos,
      fechaIngreso: ingreso || null,
    })
  }

  return (
    <Modal show={show} onHide={onHide} centered size="xl" backdrop="static" keyboard>
      <Modal.Header closeButton>
        <Modal.Title>
          Nueva asignación de vacaciones
          <small>
            {precargado
              ? `${inicial.empleado} · ${inicial.identificacion} · ${inicial.descUnes || inicial.unes}`
              : 'Registra al colaborador y programa hasta tres períodos.'}
          </small>
        </Modal.Title>
      </Modal.Header>

      <Modal.Body>
        {precargado ? (
          <Alert variant="info" className="d-flex align-items-start gap-2" role="note">
            <Icon name="info" size={18} />
            <span>
              Los datos del colaborador vienen de la vista de la empresa. Sólo falta programar los
              períodos.
            </span>
          </Alert>
        ) : null}

        {errores.general ? (
          <Alert variant="danger" className="d-flex align-items-center gap-2" role="alert">
            <Icon name="error" size={18} />
            <span>{errores.general}</span>
          </Alert>
        ) : null}

        <div className="bloque-cierre" style={{ marginTop: 0 }}>
          <Form.Group controlId={`${baseId}-identificacion`}>
            <Form.Label>Identificación</Form.Label>
            <Form.Control
              value={datos.identificacion}
              onChange={(event) => actualizar('identificacion', event.target.value)}
              isInvalid={Boolean(errores.identificacion)}
              maxLength={50}
              autoComplete="off"
            />
            {errores.identificacion ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.identificacion}</span>
              </p>
            ) : null}
          </Form.Group>

          <Form.Group controlId={`${baseId}-empleado`}>
            <Form.Label>Colaborador</Form.Label>
            <Form.Control
              value={datos.empleado}
              onChange={(event) => actualizar('empleado', event.target.value)}
              isInvalid={Boolean(errores.empleado)}
              maxLength={150}
              autoComplete="off"
            />
            {errores.empleado ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.empleado}</span>
              </p>
            ) : null}
          </Form.Group>

          <Form.Group controlId={`${baseId}-cargo`}>
            <Form.Label>Cargo</Form.Label>
            <Form.Control
              value={datos.cargo}
              onChange={(event) => actualizar('cargo', event.target.value)}
              isInvalid={Boolean(errores.cargo)}
              maxLength={100}
              autoComplete="off"
            />
            {errores.cargo ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.cargo}</span>
              </p>
            ) : null}
          </Form.Group>

          <Form.Group controlId={`${baseId}-unes`}>
            <Form.Label>UNES</Form.Label>
            <Form.Control
              value={datos.unes}
              onChange={(event) => actualizar('unes', event.target.value)}
              isInvalid={Boolean(errores.unes)}
              maxLength={10}
              autoComplete="off"
            />
            {errores.unes ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.unes}</span>
              </p>
            ) : null}
          </Form.Group>

          <Form.Group controlId={`${baseId}-descUnes`}>
            <Form.Label>
              Descripción de UNES <span className="opcional">(opcional)</span>
            </Form.Label>
            <Form.Control
              value={datos.descUnes}
              onChange={(event) => actualizar('descUnes', event.target.value)}
              isInvalid={Boolean(errores.descUnes)}
              maxLength={255}
              autoComplete="off"
            />
            {errores.descUnes ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.descUnes}</span>
              </p>
            ) : null}
          </Form.Group>

          <Form.Group controlId={`${baseId}-correo`}>
            <Form.Label>
              Correo <span className="opcional">(opcional)</span>
            </Form.Label>
            <Form.Control
              type="email"
              value={datos.correo}
              onChange={(event) => actualizar('correo', event.target.value)}
              isInvalid={Boolean(errores.correo)}
              maxLength={150}
              autoComplete="off"
              spellCheck="false"
            />
            {errores.correo ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.correo}</span>
              </p>
            ) : (
              ''
            )}
          </Form.Group>
        </div>

        <div className="periodos" style={{ marginTop: 'var(--space-4)' }}>
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

            {/* Días a usar: días a corte menos los días asignados, en ese orden.
                No se escribe: se recalcula solo al mover los períodos. Los días a
                corte vienen de la vista del colaborador (o de la asignación, si
                ya existe), por eso aquí se muestra la operación completa. */}
            {hayCorte ? (
              <>
                <div
                  className={`dias-usar dias-usar--${semaforoDiasAUsar(diasAUsar).tono}`}
                  style={{ alignSelf: 'flex-start' }}
                  title={`${semaforoDiasAUsar(diasAUsar).etiqueta}: ${UN_DECIMAL.format(diasACorteNumero)} días a corte − ${UN_DECIMAL.format(resumen.totalDias)} asignados = ${UN_DECIMAL.format(diasAUsar)}`}
                >
                  Días a usar <span className="tabular">{UN_DECIMAL.format(diasAUsar)}</span>
                </div>
                <p className="resumen-calculo__nota">
                  {UN_DECIMAL.format(diasACorteNumero)} a corte −{' '}
                  {UN_DECIMAL.format(resumen.totalDias)} asignados
                </p>
              </>
            ) : (
              <p className="resumen-calculo__nota">
                Días a usar: sin dato de días a corte para este colaborador.
              </p>
            )}

            {/* El ingreso sugerido ya no se deriva de los períodos: es la fecha
                de reintegro a labores que se elige en el campo de la izquierda
                de Observaciones, y se refleja aquí tal cual. */}
            <p className="resumen-calculo__nota">
              {datos.fechaReintegroLab
                ? `Ingreso sugerido: ${formatIsoDate(datos.fechaReintegroLab, 'long')}`
                : 'Ingreso sugerido: elige la fecha de reintegro a labores.'}
            </p>
          </div>
        </div>

        {/* Reintegro a labores a la izquierda de Observaciones: la etiqueta es
            «Fecha de ingreso», la misma de la ficha del colaborador, y el dato
            se guarda en `fecha_reintegro_lab` (no en `fecha_regreso`). */}
        <div className="bloque-cierre" style={{ marginTop: 'var(--space-4)' }}>
          <Form.Group controlId={`${baseId}-fechaReintegroLab`}>
            <Form.Label>Fecha de ingreso</Form.Label>
            <Form.Control
              type="date"
              value={datos.fechaReintegroLab}
              onChange={(event) => actualizar('fechaReintegroLab', event.target.value)}
              isInvalid={Boolean(errores.fechaReintegroLab)}
              min={ultimoDia || undefined}
            />
            {errores.fechaReintegroLab ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.fechaReintegroLab}</span>
              </p>
            ) : (
              <Form.Text>Reintegro a labores: día en que vuelve a trabajar.</Form.Text>
            )}
          </Form.Group>

          <Form.Group controlId={`${baseId}-observaciones`}>
            <Form.Label>
              Observaciones <span className="opcional">(opcional)</span>
            </Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              value={datos.observaciones}
              onChange={(event) => actualizar('observaciones', event.target.value)}
              maxLength={4000}
              placeholder="Acuerdos con el líder de UNES, reemplazos, condiciones del turno…"
            />
            <Form.Text>{datos.observaciones.length}/4000 caracteres.</Form.Text>
          </Form.Group>
        </div>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="outline-secondary" onClick={onHide} disabled={saving}>
          Cancelar
        </Button>
        <Button variant="primary" onClick={handleCrear} disabled={saving} aria-busy={saving || undefined}>
          {saving ? (
            <>
              <span className="btn__spinner" aria-hidden="true" />
              Guardando…
            </>
          ) : (
            <>
              <Icon name="crear" size={18} />
              Registrar asignación
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
