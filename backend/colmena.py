"""Jefes de Colmena: correo → cédulas de su equipo.

``data colmena/colmena.json`` es un diccionario ``correo del jefe → lista de
colaboradores``. La **cédula** es el dato que comparte con la vista corporativa
y, por eso, la llave del filtro del tablero.

Reglas que aplica este módulo:

* Un correo del archivo entra **sin UNES**: su alcance no es una unidad, es su
  equipo. El login lo valida contra una cuenta de la empresa 4 (Colmena).
* Tres correos de dirección del grupo son la excepción: ven los colaboradores
  registrados **a nombre de su propio correo** en ``colmena.json`` y en
  ``data filial/filial.json``. También es un filtro por cédula: la unión de las
  cédulas de las dos entradas de ese correo.

Además, cada colaborador de ``colmena.json`` trae ``SABADO HABIL``. Ese dato
decide si los sábados cuentan como día de vacaciones: ``SI`` los cuenta (trabaja
sábados) y ``NO`` los descuenta, igual que un domingo (ver
:func:`dias_inhabiles.dias_habiles`).

Los archivos se cachean al primer uso (igual que ``fechas_inactivas.json``). Si
se editan, hay que reiniciar el backend para que el login y el tablero los tomen.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from filial import FILIAL_JSON_PATH, normalizar_cedula

logger = logging.getLogger(__name__)

# Vive junto a los demás datos, en la carpeta con espacio «data colmena».
COLMENA_JSON_PATH = Path(__file__).resolve().parent / "data colmena" / "colmena.json"

# Campo de `colmena.json` que dice si el sábado es día hábil para el colaborador.
SABADO_HABIL_CAMPO = "SABADO HABIL"

# Correos de dirección que ven la unión de los dos archivos de colaboradores.
DIRECCION_GRUPO = frozenset(
    {
        "director.riesgos@gyj.com.co",
        "direcciontic@gyj.com.co",
        "direccion_th@gyj.com.co",
    }
)

# Tipos de alcance que devuelve :func:`alcance_de`.
TIPO_EQUIPO = "equipo"
TIPO_GRUPO = "grupo"


@dataclass(frozen=True)
class AlcanceColmena:
    """Qué puede ver un correo de Colmena.

    ``equipo`` limita a las cédulas de la lista de ese correo; ``grupo`` (los
    tres correos de dirección) limita a las cédulas que están a nombre de ese
    mismo correo en ``colmena.json`` y ``filial.json``. En los dos casos la llave
    es la cédula.
    """

    tipo: str
    cedulas: frozenset[str] = frozenset()


def _correo(valor: Any) -> str:
    return str(valor or "").strip().lower()


def _leer_cedulas_por_correo(ruta: Path, etiqueta: str) -> dict[str, frozenset[str]]:
    """Lee un archivo ``correo → colaboradores`` (``colmena.json`` o ``filial.json``)."""
    try:
        if not ruta.is_file():
            logger.warning("%s no encontrado en %s", etiqueta, ruta)
            return {}

        with ruta.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        if not isinstance(datos, dict):
            logger.warning("%s no tiene la estructura esperada (diccionario).", etiqueta)
            return {}

        por_correo: dict[str, frozenset[str]] = {}
        for correo, colaboradores in datos.items():
            clave = _correo(correo)
            if not clave:
                continue
            por_correo[clave] = _cedulas_de(colaboradores)
        return por_correo
    except Exception:  # noqa: BLE001
        logger.exception("Error leyendo %s", etiqueta)
        return {}


def _cedulas_de(colaboradores: Any) -> frozenset[str]:
    """Cédulas de una lista de colaboradores (diccionarios o valores sueltos)."""
    if not isinstance(colaboradores, (list, tuple)):
        return frozenset()
    cedulas: set[str] = set()
    for colaborador in colaboradores or []:
        if isinstance(colaborador, dict):
            cedula = normalizar_cedula(colaborador.get("cedula"))
        else:
            cedula = normalizar_cedula(colaborador)
        if cedula:
            cedulas.add(cedula)
    return frozenset(cedulas)


def cargar_jefes() -> dict[str, frozenset[str]]:
    """Lee ``colmena.json`` y devuelve ``correo → cédulas`` (sin caché).

    Si el archivo falta o no tiene la forma esperada se devuelve un diccionario
    vacío: el login sigue funcionando con las reglas de siempre y se registra el
    aviso. Un archivo de datos no debe tumbar el acceso al sistema.
    """
    return _leer_cedulas_por_correo(COLMENA_JSON_PATH, "colmena.json")


def cargar_filial() -> dict[str, frozenset[str]]:
    """Lee ``data filial/filial.json`` y devuelve ``correo → cédulas`` (sin caché)."""
    return _leer_cedulas_por_correo(FILIAL_JSON_PATH, "filial.json")


def _a_booleano(valor: Any) -> bool | None:
    """``SI``/``NO`` de ``SABADO HABIL`` como booleano; ``None`` si no se reconoce."""
    texto = str(valor or "").strip().lower()
    if texto in {"si", "sí", "s", "1", "true", "yes", "y", "habil", "hábil"}:
        return True
    if texto in {"no", "n", "0", "false", "inhábil", "inhabilitado"}:
        return False
    return None


def cargar_sabados() -> dict[str, bool]:
    """Lee ``SABADO HABIL`` de cada colaborador de ``colmena.json`` (sin caché).

    Devuelve ``cédula → True/False``. ``True`` significa que el sábado es hábil y
    por tanto cuenta como día de vacaciones; ``False`` que no se trabaja y debe
    descontarse. Una cédula sin el campo (o sin valor reconocible) no entra al
    mapa: el cálculo sigue con la regla general.
    """
    try:
        if not COLMENA_JSON_PATH.is_file():
            return {}
        with COLMENA_JSON_PATH.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if not isinstance(datos, dict):
            return {}

        por_cedula: dict[str, bool] = {}
        for colaboradores in datos.values():
            if not isinstance(colaboradores, (list, tuple)):
                continue
            for colaborador in colaboradores:
                if not isinstance(colaborador, dict):
                    continue
                cedula = normalizar_cedula(colaborador.get("cedula"))
                if not cedula:
                    continue
                valor = _a_booleano(colaborador.get(SABADO_HABIL_CAMPO))
                if valor is not None:
                    # La primera aparición manda; en el archivo no hay cédulas
                    # repetidas con valores distintos.
                    por_cedula.setdefault(cedula, valor)
        return por_cedula
    except Exception:  # noqa: BLE001
        logger.exception("Error leyendo SABADO HABIL de colmena.json")
        return {}


@lru_cache(maxsize=1)
def _sabados() -> dict[str, bool]:
    return cargar_sabados()


def sabado_habil(cedula: Any) -> bool | None:
    """¿El sábado es hábil para esta cédula? ``None`` si no está en el archivo."""
    return _sabados().get(normalizar_cedula(cedula))


def anotar_sabado_habil(
    filas: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Devuelve las filas con ``sabadoHabil`` cuando la cédula está en el archivo.

    La interfaz usa ese dato para previsualizar los días con la misma regla que
    el servidor. Las filas de empleados que no están en ``colmena.json`` quedan
    sin el campo y conservan el cálculo general (el sábado cuenta).
    """
    sabados = _sabados()
    if not sabados:
        return list(filas)

    salida: list[dict[str, Any]] = []
    for fila in filas:
        valor = sabados.get(normalizar_cedula(fila.get("identificacion")))
        salida.append({**fila, "sabadoHabil": valor} if valor is not None else fila)
    return salida


def cedulas_direccion(correo: Any) -> frozenset[str]:
    """Cédulas del propio correo en ``colmena.json`` más las de ``filial.json``.

    Cada archivo guarda un conjunto por correo. La dirección ve lo que está a
    nombre de **su** correo en los dos; no los conjuntos de los demás jefes.
    """
    clave = _correo(correo)
    return _jefes().get(clave, frozenset()) | _filial().get(clave, frozenset())


@lru_cache(maxsize=1)
def _jefes() -> dict[str, frozenset[str]]:
    return cargar_jefes()


@lru_cache(maxsize=1)
def _filial() -> dict[str, frozenset[str]]:
    return cargar_filial()


def correo_en_colmena(correo: Any) -> bool:
    """¿El correo figura en el archivo de jefes de Colmena?"""
    return _correo(correo) in _jefes()


def es_direccion_de_grupo(correo: Any) -> bool:
    """¿Es uno de los correos de dirección del grupo?"""
    return _correo(correo) in DIRECCION_GRUPO


def alcance_de(correo: Any) -> AlcanceColmena | None:
    """Alcance especial del correo, o ``None`` si no es de Colmena.

    Los correos de dirección se resuelven primero: su alcance es la unión de sus
    dos entradas (``colmena.json`` y ``filial.json``), no la de todos los jefes.
    """
    clave = _correo(correo)
    if clave in DIRECCION_GRUPO:
        return AlcanceColmena(tipo=TIPO_GRUPO, cedulas=cedulas_direccion(clave))
    jefes = _jefes()
    if clave in jefes:
        return AlcanceColmena(tipo=TIPO_EQUIPO, cedulas=jefes[clave])
    return None


def filtrar_filas(
    filas: Sequence[dict[str, Any]], alcance: AlcanceColmena | None
) -> list[dict[str, Any]]:
    """Acota el tablero al alcance de Colmena, sin mutar las filas.

    La llave es siempre la **cédula** (``identificacion``): la lista del correo
    para un jefe de equipo, o la unión de las entradas de ese mismo correo en
    ``colmena.json`` y ``filial.json`` para la dirección. No se filtra por
    empresa ni por UNES.
    """
    if alcance is None:
        return list(filas)

    return [
        fila
        for fila in filas
        if normalizar_cedula(fila.get("identificacion")) in alcance.cedulas
    ]

