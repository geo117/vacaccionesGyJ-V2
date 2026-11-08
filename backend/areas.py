"""Áreas de las empresas del grupo, agrupadas por cédula.

Cada archivo es un diccionario ``área → colaboradores``. La lista de cada área
trae ``cedula``, ``empleado``, ``cargo`` y ``area``. El dato que comparte con la
plantilla corporativa es la **cédula**, así que es la llave para saber a qué área
pertenece cada fila del tablero.

Hay un archivo por empresa:

* ``data filial/areas_filial.json``   → GyJ Ferreterías (``company`` 2);
* ``data colmena/areas_colmena.json`` → Colmena (``company`` 4).

``company`` es la empresa que el login guarda en ``dbo.Usuarios.company``. El
tablero usa el archivo de la empresa de la sesión. El **admin** ve la plantilla
de las dos empresas y, por eso, su desplegable reúne las dos listas.

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

# Archivos de áreas. La carpeta conserva el espacio en el nombre: es la que ya
# existía en el repositorio.
AREAS_JSON_PATH = Path(__file__).resolve().parent / "data filial" / "areas_filial.json"
AREAS_FILIAL_JSON_PATH = AREAS_JSON_PATH
AREAS_COLMENA_JSON_PATH = (
    Path(__file__).resolve().parent / "data colmena" / "areas_colmena.json"
)

# Empresas del grupo (ver ``users.py`` y el README). La 3 no tiene archivo de
# áreas todavía: se devuelve un índice vacío en lugar de mostrar las de otra.
EMPRESA_GYJ = 2
EMPRESA_ALMASA = 3
EMPRESA_COLMENA = 4


@dataclass(frozen=True)
class IndiceAreas:
    """Áreas disponibles y el área que corresponde a cada cédula."""

    areas: tuple[str, ...]
    por_cedula: Mapping[str, str]

    def area_de(self, cedula: Any) -> str:
        """Área de una cédula; cadena vacía si no figura en el archivo."""
        return self.por_cedula.get(normalizar_cedula(cedula), "")


def _leer_indice(ruta: Path, etiqueta: str) -> IndiceAreas:
    """Lee un archivo ``área → colaboradores`` y arma el índice ``cédula → área``.

    La llave de cada conjunto es el nombre del área. Se conservan todas las áreas
    aunque alguna no tenga colaboradores en la empresa de la sesión: la interfaz
    decide qué mostrar con las filas que recibe. Una cédula repetida se queda con
    la primera área: el archivo es la fuente y no se inventa una pertenencia
    múltiple.
    """
    try:
        if not ruta.is_file():
            logger.warning("%s no encontrado en %s", etiqueta, ruta)
            return IndiceAreas(areas=(), por_cedula={})

        with ruta.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        if not isinstance(datos, dict):
            logger.warning("%s no tiene la estructura esperada (diccionario).", etiqueta)
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
                if cedula:
                    por_cedula.setdefault(cedula, area)

        return IndiceAreas(
            areas=tuple(sorted(set(areas), key=lambda valor: valor.casefold())),
            por_cedula=por_cedula,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Error leyendo %s", etiqueta)
        return IndiceAreas(areas=(), por_cedula={})


def cargar_indice() -> IndiceAreas:
    """Áreas de GyJ Ferreterías (``data filial/areas_filial.json``)."""
    return _leer_indice(AREAS_FILIAL_JSON_PATH, "areas_filial.json")


def cargar_indice_colmena() -> IndiceAreas:
    """Áreas de Colmena (``data colmena/areas_colmena.json``)."""
    return _leer_indice(AREAS_COLMENA_JSON_PATH, "areas_colmena.json")


def _combinar(indices: Sequence[IndiceAreas]) -> IndiceAreas:
    """Une varios índices; la primera aparición de una cédula manda."""
    areas: set[str] = set()
    por_cedula: dict[str, str] = {}
    for indice in indices:
        areas.update(indice.areas)
        for cedula, area in indice.por_cedula.items():
            por_cedula.setdefault(cedula, area)
    return IndiceAreas(
        areas=tuple(sorted(areas, key=lambda valor: valor.casefold())),
        por_cedula=por_cedula,
    )


def cargar_indice_empresa(empresa: int) -> IndiceAreas:
    """Áreas que corresponden a la empresa de la sesión.

    ``4`` → Colmena; ``2`` (y el valor histórico por defecto) → GyJ. Almasa
    todavía no tiene archivo de áreas, así que se devuelve un índice vacío en
    lugar de mostrar las áreas de otra empresa.
    """
    try:
        codigo = int(empresa)
    except (TypeError, ValueError):
        codigo = EMPRESA_GYJ
    if codigo == EMPRESA_COLMENA:
        return cargar_indice_colmena()
    if codigo == EMPRESA_GYJ:
        return cargar_indice()
    if codigo == EMPRESA_ALMASA:
        return IndiceAreas(areas=(), por_cedula={})
    return cargar_indice()


def cargar_indice_admin() -> IndiceAreas:
    """Las dos listas en una sola: el admin ve la plantilla de las dos empresas."""
    return _combinar((cargar_indice(), cargar_indice_colmena()))


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
