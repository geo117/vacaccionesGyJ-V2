"""Filtro por filial para los jefes de filial (UNES 106).

`data filial/filial.json` mapea cada **correo de jefe de filial** con las cédulas
de su equipo. Cuando alguien entra con la UNES 106 y su correo figura en ese
archivo, el tablero debe mostrarle **solo** a sus colaboradores y no a toda la
plantilla de la UNES.

Esta lógica viene de ``tomar_funciones_ok.py`` (V1) y se reproduce aquí tal cual:
la comparación de cédulas es por texto, sin decimales ni espacios, porque la
vista corporativa puede devolver ``cedula`` como número (``1015407464.0``) y el
JSON la trae como entero.

Es una **regla de acceso**, así que se aplica en el servidor (ver
:func:`app._filas_tablero`) y no en el navegador: la lista que llega por la API
ya viene acotada. Si el correo no está en el archivo, ``obtener_cedulas_filial``
devuelve ``None`` y quien llama **no filtra**, para no dejar la vista en blanco
si el archivo falta o el jefe de filial todavía no está cargado.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# La UNES que identifica a las filiales. El filtro sólo aplica con este código.
UNES_FILIAL = "106"

# Archivo que mapea correo del jefe de filial → cédulas de su equipo. Vive junto
# a este módulo, en la carpeta con espacio «data filial».
FILIAL_JSON_PATH = Path(__file__).resolve().parent / "data filial" / "filial.json"


def normalizar_cedula(valor: Any) -> str:
    """Normaliza una cédula a texto sin decimales ni espacios para compararla."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if "." in texto:
        texto = texto.split(".")[0]
    return texto.strip()


def obtener_cedulas_filial(correo: str | None) -> set[str] | None:
    """Cédulas del equipo asociadas a un correo de jefe de filial.

    Devuelve:

    * el ``set`` de cédulas (texto) cuando el correo existe en el archivo;
    * ``None`` cuando el correo no está, el archivo falta o no se pudo leer —en
      ese caso quien llama **no** debe aplicar filtro, para no romper la vista.
    """
    if not correo:
        return None
    try:
        if not FILIAL_JSON_PATH.is_file():
            logger.warning("filial.json no encontrado en %s", FILIAL_JSON_PATH)
            return None

        with FILIAL_JSON_PATH.open("r", encoding="utf-8") as archivo:
            filial_data = json.load(archivo)

        if not isinstance(filial_data, dict):
            logger.warning("filial.json no tiene la estructura esperada (diccionario).")
            return None

        correo_key = str(correo).strip().lower()
        registros = None
        for llave, valor in filial_data.items():
            if str(llave).strip().lower() == correo_key:
                registros = valor
                break

        if registros is None:
            logger.info("Correo %s no encontrado en filial.json", correo_key)
            return None

        cedulas: set[str] = set()
        for item in registros or []:
            if isinstance(item, dict):
                cedula = normalizar_cedula(item.get("cedula"))
            else:
                cedula = normalizar_cedula(item)
            if cedula:
                cedulas.add(cedula)
        return cedulas
    except Exception:  # noqa: BLE001
        logger.exception("Error leyendo filial.json")
        return None


def normalizar_unes_filial(valor: Any) -> str:
    """Deja sólo los tres dígitos de la UNES (``'2-106'`` → ``'106'``)."""
    if valor is None:
        return ""
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    return digitos[-3:] if digitos else ""


def filtrar_por_filial(
    filas: Sequence[Any],
    correo: str | None,
    *,
    unes: str = "",
    clave: str = "identificacion",
) -> list[Any]:
    """Acota las filas a la filial del correo cuando la UNES es la de filial.

    ``filas`` puede ser una lista de diccionarios (con la clave ``clave``) o de
    objetos con el atributo ``identificacion``. Si la UNES no es 106, o el correo
    no es de un jefe de filial, se devuelve la lista sin tocar.

    Cada decisión se registra en el log del servidor para poder responder "¿por
    qué este usuario ve toda la UNES y no su filial?" sin adivinar:
    ``unes`` recibida, ``correo`` de la sesión y filas de entrada/salida.
    """
    total = len(filas)

    if normalizar_unes_filial(unes) != UNES_FILIAL:
        return list(filas)

    if not correo:
        logger.info("Filtro filial (UNES %s): la sesión no tiene correo; no se filtra.", unes)
        return list(filas)

    permitidas = obtener_cedulas_filial(correo)
    if permitidas is None:
        logger.info(
            "Filtro filial (UNES %s): el correo %s no está en filial.json; no se filtra.",
            unes,
            correo,
        )
        return list(filas)

    resultado = []
    for fila in filas:
        if isinstance(fila, dict):
            cedula = fila.get(clave)
        else:
            cedula = getattr(fila, clave, None)
        if normalizar_cedula(cedula) in permitidas:
            resultado.append(fila)

    logger.info(
        "Filtro filial aplicado para %s (UNES %s): %d de %d fila(s), %d cédula(s) del equipo.",
        correo,
        UNES_FILIAL,
        len(resultado),
        total,
        len(permitidas),
    )
    return resultado
