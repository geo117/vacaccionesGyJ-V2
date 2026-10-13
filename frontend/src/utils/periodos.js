/**
 * Reglas de negocio de los períodos de vacaciones.
 *
 * Este módulo es **puro**: no conoce React, ni la base de datos, ni el DOM. Por
 * eso puede probarse directamente con Node
 * (`node --input-type=module`), sin montar un componente ni un navegador.
 *
 * Vive separado de `hooks/useAsignaciones.js` a propósito: el hook se encarga
 * del estado y el componente de la pantalla; aquí queda lo que hay que poder
 * probar y explicar sin interfaz de por medio —cuántos días son, si dos
 * períodos se cruzan, cuándo vuelve la persona—.
 */

import { daysInclusive, parseIsoDate } from '../utils/fechas.js'

/**
 * Días de un período.
 *
 * Devuelve `null` mientras falte una fecha o el rango esté invertido. Es
 * importante no devolver `0`: "no programado" y "cero días" son cosas distintas
 * y confundirlas produciría un total creíble pero falso.
 */
export function calcularDias(periodo) {
  if (!periodo?.inicio || !periodo?.fin) return null
  return daysInclusive(periodo.inicio, periodo.fin)
}

/** Suma los días programados y cuenta cuántos períodos tienen fechas. */
export function resumirPeriodos(periodos) {
  const dias = (periodos ?? []).map(calcularDias)
  const programados = dias.filter((valor) => valor !== null)
  return {
    totalDias: programados.reduce((suma, valor) => suma + valor, 0),
    periodosProgramados: programados.length,
    dias,
  }
}

/**
 * Detecta errores en los tres períodos.
 *
 * El solapamiento es el que de verdad importa: dos períodos encima del mismo
 * día inflan el total y descuadran la nómina. Un período completamente vacío es
 * válido (no todo el mundo parte sus vacaciones en tres).
 *
 * @returns {Record<string, string>} claves `periodo1..3` con el mensaje de error.
 */
export function validarPeriodos(periodos) {
  const errores = {}

  periodos.forEach((periodo, indice) => {
    const clave = `periodo${indice + 1}`
    const tieneInicio = Boolean(periodo.inicio)
    const tieneFin = Boolean(periodo.fin)

    if (!tieneInicio && !tieneFin) return // Período deliberadamente vacío.

    if (!tieneInicio || !tieneFin) {
      errores[clave] = 'Completa la fecha de inicio y la de fin.'
      return
    }
    if (daysInclusive(periodo.inicio, periodo.fin) === null) {
      errores[clave] = 'La fecha de fin no puede ser anterior a la de inicio.'
    }
  })

  // Sólo se cruzan los períodos que ya están bien formados. Cada uno debe
  // nombrar a su contraparte: si el 2 choca con el 3, el 3 choca con el 2.
  const completos = periodos
    .map((periodo, indice) => ({ ...periodo, indice }))
    .filter((periodo) => periodo.inicio && periodo.fin && !errores[`periodo${periodo.indice + 1}`])

  /** índice → números de período con los que choca. */
  const cruces = new Map()

  for (let i = 0; i < completos.length; i += 1) {
    for (let j = i + 1; j < completos.length; j += 1) {
      const a = completos[i]
      const b = completos[j]
      const inicioA = parseIsoDate(a.inicio)
      const finA = parseIsoDate(a.fin)
      const inicioB = parseIsoDate(b.inicio)
      const finB = parseIsoDate(b.fin)
      if (!inicioA || !finA || !inicioB || !finB) continue

      if (inicioA <= finB && inicioB <= finA) {
        cruces.set(a.indice, [...(cruces.get(a.indice) ?? []), b.indice + 1])
        cruces.set(b.indice, [...(cruces.get(b.indice) ?? []), a.indice + 1])
      }
    }
  }

  for (const [indice, contrarios] of cruces) {
    const lista = [...contrarios].sort((x, y) => x - y)
    errores[`periodo${indice + 1}`] =
      lista.length === 1
        ? `Se cruza con el período ${lista[0]}.`
        : `Se cruza con los períodos ${lista.join(' y ')}.`
  }

  return errores
}

/** Último día programado, o cadena vacía si no hay ninguno. */
export function ultimoDiaProgramado(periodos) {
  const fines = (periodos ?? []).map((periodo) => periodo?.fin).filter(Boolean).sort()
  return fines.length ? fines[fines.length - 1] : ''
}

/** Completa la lista a exactamente tres períodos. */
export function normalizarTresPeriodos(periodos) {
  const lista = (periodos ?? []).slice(0, 3).map((periodo) => ({
    inicio: periodo?.inicio ?? null,
    fin: periodo?.fin ?? null,
  }))
  while (lista.length < 3) lista.push({ inicio: null, fin: null })
  return lista
}

/**
 * Semáforo de «Días a usar».
 *
 * El valor es **días a corte − días asignados**:
 *   positivo  → le quedan días por disfrutar sobre lo que se programó
 *   negativo  → programó más días de los que tiene a corte
 *
 * Umbrales que pidió el negocio, sobre el valor en días:
 *   menos de −3  → rojo
 *   de −3 a 10   → amarillo
 *   más de 10    → verde
 *
 * Los límites son inclusivos hacia el rojo: exactamente −3 es rojo, y
 * exactamente 10 es amarillo. Se documenta porque un umbral mal cerrado es el
 * tipo de detalle que nadie nota hasta que alguien reclama por un color.
 *
 * Devuelve también una `etiqueta`: el color nunca es la única señal.
 */
export function semaforoDiasAUsar(valor) {
  // `Number(null)` es 0 y `Number('')` también, así que hay que descartar los
  // vacíos antes de convertir: si no, un dato ausente se pintaría como «saldo
  // justo» en lugar de «sin dato».
  if (valor === null || valor === undefined || valor === '') {
    return { tono: 'neutral', etiqueta: 'Sin dato' }
  }
  const numero = Number(valor)
  if (!Number.isFinite(numero)) {
    return { tono: 'neutral', etiqueta: 'Sin dato' }
  }
  if (numero < -3) {
    return { tono: 'danger', etiqueta: 'Más días de los que tiene' }
  }
  if (numero <= 10) {
    return { tono: 'warn', etiqueta: 'Ajustado' }
  }
  return { tono: 'ok', etiqueta: 'Le quedan días' }
}
