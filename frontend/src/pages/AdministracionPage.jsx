/**
 * Administración de usuarios.
 *
 * Exclusiva del administrador. Dos controles, y conviene tener claro cuál manda:
 *
 *  1. La opción del sidebar sólo se dibuja si el cargo es «admin»
 *     (`navItemsPara`) y la ruta está detrás de `RequireAdmin`.
 *  2. **El control real es el backend**: cada endpoint de `/api/usuarios`
 *     responde 403 a quien no tenga ese cargo. Ocultar un botón no impide que
 *     alguien llame a la API con su token.
 *
 * Talento Humano conserva la decisión sobre las asignaciones, pero ya no entra
 * aquí. La contraseña nunca se muestra ni se puede leer: al crear es obligatoria
 * y al editar es opcional ("dejar en blanco para no cambiarla"). El servidor la
 * hashea antes de guardarla.
 */

import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import Alert from 'react-bootstrap/Alert'
import Button from 'react-bootstrap/Button'
import Form from 'react-bootstrap/Form'
import Modal from 'react-bootstrap/Modal'
import OverlayTrigger from 'react-bootstrap/OverlayTrigger'
import Pagination from 'react-bootstrap/Pagination'
import Popover from 'react-bootstrap/Popover'
import Table from 'react-bootstrap/Table'
import Swal from 'sweetalert2'
import EmptyState from '../components/EmptyState'
import Icon from '../components/Icon'
import StatusChip from '../components/StatusChip'
import { useAuth } from '../auth/useAuth'
import { ApiError, usuariosApi } from '../services/api'
import { formatDateTime, NUMERO } from '../utils/fechas'

const SWAL_BASE = {
  confirmButtonColor: '#003366',
  cancelButtonColor: '#5a6b7b',
  customClass: { popup: 'gv-swal' },
}

const CARGO_TALENTO_HUMANO = 'talento humano'
const CARGO_ADMIN = 'admin'

/** Filas por página de la tabla de usuarios. */
const POR_PAGINA = 10

/** Mensajes por código de error del backend. */
const MENSAJES = {
  CORREO_DUPLICADO: 'Ya existe un usuario con ese correo. Usa otro o edita el existente.',
  NOMBRE_REQUERIDO: 'Escribe el nombre completo.',
  CARGO_REQUERIDO: 'Escribe el cargo.',
  COMPANY_REQUERIDA: 'Selecciona la empresa del usuario.',
  COMPANY_INVALIDA: 'La empresa seleccionada no es válida.',
  EMAIL_INVALID: 'El correo no tiene un formato válido.',
  PASSWORD_INVALID: 'La contraseña debe tener al menos 8 caracteres.',
  PASSWORD_WHITESPACE: 'La contraseña no puede empezar ni terminar con un espacio.',
  ULTIMO_TALENTO_HUMANO: 'Debe quedar al menos un usuario de Talento Humano activo con acceso.',
  ULTIMO_ADMIN: 'Debe quedar al menos un usuario administrador activo con acceso.',
  NO_SE_PUEDE_ELIMINAR_A_SI_MISMO: 'No puedes eliminar tu propio usuario.',
  NO_SE_PUEDE_DESACTIVAR_A_SI_MISMO: 'No puedes desactivar tu propio usuario.',
  FORBIDDEN_ROLE: 'Esta opción es exclusiva del administrador.',
  DEPENDENCIA: 'No se puede eliminar: el usuario tiene registros asociados.',
}

const NOMBRE_MAX = 100
const CORREO_MAX = 150
const CARGO_MAX = 60
const PASSWORD_MAX = 128

const ESTADOS = [
  { value: 'todos', label: 'Todos los cargos' },
  { value: 'th', label: 'Solo Talento Humano' },
  { value: 'otros', label: 'Sin Talento Humano' },
]

/**
 * Empresas del grupo. El número es el que se guarda en `Usuarios.company` y el
 * que el backend convierte en el primer dígito de `IDCia_CO` para filtrar la
 * plantilla (`2-…`, `3-…`, `4-…`). Coincide con `EMPRESAS` en `backend/users.py`.
 */
const EMPRESAS = [
  { value: '2', label: 'GyJ Ferreterías' },
  { value: '3', label: 'Almasa' },
  { value: '4', label: 'Colmena' },
]

function etiquetaEmpresa(valor) {
  return EMPRESAS.find((empresa) => empresa.value === String(valor ?? ''))?.label ?? '—'
}

function esTalentoHumano(usuario) {
  return String(usuario?.cargo || '').trim().toLowerCase() === CARGO_TALENTO_HUMANO
}

function esAdministrador(usuario) {
  return String(usuario?.cargo || '').trim().toLowerCase() === CARGO_ADMIN
}

function iniciales(nombre) {
  return String(nombre || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((palabra) => palabra[0]?.toUpperCase() ?? '')
    .join('')
}

export default function AdministracionPage() {
  const { user } = useAuth()

  const [usuarios, setUsuarios] = useState([])
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState(null)
  const [busqueda, setBusqueda] = useState('')
  const [filtroCargo, setFiltroCargo] = useState('todos')
  const [pagina, setPagina] = useState(1)

  const [editando, setEditando] = useState(null) // usuario | 'nuevo'
  const [guardando, setGuardando] = useState(false)
  // Usuario cuyo menú de acciones está abierto, o `null`.
  const [menuAbierto, setMenuAbierto] = useState(null)

  const searchId = useId()
  const filtroId = useId()

  /**
   * Trae la lista y devuelve el resultado, sin tocar el estado.
   *
   * Se separa el "traer" del "guardar en el estado" porque la regla
   * `set-state-in-effect` señala cualquier `setState` que ocurra de forma
   * síncrona al montar. Aquí la primera escritura de estado sucede **después**
   * del `await`, es decir en un microtask, no durante el render.
   */
  const traerUsuarios = useCallback(async () => {
    try {
      const datos = await usuariosApi.listar()
      return { usuarios: datos.usuarios ?? [], error: null }
    } catch (error) {
      return {
        usuarios: null,
        error:
          error instanceof ApiError
            ? MENSAJES[error.code] ?? error.message
            : 'No pudimos cargar los usuarios.',
      }
    }
  }, [])

  /** Recarga la lista, para el botón «Actualizar». */
  const recargar = useCallback(async () => {
    const { usuarios: lista, error } = await traerUsuarios()
    if (lista) setUsuarios(lista)
    setErrorCarga(error)
    setCargando(false)
  }, [traerUsuarios])

  useEffect(() => {
    let vigente = true
    traerUsuarios().then(({ usuarios: lista, error }) => {
      if (!vigente) return
      if (lista) setUsuarios(lista)
      setErrorCarga(error)
      setCargando(false)
    })
    return () => {
      vigente = false
    }
  }, [traerUsuarios])

  const visibles = useMemo(() => {
    const needle = busqueda.trim().toLowerCase()
    return usuarios.filter((u) => {
      if (filtroCargo === 'th' && !esTalentoHumano(u)) return false
      if (filtroCargo === 'otros' && esTalentoHumano(u)) return false
      if (!needle) return true
      return (
        u.nombre.toLowerCase().includes(needle) ||
        u.correo.toLowerCase().includes(needle) ||
        (u.cargo || '').toLowerCase().includes(needle)
      )
    })
  }, [usuarios, busqueda, filtroCargo])

  /* Paginación sobre lo ya filtrado: la búsqueda y el filtro de cargo mandan;
     la página sólo recorta lo que se ve. La página se acota a la última para que
     borrar o desactivar la última fila de una página no deje la tabla vacía. */
  const totalPaginas = Math.max(1, Math.ceil(visibles.length / POR_PAGINA))
  const paginaActual = Math.min(pagina, totalPaginas)
  const visiblesPagina = useMemo(
    () => visibles.slice((paginaActual - 1) * POR_PAGINA, paginaActual * POR_PAGINA),
    [visibles, paginaActual],
  )
  const primerVisible = visibles.length === 0 ? 0 : (paginaActual - 1) * POR_PAGINA + 1
  const ultimoVisible = Math.min(paginaActual * POR_PAGINA, visibles.length)

  function irAPagina(destino) {
    setPagina(Math.min(Math.max(1, destino), totalPaginas))
  }

  /**
   * Talento Humano **activo**. Es el número que decide si se puede desactivar o
   * eliminar a alguien: desactivar al último dejaría el sistema sin quien
   * apruebe asignaciones. Se cuentan los activos, no todos, porque degradar a
   * alguien ya desactivado no cambia nada.
   */
  const totalTalentoHumanoActivos = useMemo(
    () => usuarios.filter((u) => esTalentoHumano(u) && u.activo !== false).length,
    [usuarios],
  )

  /**
   * Administradores **activos**: el número que protege el acceso a esta misma
   * vista. Desactivar o degradar al último dejaría las cuentas sin quien las
   * administre.
   */
  const totalAdminActivos = useMemo(
    () => usuarios.filter((u) => esAdministrador(u) && u.activo !== false).length,
    [usuarios],
  )

  const totalInactivos = useMemo(
    () => usuarios.filter((u) => u.activo === false).length,
    [usuarios],
  )

  const hayFiltros = busqueda.trim() !== '' || filtroCargo !== 'todos'

  async function handleGuardar(datos) {
    setGuardando(true)
    try {
      if (editando === 'nuevo') {
        await usuariosApi.crear(datos)
      } else {
        await usuariosApi.actualizar(editando.id, datos)
      }
      setEditando(null)
      await recargar()
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: editando === 'nuevo' ? 'Usuario creado' : 'Cambios guardados',
        text:
          editando === 'nuevo'
            ? 'La cuenta ya puede iniciar sesión con la contraseña asignada.'
            : 'Los datos del usuario quedaron actualizados.',
        confirmButtonText: 'Listo',
        timer: 4000,
        timerProgressBar: true,
      })
    } catch (error) {
      const codigo = error instanceof ApiError ? error.code : null
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudieron guardar los cambios',
        text: MENSAJES[codigo] ?? (error instanceof ApiError ? error.message : 'Intenta de nuevo.'),
        confirmButtonText: 'Entendido',
      })
    } finally {
      setGuardando(false)
    }
  }

  /**
   * Activa o desactiva una cuenta.
   *
   * Desactivar tiene efecto inmediato: el servidor cierra las sesiones abiertas
   * de esa persona y vuelve a comprobar su estado en cada petición, así que su
   * token deja de servir en el acto. Por eso se advierte en la confirmación.
   */
  async function handleCambiarActivo(usuario, activo) {
    const nombre = usuario.nombre
    const confirmacion = await Swal.fire({
      ...SWAL_BASE,
      icon: activo ? 'question' : 'warning',
      title: activo ? '¿Activar esta cuenta?' : '¿Desactivar esta cuenta?',
      html: activo
        ? `<strong>${nombre}</strong> podrá volver a iniciar sesión con su contraseña actual.`
        : `<strong>${nombre}</strong> no podrá iniciar sesión.<br /><span style="color:#5a6b7b">Si tiene la sesión abierta, se cerrará de inmediato.</span>`,
      showCancelButton: true,
      confirmButtonText: activo ? 'Sí, activar' : 'Sí, desactivar',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: activo ? '#003366' : '#a81f2b',
      reverseButtons: true,
      focusCancel: true,
    })
    if (!confirmacion.isConfirmed) return

    try {
      const respuesta = await usuariosApi.cambiarActivo(usuario.id, activo)
      await recargar()
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: activo ? 'Cuenta activada' : 'Cuenta desactivada',
        text: activo
          ? 'La persona ya puede iniciar sesión.'
          : respuesta.sesionesCerradas
            ? `Se cerraron ${respuesta.sesionesCerradas} sesiones abiertas.`
            : 'La cuenta no podrá iniciar sesión.',
        confirmButtonText: 'Listo',
        timer: 4000,
        timerProgressBar: true,
      })
    } catch (error) {
      const codigo = error instanceof ApiError ? error.code : null
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudo cambiar el estado',
        text: MENSAJES[codigo] ?? (error instanceof ApiError ? error.message : 'Intenta de nuevo.'),
        confirmButtonText: 'Entendido',
      })
    }
  }

  async function handleEliminar(usuario) {
    const confirmacion = await Swal.fire({
      ...SWAL_BASE,
      icon: 'warning',
      title: '¿Eliminar este usuario?',
      html: `Se eliminará la cuenta de <strong>${usuario.nombre}</strong> (${usuario.correo}).<br /><span style="color:#5a6b7b">Sus sesiones abiertas se cerrarán de inmediato. Esta acción no se puede deshacer.</span>`,
      showCancelButton: true,
      confirmButtonText: 'Sí, eliminar',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: '#a81f2b',
      reverseButtons: true,
      focusCancel: true,
    })
    if (!confirmacion.isConfirmed) return

    try {
      const respuesta = await usuariosApi.eliminar(usuario.id)
      await recargar()
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'success',
        title: 'Usuario eliminado',
        text: respuesta.sesionesCerradas
          ? `Se cerraron ${respuesta.sesionesCerradas} sesiones abiertas.`
          : 'La cuenta ya no existe.',
        confirmButtonText: 'Listo',
        timer: 4000,
        timerProgressBar: true,
      })
    } catch (error) {
      const codigo = error instanceof ApiError ? error.code : null
      await Swal.fire({
        ...SWAL_BASE,
        icon: 'error',
        title: 'No se pudo eliminar',
        text: MENSAJES[codigo] ?? (error instanceof ApiError ? error.message : 'Intenta de nuevo.'),
        confirmButtonText: 'Entendido',
      })
    }
  }

  return (
    <>
      <header className="page__header">
        <div>
          <h1 className="page__title">Administración de usuarios</h1>
          <p className="page__lead">
            Cuentas registradas en la base de datos. Desde aquí se crean, se editan y se
            eliminan.
          </p>
        </div>
        <div className="page__actions">
          <Button variant="outline-secondary" onClick={recargar} disabled={cargando}>
            <Icon name="buscar" size={18} />
            Actualizar
          </Button>
          <Button variant="primary" onClick={() => setEditando('nuevo')}>
            <Icon name="crear" size={18} />
            Crear usuario
          </Button>
        </div>
      </header>

      {errorCarga ? (
        <Alert variant="danger" className="d-flex align-items-start gap-2" role="alert">
          <Icon name="error" size={18} />
          <span>{errorCarga}</span>
        </Alert>
      ) : null}

      <Alert variant="info" className="d-flex align-items-start gap-2" role="note">
        <Icon name="escudo" size={18} />
        <span>
          Las contraseñas se guardan con hash y no se pueden consultar: si alguien la olvida, hay
          que asignarle una nueva desde <strong>Editar</strong>.
        </span>
      </Alert>

      <section className="card" aria-labelledby="tabla-usuarios">
        <header className="card__header">
          <div>
            <h2 className="card__title" id="tabla-usuarios">
              Usuarios registrados
            </h2>
            <p className="card__subtitle">
              {cargando
                ? 'Consultando la base de datos…'
                : `${NUMERO.format(visibles.length)} de ${NUMERO.format(usuarios.length)} cuentas · ${NUMERO.format(totalTalentoHumanoActivos)} con Talento Humano activo${
                    totalInactivos > 0 ? ` · ${NUMERO.format(totalInactivos)} inactivas` : ''
                  }`}
            </p>
          </div>
        </header>

        <div className="card__body" style={{ borderBottom: '1px solid var(--line)' }}>
          <div className="toolbar">
            <div className="toolbar__field toolbar__field--grow">
              <Form.Label htmlFor={searchId}>Buscar</Form.Label>
              <div className="field__control">
                <Form.Control
                  id={searchId}
                  type="search"
                  value={busqueda}
                  onChange={(event) => {
                    setBusqueda(event.target.value)
                    setPagina(1)
                  }}
                  placeholder="Nombre, correo o cargo"
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
                  <Icon name="buscarPersona" size={18} />
                </span>
              </div>
            </div>

            <div className="toolbar__field">
              <Form.Label htmlFor={filtroId}>Cargo</Form.Label>
              <Form.Select
                id={filtroId}
                value={filtroCargo}
                onChange={(event) => {
                  setFiltroCargo(event.target.value)
                  setPagina(1)
                }}
              >
                {ESTADOS.map((opcion) => (
                  <option key={opcion.value} value={opcion.value}>
                    {opcion.label}
                  </option>
                ))}
              </Form.Select>
            </div>

            <Button
              variant="outline-secondary"
              onClick={() => {
                setBusqueda('')
                setFiltroCargo('todos')
                setPagina(1)
              }}
              disabled={!hayFiltros}
            >
              Limpiar
            </Button>
          </div>
        </div>

        <div className="card__body card__body--flush">
          {visibles.length > 0 ? (
            <>
              <Table className="data admin-tabla" borderless responsive>
              <caption className="visually-hidden">
                Usuarios registrados con su correo, empresa, cargo, fecha de creación y acciones
                de administración.
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="col-usuario">Usuario</th>
                  <th scope="col">Correo</th>
                  <th scope="col">Empresa</th>
                  <th scope="col" className="col-cargo">Cargo</th>
                  <th scope="col">Acceso</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Creado</th>
                  <th scope="col">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {visiblesPagina.map((usuario) => {
                  const soyYo = usuario.id === user?.id
                  const esTh = esTalentoHumano(usuario)
                  const esAdm = esAdministrador(usuario)
                  const estaActivo = usuario.activo !== false
                  // Desactivar al último Talento Humano activo dejaría el
                  // sistema sin quien apruebe; desactivar al último admin, sin
                  // quien administre. El backend también lo rechaza.
                  const ultimoThActivo = esTh && estaActivo && totalTalentoHumanoActivos <= 1
                  const ultimoAdminActivo = esAdm && estaActivo && totalAdminActivos <= 1
                  const noPuedeDesactivarse = soyYo || ultimoThActivo || ultimoAdminActivo
                  const noPuedeEliminarse =
                    soyYo ||
                    (esTh && !estaActivo && totalTalentoHumanoActivos <= 0) ||
                    (esAdm && !estaActivo && totalAdminActivos <= 0)

                  return (
                    <tr key={usuario.id} data-inactivo={estaActivo ? undefined : 'si'}>
                      <td className="col-usuario">
                        <div className="usuario-celda">
                          <span
                            className="usuario-avatar"
                            data-propio={soyYo ? 'si' : undefined}
                            aria-hidden="true"
                          >
                            {iniciales(usuario.nombre)}
                          </span>
                          <span className="usuario-celda__nombre">
                            {usuario.nombre}
                            {soyYo ? <span className="chip chip--info">Tú</span> : null}
                          </span>
                        </div>
                      </td>
                      <td>{usuario.correo}</td>
                      <td>{usuario.empresa || etiquetaEmpresa(usuario.company)}</td>
                      <td className="col-cargo">{usuario.cargo || '—'}</td>
                      <td>
                        {esTh ? (
                          <StatusChip estado="ok" label="Talento Humano" />
                        ) : esAdm ? (
                          <StatusChip estado="info" label="Administrador" />
                        ) : (
                          <StatusChip estado="info" label="Solo consulta" />
                        )}
                      </td>
                      <td>
                        {estaActivo ? (
                          <StatusChip estado="ok" label="Activo" />
                        ) : (
                          <StatusChip estado="danger" label="Inactivo" />
                        )}
                      </td>
                      <td>{formatDateTime(usuario.fechaCreacion) || '—'}</td>
                      <td>
                        {/* Menú de tres puntos, igual que en asignaciones. Se
                            arma con `OverlayTrigger` + `Popover` porque el
                            `Dropdown` de react-bootstrap aplica modificadores de
                            Popper que competían entre sí y descentraban el menú;
                            el Popover ya trae `preventOverflow` y `strategy:
                            fixed`, que es lo que hace falta dentro de una tabla
                            con desplazamiento horizontal. */}
                        <OverlayTrigger
                          trigger="click"
                          placement="left-start"
                          rootClose
                          show={menuAbierto === usuario.id}
                          onToggle={(next) => setMenuAbierto(next ? usuario.id : null)}
                          overlay={
                            <Popover
                              id={`acciones-usuario-${usuario.id}`}
                              className="acciones__popover"
                            >
                              <Popover.Body className="acciones__cuerpo">
                                <button
                                  type="button"
                                  className="acciones__item"
                                  onClick={() => {
                                    setMenuAbierto(null)
                                    setEditando(usuario)
                                  }}
                                >
                                  <Icon name="editar" size={16} />
                                  Editar
                                </button>

                                <button
                                  type="button"
                                  className="acciones__item"
                                  onClick={() => {
                                    setMenuAbierto(null)
                                    handleCambiarActivo(usuario, !estaActivo)
                                  }}
                                  disabled={noPuedeDesactivarse && estaActivo}
                                  title={
                                    estaActivo && soyYo
                                      ? 'No puedes desactivar tu propio usuario'
                                      : estaActivo && ultimoThActivo
                                        ? 'Debe quedar al menos un Talento Humano activo'
                                        : estaActivo && ultimoAdminActivo
                                          ? 'Debe quedar al menos un administrador activo'
                                          : estaActivo
                                            ? `Desactivar a ${usuario.nombre}`
                                            : `Activar a ${usuario.nombre}`
                                  }
                                >
                                  <Icon name={estaActivo ? 'desactivar' : 'activar'} size={16} />
                                  {estaActivo ? 'Desactivar' : 'Activar'}
                                </button>

                                <hr className="acciones__separador" />

                                <button
                                  type="button"
                                  className="acciones__item acciones__item--peligro"
                                  onClick={() => {
                                    setMenuAbierto(null)
                                    handleEliminar(usuario)
                                  }}
                                  disabled={noPuedeEliminarse}
                                  title={
                                    soyYo
                                      ? 'No puedes eliminar tu propio usuario'
                                      : 'Eliminar definitivamente'
                                  }
                                >
                                  <Icon name="eliminar" size={16} />
                                  Eliminar
                                </button>
                              </Popover.Body>
                            </Popover>
                          }
                        >
                          <button
                            type="button"
                            className="acciones__toggle"
                            aria-label={`Acciones para ${usuario.nombre}`}
                            aria-haspopup="menu"
                            aria-expanded={menuAbierto === usuario.id}
                            title="Acciones"
                          >
                            <Icon name="masOpciones" size={20} />
                          </button>
                        </OverlayTrigger>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>

              <div className="tabla-paginador">
                <p className="tabla-paginador__info">
                  Mostrando {NUMERO.format(primerVisible)}–{NUMERO.format(ultimoVisible)} de{' '}
                  {NUMERO.format(visibles.length)}{' '}
                  {visibles.length === 1 ? 'usuario' : 'usuarios'}
                  {totalPaginas > 1 ? ` · página ${paginaActual} de ${totalPaginas}` : ''}
                </p>

                <Pagination
                  className="tabla-paginador__controles"
                  aria-label="Paginación de la tabla de usuarios"
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
              title={cargando ? 'Consultando los usuarios…' : 'Ningún usuario coincide con el filtro'}
              text={
                cargando
                  ? 'Un momento.'
                  : 'Prueba con otro nombre o correo, o cambia el filtro de cargo.'
              }
              action={
                hayFiltros ? (
                  <Button
                    variant="outline-secondary"
                    onClick={() => {
                      setBusqueda('')
                      setFiltroCargo('todos')
                      setPagina(1)
                    }}
                  >
                    Limpiar filtros
                  </Button>
                ) : null
              }
            />
          )}
        </div>
      </section>

      <UsuarioModal
        key={editando === 'nuevo' ? 'nuevo' : (editando?.id ?? 'cerrado')}
        abierto={Boolean(editando)}
        usuario={editando === 'nuevo' ? null : editando}
        guardando={guardando}
        onCerrar={() => setEditando(null)}
        onGuardar={handleGuardar}
      />
    </>
  )
}

/* --------------------------------------------------------------------------
   Modal de creación y edición
   -------------------------------------------------------------------------- */

function UsuarioModal({ abierto, usuario, guardando, onCerrar, onGuardar }) {
  const esNuevo = !usuario
  const baseId = useId()

  // El estado inicial sale del usuario recibido y el remontaje por `key` lo
  // reinicia al cambiar de fila; así no hace falta un efecto de sincronización.
  const [nombre, setNombre] = useState(usuario?.nombre ?? '')
  const [correo, setCorreo] = useState(usuario?.correo ?? '')
  const [cargo, setCargo] = useState(usuario?.cargo ?? '')
  const [company, setCompany] = useState(String(usuario?.company ?? ''))
  const [password, setPassword] = useState('')
  const [verPassword, setVerPassword] = useState(false)
  const [errores, setErrores] = useState({})

  if (!abierto) return null

  function validar() {
    const nuevos = {}
    if (!nombre.trim()) nuevos.nombre = 'Escribe el nombre completo.'
    else if (nombre.trim().length > NOMBRE_MAX) nuevos.nombre = `Máximo ${NOMBRE_MAX} caracteres.`

    if (!correo.trim()) nuevos.correo = 'Escribe el correo.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo.trim())) {
      nuevos.correo = 'El correo no tiene un formato válido.'
    } else if (correo.trim().length > CORREO_MAX) {
      nuevos.correo = `Máximo ${CORREO_MAX} caracteres.`
    }

    if (!cargo.trim()) nuevos.cargo = 'Escribe el cargo.'
    else if (cargo.trim().length > CARGO_MAX) nuevos.cargo = `Máximo ${CARGO_MAX} caracteres.`

    if (!company) nuevos.company = 'Selecciona la empresa del usuario.'

    if (esNuevo) {
      if (!password) nuevos.password = 'Asigna una contraseña inicial.'
      else if (password.length < 8) nuevos.password = 'Mínimo 8 caracteres.'
    } else if (password && password.length < 8) {
      nuevos.password = 'Mínimo 8 caracteres, o déjala en blanco para no cambiarla.'
    }
    if (password && password !== password.trim()) {
      nuevos.password = 'La contraseña no puede empezar ni terminar con un espacio.'
    }

    return nuevos
  }

  async function handleGuardar() {
    const nuevos = validar()
    if (Object.keys(nuevos).length > 0) {
      setErrores(nuevos)
      const primero = ['nombre', 'correo', 'cargo', 'password', 'company'].find(
        (campo) => nuevos[campo],
      )
      if (primero) document.getElementById(`${baseId}-${primero}`)?.focus()
      return
    }
    setErrores({})

    const datos = {
      nombre: nombre.trim(),
      correo: correo.trim().toLowerCase(),
      cargo: cargo.trim(),
      company: Number(company),
    }
    // En la edición, dejar la contraseña en blanco significa "no cambiarla": no
    // se envía el campo, así el backend no la toca.
    if (password) datos.password = password
    await onGuardar(datos)
  }

  return (
    <Modal show onHide={onCerrar} centered size="lg" backdrop="static" keyboard>
      <Modal.Header closeButton>
        <Modal.Title>
          {esNuevo ? 'Crear usuario' : 'Editar usuario'}
          <small>
            {esNuevo
              ? 'La cuenta podrá iniciar sesión con la contraseña que asignes.'
              : `${usuario.nombre} · ${usuario.correo}`}
          </small>
        </Modal.Title>
      </Modal.Header>

      <Modal.Body>
        <div className="usuario-form">
          <Form.Group controlId={`${baseId}-nombre`} className="usuario-form__ancho">
            <Form.Label>Nombre completo</Form.Label>
            <Form.Control
              value={nombre}
              onChange={(event) => {
                setNombre(event.target.value)
                if (errores.nombre) setErrores((previos) => ({ ...previos, nombre: undefined }))
              }}
              isInvalid={Boolean(errores.nombre)}
              maxLength={NOMBRE_MAX}
              autoComplete="off"
              placeholder="Nombre y apellidos"
            />
            {errores.nombre ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.nombre}</span>
              </p>
            ) : null}
          </Form.Group>

          <Form.Group controlId={`${baseId}-correo`}>
            <Form.Label>Correo</Form.Label>
            <Form.Control
              type="email"
              value={correo}
              onChange={(event) => {
                setCorreo(event.target.value)
                if (errores.correo) setErrores((previos) => ({ ...previos, correo: undefined }))
              }}
              isInvalid={Boolean(errores.correo)}
              maxLength={CORREO_MAX}
              autoComplete="off"
              spellCheck="false"
              placeholder="nombre@gyj.com.co"
            />
            {errores.correo ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.correo}</span>
              </p>
            ) : (
              <Form.Text>Con este correo inicia sesión. No puede repetirse.</Form.Text>
            )}
          </Form.Group>

          <Form.Group controlId={`${baseId}-cargo`}>
            <Form.Label>Cargo</Form.Label>
            <Form.Control
              value={cargo}
              onChange={(event) => {
                setCargo(event.target.value)
                if (errores.cargo) setErrores((previos) => ({ ...previos, cargo: undefined }))
              }}
              isInvalid={Boolean(errores.cargo)}
              maxLength={CARGO_MAX}
              autoComplete="off"
              list={`${baseId}-cargos`}
              placeholder="talento humano"
            />
            <datalist id={`${baseId}-cargos`}>
              <option value="admin" />
              <option value="talento humano" />
              <option value="gerente unes" />
              <option value="analista" />
            </datalist>
            {errores.cargo ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.cargo}</span>
              </p>
            ) : (
              <Form.Text>
                Escribe <strong>admin</strong> para administrar las cuentas y ver toda la
                plantilla; <strong>talento humano</strong> para aprobar o rechazar asignaciones y
                ver también toda la plantilla. Cualquier otro cargo entra en modo consulta.
              </Form.Text>
            )}
          </Form.Group>

          <Form.Group controlId={`${baseId}-password`}>
            <Form.Label>
              Contraseña {esNuevo ? null : <span className="opcional">(en blanco = no cambiarla)</span>}
            </Form.Label>
            <div className="field__control">
              <Form.Control
                type={verPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value)
                  if (errores.password) setErrores((previos) => ({ ...previos, password: undefined }))
                }}
                isInvalid={Boolean(errores.password)}
                maxLength={PASSWORD_MAX}
                autoComplete="new-password"
                className="field__input--with-action"
              />
              <button
                type="button"
                className="field__action"
                onClick={() => setVerPassword((previo) => !previo)}
                aria-pressed={verPassword}
                aria-label={verPassword ? 'Ocultar la contraseña' : 'Mostrar la contraseña'}
              >
                <Icon name={verPassword ? 'ocultar' : 'ver'} size={20} />
              </button>
            </div>
            {errores.password ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.password}</span>
              </p>
            ) : (
              <Form.Text>
                <Icon name="clave" size={14} /> Se guarda con hash; nadie puede consultarla después.
              </Form.Text>
            )}
          </Form.Group>

          <Form.Group controlId={`${baseId}-company`}>
            <Form.Label>Empresa</Form.Label>
            <Form.Select
              value={company}
              onChange={(event) => {
                setCompany(event.target.value)
                if (errores.company) setErrores((previos) => ({ ...previos, company: undefined }))
              }}
              isInvalid={Boolean(errores.company)}
            >
              <option value="">Selecciona una empresa</option>
              {EMPRESAS.map((empresa) => (
                <option key={empresa.value} value={empresa.value}>
                  {empresa.label}
                </option>
              ))}
            </Form.Select>
            {errores.company ? (
              <p className="invalid-feedback" role="alert">
                <Icon name="error" size={16} />
                <span>{errores.company}</span>
              </p>
            ) : (
              <Form.Text>
                Define la plantilla de colaboradores que verá la cuenta. Es una regla de acceso,
                no un dato de presentación.
              </Form.Text>
            )}
          </Form.Group>
        </div>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="outline-secondary" onClick={onCerrar} disabled={guardando}>
          Cancelar
        </Button>
        <Button variant="primary" onClick={handleGuardar} disabled={guardando} aria-busy={guardando || undefined}>
          {guardando ? (
            <>
              <span className="btn__spinner" aria-hidden="true" />
              Guardando…
            </>
          ) : (
            <>
              <Icon name={esNuevo ? 'crear' : 'editar'} size={18} />
              {esNuevo ? 'Crear usuario' : 'Guardar cambios'}
            </>
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  )
}
