/**
 * Configuración de la navegación. Una sola definición alimenta el sidebar, el
 * título de la barra superior y las rutas.
 *
 * `soloTalentoHumano` marca las opciones que no todo el mundo debe ver. El
 * sidebar las filtra con el cargo que devolvió el servidor; el backend las
 * vuelve a proteger por su cuenta.
 */

export const NAV_ITEMS = [
  {
    id: 'resumen',
    to: '/app/resumen',
    label: 'Resumen',
    title: 'Resumen general',
    description: 'Indicadores de asignaciones y consolidado por empleado.',
    icon: 'resumen',
    end: true,
  },
  {
    id: 'asignaciones',
    to: '/app/asignaciones',
    label: 'Asignaciones',
    title: 'Asignaciones de vacaciones',
    description: 'Consulta, programa los períodos y registra la decisión.',
    icon: 'asignaciones',
  },
  {
    id: 'notificaciones',
    to: '/app/notificaciones',
    label: 'Notificaciones',
    title: 'Notificaciones',
    description: 'Novedades del proceso de asignación y decisiones registradas.',
    icon: 'notificaciones',
  },
  {
    id: 'administracion',
    to: '/app/administracion',
    label: 'Administración',
    title: 'Administración de usuarios',
    description: 'Usuarios registrados en la base de datos: crear, editar y eliminar.',
    icon: 'administracion',
    soloTalentoHumano: true,
  },
]

export const DEFAULT_ROUTE = '/app/resumen'

export function findNavItem(pathname) {
  return (
    NAV_ITEMS.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`)) ?? null
  )
}

/** Opciones visibles para un cargo dado. */
export function navItemsPara(esTalentoHumano) {
  return NAV_ITEMS.filter((item) => !item.soloTalentoHumano || esTalentoHumano)
}
