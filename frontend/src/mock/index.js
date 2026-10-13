/**
 * DATOS FICTICIOS — no provienen de SQL Server.
 *
 * El backend sólo expone hoy los endpoints de autenticación
 * (`/api/auth/login`, `/api/auth/logout`, `/api/auth/session`). Las consultas
 * reales a `dbo.Usuarios` y a las tablas de asignaciones aún no están
 * implementadas, así que las vistas de contenido se dibujan con estos
 * fixtures con el fin de validar la estructura visual y la interacción.
 *
 * Reglas de uso:
 *  1. Todo dato de este archivo es inventado y debe mostrarse con la franja
 *     `FIXTURE_DISCLAIMER` visible; nunca debe presentarse como información
 *     real de talento humano.
 *  2. Cuando se implemente el endpoint real, se reemplaza el import y estos
 *     objetos se eliminan; no se dejan como respaldo silencioso.
 *  3. Nada aquí puede usarse para tomar una decisión sobre una persona.
 */

export const FIXTURE_META = Object.freeze({
  isFake: true,
  label: 'Datos de ejemplo',
  generatedAt: '2026-10-12T09:00:00-05:00',
  note: 'Cifras inventadas para revisar el diseño. No corresponden a personas ni a solicitudes reales.',
})

export const FIXTURE_DISCLAIMER =
  'Estas cifras son datos de ejemplo (mock): no provienen de la base de datos y no deben usarse para tomar decisiones.'

/** Indicadores del resumen. */
export const dashboardKpis = [
  {
    id: 'pendientes',
    label: 'Asignaciones pendientes',
    value: 128,
    tone: 'warn',
    icon: 'pendiente',
    foot: '42 llevan más de 5 días sin revisión',
  },
  {
    id: 'aprobadas',
    label: 'Aprobadas este mes',
    value: 341,
    tone: 'ok',
    icon: 'aprobada',
    foot: 'Frente a 298 del mes anterior',
  },
  {
    id: 'rechazadas',
    label: 'Devueltas al área',
    value: 27,
    tone: 'danger',
    icon: 'rechazada',
    foot: 'Motivo más frecuente: fechas superpuestas',
  },
  {
    id: 'dias',
    label: 'Días programados',
    value: 4820,
    tone: 'brand',
    icon: 'dias',
    foot: 'Promedio de 12,4 días por colaborador',
  },
]

/** Actividad reciente del resumen. */
export const recentActivity = [
  {
    id: 'ACT-3041',
    empleado: 'Ana María Restrepo',
    identificacion: '10245871',
    unes: 'UNES 120',
    cargo: 'Auxiliar administrativo',
    estado: 'pendiente',
    dias: 15,
    fechaRegreso: '2026-11-04',
  },
  {
    id: 'ACT-3038',
    empleado: 'Julián Ospina Cardona',
    identificacion: '79452110',
    unes: 'UNES 118',
    cargo: 'Operario de planta',
    estado: 'aprobada',
    dias: 8,
    fechaRegreso: '2026-10-27',
  },
  {
    id: 'ACT-3035',
    empleado: 'Leidy Johana Marín',
    identificacion: '10369982',
    unes: 'UNES 120',
    cargo: 'Técnica de calidad',
    estado: 'rechazada',
    dias: 22,
    fechaRegreso: '2026-12-01',
  },
  {
    id: 'ACT-3030',
    empleado: 'Carlos Andrés Peña',
    identificacion: '71258934',
    unes: 'UNES 121',
    cargo: 'Supervisor de turno',
    estado: 'aprobada',
    dias: 5,
    fechaRegreso: '2026-10-22',
  },
  {
    id: 'ACT-3026',
    empleado: 'Diana Carolina Serna',
    identificacion: '43987120',
    unes: 'UNES 118',
    cargo: 'Analista de nómina',
    estado: 'pendiente',
    dias: 12,
    fechaRegreso: '2026-11-10',
  },
]

/**
 * Detalle de los tres períodos de cada asignación.
 *
 * `periodos` es la fuente de verdad para el modal de asignación: cada entrada
 * tiene `inicio` y `fin` en `aaaa-mm-dd` o `null` cuando ese período aún no se
 * programa. El total de días se calcula sumando los períodos, nunca se escribe
 * a mano.
 */
const detallePorRadicado = {
  'ACT-3041': {
    periodos: [
      { inicio: '2026-10-20', fin: '2026-10-24' },
      { inicio: null, fin: null },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-11-04',
    observaciones: 'Solicitud radicada por el líder de UNES 120.',
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-11',
  },
  'ACT-3038': {
    periodos: [
      { inicio: '2026-10-19', fin: '2026-10-23' },
      { inicio: '2026-10-26', fin: '2026-10-26' },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-10-27',
    observaciones: 'Período partido para cubrir el turno de inventario.',
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-09',
  },
  'ACT-3035': {
    periodos: [
      { inicio: '2026-11-16', fin: '2026-12-01' },
      { inicio: null, fin: null },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-12-01',
    observaciones: 'Se solicitó el período completo en una sola franja.',
    motivoRechazo: 'Superposición con el período 2 de otras dos personas del mismo turno.',
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-08',
  },
  'ACT-3030': {
    periodos: [
      { inicio: '2026-10-19', fin: '2026-10-23' },
      { inicio: null, fin: null },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-10-22',
    observaciones: null,
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-07',
  },
  'ACT-3026': {
    periodos: [
      { inicio: '2026-11-02', fin: '2026-11-06' },
      { inicio: '2026-11-09', fin: '2026-11-09' },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-11-10',
    observaciones: 'Pendiente confirmar el tercer período con la persona.',
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-05',
  },
  'ACT-3021': {
    periodos: [
      { inicio: '2026-10-19', fin: '2026-10-24' },
      { inicio: null, fin: null },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-10-24',
    observaciones: null,
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-04',
  },
  'ACT-3018': {
    periodos: [
      { inicio: '2026-10-27', fin: '2026-10-30' },
      { inicio: '2026-11-03', fin: '2026-11-05' },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-11-06',
    observaciones: 'Aprendiz SENA: períodos cortos por compromiso de formación.',
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-02',
  },
  'ACT-3012': {
    periodos: [
      { inicio: '2026-11-16', fin: '2026-12-15' },
      { inicio: null, fin: null },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-12-15',
    observaciones: 'Solicita 30 días continuos por viaje familiar.',
    motivoRechazo: 'Excede los días acumulados disponibles y coincide con el cierre de mes.',
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-10-01',
  },
  'ACT-3009': {
    periodos: [
      { inicio: '2026-10-20', fin: '2026-10-26' },
      { inicio: '2026-10-28', fin: '2026-11-02' },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-11-02',
    observaciones: null,
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-09-30',
  },
  'ACT-3004': {
    periodos: [
      { inicio: '2026-10-22', fin: '2026-10-30' },
      { inicio: null, fin: null },
      { inicio: null, fin: null },
    ],
    fechaIngreso: '2026-10-31',
    observaciones: 'Pendiente validar disponibilidad del equipo de redes.',
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-09-28',
  },
  'ACT-2999': {
    periodos: [
      { inicio: '2026-11-02', fin: '2026-11-06' },
      { inicio: '2026-11-09', fin: '2026-11-13' },
      { inicio: '2026-11-16', fin: '2026-11-19' },
    ],
    fechaIngreso: '2026-11-19',
    observaciones: 'Períodos acordados con el equipo de logística.',
    motivoRechazo: null,
    thAsignacion: 'Talento Humano',
    fechaRegistro: '2026-09-26',
  },
}

/** Lista base de la vista de asignaciones, sin el detalle de períodos. */
const asignacionesBase = [
  ...recentActivity,
  {
    id: 'ACT-3021',
    empleado: 'Óscar Iván Betancur',
    identificacion: '9852147',
    unes: 'UNES 119',
    cargo: 'Conductor',
    estado: 'aprobada',
    dias: 6,
    fechaRegreso: '2026-10-24',
  },
  {
    id: 'ACT-3018',
    empleado: 'Paula Andrea Gil',
    identificacion: '10557742',
    unes: 'UNES 121',
    cargo: 'Aprendiz SENA',
    estado: 'pendiente',
    dias: 10,
    fechaRegreso: '2026-11-06',
  },
  {
    id: 'ACT-3012',
    empleado: 'Jorge Eliécer Ramírez',
    identificacion: '16332987',
    unes: 'UNES 118',
    cargo: 'Jefe de mantenimiento',
    estado: 'rechazada',
    dias: 30,
    fechaRegreso: '2026-12-15',
  },
  {
    id: 'ACT-3009',
    empleado: 'Sandra Milena Torres',
    identificacion: '52998741',
    unes: 'UNES 120',
    cargo: 'Auxiliar de bodega',
    estado: 'aprobada',
    dias: 14,
    fechaRegreso: '2026-11-02',
  },
  {
    id: 'ACT-3004',
    empleado: 'Felipe Andrés Quintero',
    identificacion: '10381120',
    unes: 'UNES 119',
    cargo: 'Técnico de redes',
    estado: 'pendiente',
    dias: 9,
    fechaRegreso: '2026-10-31',
  },
  {
    id: 'ACT-2999',
    empleado: 'Marcela Duque Herrera',
    identificacion: '43661908',
    unes: 'UNES 121',
    cargo: 'Coordinadora de logística',
    estado: 'aprobada',
    dias: 18,
    fechaRegreso: '2026-11-19',
  },
]

/**
 * Listado completo de la vista de asignaciones: cada fila lleva el detalle de
 * sus tres períodos. Se construye aquí para no repetir el detalle dos veces.
 */
export const assignments = asignacionesBase.map((fila) => {
  const detalle = detallePorRadicado[fila.id] ?? {}
  const periodos = (detalle.periodos ?? []).map((periodo) => ({
    inicio: periodo.inicio ?? null,
    fin: periodo.fin ?? null,
  }))
  while (periodos.length < 3) periodos.push({ inicio: null, fin: null })

  return {
    ...fila,
    periodos,
    fechaIngreso: detalle.fechaIngreso ?? fila.fechaRegreso,
    observaciones: detalle.observaciones ?? null,
    motivoRechazo: detalle.motivoRechazo ?? null,
    thAsignacion: detalle.thAsignacion ?? null,
    fechaRegistro: detalle.fechaRegistro ?? null,
  }
})


/** Centros de operación de referencia para los filtros. */
export const operationCenters = [
  { id: 1, nombre: 'UNES 118 — Planta principal', estado: true },
  { id: 2, nombre: 'UNES 119 — Centro de distribución', estado: true },
  { id: 3, nombre: 'UNES 120 — Sede administrativa', estado: true },
  { id: 4, nombre: 'UNES 121 — Bodega norte', estado: true },
  { id: 5, nombre: 'UNES 122 — Bodega sur', estado: false },
]

/** Bandeja de notificaciones. */
export const notifications = [
  {
    id: 'NTF-8801',
    titulo: 'Nueva asignación por revisar',
    mensaje: 'Ana María Restrepo (UNES 120) registró una solicitud de 15 días con regreso el 4/11/2026.',
    leida: false,
    tipo: 'info',
    fecha: '2026-10-12T08:14:00-05:00',
  },
  {
    id: 'NTF-8798',
    titulo: 'Asignación devuelta',
    mensaje: 'La solicitud de Jorge Eliécer Ramírez se devolvió por superposición con el período 2 del equipo.',
    leida: false,
    tipo: 'danger',
    fecha: '2026-10-11T16:42:00-05:00',
  },
  {
    id: 'NTF-8794',
    titulo: 'Corte de nómina próximo',
    mensaje: 'Quedan 3 días hábiles para cerrar las asignaciones del período en curso.',
    leida: false,
    tipo: 'warn',
    fecha: '2026-10-11T07:00:00-05:00',
  },
  {
    id: 'NTF-8790',
    titulo: 'Asignación aprobada',
    mensaje: 'Julián Ospina Cardona (UNES 118) quedó aprobado con 8 días y regreso el 27/10/2026.',
    leida: true,
    tipo: 'ok',
    fecha: '2026-10-10T15:20:00-05:00',
  },
  {
    id: 'NTF-8785',
    titulo: 'Centro de operación inactivo',
    mensaje: 'UNES 122 figura inactivo; sus asignaciones no se incluyen en los totales del resumen.',
    leida: true,
    tipo: 'info',
    fecha: '2026-10-09T11:05:00-05:00',
  },
]
