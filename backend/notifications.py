"""Notificaciones: avisos de las acciones sobre las asignaciones.

Tabla ``dbo.notificaciones``: ``id``, ``unes``, ``msj_notificacion``,
``usuario_id``, ``fecha_registro``, ``fecha_update``. ``usuario_id`` relaciona
con ``dbo.Usuarios``.

Quién recibe qué
----------------
La regla del negocio es explícita:

* **Talento Humano y el admin** ven toda la bandeja general: todas las
  asignaciones, aprobaciones, rechazos y observaciones.
* **Los demás cargos** ven los avisos de **la UNES de su sesión**. Así quien
  entró con la UNES 115 ve que Talento Humano aprobó, rechazó o comentó una
  asignación de la 2-115, aunque la acción la haya hecho otra persona. El
  filtro va en el ``WHERE`` de SQL y no en el navegador.
* **``usuario_id`` guarda el id del usuario que hizo la acción** (quien asigna
  las fechas, aprueba, rechaza o comenta), como pide el negocio. Es el dato con
  el que cada quien puede contar sus avisos pendientes.
* La columna **``unes`` guarda la UNES de la asignación** (``2-115``), no la del
  autor: es la que decide quién más ve el aviso.

El filtro se aplica en el ``WHERE`` de SQL y no en el navegador: si se filtrara
en el cliente, cualquiera podría leer de más mirando la respuesta de la API.
"""

from __future__ import annotations

import logging
from typing import Any

from db import Database

logger = logging.getLogger(__name__)

TABLA = "dbo.notificaciones"

# Etiqueta con la que se marcan los avisos generales de una UNES. Es una
# constante, no un dato que llegue del cliente.
UNES_TALENTO_HUMANO = "TALENTO HUMANO"

MSJ_MAX = 4000
UNES_MAX = 50

_COLUMNAS = "id, unes, msj_notificacion, usuario_id, fecha_registro, fecha_update"

_SELECT = f"SELECT {_COLUMNAS} FROM {TABLA}"
_SELECT_TODAS = f"{_SELECT} ORDER BY fecha_registro DESC, id DESC"
_SELECT_UNA = f"{_SELECT} WHERE id = ?"
# La UNES de la asignación viene completa ('2-115'); la de la sesión, con tres
# dígitos. Se comparan los tres últimos, la misma convención del resto del API.
_SELECT_POR_UNES = (
    f"{_SELECT} WHERE RIGHT(RTRIM(LTRIM(unes)), 3) = ? "
    "ORDER BY fecha_registro DESC, id DESC"
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

    def listar_por_unes(self, unes: str) -> list[dict[str, Any]]:
        """Avisos cuya columna ``unes`` corresponde a la UNES de la sesión.

        Se comparan los tres últimos dígitos porque la asignación guarda la UNES
        completa (``2-115``) y la sesión sólo los tres dígitos (``115``). El
        filtro va en el ``WHERE``: la API no devuelve avisos de otras unidades.
        """
        sufijo = "".join(caracter for caracter in str(unes or "") if caracter.isdigit())[-3:]
        if len(sufijo) < 3:
            return []
        filas = self._database.query_named(_SELECT_POR_UNES, (sufijo,))
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

    def listar_para(self, usuario: Any, unes: str = "") -> list[dict[str, Any]]:
        """Qué avisos puede ver este usuario.

        * **Talento Humano y el admin** ven toda la bandeja general.
        * Cualquier otro cargo ve los avisos de **la UNES de su sesión**: así
          quien entró con la UNES 115 se entera de que Talento Humano aprobó,
          rechazó o comentó una asignación de esa unidad, aunque no haya sido
          quien hizo la acción.
        * Sin UNES en la sesión (por ejemplo, un jefe de Colmena) esta bandeja
          general queda vacía; sus propios avisos se consultan por
          ``usuario_id`` en `/api/notificaciones/mias`.

        El alcance se decide con el cargo y la UNES de la sesión, no con nada
        que mande el navegador.
        """
        if (
            getattr(usuario, "es_talento_humano", False)
            or getattr(usuario, "es_admin", False)
        ):
            return self._repository.listar()
        if not unes:
            return []
        return self._repository.listar_por_unes(unes)

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
