"""Áreas de la filial: agrupación de colaboradores por cédula.

``data filial/areas_filial.json`` es un diccionario ``área → colaboradores``. La
lista de cada área trae ``cedula``, ``empleado``, ``cargo`` y ``area``. El dato
que comparte con la plantilla corporativa es la **cédula**, así que es la llave
para saber a qué área pertenece cada fila del tablero.

Sólo se usa para el filtro por área de Talento Humano y administración. El
servidor anota cada fila con su ``area`` y devuelve la lista de áreas junto con
el tablero; la interfaz se limita a filtrar lo que ya recibió (ver
:func:`app.listar_asignaciones`).

Si el archivo falta o no tiene la estructura esperada se devuelve un índice
vacío: el tablero sigue funcionando, sólo que sin filtro por área.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from filial import normalizar_cedula

logger = logging.getLogger(__name__)

# Vive junto a este módulo, en la misma carpeta con espacio que ``filial.json``.
AREAS_JSON_PATH = Path(__file__).resolve().parent / "data filial" / "areas_filial.json"


@dataclass(frozen=True)
class IndiceAreas:
    """Áreas disponibles y el área que corresponde a cada cédula."""

    areas: tuple[str, ...]
    por_cedula: Mapping[str, str]

    def area_de(self, cedula: Any) -> str:
        """Área de una cédula; cadena vacía si no figura en el archivo."""
        return self.por_cedula.get(normalizar_cedula(cedula), "")


def cargar_indice() -> IndiceAreas:
    """Lee el archivo y arma el índice ``cédula → área``.

    La llave de cada conjunto es el nombre del área. Se conservan todas las áreas
    aunque alguna no tenga colaboradores en la empresa de la sesión: la interfaz
    decide qué mostrar con las filas que recibe.
    """
    try:
        if not AREAS_JSON_PATH.is_file():
            logger.warning("areas_filial.json no encontrado en %s", AREAS_JSON_PATH)
            return IndiceAreas(areas=(), por_cedula={})

        with AREAS_JSON_PATH.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        if not isinstance(datos, dict):
            logger.warning("areas_filial.json no tiene la estructura esperada (diccionario).")
            return IndiceAreas(areas=(), por_cedula={})

        por_cedula: dict[str, str] = {}
        areas: list[str] = []
        for nombre_area, colaboradores in datos.items():
            area = " ".join(str(nombre_area or "").split())
            if not area:
                continue
            areas.append(area)
            if not isinstance(colaboradores, list):
                continue
            for colaborador in colaboradores:
                if isinstance(colaborador, dict):
                    cedula = normalizar_cedula(colaborador.get("cedula"))
                else:
                    cedula = normalizar_cedula(colaborador)
                # Una cédula repetida se queda con la primera área: el archivo es
                # la fuente y no se inventa una pertenencia múltiple.
                if cedula:
                    por_cedula.setdefault(cedula, area)

        return IndiceAreas(
            areas=tuple(sorted(set(areas), key=lambda valor: valor.casefold())),
            por_cedula=por_cedula,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Error leyendo areas_filial.json")
        return IndiceAreas(areas=(), por_cedula={})


def anotar_areas(
    filas: Sequence[dict[str, Any]],
    indice: IndiceAreas | None = None,
) -> list[dict[str, Any]]:
    """Devuelve las filas con su ``area``, sin modificar los diccionarios originales.

    La búsqueda es por ``identificacion`` (la cédula), que es el dato que
    comparten el archivo de áreas y la vista de colaboradores.
    """
    indice = indice or cargar_indice()
    if not indice.por_cedula:
        return list(filas)
    return [{**fila, "area": indice.area_de(fila.get("identificacion"))} for fila in filas]
