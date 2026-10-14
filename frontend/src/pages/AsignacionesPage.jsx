/**
 * Asignaciones de vacaciones.
 *
 * La tabla es **la plantilla que corresponde a la sesión**: una fila por
 * colaborador de la vista corporativa `PBI_Colaborador_Vacaciones`, con la
 * asignación que tenga (o ninguna). Talento Humano entra sin UNES y ve toda la
 * plantilla de la empresa; los demás cargos, sólo la de su UNES. Los que todavía
 * no tienen fechas aparecen igual, porque son justamente a quienes hay que
 * programárselas.
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
 * El filtro por UNES lo aplica el **servidor** con la UNES de la sesión: a quien
 * entra con una UNES no le llega la plantilla de otras, así que no hay nada que
 * filtrar en el navegador. Talento Humano sí recibe todo y por eso tiene el
 * filtro de UNES en la barra.
 *
 * La tabla se pagina **de a 20 registros**. La búsqueda y los filtros se aplican
 * antes de paginar: el total que se ve es el de los filtros, no el de la vista.
 *
 * Si la vista corporativa no responde, el servidor degrada al listado local de
 * asignaciones y lo dice en `origen`; la pantalla lo avisa.
 *
 * Descargas
 * ---------
 * El botón «Descargar» abre un submenú con dos documentos que genera el
 * **servidor** con las plantillas oficiales:
 *
 *   - «Descargar planilla»    → la planilla de vacaciones en PDF. Talento Humano
 *     elige la UNES en un modal; los demás cargos descargan la suya sin pasar
 *     por el modal, porque el servidor la limita a la UNES de la sesión.
 *   - «Descargar plano UNOEE» → el plano en Excel, en un modal que elige entre
 *     el plano general o el de una UNES. Sólo lo ve Talento Humano; el backend
 *     además lo exige con `@require_talento_humano`, así que ocultar la opción
 *     no es el control.
 *
 * La búsqueda y el filtro de estado del navegador no viajan: los documentos son
 * por UNES, que es como están definidos.
 */

import { useDeferredValue, useId, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import OverlayTrigger from 'react-bootstrap/OverlayTrigger'
import Pagination from 'react-bootstrap/Pagination'
import Popover from 'react-bootstrap/Popover'
import Table from 'react-bootstrap/Table'
import Swal from 'sweetalert2'
import AsignarPeriodosModal from '../components/AsignarPeriodosModal'
import DecisionModal from '../components/DecisionModal'
import DescargarPlanillaModal from '../components/DescargarPlanillaModal'
import DescargarPlanoModal from '../components/DescargarPlanoModal'
import EmpleadoDetalleModal from '../components/EmpleadoDetalleModal'
import EmptyState from '../components/EmptyState'
import Icon from '../components/Icon'
import NuevaAsignacionModal from '../components/NuevaAsignacionModal'
import StatusChip from '../components/StatusChip'
import { useAuth } from '../auth/useAuth'
import useAsignaciones, { mensajeDeError } from '../hooks/useAsignaciones'
import { useNotificaciones } from '../notifications/useNotificaciones'
import { reportesApi } from '../services/api'
import { descargarBlob } from '../utils/descargas'
import { NUMERO } from '../utils/fechas'
import { semaforoDiasAUsar } from '../utils/periodos'

/** Filas por página de la tabla. */
const POR_PAGINA = 20

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

/**
 * Números de página a mostrar: siempre el primero, el último y los vecinos del
 * actual. Los huecos se representan con un valor de texto, no con un número, para
 * que nadie confunda la elipsis con una página.
 */
function ventanaDePaginas(actual, total) {
  if (total <= 7) return Array.from({ length: total }, (_, indice) => indice + 1)

  const candidatas = [1, total, actual - 1, actual, actual + 1]
    .filter((numero) => numero >= 1 && numero <= total)
    .sort((a, b) => a - b)

  const salida = []
  let anterior = 0
  for (const numero of candidatas) {
    if (anterior && numero - anterior > 1) salida.push(`hueco-${numero}`)
    salida.push(numero)
    anterior = numero
  }
  return salida
}

export default function AsignacionesPage() {
  const searchId = useId()
  const stateId = useId()
  const unesId = useId()

  const { esTalentoHumano, puedeAprobar, unes } = useAuth()
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
  /* El contador del sidebar y esta bandeja comparten estado: tras una acción que
     genera un aviso, se refresca para que el número del menú lo refleje. */
  const { recargar: recargarNotificaciones } = useNotificaciones()

  const [query, setQuery] = useState('')
  const [estado, setEstado] = useState('todas')
  const [filtroUnes, setFiltroUnes] = useState('todas')
  const [pagina, setPagina] = useState(1)

  const [empleadoAbierto, setEmpleadoAbierto] = useState(null)
  const [fechasAbiertas, setFechasAbiertas] = useState(null)
  const [decisionAbierta, setDecisionAbierta] = useState(null)
  const [nuevaAbierta, setNuevaAbierta] = useState(false)
  const [nuevaInicial, setNuevaInicial] = useState(null)
  const [guardando, setGuardando] = useState(false)
  const [menuAbierto, setMenuAbierto] = useState(null)
  const [menuDescargaAbierto, setMenuDescargaAbierto] = useState(false)
  /* Qué documento se está generando: 'planilla' | 'plano' | null. */
  const [descargando, setDescargando] = useState(null)
  /* Modales de descarga: planilla (Talento Humano) y plano UNOEE. */
  const [modalPlanillaAbierto, setModalPlanillaAbierto] = useState(false)
  const [modalPlanoAbierto, setModalPlanoAbierto] = useState(false)

  const deferredQuery = useDeferredValue(query)

  /* UNES de la tabla, con su descripción para el desplegable. Se arma una sola
     vez para el filtro de la barra y para los dos modales de descarga. */
  const opcionesUnes = useMemo(() => {
    const mapa = new Map()
    for (const fila of filas) {
      const valor = String(fila.unes || '').trim()
      if (!valor || mapa.has(valor)) continue
      const descripcion = String(fila.descUnes || '').trim()
      mapa.set(valor, descripcion ? `${valor} · ${descripcion}` : valor)
    }
    return [...mapa.entries()]
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.value.localeCompare(b.value, 'es'))
  }, [filas])

  const unesDisponibles = useMemo(() => opcionesUnes.map((opcion) => opcion.value), [opcionesUnes])

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

  /* Paginación sobre lo ya filtrado: la búsqueda y los filtros mandan; la página
     sólo recorta lo que se ve. */
  const totalPaginas = Math.max(1, Math.ceil(filtradas.length / POR_PAGINA))
  const paginaActual = Math.min(pagina, totalPaginas)
  const visibles = useMemo(
    () => filtradas.slice((paginaActual - 1) * POR_PAGINA, paginaActual * POR_PAGINA),
    [filtradas, paginaActual],
  )
  const primerVisible = filtradas.length === 0 ? 0 : (paginaActual - 1) * POR_PAGINA + 1
  const ultimoVisible = Math.min(paginaActual * POR_PAGINA, filtradas.length)

  const paginas = useMemo(
    () => ventanaDePaginas(paginaActual, totalPaginas),
    [paginaActual, totalPaginas],
  )

  /* Cambiar la búsqueda o un filtro devuelve a la primera página: quedarse en la
     cinco de una lista de dos no muestra nada. Se reinicia al cambiar el filtro y
     no con un efecto sobre su valor, que provocaría un render de más. */
  function irAPagina(destino) {
    setPagina(Math.min(Math.max(1, destino), totalPaginas))
  }

  function cambiarQuery(valor) {
    setQuery(valor)
    setPagina(1)
  }

  function cambiarEstado(valor) {
    setEstado(valor)
    setPagina(1)
  }

  function cambiarFiltroUnes(valor) {
    setFiltroUnes(valor)
    setPagina(1)
  }

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
    setPagina(1)
  }

  /* -- Descargas ----------------------------------------------------------- */

  /**
   * Descarga un documento generado por el servidor.
   *
   * `tipo` es `'planilla'` (PDF) o `'plano'` (Excel UNOEE). `unes` es opcional:
   * sin él, el servidor decide el alcance —la UNES de la sesión para la
   * planilla, o toda la plantilla para el plano—.
   */
  async function ejecutarDescarga({ tipo, unes }) {
    const esPlano = tipo === 'plano'
    setDescargando(tipo)

    Swal.fire({
      ...SWAL_BASE,
      title: esPlano ? 'Generando el plano UNOEE…' : 'Generando la planilla…',
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    })

    try {
      const { blob, filename } = esPlano
        ? await reportesApi.planoUnoee(unes)
        : await reportesApi.planilla(unes)

      const nombre =
        filename || (esPlano ? 'plano_vacaciones.xlsx' : 'planilla_vacaciones.pdf')
      descargarBlob(blob, nombre)

      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: esPlano ? 'Plano descargado' : 'Planilla descargada',
        html: `<strong>${nombre}</strong><br /><span style="color:#5a6b7b">${NUMERO.format(
          Math.max(1, Math.round(blob.size / 1024)),
        )} kB · ábrelo con ${esPlano ? 'Excel' : 'un lector de PDF'}</span>`,
        confirmButtonText: 'Listo',
      })
    } catch (error) {
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudo generar la descarga',
        // «Prohibido» aquí significa que el cargo no es de Talento Humano: el
        // mensaje del backend es genérico, así que se concreta para la descarga.
        text:
          error?.code === 'FORBIDDEN_ROLE'
            ? 'El plano UNOEE es exclusivo de Talento Humano.'
            : mensajeDeError(error),
        confirmButtonText: 'Entendido',
      })
    } finally {
      setDescargando(null)
    }
  }

  /** «Descargar planilla»: Talento Humano elige la UNES; el resto descarga directo. */
  function abrirDescargarPlanilla() {
    setMenuDescargaAbierto(false)
    if (esTalentoHumano) {
      setModalPlanillaAbierto(true)
      return
    }
    // Sin modal: el servidor limita el PDF a la UNES de la sesión.
    ejecutarDescarga({ tipo: 'planilla' })
  }

  async function descargarPlanilla(unes) {
    setModalPlanillaAbierto(false)
    await ejecutarDescarga({ tipo: 'planilla', unes })
  }

  /** «Descargar plano UNOEE»: abre el modal con alcance general o por UNES. */
  function abrirDescargarPlano() {
    setMenuDescargaAbierto(false)
    setModalPlanoAbierto(true)
  }

  async function descargarPlano({ unes }) {
    setModalPlanoAbierto(false)
    await ejecutarDescarga({ tipo: 'plano', unes: unes || undefined })
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
      // El aviso acaba de registrarse en el servidor: se refresca el contador
      // del sidebar para que lo refleje sin recargar la página.
      await recargarNotificaciones()
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
      await recargarNotificaciones()
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
      await recargarNotificaciones()
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
              : 'Toda la plantilla de la empresa con sus días de vacaciones.'}{' '}
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
          <OverlayTrigger
            trigger="click"
            placement="bottom-end"
            rootClose
            show={menuDescargaAbierto}
            onToggle={setMenuDescargaAbierto}
            overlay={
              <Popover id="menu-descargas" className="acciones__popover">
                <Popover.Body className="acciones__cuerpo">
                  {/* El plano UNOEE es exclusivo de Talento Humano. Además de
                      ocultarlo aquí, el backend lo exige con 403. */}
                  {esTalentoHumano ? (
                    <button
                      type="button"
                      className="acciones__item"
                      disabled={descargando !== null}
                      onClick={abrirDescargarPlano}
                    >
                      <Icon name="plano" size={16} />
                      Descargar plano UNOEE
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="acciones__item"
                    disabled={descargando !== null}
                    onClick={abrirDescargarPlanilla}
                  >
                    <Icon name="planilla" size={16} />
                    Descargar planilla
                  </button>
                </Popover.Body>
              </Popover>
            }
          >
            <Button
              variant="outline-secondary"
              aria-haspopup="menu"
              aria-expanded={menuDescargaAbierto}
              disabled={descargando !== null}
            >
              <Icon name="descargar" size={18} />
              Descargar
              <Icon name="desplegar" size={16} />
            </Button>
          </OverlayTrigger>
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
              {unes ? 'Plantilla de la UNES' : 'Plantilla de la empresa'}
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
                  onChange={(event) => cambiarQuery(event.target.value)}
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
                onChange={(event) => cambiarEstado(event.target.value)}
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
                  onChange={(event) => cambiarFiltroUnes(event.target.value)}
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
            <>
              {/* El contenedor lleva el desplazamiento horizontal y `min-width: 0`
                  para que la tabla se desplace dentro de la tarjeta en lugar de
                  estirar la página entera. */}
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
                    {visibles.map((fila) => (
                      <tr
                        key={`${fila.identificacion}-${fila.id ?? 'sin'}`}
                        data-sin-asignacion={fila.sinAsignacion ? 'si' : undefined}
                      >
                        <td title={fila.descUnes || undefined} classname="text-wrap">{fila.descUnes || '—'}</td>
                        <td title={fila.empleado || undefined}>{fila.empleado}</td>
                        <td className="tabular">{fila.identificacion || '—'}</td>
                        <td>{fila.unes || '—'}</td>
                        <td title={fila.cargo || undefined}>{fila.cargo || '—'}</td>
                        <td>
                          {/* En columna, no en fila: el botón «Motivo» al lado del
                              chip desbordaba la columna y se montaba encima del
                              dato de «Corte». Apilado, cada cosa ocupa su sitio. */}
                          <div className="d-flex flex-column align-items-start gap-2">
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

              <div className="tabla-paginador">
                <p className="tabla-paginador__info">
                  Mostrando {NUMERO.format(primerVisible)}–{NUMERO.format(ultimoVisible)} de{' '}
                  {NUMERO.format(filtradas.length)}{' '}
                  {filtradas.length === 1 ? 'colaborador' : 'colaboradores'}
                  {totalPaginas > 1 ? ` · página ${paginaActual} de ${totalPaginas}` : ''}
                </p>

                <Pagination
                  className="tabla-paginador__controles"
                  aria-label="Paginación de la tabla de asignaciones"
                  size="sm"
                >
                  <Pagination.First
                    onClick={() => irAPagina(1)}
                    disabled={paginaActual === 1}
                    aria-label="Ir a la primera página"
                  />
                  <Pagination.Prev
                    onClick={() => irAPagina(paginaActual - 1)}
                    disabled={paginaActual === 1}
                    aria-label="Página anterior"
                  />
                  {paginas.map((valor) =>
                    typeof valor === 'number' ? (
                      <Pagination.Item
                        key={valor}
                        active={valor === paginaActual}
                        onClick={() => irAPagina(valor)}
                        aria-label={`Ir a la página ${valor}`}
                      >
                        {valor}
                      </Pagination.Item>
                    ) : (
                      <Pagination.Ellipsis key={valor} disabled />
                    ),
                  )}
                  <Pagination.Next
                    onClick={() => irAPagina(paginaActual + 1)}
                    disabled={paginaActual === totalPaginas}
                    aria-label="Página siguiente"
                  />
                  <Pagination.Last
                    onClick={() => irAPagina(totalPaginas)}
                    disabled={paginaActual === totalPaginas}
                    aria-label="Ir a la última página"
                  />
                </Pagination>
              </div>
            </>
          ) : (
            <EmptyState
              icon="buscarPersona"
              title={
                cargando
                  ? 'Consultando los colaboradores…'
                  : filas.length === 0
                    ? unes
                      ? 'No hay colaboradores para esta UNES'
                      : 'No hay colaboradores en la plantilla'
                    : 'Ningún colaborador coincide con la búsqueda'
              }
              text={
                cargando
                  ? 'Un momento.'
                  : filas.length === 0
                    ? unes
                      ? `La vista no devolvió colaboradores para la UNES ${unes}. Revisa el número o consulta con Soporte.`
                      : 'La vista no devolvió colaboradores. Consulta con Soporte.'
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

      {/* Descargas: dos modales, uno por documento. El de la planilla sólo se
          abre para Talento Humano (los demás descargan su UNES directo). La
          `key` reinicia el estado interno en cada apertura. */}
      <DescargarPlanillaModal
        key={modalPlanillaAbierto ? 'planilla-abierta' : 'planilla-cerrada'}
        show={modalPlanillaAbierto}
        opcionesUnes={opcionesUnes}
        unesInicial={filtroUnes !== 'todas' ? filtroUnes : ''}
        descargando={descargando !== null}
        onHide={() => setModalPlanillaAbierto(false)}
        onConfirmar={descargarPlanilla}
      />

      <DescargarPlanoModal
        key={modalPlanoAbierto ? 'plano-abierto' : 'plano-cerrado'}
        show={modalPlanoAbierto}
        opcionesUnes={opcionesUnes}
        unesInicial={filtroUnes !== 'todas' ? filtroUnes : ''}
        descargando={descargando !== null}
        onHide={() => setModalPlanoAbierto(false)}
        onConfirmar={descargarPlano}
      />
    </>
  )
}
