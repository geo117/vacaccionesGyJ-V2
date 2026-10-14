/**
 * Descarga de archivos generados por el servidor (planilla PDF, plano Excel).
 *
 * A diferencia del reporte CSV, que se arma en el navegador, estos documentos
 * los produce el backend con las plantillas institucionales. Aquí sólo se
 * resuelve el nombre del archivo y se dispara la descarga del `Blob`.
 */

/**
 * Extrae el nombre del archivo de la cabecera `Content-Disposition`.
 *
 * Prioriza `filename*` (con codificación UTF-8), que es el que conserva tildes y
 * la ñ; si no está, cae al `filename` simple. Devuelve `null` cuando la cabecera
 * no trae un nombre utilizable, para que quien llame decida el reemplazo.
 */
export function nombreDeArchivoDesdeCabecera(cabecera) {
  if (!cabecera) return null

  const extendido = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(cabecera)
  if (extendido) {
    const bruto = extendido[1].trim().replace(/^"|"$/g, '')
    try {
      return decodeURIComponent(bruto)
    } catch {
      return bruto
    }
  }

  const simple = /filename\s*=\s*"?([^";]+)"?/i.exec(cabecera)
  return simple ? simple[1].trim() : null
}

/**
 * Dispara la descarga de un `Blob` y libera la URL al terminar.
 *
 * Se retira el `<a>` después del clic y se revoca la URL en el siguiente ciclo
 * —revocar antes puede cancelar la descarga—.
 */
export function descargarBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = filename
  enlace.rel = 'noopener'
  document.body.appendChild(enlace)
  enlace.click()
  document.body.removeChild(enlace)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
