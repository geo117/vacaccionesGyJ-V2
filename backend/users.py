"""Usuarios: modelo, repositorio y reglas del cargo.

Separado de :mod:`auth` a propósito. `auth` responde "¿esta persona es quien
dice ser?"; este módulo responde "¿qué es y qué puede hacer?". Mezclarlos hacía
que un cambio en la administración de usuarios tocara la ruta del login.

El **cargo vive en la base** (`Usuarios.cargo`), nunca en el cliente. Ningún
endpoint acepta un cargo enviado por el navegador para decidir permisos: lo lee
de la fila del usuario autenticado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from db import Database
from security import ValidationError, normalize_email, validate_password

logger = logging.getLogger(__name__)

USERS_TABLE = "dbo.Usuarios"

# Cargos con privilegios. Se comparan normalizados (minúsculas y sin espacios
# sobrantes) porque en la base están capturados a mano.
#
#   talento humano → aprueba/rechaza asignaciones y ve toda la plantilla.
#   admin          → administra las cuentas y además puede hacer lo mismo que
#                    Talento Humano sobre las asignaciones.
#
# Administración de usuarios es exclusiva de «admin»; el admin hereda las
# capacidades operativas de Talento Humano.
CARGO_TALENTO_HUMANO = "talento humano"
CARGO_ADMIN = "admin"

# Empresa a la que pertenece la cuenta. Vive en `Usuarios.company` y decide qué
# plantilla de colaboradores se le muestra: la vista corporativa identifica la
# empresa con el **primer dígito** de `IDCia_CO` (`'2-109'`, `'3-…'`, `'4-301'`).
# El número es el que se guarda; el texto es sólo para mostrar.
EMPRESAS = {
    2: "GyJ Ferreterías",
    3: "Almasa",
    4: "Colmena",
}

# Cuentas anteriores a la columna `company` no traen empresa. La aplicación nació
# para GyJ (la vista original sólo tenía UNES `2-…`), así que se asumen de GyJ en
# lugar de dejarlas sin filtro y exponerles la plantilla de las otras empresas.
EMPRESA_POR_DEFECTO = 2

# `activo` es VARCHAR(10) y en la base está capturado con texto ("si"/"no"), no
# como BIT. Se acepta un conjunto amplio de valores afirmativos para no depender
# de cómo lo escriba quien lo edite a mano, y **se falla del lado seguro**: todo
# lo que no se reconozca como afirmativo deja la cuenta inactiva.
VALORES_ACTIVO = {"si", "sí", "s", "1", "true", "verdadero", "yes", "y", "activo"}
VALORES_INACTIVO = {"no", "n", "0", "false", "falso", "inactivo", ""}

# Lo que se escribe en la columna al activar o desactivar.
ACTIVO_SI = "si"
ACTIVO_NO = "no"

# Anchos reales de las columnas: se validan antes de escribir para no confiar en
# que SQL Server vaya a truncar en silencio.
NOMBRE_MAX = 100
CORREO_MAX = 150
CARGO_MAX = 60

_SELECT_COLUMNS = "id, nombre, correo, cargo, activo, fecha_creacion, company"

_SELECT_BY_EMAIL = (
    f"SELECT {_SELECT_COLUMNS}, password_hash FROM {USERS_TABLE} WHERE LOWER(correo) = ?"
)
_SELECT_BY_ID = f"SELECT {_SELECT_COLUMNS} FROM {USERS_TABLE} WHERE id = ?"
_SELECT_BY_CORREO = f"SELECT {_SELECT_COLUMNS} FROM {USERS_TABLE} WHERE LOWER(correo) = ?"
_SELECT_ALL = f"SELECT {_SELECT_COLUMNS} FROM {USERS_TABLE} ORDER BY nombre"
_INSERT = (
    f"INSERT INTO {USERS_TABLE} (nombre, correo, password_hash, cargo, activo, company, fecha_creacion) "
    "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, GETDATE())"
)
_UPDATE = f"UPDATE {USERS_TABLE} SET nombre = ?, correo = ?, cargo = ?, company = ? WHERE id = ?"
_UPDATE_ACTIVO = f"UPDATE {USERS_TABLE} SET activo = ? WHERE id = ?"
_UPDATE_PASSWORD = f"UPDATE {USERS_TABLE} SET password_hash = ? WHERE id = ?"
_DELETE = f"DELETE FROM {USERS_TABLE} WHERE id = ?"
_COUNT_BY_EMAIL = f"SELECT COUNT(*) FROM {USERS_TABLE} WHERE LOWER(correo) = ? AND id <> ?"
_COUNT_ALL = f"SELECT COUNT(*) FROM {USERS_TABLE}"


def normalizar_cargo(valor: object) -> str:
    """Deja el cargo comparable: minúsculas y sin espacios sobrantes."""
    return " ".join(str(valor or "").split()).lower()


def es_activo(valor: object) -> bool:
    """`activo` → booleano, con criterio conservador.

    La columna es VARCHAR(10) y en la base convive con 'si', 'no' y valores
    escritos a mano. Se acepta un conjunto amplio de formas afirmativas y
    **cualquier cosa no reconocida cuenta como inactiva**: ante la duda, no se
    deja entrar a nadie. Un `NULL` (columna agregada después, filas viejas sin
    llenar) también es inactivo, que es la lectura segura.
    """
    if valor is None or isinstance(valor, bool):
        return bool(valor)
    return str(valor).strip().lower() in VALORES_ACTIVO


def company_desde_bd(valor: object) -> int:
    """Empresa leída de la fila → entero.

    Una fila anterior a la columna `company` (o con el valor vacío) se asume de
    GyJ: la aplicación nació para esa empresa y dejarla sin empresa equivaldría a
    mostrarle la plantilla de todas. Un valor desconocido se conserva tal cual
    para que el filtro siga acotando por el primer dígito de `IDCia_CO`.
    """
    if valor is None:
        return EMPRESA_POR_DEFECTO
    texto = str(valor).strip()
    if not texto:
        return EMPRESA_POR_DEFECTO
    try:
        numero = int(texto)
    except (TypeError, ValueError):
        return EMPRESA_POR_DEFECTO
    return numero if numero > 0 else EMPRESA_POR_DEFECTO


def etiqueta_empresa(valor: object) -> str:
    """Nombre visible de la empresa; nunca deja el desplegable en blanco."""
    numero = company_desde_bd(valor)
    return EMPRESAS.get(numero, f"Empresa {numero}")


def validar_company(valor: object) -> int:
    """Empresa enviada por el navegador.

    Se acepta un entero o el texto que envía un formulario, pero sólo los valores
    del catálogo: es una regla de acceso, no un dato libre. Si se permitiera un
    número arbitrario, el filtro por `IDCia_CO` quedaría a merced del cliente.
    """
    if valor is None or str(valor).strip() == "":
        raise ValidationError("COMPANY_REQUERIDA", "Selecciona la empresa del usuario.")
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "COMPANY_INVALIDA", "La empresa seleccionada no es válida."
        ) from exc
    if numero not in EMPRESAS:
        raise ValidationError("COMPANY_INVALIDA", "La empresa seleccionada no es válida.")
    return numero


@dataclass(frozen=True)
class User:
    """Identidad de la sesión. ``password_hash`` no forma parte de este objeto."""

    id: int
    nombre: str
    correo: str
    cargo: str
    activo: bool = False
    company: int = EMPRESA_POR_DEFECTO

    @property
    def empresa(self) -> str:
        return etiqueta_empresa(self.company)

    @property
    def es_talento_humano(self) -> bool:
        return normalizar_cargo(self.cargo) == CARGO_TALENTO_HUMANO

    @property
    def es_admin(self) -> bool:
        """Administra las cuentas (crear, editar, activar y eliminar)."""
        return normalizar_cargo(self.cargo) == CARGO_ADMIN

    @property
    def ve_toda_la_plantilla(self) -> bool:
        """Quién ve la plantilla completa de su empresa, no sólo una UNES.

        Es una regla de alcance distinta de «puede aprobar»: el admin necesita
        ver todos los colaboradores para gestionar las cuentas, pero no decide
        sobre las asignaciones.
        """
        return self.es_talento_humano or self.es_admin

    @property
    def puede_aprobar(self) -> bool:
        """Quién puede aprobar o rechazar una asignación.

        El admin hereda las capacidades operativas de Talento Humano: además de
        administrar las cuentas, puede decidir sobre las asignaciones y usar las
        descargas reservadas a ese rol.
        """
        return (self.es_talento_humano or self.es_admin) and self.activo

    def to_public_dict(self) -> dict[str, Any]:
        """Lo único que puede viajar al navegador."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "correo": self.correo,
            "cargo": self.cargo or "",
            "activo": self.activo,
            "company": self.company,
            "empresa": self.empresa,
            "esTalentoHumano": self.es_talento_humano,
            "esAdmin": self.es_admin,
            "veTodaLaPlantilla": self.ve_toda_la_plantilla,
            "puedeAprobar": self.puede_aprobar,
        }


def _fila_a_usuario(row: tuple[Any, ...]) -> User:
    """Mapea ``_SELECT_COLUMNS`` a ``User``.

    El orden es ``id, nombre, correo, cargo, activo, fecha_creacion, company``.
    """
    return User(
        id=int(row[0]),
        nombre=str(row[1] or ""),
        correo=str(row[2] or ""),
        cargo=str(row[3] or ""),
        activo=es_activo(row[4]),
        company=company_desde_bd(row[6]),
    )


def validar_nombre(valor: object, *, campo: str = "nombre") -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValidationError("NOMBRE_REQUERIDO", "Escribe el nombre completo.")
    nombre = " ".join(valor.split())
    if len(nombre) > NOMBRE_MAX:
        raise ValidationError(
            "NOMBRE_LARGO", f"El nombre no puede superar {NOMBRE_MAX} caracteres."
        )
    return nombre


def validar_cargo(valor: object) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValidationError("CARGO_REQUERIDO", "Escribe el cargo.")
    cargo = " ".join(valor.split())
    if len(cargo) > CARGO_MAX:
        raise ValidationError("CARGO_LARGO", f"El cargo no puede superar {CARGO_MAX} caracteres.")
    return cargo


class UserRepository:
    """Único punto que consulta y modifica ``dbo.Usuarios``."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # -- lectura -------------------------------------------------------------

    def find_by_email(self, email: str) -> tuple[User, str] | None:
        """``(usuario, password_almacenado)`` o ``None``.

        La contraseña se devuelve aparte del objeto ``User`` para que no pueda
        viajar por accidente dentro de una respuesta.

        Ojo con el índice: ``_SELECT_BY_EMAIL`` es
        ``id, nombre, correo, cargo, activo, fecha_creacion, company,
        password_hash``, así que el hash va en la **posición 7**. Leerlo de otra
        posición no falla: compara contra un valor que no es un hash y todo
        inicio de sesión devuelve "credenciales incorrectas".
        """
        row = self._database.query_one(_SELECT_BY_EMAIL, (email,))
        if row is None:
            return None
        return _fila_a_usuario(row), str(row[7] or "")

    def find_by_id(self, user_id: int) -> User | None:
        row = self._database.query_one(_SELECT_BY_ID, (user_id,))
        return None if row is None else _fila_a_usuario(row)

    def find_by_correo(self, correo: str) -> User | None:
        """Usuario por correo, sin la contraseña.

        Se usa para relacionar una asignación con su dueño: el correo es el dato
        que comparten la vista de colaboradores y ``dbo.Usuarios``.
        """
        if not correo:
            return None
        fila = self._database.query_one(_SELECT_BY_CORREO, (str(correo).strip().lower(),))
        return None if fila is None else _fila_a_usuario(fila)

    def listar(self) -> list[dict[str, Any]]:
        """Todos los usuarios. Nunca incluye ``password_hash``."""
        filas = self._database.query_all(_SELECT_ALL)
        return [
            {
                "id": int(row[0]),
                "nombre": str(row[1] or ""),
                "correo": str(row[2] or ""),
                "cargo": str(row[3] or ""),
                "activo": es_activo(row[4]),
                "fechaCreacion": row[5].isoformat() if row[5] else None,
                "company": company_desde_bd(row[6]),
                "empresa": etiqueta_empresa(row[6]),
                "esTalentoHumano": normalizar_cargo(row[3]) == CARGO_TALENTO_HUMANO,
                "esAdmin": normalizar_cargo(row[3]) == CARGO_ADMIN,
            }
            for row in filas
        ]

    def contar(self) -> int:
        row = self._database.query_one(_COUNT_ALL)
        return int(row[0]) if row else 0

    def contar_talento_humano_activo(self, *, excluir_id: int = 0) -> int:
        """Cuántos usuarios de Talento Humano **activos** quedan.

        Se cuenta sobre las filas leídas en lugar de con un `COUNT` en SQL
        porque la interpretación de ``activo`` (varchar con texto libre) vive en
        Python, y duplicar esa regla en una consulta sería tener dos verdades.
        """
        return sum(
            1
            for usuario in self.listar()
            if usuario["esTalentoHumano"] and usuario["activo"] and usuario["id"] != excluir_id
        )

    def contar_admin_activo(self, *, excluir_id: int = 0) -> int:
        """Cuántos administradores **activos** quedan.

        Igual que con Talento Humano, se cuenta en Python para no duplicar la
        interpretación de ``activo``. Evita que el último admin se degrade a sí
        mismo y deje el sistema sin quien administre las cuentas.
        """
        return sum(
            1
            for usuario in self.listar()
            if usuario["esAdmin"] and usuario["activo"] and usuario["id"] != excluir_id
        )

    def correo_en_uso(self, email: str, *, excluir_id: int = 0) -> bool:
        row = self._database.query_one(_COUNT_BY_EMAIL, (email, excluir_id))
        return bool(row and int(row[0]) > 0)

    # -- escritura -----------------------------------------------------------

    def crear(
        self,
        *,
        nombre: str,
        correo: str,
        password_hash: str,
        cargo: str,
        company: int,
        activo: bool = True,
    ) -> int:
        with self._database.cursor(commit=True) as cursor:
            cursor.execute(
                _INSERT,
                (
                    nombre,
                    correo,
                    password_hash,
                    cargo,
                    ACTIVO_SI if activo else ACTIVO_NO,
                    company,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("La inserción no devolvió el identificador del usuario.")
        return int(row[0])

    def actualizar(
        self, user_id: int, *, nombre: str, correo: str, cargo: str, company: int
    ) -> int:
        return self._database.execute(_UPDATE, (nombre, correo, cargo, company, user_id))

    def actualizar_activo(self, user_id: int, activo: bool) -> int:
        return self._database.execute(
            _UPDATE_ACTIVO, (ACTIVO_SI if activo else ACTIVO_NO, user_id)
        )

    def desactivar_sin_privilegios(self) -> int:
        """Corte de vacaciones colectivas: desactiva a todos menos admin y TH.

        Se aplica cuando ya pasó la fecha límite. Deja intactos los cargos que
        administran el sistema y pone ``activo = 'no'`` al resto. Devuelve
        cuántas filas tocó.
        """
        return self._database.execute(
            "UPDATE dbo.Usuarios SET activo = ? "
            "WHERE LOWER(LTRIM(RTRIM(ISNULL(cargo, '')))) NOT IN (?, ?)",
            (ACTIVO_NO, CARGO_ADMIN, CARGO_TALENTO_HUMANO),
        )

    def actualizar_password_hash(self, user_id: int, password_hash: str) -> int:
        return self._database.execute(_UPDATE_PASSWORD, (password_hash, user_id))

    def eliminar(self, user_id: int) -> int:
        return self._database.execute(_DELETE, (user_id,))


def validar_usuario_nuevo(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida el alta de un usuario y devuelve los valores ya normalizados."""
    return {
        "nombre": validar_nombre(payload.get("nombre")),
        "correo": normalize_email(payload.get("correo")),
        "cargo": validar_cargo(payload.get("cargo")),
        "company": validar_company(payload.get("company")),
        "password": validate_password(payload.get("password")),
        # Si no se dice nada, el usuario nace activo: es lo que se espera al
        # crearlo, y dejarlo inactivo por omisión sería una sorpresa.
        "activo": a_booleano(payload.get("activo"), por_defecto=True),
    }


def a_booleano(valor: Any, *, por_defecto: bool) -> bool:
    """Interpreta un booleano que llega del cliente.

    Acepta el booleano real y las formas en texto que envía un formulario.
    Cualquier otra cosa usa el valor por defecto en lugar de adivinar.
    """
    if valor is None:
        return por_defecto
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in VALORES_ACTIVO:
        return True
    if texto in {"no", "n", "0", "false", "falso", "inactivo"}:
        return False
    return por_defecto
