/**
 * Fechas que no cuentan como días de vacaciones (domingos y festivos).
 *
 * La lista es **una sola para todo el sistema**: vive en
 * `backend/fechas_inactivas.json` y la leen las dos partes —el backend en
 * `backend/dias_inhabiles.py` y esta vista—. Si se duplicara aquí, la pantalla y
 * la base podrían calcular días distintos para las mismas fechas al guardar.
 *
 * Este archivo sólo la expone con el nombre que ya usan los componentes. Para
 * agregar un festivo se edita el JSON, no este módulo.
 */
import datos from '../../../backend/fechas_inactivas.json'

export const diasInhabiles = datos.diasInhabiles
