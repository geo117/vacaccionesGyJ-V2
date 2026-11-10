/**
 * Resumen general.
 *
 * Cuatro indicadores y nada más. El alcance lo decide el servidor: `GET
 * /api/resumen` devuelve los totales de toda la empresa para Talento Humano y
 * para el admin, y los de la UNES de la sesión para cualquier otro cargo. Esta
 * vista no filtra: sólo presenta lo que recibe y ajusta los rótulos al alcance.
 *
 * Al entrar durante los seis días previos al **1 de diciembre de 2026** se
 * muestra un aviso de vacaciones colectivas con la cuenta regresiva. Pasada esa
 * fecha, el backend desactiva las cuentas que no sean admin ni Talento Humano.
 *
 * Los cuatro indicadores son los mismos en ambos casos porque los resuelve la
 * misma consulta; lo que cambia es la unidad que cubren. «Usuarios registrados»
 * para una UNES es su plantilla de colaboradores, no las cuentas de la
 * aplicación (que no llevan UNES: es un dato de la sesión).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Swal from 'sweetalert2'
import Icon from '../components/Icon'
import { ApiError, resumenApi } from '../services/api'
import { useAuth } from '../auth/useAuth'
import { NUMERO } from '../utils/fechas'
import {
  debeMostrarAviso,
  diasHastaLimite,
  textoCuentaRegresiva,
} from '../utils/vacaciones_colectivas'

export default function ResumenPage() {
  const { veTodaLaPlantilla, unes } = useAuth()
  const [datos, setDatos] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState(null)
  const avisoMostrado = useRef(false)

  const traerResumen = useCallback(async () => {
    try {
      return { datos: await resumenApi.obtener(), error: null }
    } catch (error) {
      return {
        datos: null,
        error: error instanceof ApiError ? error.message : 'No pudimos cargar el resumen.',
      }
    }
  }, [])

  const recargar = useCallback(async () => {
    setCargando(true)
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

  /* Aviso de vacaciones colectivas: se muestra al entrar al resumen en los
     seis días previos al 1 de diciembre de 2026. Es informativo; el corte de
     cuentas lo aplica el backend cuando pasa la fecha. */
  useEffect(() => {
    if (cargando || avisoMostrado.current || !debeMostrarAviso()) return
    avisoMostrado.current = true
    const dias = diasHastaLimite()
    Swal.fire({
      icon: 'warning',
      title: 'Vacaciones colectivas',
      html: `
        <p style="margin:0 0 12px">
          Se acaba el tiempo de asignar las vacaciones colectivas; regístralas antes del
          <strong>1 de diciembre de 2026</strong>.
        </p>
        <p style="margin:0;color:#5a6b7b">${textoCuentaRegresiva(dias)} para el cierre.</p>
      `,
      confirmButtonText: 'Entendido',
      confirmButtonColor: '#003366',
      customClass: { popup: 'gv-swal' },
    })
  }, [cargando])

  const totales = datos?.totales ?? {}
  // Sólo hay alcance por UNES cuando la persona no ve toda la plantilla y entró
  // con una UNES digitada.
  const alcanceUnes = !veTodaLaPlantilla && Boolean(unes)

  const indicadores = [
    {
      id: 'usuarios',
      label: 'Usuarios registrados',
      value: totales.usuarios ?? 0,
      tone: 'info',
      icon: 'empleado',
      foot: alcanceUnes
        ? `Colaboradores de la UNES ${unes}`
        : 'Cuentas registradas en la base de datos',
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
            {alcanceUnes
              ? `Estado de las asignaciones de la UNES ${unes}, con sus cifras actuales.`
              : 'Estado de las asignaciones de toda la empresa, con sus cifras actuales.'}
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
            <p className="kpi__value tabular">{cargando ? '—' : NUMERO.format(kpi.value)}</p>
            <p className="kpi__foot">{kpi.foot}</p>
          </article>
        ))}
      </section>
    </>
  )
}
