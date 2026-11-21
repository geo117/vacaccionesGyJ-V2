"""Días de corte de los empleados temporales de Colmena (empresa 4).

``data colmena/temporales.json`` reúne a los colaboradores temporales de la
empresa 4. Para ellos, la columna **CORTE** no sale de la vista corporativa
(``dias_vacaciones_corteDic``) sino del campo ``DIAS`` de este archivo. El
cálculo posterior es el de siempre: ``días a usar = días a corte − días
asignados``.

Reglas:

* La coincidencia es por **cédula** y sólo aplica a filas de la empresa 4: una
  cédula del archivo no cambia los días de otra empresa.
* Si el archivo falta, no se puede leer o la cédula no está en él, no se altera
  ninguna fila: la vista corporativa sigue siendo la fuente.
* El archivo se cachea al primer uso, igual que ``colmena.json``. Si se edita,
  hay que reiniciar el backend para que el tablero y los cálculos lo tomen.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from filial import normalizar_cedula

logger = logging.getLogger(__name__)

# Vive junto a los demás datos de Colmena, en la carpeta con espacio.
TEMPORALES_JSON_PATH = (
    Path(__file__).resolve().parent / "data colmena" / "temporales.json"
)

# La empresa a la que pertenece el archivo y a la que se limita el ajuste.
EMPRESA_TEMPORALES = "4"

# Campos del JSON. Se aceptan también en minúsculas para tolerar ediciones
# manuales del archivo.
CAMPO_CEDULA = "CEDULA"
CAMPO_DIAS = "DIAS"
CAMPO_COMPANIA = "COMPANIA"


def _campo(registro: dict[str, Any], nombre: str) -> Any:
    """Valor del campo, aceptando el nombre en mayúsculas o minúsculas."""
    for clave in (nombre, nombre.lower()):
        if clave in registro:
            return registro[clave]
    return None


def _numero_dias(valor: Any) -> float | None:
    """``DIAS`` como número redondeado a un decimal; ``None`` si no es válido."""
    try:
        dias = float(valor)
    except (TypeError, ValueError):
        return None
    if dias != dias or dias < 0:  # NaN o negativo
        return None
    return round(dias, 1)


def _registros(datos: Any) -> list[Any]:
    """Lista de temporales desde la estructura del archivo.

    El archivo actual es ``{"temporales": [...]}``; se acepta también una lista
    en la raíz para no romper si alguien lo simplifica.
    """
    if isinstance(datos, dict):
        datos = datos.get("temporales")
    return datos if isinstance(datos, list) else []


def cargar_temporales() -> dict[str, float]:
    """Lee ``temporales.json`` y devuelve ``cédula → días`` (sin caché).

    Si el archivo falta o no tiene la forma esperada se devuelve un diccionario
    vacío: un archivo de datos no debe tumbar el tablero.
    """
    try:
        if not TEMPORALES_JSON_PATH.is_file():
            logger.warning("temporales.json no encontrado en %s", TEMPORALES_JSON_PATH)
            return {}

        with TEMPORALES_JSON_PATH.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        por_cedula: dict[str, float] = {}
        for registro in _registros(datos):
            if not isinstance(registro, dict):
                continue
            cedula = normalizar_cedula(_campo(registro, CAMPO_CEDULA))
            dias = _numero_dias(_campo(registro, CAMPO_DIAS))
            compania = str(
                _campo(registro, CAMPO_COMPANIA) or EMPRESA_TEMPORALES
            ).strip()
            if not cedula or dias is None or compania != EMPRESA_TEMPORALES:
                continue
            # La primera aparición manda; en el archivo no hay cédulas repetidas.
            por_cedula.setdefault(cedula, dias)
        return por_cedula
    except Exception:  # noqa: BLE001
        logger.exception("Error leyendo temporales.json")
        return {}


@lru_cache(maxsize=1)
def _temporales() -> dict[str, float]:
    return cargar_temporales()


def dias_temporales(cedula: Any, empresa: Any = 0) -> float | None:
    """Días de corte del archivo para la cédula, o ``None`` si no aplica.

    ``empresa`` acota el ajuste a la empresa 4. Se deja vacío cuando quien llama
    no conoce la empresa (una asignación antigua sin prefijo, por ejemplo): en
    ese caso manda la cédula, que es la llave del archivo.
    """
    codigo = str(empresa or "").strip()
    if codigo and codigo != EMPRESA_TEMPORALES:
        return None
    return _temporales().get(normalizar_cedula(cedula))


def _es_empresa_4(fila: dict[str, Any]) -> bool:
    """¿La fila pertenece a Colmena? Sin UNES se deja pasar (dato desconocido)."""
    unes = str(fila.get("unes") or "").strip()
    if not unes:
        return True
    return unes.split("-", 1)[0].strip() == EMPRESA_TEMPORALES


def _dias_asignados(fila: dict[str, Any]) -> float:
    """Días ya programados en la fila.

    El tablero los trae en ``diasAsignados``; el listado local de respaldo, en
    ``totalDias``. Si no viene ninguno, se asume cero, igual que la tabla.
    """
    valor = fila.get("diasAsignados")
    if valor is None:
        valor = fila.get("totalDias")
    try:
        return round(float(valor or 0), 1)
    except (TypeError, ValueError):
        return 0.0


def anotar_temporales(
    filas: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aplica el ``DIAS`` del archivo a las filas de empleados temporales.

    Devuelve copias de las filas afectadas con:

    * ``diasACorte`` tomado del archivo (la columna «Corte»);
    * ``diasAUsar`` recalculado con la misma fórmula de siempre;
    * ``corteTemporal`` en ``True`` para que la interfaz lo distinga.

    Las filas de otras empresas o de cédulas que no están en el archivo se
    devuelven intactas.
    """
    dias_por_cedula = _temporales()
    if not dias_por_cedula:
        return list(filas)

    salida: list[dict[str, Any]] = []
    for fila in filas:
        cedula = normalizar_cedula(fila.get("identificacion"))
        dias = dias_por_cedula.get(cedula)
        if dias is None or not _es_empresa_4(fila):
            salida.append(fila)
            continue

        asignados = _dias_asignados(fila)
        salida.append(
            {
                **fila,
                "diasACorte": round(dias, 1),
                "diasAsignados": asignados,
                "diasAUsar": round(dias - asignados, 1),
                "corteTemporal": True,
            }
        )
    return salida
