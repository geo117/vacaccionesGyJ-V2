"""Notificaciones: avisos de las acciones sobre las asignaciones.

Tabla ``dbo.notificaciones``: ``id``, ``unes``, ``msj_notificacion``,
``usuario_id``, ``fecha_registro``, ``fecha_update``. ``usuario_id`` relaciona
con ``dbo.Usuarios``.

Quién recibe qué
----------------
La regla del negocio es explícita:

* **Cada usuario** ve únicamente los avisos que él mismo registró, es decir,
  los que tienen su ``id`` en ``usuario_id``. Ya no se filtra por UNES: un jefe
  de UNES no debe enterarse de las acciones de otros usuarios.
* **Talento Humano** ve todos los avisos de **su compañía** (``Usuarios.company``
  del autor): quien es de la compañía 2 ve la 2 y quien es de la compañía 4 ve
  la 4.
* **El admin** ve los avisos de las compañías **2 y 4**, sin importar la
  compañía de su propia cuenta.

La compañía del aviso se deduce del **autor** (``notificaciones.usuario_id`` →
``dbo.Usuarios.company``), no de la UNES guardada en el aviso. La columna
``unes`` queda como dato informativo de la asignación.

El filtro se aplica en el ``WHERE`` de SQL y no en el navegador: si se filtrara
en el cliente, cualquiera podría leer de más mirando la respuesta de la API.
"""

from __future__ import annotations

import logging
from typing import Any

from db import Database
from users import USERS_TABLE

logger = logging.getLogger(__name__)

TABLA = "dbo.notificaciones"

# Compañías cuyos avisos ve el administrador. El negocio lo limita a GyJ (2) y
# Colmena (4); no incluye Almasa (3).
COMPANIAS_ADMIN = (2, 4)

# Etiqueta con la que se marcan los avisos generales de una UNES. Es una
# constante, no un dato que llegue del cliente.
UNES_TALENTO_HUMANO = "TALENTO HUMANO"

MSJ_MAX = 4000
UNES_MAX = 50

_COLUMNAS = "id, unes, msj_notificacion, usuario_id, fecha_registro, fecha_update"

_SELECT = f"SELECT {_COLUMNAS} FROM {TABLA}"
_SELECT_TODAS = f"{_SELECT} ORDER BY fecha_registro DESC, id DESC"
_SELECT_UNA = f"{_SELECT} WHERE id = ?"
# La compañía sale del autor del aviso. Se aliasan las columnas del SELECT
# porque ahora la consulta une dos tablas y `fila_a_dict` lee por nombre.
_SELECT_POR_COMPANIA = (
    "SELECT n.id AS id, n.unes AS unes, n.msj_notificacion AS msj_notificacion, "
    "n.usuario_id AS usuario_id, n.fecha_registro AS fecha_registro, "
    "n.fecha_update AS fecha_update "
    f"FROM {TABLA} AS n "
    f"INNER JOIN {USERS_TABLE} AS u ON u.id = n.usuario_id "
)


def _select_por_companias(cantidad: int) -> str:
    """Consulta de avisos de una o varias compañías, con sus parámetros.

    Los marcadores se generan a partir de la cantidad de compañías; los valores
    viajan como parámetros y nunca se interpolan en el SQL.
    """
    marcadores = ", ".join("?" for _ in range(cantidad))
    return (
        f"{_SELECT_POR_COMPANIA} WHERE u.company IN ({marcadores}) "
        "ORDER BY n.fecha_registro DESC, n.id DESC"
    )


_INSERT = (
    f"INSERT INTO {TABLA} (unes, msj_notificacion, usuario_id, fecha_registro, fecha_update) "
    "OUTPUT INSERTED.id VALUES (?, ?, ?, GETDATE(), GETDATE())"
)
_DELETE = f"DELETE FROM {TABLA} WHERE id = ?"


def _a_iso(valor: Any) -> str | None:
    return valor.isoformat() if hasattr(valor, "isoformat") else (None if valor is None else str(valor))


def fila_a_dict(fila: Any) -> dict[str, Any]:
    return {
        "id": int(fila["id"]),
        "unes": str(fila["unes"] or ""),
        "mensaje": str(fila["msj_notificacion"] or ""),
        "usuarioId": fila["usuario_id"],
        "fechaRegistro": _a_iso(fila["fecha_registro"]),
        "fechaUpdate": _a_iso(fila["fecha_update"]),
    }


def _recortar(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[: maximo - 1] + "…"


def _fecha_reintegro(asignacion: dict[str, Any]) -> str:
    """Fecha de regreso a labores del aviso.

    Sale de ``asignacion_vacaciones.fecha_reintegro_lab`` (``fechaReintegroLab``),
    la fecha que se elige a mano para el reintegro, y **no** de
    ``fecha_regreso`` (``fechaIngreso``), que es la que se deriva de los períodos.
    """
    return str(asignacion.get("fechaReintegroLab") or "por definir")


class NotificationRepository:
    """Único punto que lee y escribe ``dbo.notificaciones``."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def listar(self) -> list[dict[str, Any]]:
        return [fila_a_dict(f) for f in self._database.query_named(_SELECT_TODAS)]

    def listar_por_usuario(self, usuario_id: int) -> list[dict[str, Any]]:
        """Avisos generados por una persona concreta (``usuario_id``)."""
        filas = self._database.query_named(
            f"{_SELECT} WHERE usuario_id = ? ORDER BY fecha_registro DESC, id DESC",
            (usuario_id,),
        )
        return [fila_a_dict(f) for f in filas]

    def listar_por_companias(self, companias: tuple[int, ...]) -> list[dict[str, Any]]:
        """Avisos cuyo autor pertenece a alguna de las compañías indicadas.

        La compañía se toma de ``dbo.Usuarios.company`` a través de
        ``usuario_id``. Si no se indica ninguna compañía, no se devuelve nada:
        el alcance nunca debe quedar abierto por un valor vacío.
        """
        valores = tuple(int(compania) for compania in companias)
        if not valores:
            return []
        filas = self._database.query_named(
            _select_por_companias(len(valores)), valores
        )
        return [fila_a_dict(f) for f in filas]

    def contar(self) -> int:
        fila = self._database.query_one(f"SELECT COUNT(*) FROM {TABLA}")
        return int(fila[0]) if fila else 0

    def crear(self, *, unes: str, mensaje: str, usuario_id: int | None) -> int:
        with self._database.cursor(commit=True) as cursor:
            cursor.execute(
                _INSERT,
                (unes[:UNES_MAX], _recortar(mensaje, MSJ_MAX), usuario_id),
            )
            fila = cursor.fetchone()
        return int(fila[0]) if fila else 0

    def eliminar(self, notification_id: int) -> int:
        return self._database.execute(_DELETE, (notification_id,))


class NotificationService:
    """Redacta y enruta los avisos.

    Redactar es responsabilidad del servidor y no del navegador: si el cliente
    mandara el texto, cualquiera podría escribir el aviso que quisiera en la
    bandeja de los demás.
    """

    def __init__(self, database: Database) -> None:
        self._repository = NotificationRepository(database)

    @property
    def repository(self) -> NotificationRepository:
        return self._repository

    # -- lectura ------------------------------------------------------------

    def listar_para(self, usuario: Any) -> list[dict[str, Any]]:
        """Qué avisos puede ver este usuario.

        * **El admin** ve los avisos de las compañías 2 y 4.
        * **Talento Humano** ve los avisos de su propia compañía
          (``Usuarios.company``).
        * **Cualquier otro cargo** ve únicamente los avisos que él mismo
          registró (``usuario_id``). Ya no ve los de su UNES: las acciones de
          otros usuarios no le pertenecen.

        El alcance se decide con el rol y la compañía de la sesión, no con nada
        que mande el navegador.
        """
        if getattr(usuario, "es_admin", False):
            return self._repository.listar_por_companias(COMPANIAS_ADMIN)
        if getattr(usuario, "es_talento_humano", False):
            return self._repository.listar_por_companias((usuario.company,))
        return self._repository.listar_por_usuario(int(usuario.id))

    def listar_para_usuario(self, usuario_id: int) -> list[dict[str, Any]]:
        """Avisos generados por una persona concreta (``usuario_id``)."""
        return self._repository.listar_por_usuario(usuario_id)

    # -- escritura ----------------------------------------------------------

    def avisar_asignacion(self, asignacion: dict[str, Any], autor: Any) -> None:
        """Avisa que se programaron (o cambiaron) las fechas de alguien.

        ``usuario_id`` guarda el id de **quien hizo la asignación**, como pide el
        negocio: es lo que permite contar sus avisos pendientes.
        """
        mensaje = (
            f"{autor.nombre} asignó las fechas de vacaciones de "
            f"{asignacion['empleado']} ({asignacion['totalDias']} días, "
            f"regreso el {_fecha_reintegro(asignacion)})."
        )
        self._registrar(
            mensaje,
            unes=str(asignacion.get("unes") or UNES_TALENTO_HUMANO),
            usuario_id=int(autor.id),
        )

    def avisar_decision(self, asignacion: dict[str, Any], autor: Any) -> None:
        """Avisa la aprobación o el rechazo, y deja constancia de quién lo hizo.

        ``en_verificacion`` significa que sólo algunos períodos quedaron
        rechazados. El aviso lo dice así en lugar de afirmar que se rechazó toda
        la asignación, que sería falso. Si la decisión trae observaciones, se
        incluyen en el mismo aviso.
        """
        if asignacion["estado"] == "aprobada":
            mensaje = (
                f"{autor.nombre} aprobó las vacaciones de {asignacion['empleado']} "
                f"({asignacion['totalDias']} días, regreso el "
                f"{_fecha_reintegro(asignacion)})."
            )
        elif asignacion["estado"] == "en_verificacion":
            motivo = (asignacion.get("motivoRechazo") or "").strip()
            mensaje = (
                f"{autor.nombre} registró el rechazo de uno o más períodos de "
                f"las vacaciones de {asignacion['empleado']}. Motivo: {_recortar(motivo, 500)}"
            )
        else:
            motivo = (asignacion.get("motivoRechazo") or "").strip()
            mensaje = (
                f"{autor.nombre} rechazó las vacaciones de {asignacion['empleado']}. "
                f"Motivo: {_recortar(motivo, 500)}"
            )

        observaciones = str(asignacion.get("observaciones") or "").strip()
        if observaciones:
            mensaje += f" Observación: {_recortar(observaciones, 500)}"

        self._registrar(
            mensaje,
            unes=str(asignacion.get("unes") or UNES_TALENTO_HUMANO),
            usuario_id=int(autor.id),
        )

    def avisar_decision_periodo(
        self,
        asignacion: dict[str, Any],
        autor: Any,
        numero_periodo: int,
        decision: str,
    ) -> None:
        """Avisa una aprobación o un rechazo de **un período**.

        Se redacta con la acción concreta y no con el estado final: aprobar uno
        de dos períodos puede dejar la asignación en ``pendiente``, y decir
        "rechazó" en ese caso sería falso.
        """
        accion = "aprobó" if decision == "aprobada" else "rechazó"
        mensaje = (
            f"{autor.nombre} {accion} el período {numero_periodo} de las vacaciones "
            f"de {asignacion['empleado']}."
        )
        if accion == "rechazó":
            motivo = str(asignacion.get("motivoRechazo") or "").strip()
            if motivo:
                mensaje += f" Motivo: {_recortar(motivo, 500)}"

        self._registrar(
            mensaje,
            unes=str(asignacion.get("unes") or UNES_TALENTO_HUMANO),
            usuario_id=int(autor.id),
        )

    def avisar_observacion(
        self, asignacion: dict[str, Any], autor: Any, observacion: str
    ) -> None:
        """Avisa que se agregó o cambió una descripción u observación.

        Va en un aviso propio para que la bandeja muestre el texto que se añadió,
        no sólo que "se modificó" la asignación.
        """
        detalle = _recortar(str(observacion or "").strip(), 600)
        mensaje = (
            f"{autor.nombre} agregó una observación a las vacaciones de "
            f"{asignacion['empleado']}."
        )
        if detalle:
            mensaje += f" Observación: {detalle}"

        self._registrar(
            mensaje,
            unes=str(asignacion.get("unes") or UNES_TALENTO_HUMANO),
            usuario_id=int(autor.id),
        )

    def _registrar(self, mensaje: str, *, unes: str, usuario_id: int | None) -> None:
        """Guarda el aviso.

        Un fallo al avisar **no** debe tumbar la acción que ya se guardó: la
        asignación ya quedó registrada y perderla por un aviso fallido sería
        peor. Se deja constancia en el log.
        """
        try:
            self._repository.crear(
                unes=unes or UNES_TALENTO_HUMANO,
                mensaje=mensaje,
                usuario_id=usuario_id,
            )
        except Exception:  # noqa: BLE001
            logger.error("No se pudo registrar una notificación.")
