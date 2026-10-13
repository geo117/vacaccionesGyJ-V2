"""Colaboradores de la empresa, leídos de la vista corporativa.

Fuente: ``BD_Integraciones.dbo.PBI_Colaborador_Vacaciones``, en el servidor
corporativo (la conexión **sin** sufijo del ``.env``). Es una vista de solo
lectura mantenida por otro proceso: aquí no se escribe nada.

El filtro por UNES
------------------
``IDCia_CO`` viene como ``'2-109'`` y el login pide la UNES al usuario. Se
comparan los **tres últimos dígitos**, como pide el negocio. Se verificó contra
la vista real que ese sufijo es inequívoco: ningún sufijo apunta a dos
``DescCO`` distintos.

El filtro se aplica en el ``WHERE`` de SQL y no en Python: traer 1081 filas para
descartar la mayoría no escala, y además el filtro es una regla de acceso —un
usuario no debería recibir por la API la plantilla de otras UNES—.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from db import Database, DatabaseUnavailable
from security import ValidationError

logger = logging.getLogger(__name__)

VISTA = "dbo.PBI_Colaborador_Vacaciones"

# La UNES que se digita en el login. Se aceptan las formas "109" y "2-109"
# porque en la vista el identificador viene completo y el usuario puede escribir
# cualquiera de las dos.
UNES_RE = re.compile(r"^(?:\d{1,3}-)?(\d{3})$")

# Días de vacaciones que corresponden por ley en Colombia.
DIAS_VACACIONES_LEY = 15

_SELECT = f"""
SELECT
    IDCia_CO,
    DescCO,
    cedula,
    Empleado,
    Cargo,
    dias_vacaciones_acumulado,
    dias_vacaciones_corteDic,
    email,
    emailCorporativo
FROM {VISTA}
"""

# `RTRIM(LTRIM(...))` porque `IDCia_CO` es VARCHAR y podría venir con espacios;
# sin eso, `RIGHT(x, 3)` devolvería espacios en lugar de dígitos.
_FILTRO_UNES = "RIGHT(RTRIM(LTRIM(IDCia_CO)), 3) = ?"
_ORDER = "ORDER BY Empleado"


def normalizar_unes(valor: object) -> str:
    """Deja sólo los tres dígitos de la UNES.

    Acepta ``'109'`` y ``'2-109'``. Devuelve ``''`` si no se reconoce, para que
    quien llame decida: en el login es un error; en un listado, "sin filtro".
    """
    if valor is None:
        return ""
    coincidencia = UNES_RE.match(str(valor).strip())
    return coincidencia.group(1) if coincidencia else ""


def validar_unes_login(valor: object) -> str:
    """Valida la UNES que se digita al entrar."""
    if valor is None or str(valor).strip() == "":
        raise ValidationError("UNES_REQUERIDA", "Escribe la UNES con la que vas a trabajar.")
    unes = normalizar_unes(valor)
    if not unes:
        raise ValidationError(
            "UNES_INVALIDA",
            "La UNES debe ser un número de tres dígitos (por ejemplo, 109).",
        )
    return unes


def _texto(valor: object) -> str:
    """Normaliza texto de la vista: sin espacios sobrantes ni repetidos."""
    if valor is None:
        return ""
    return " ".join(str(valor).split())


def _texto_exacto(valor: object) -> str:
    """Como ``_texto`` pero conserva los espacios internos tal cual.

    Se usa para el correo: colapsar espacios internos de un correo sería un
    cambio silencioso del dato.
    """
    return "" if valor is None else str(valor).strip()


def _decimal(valor: object) -> float:
    """``float`` redondeado a un decimal.

    La vista devuelve ``float`` (7.2, 14.2). Se redondea a un decimal porque es
    como se muestra y como se compara en el semáforo.
    """
    if valor is None:
        return 0.0
    try:
        return round(float(valor), 1)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class Colaborador:
    """Una fila de la vista, con los nombres que usa la interfaz."""

    unes: str
    descUnes: str
    identificacion: str
    empleado: str
    cargo: str
    diasAcumulados: float
    diasACorte: float
    correo: str
    correoCorporativo: str

    @property
    def correoParaUsar(self) -> str:
        """El corporativo manda; si no hay, el personal.

        En la vista el corporativo viene vacío en buena parte de las filas, así
        que no se puede depender sólo de él.
        """
        return self.correoCorporativo or self.correo

    def to_dict(self) -> dict[str, Any]:
        return {
            "unes": self.unes,
            "descUnes": self.descUnes,
            "identificacion": self.identificacion,
            "empleado": self.empleado,
            "cargo": self.cargo,
            "diasAcumulados": self.diasAcumulados,
            "diasACorte": self.diasACorte,
            "correo": self.correo,
            "correoCorporativo": self.correoCorporativo,
            "correoParaUsar": self.correoParaUsar,
        }


def _fila_a_colaborador(fila: Any) -> Colaborador:
    return Colaborador(
        unes=_texto(fila["IDCia_CO"]),
        descUnes=_texto(fila["DescCO"]),
        identificacion=_texto(fila["cedula"]),
        empleado=_texto(fila["Empleado"]),
        cargo=_texto(fila["Cargo"]),
        diasAcumulados=_decimal(fila["dias_vacaciones_acumulado"]),
        diasACorte=_decimal(fila["dias_vacaciones_corteDic"]),
        correo=_texto_exacto(fila["email"]),
        correoCorporativo=_texto_exacto(fila["emailCorporativo"]),
    )


class EmployeeDirectory:
    """Consultas de solo lectura sobre la vista corporativa."""

    def __init__(self, database: Database | None) -> None:
        self._database = database

    @property
    def disponible(self) -> bool:
        return self._database is not None

    def _exigir_conexion(self) -> Database:
        if self._database is None:
            raise DatabaseUnavailable(
                "La conexión con el directorio de colaboradores no está configurada."
            )
        return self._database

    def listar_por_unes(self, unes: str, *, limite: int = 2000) -> list[Colaborador]:
        """Colaboradores de una UNES, ordenados por nombre."""
        database = self._exigir_conexion()
        if not unes:
            raise ValidationError("UNES_INVALIDA", "La UNES no es válida.")

        sql = f"{_SELECT} WHERE {_FILTRO_UNES} {_ORDER}"
        filas = database.query_named(sql, (unes,), limit=limite)
        return [_fila_a_colaborador(fila) for fila in filas]

    def buscar(self, unes: str, identificacion: str) -> Colaborador | None:
        """Un colaborador concreto dentro de su UNES."""
        database = self._exigir_conexion()
        if not unes or not identificacion:
            return None
        sql = f"{_SELECT} WHERE {_FILTRO_UNES} AND RTRIM(LTRIM(cedula)) = ?"
        filas = database.query_named(sql, (unes, str(identificacion).strip()), limit=1)
        return _fila_a_colaborador(filas[0]) if filas else None

    def unes_disponibles(self) -> list[dict[str, str]]:
        """UNES distintas, para diagnóstico. No se expone por HTTP."""
        database = self._exigir_conexion()
        sql = f"SELECT DISTINCT IDCia_CO, DescCO FROM {VISTA} ORDER BY IDCia_CO"
        filas = database.query_named(sql, limit=200)
        return [
            {"id": _texto(f["IDCia_CO"]), "descripcion": _texto(f["DescCO"])} for f in filas
        ]

    def health(self) -> tuple[bool, str]:
        """Comprueba que la vista responda.

        No basta con un ``SELECT 1``: se lee una columna real, porque un nombre
        de vista equivocado también responde si se consulta sin ``FROM``.
        """
        if self._database is None:
            return False, "sin configurar"
        try:
            fila = self._database.query_named(f"SELECT TOP 1 cedula FROM {VISTA}", limit=1)
            return True, "ok" if fila else "vista vacía"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "La vista de colaboradores no respondió: %s", exc.__class__.__name__
            )
            return False, "sin respuesta"
