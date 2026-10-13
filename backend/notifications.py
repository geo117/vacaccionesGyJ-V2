"""Notificaciones: avisos de las acciones sobre las asignaciones.

Tabla ``dbo.notificaciones``: ``id``, ``unes``, ``msj_notificacion``,
``usuario_id``, ``fecha_registro``, ``fecha_update``. ``usuario_id`` relaciona
con ``dbo.Usuarios``.

Quién recibe qué
----------------
La regla del negocio es explícita:

* **Los avisos de asignación de fechas, aprobación y rechazo los ve únicamente
  Talento Humano.** Son las tres acciones que existen hoy, así que en la
  práctica Talento Humano ve todo y los demás cargos no ven ninguno.
* **Al modificar, Talento Humano notifica al usuario dueño de esas fechas.**
  Ese aviso va dirigido a esa persona concreta; ``usuario_id` lo identifica.

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


class NotificationRepository:
    """Único punto que lee y escribe ``dbo.notificaciones``."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def listar(self) -> list[dict[str, Any]]:
        return [fila_a_dict(f) for f in self._database.query_named(_SELECT_TODAS)]

    def listar_por_usuario(self, usuario_id: int) -> list[dict[str, Any]]:
        """Avisos dirigidos a una persona concreta."""
        filas = self._database.query_named(
            f"{_SELECT} WHERE usuario_id = ? ORDER BY fecha_registro DESC, id DESC",
            (usuario_id,),
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

        Los avisos de asignación, aprobación y rechazo son **sólo para Talento
        Humano**. Para el resto de cargos devuelve la lista vacía: no hay hoy
        ningún tipo de aviso que les corresponda ver en esta bandeja (los avisos
        que Talento Humano genera al modificar van dirigidos a una persona, y se
        consultan por ``usuario_id``, no en esta bandeja general).

        La comprobación se hace con el cargo de la sesión, no con nada que
        llegue en la petición.
        """
        if not getattr(usuario, "es_talento_humano", False):
            return []
        return self._repository.listar()

    def listar_para_usuario(self, usuario_id: int) -> list[dict[str, Any]]:
        """Avisos dirigidos a una persona concreta."""
        return self._repository.listar_por_usuario(usuario_id)

    # -- escritura ----------------------------------------------------------

    def avisar_asignacion(
        self,
        asignacion: dict[str, Any],
        autor: Any,
        *,
        usuario_destino: int | None = None,
    ) -> None:
        """Avisa que se programaron (o cambiaron) las fechas de alguien.

        Se guarda el ``usuario_id`` de quien hizo la asignación, como pide el
        negocio, y el aviso queda dirigido al usuario dueño de esas fechas.
        """
        mensaje = (
            f"{autor.nombre} asignó las fechas de vacaciones de "
            f"{asignacion['empleado']} ({asignacion['totalDias']} días, "
            f"regreso el {asignacion['fechaIngreso'] or 'por definir'})."
        )
        self._registrar(
            mensaje,
            unes=str(asignacion.get("unes") or UNES_TALENTO_HUMANO),
            usuario_id=usuario_destino,
        )

    def avisar_decision(
        self,
        asignacion: dict[str, Any],
        autor: Any,
        *,
        usuario_destino: int | None = None,
    ) -> None:
        """Avisa la aprobación o el rechazo, y deja constancia de quién lo hizo."""
        if asignacion["estado"] == "aprobada":
            mensaje = (
                f"{autor.nombre} aprobó las vacaciones de {asignacion['empleado']} "
                f"({asignacion['totalDias']} días, regreso el "
                f"{asignacion['fechaIngreso'] or 'por definir'})."
            )
        else:
            motivo = (asignacion.get("motivoRechazo") or "").strip()
            mensaje = (
                f"{autor.nombre} rechazó las vacaciones de {asignacion['empleado']}. "
                f"Motivo: {motivo}"
            )
        self._registrar(
            mensaje,
            unes=str(asignacion.get("unes") or UNES_TALENTO_HUMANO),
            usuario_id=usuario_destino,
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
