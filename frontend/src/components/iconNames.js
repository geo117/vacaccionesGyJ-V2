/**
 * Tabla de iconos y metadatos de estado.
 *
 * Vive en su propio archivo para que `Icon.jsx` sólo exporte componentes.
 * Regla del sistema: ningún emoji hace de icono; todo icono sale de aquí, de
 * modo que el trazo, el tamaño y el significado sean consistentes.
 */

import {
  MdChevronLeft,
  MdClose,
  MdDownload,
  MdEditCalendar,
  MdFactCheck,
  MdInsights,
  MdNotifications,
  MdOutlineBeachAccess,
  MdOutlineCheckCircle,
  MdOutlineDangerous,
  MdOutlineErrorOutline,
  MdOutlineEventAvailable,
  MdOutlineInfo,
  MdOutlineLock,
  MdOutlineLogout,
  MdOutlineMenu,
  MdOutlineSearch,
  MdOutlineShield,
  MdOutlineThumbUp,
  MdOutlineVisibility,
  MdOutlineVisibilityOff,
  MdOutlineWarningAmber,
  MdMoreVert,
  MdPersonOutline,
  MdPersonSearch,
  MdManageAccounts,
  MdOutlinePersonAdd,
  MdOutlineEdit,
  MdOutlineDeleteForever,
  MdOutlineKey,
  MdOutlineToggleOn,
  MdOutlineToggleOff,
  MdSchedule,
  MdWarningAmber,
} from 'react-icons/md'
import { HiOutlineInboxStack } from 'react-icons/hi2'

export const ICONS = {
  resumen: MdInsights,
  asignaciones: MdFactCheck,
  notificaciones: MdNotifications,
  pendiente: MdSchedule,
  aprobada: MdOutlineCheckCircle,
  rechazada: MdOutlineDangerous,
  dias: MdOutlineEventAvailable,
  bloqueo: MdOutlineLock,
  escudo: MdOutlineShield,
  salir: MdOutlineLogout,
  menu: MdOutlineMenu,
  buscar: MdOutlineSearch,
  ver: MdOutlineVisibility,
  ocultar: MdOutlineVisibilityOff,
  alerta: MdOutlineWarningAmber,
  error: MdOutlineErrorOutline,
  info: MdOutlineInfo,
  vacio: HiOutlineInboxStack,
  playa: MdOutlineBeachAccess,
  colapsar: MdChevronLeft,
  cerrar: MdClose,
  descargar: MdDownload,
  empleado: MdPersonOutline,
  editarFechas: MdEditCalendar,
  aprobar: MdOutlineThumbUp,
  rechazar: MdOutlineDangerous,
  advertencia: MdWarningAmber,
  masOpciones: MdMoreVert,
  administracion: MdManageAccounts,
  crear: MdOutlinePersonAdd,
  editar: MdOutlineEdit,
  eliminar: MdOutlineDeleteForever,
  clave: MdOutlineKey,
  buscarPersona: MdPersonSearch,
  activar: MdOutlineToggleOn,
  desactivar: MdOutlineToggleOff,
  porDefecto: MdOutlineInfo,
}

/**
 * Estado → `{ label, tone, icon }`.
 *
 * El color nunca viaja solo: `tone` alimenta la clase del chip y `label` la
 * palabra; un estado desconocido cae en informativo, jamás en "aprobada".
 */
export const ESTADO_META = {
  pendiente: { label: 'Pendiente', tone: 'warn', icon: 'pendiente' },
  aprobada: { label: 'Aprobada', tone: 'ok', icon: 'aprobada' },
  rechazada: { label: 'Rechazada', tone: 'danger', icon: 'rechazada' },
  ok: { label: 'Correcta', tone: 'ok', icon: 'aprobada' },
  danger: { label: 'Requiere atención', tone: 'danger', icon: 'alerta' },
  warn: { label: 'Aviso', tone: 'warn', icon: 'alerta' },
  info: { label: 'Información', tone: 'info', icon: 'info' },
}

export function estadoMeta(key) {
  return ESTADO_META[key] ?? ESTADO_META.info
}
