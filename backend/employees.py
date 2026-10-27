"""Colaboradores de la empresa, leídos de la vista corporativa.

Fuente: ``BD_Integraciones.dbo.PBI_Colaborador_Vacaciones_V2``, en el servidor
corporativo (la conexión **sin** sufijo del ``.env``). Es una vista de solo
lectura mantenida por otro proceso: aquí no se escribe nada.

El filtro por empresa y por UNES
--------------------------------
La vista reúne la plantilla de las tres empresas del grupo. ``IDCia_CO`` viene
como ``'2-109'``, ``'3-…'`` o ``'4-301'``: el **primer dígito** identifica la
empresa y los **tres últimos** la UNES. El login guarda la empresa en
``Usuarios.company`` (2 = GyJ Ferreterías, 3 = Almasa, 4 = Colmena) y aquí se
traduce a ese primer dígito.

Los dos filtros se aplican en el ``WHERE`` de SQL y no en Python: traer toda la
vista para descartar la mayoría no escala, y además son reglas de acceso —un
usuario no debería recibir por la API la plantilla de otra empresa ni de otra
UNES—.

Talento Humano es la excepción a la UNES: entra sin digitarla y su tablero es la
plantilla completa **de su empresa** (:meth:`EmployeeDirectory.listar_todos`).
El permiso lo decide el servidor con la empresa y el cargo de la sesión, nunca
la petición.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from db import Database, DatabaseUnavailable
from security import ValidationError

logger = logging.getLogger(__name__)

VISTA = "dbo.PBI_Colaborador_Vacaciones_V2"

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
    fecha_ingreso,
    Cargo,
    dias_vacaciones_acumulado,
    dias_vacaciones_corteDic,
    email,
    emailCorporativo
FROM {VISTA}
"""

# `RTRIM(LTRIM(...))` porque `IDCia_CO` es VARCHAR y podría venir con espacios;
# sin eso, `RIGHT(x, 3)` devolvería espacios en lugar de dígitos. El `CAST`
# protege el caso de una columna numérica y no cambia el resultado para texto.
_IDCIA = "RTRIM(LTRIM(CAST(IDCia_CO AS VARCHAR(20))))"
_FILTRO_UNES = f"RIGHT({_IDCIA}, 3) = ?"
# Empresa = primer dígito de `IDCia_CO`: '4-301' → '4' (Colmena).
_FILTRO_EMPRESA = f"LEFT({_IDCIA}, 1) = ?"
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


def normalizar_empresa(valor: object) -> str:
    """Empresa (2, 3 o 4) como el dígito que se compara en la vista.

    Devuelve ``''`` cuando no hay empresa: quien llama decide si eso significa
    "sin filtro". En la API siempre llega una empresa, porque las cuentas
    anteriores a la columna `company` se asumen de GyJ.
    """
    texto = str(valor or "").strip()
    return texto if texto.isdigit() else ""


def empresa_de_unes(valor: object) -> str:
    """Primer dígito de un ``IDCia_CO`` ya almacenado (``'4-301'`` → ``'4'``).

    Se usa para filtrar las asignaciones guardadas cuando la vista corporativa
    no responde: el registro local conserva la UNES completa, así que la empresa
    sigue siendo deducible sin consultar el directorio.
    """
    coincidencia = re.match(r"^(\d)\s*-\s*\d{3}$", str(valor or "").strip())
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
    # Fecha de ingreso a la empresa. Alimenta la columna «FECHA DE INGRESO» de la
    # planilla en PDF; el tablero no la usa. Se llama distinto de ``fechaIngreso``
    # a propósito: en la asignación ese nombre es la fecha de regreso.
    fechaIngresoLaboral: str = ""

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
            "fechaIngresoLaboral": self.fechaIngresoLaboral,
        }


def _fecha(valor: object) -> str:
    """``date``/``datetime`` de la vista → ``aaaa-mm-dd``; el resto, tal cual."""
    if valor is None or valor == "":
        return ""
    if hasattr(valor, "strftime"):
        try:
            return valor.strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return str(valor)
    return str(valor)[:10]


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
        fechaIngresoLaboral=_fecha(fila["fecha_ingreso"]),
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

    def listar_por_unes(
        self, unes: str, *, empresa: object = 0, limite: int = 2000
    ) -> list[Colaborador]:
        """Colaboradores de una UNES (y de una empresa, si se indica)."""
        database = self._exigir_conexion()
        if not unes:
            raise ValidationError("UNES_INVALIDA", "La UNES no es válida.")

        condiciones = [_FILTRO_UNES]
        parametros: list[Any] = [unes]
        digito_empresa = normalizar_empresa(empresa)
        if digito_empresa:
            condiciones.append(_FILTRO_EMPRESA)
            parametros.append(digito_empresa)

        sql = f"{_SELECT} WHERE {' AND '.join(condiciones)} {_ORDER}"
        filas = database.query_named(sql, tuple(parametros), limit=limite)
        return [_fila_a_colaborador(fila) for fila in filas]

    def listar_todos(self, *, empresa: object = 0, limite: int = 5000) -> list[Colaborador]:
        """Toda la plantilla, sin filtrar por UNES, ordenada por nombre.

        Talento Humano entra sin digitar una UNES: su tablero es la plantilla
        completa **de su empresa**, no la de una unidad concreta. El límite es un
        techo de seguridad —la vista tiene del orden de mil filas— y no un filtro
        de negocio.
        """
        database = self._exigir_conexion()
        digito_empresa = normalizar_empresa(empresa)
        if digito_empresa:
            sql = f"{_SELECT} WHERE {_FILTRO_EMPRESA} {_ORDER}"
            filas = database.query_named(sql, (digito_empresa,), limit=limite)
        else:
            filas = database.query_named(f"{_SELECT} {_ORDER}", limit=limite)
        return [_fila_a_colaborador(fila) for fila in filas]

    def buscar(
        self, unes: str, identificacion: str, *, empresa: object = 0
    ) -> Colaborador | None:
        """Un colaborador concreto dentro de su UNES y su empresa."""
        database = self._exigir_conexion()
        if not unes or not identificacion:
            return None

        condiciones = [_FILTRO_UNES, "RTRIM(LTRIM(cedula)) = ?"]
        parametros: list[Any] = [unes, str(identificacion).strip()]
        digito_empresa = normalizar_empresa(empresa)
        if digito_empresa:
            condiciones.insert(1, _FILTRO_EMPRESA)
            parametros.insert(1, digito_empresa)

        sql = f"{_SELECT} WHERE {' AND '.join(condiciones)}"
        filas = database.query_named(sql, tuple(parametros), limit=1)
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
