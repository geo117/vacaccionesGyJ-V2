"""Resumen: totales y consolidado por empleado.

Junta las dos fuentes que ya existen —``dbo.Usuarios`` y
``dbo.asignacion_vacaciones``— en una sola consulta agregada.

Se resuelve con un ``LEFT JOIN`` y no recorriendo las tablas desde Python: traer
todas las asignaciones para contarlas en memoria funciona con once filas y deja
de funcionar con once mil.
"""

from __future__ import annotations

import logging
from typing import Any

from db import Database

logger = logging.getLogger(__name__)

# Consolidado por colaborador. `LEFT JOIN` para que aparezca quien todavía no
# tiene ninguna asignación: son justamente a quienes hay que mirar.
_SELECT_POR_EMPLEADO = """
SELECT
    u.id                      AS usuario_id,
    u.nombre                  AS nombre,
    u.correo                  AS correo,
    u.cargo                   AS cargo,
    u.fecha_creacion          AS fecha_creacion,
    COUNT(a.id)               AS asignaciones,
    COALESCE(SUM(a.total_dias_empleado), 0) AS dias_totales,
    COALESCE(SUM(CASE WHEN a.estado_asignacion = 'pendiente' THEN 1 ELSE 0 END), 0) AS pendientes,
    COALESCE(SUM(CASE WHEN a.estado_asignacion = 'aprobada'  THEN 1 ELSE 0 END), 0) AS aprobadas,
    COALESCE(SUM(CASE WHEN a.estado_asignacion = 'rechazada' THEN 1 ELSE 0 END), 0) AS rechazadas,
    MAX(a.fecha_update)       AS ultima_actualizacion
FROM dbo.Usuarios u
LEFT JOIN dbo.asignacion_vacaciones a ON LOWER(a.correo) = LOWER(u.correo)
GROUP BY u.id, u.nombre, u.correo, u.cargo, u.fecha_creacion
ORDER BY u.nombre
"""

_SELECT_TOTALES = """
SELECT
    COUNT(*) AS total,
    COALESCE(SUM(total_dias_empleado), 0) AS dias,
    COALESCE(SUM(CASE WHEN estado_asignacion = 'pendiente' THEN 1 ELSE 0 END), 0) AS pendientes,
    COALESCE(SUM(CASE WHEN estado_asignacion = 'aprobada'  THEN 1 ELSE 0 END), 0) AS aprobadas,
    COALESCE(SUM(CASE WHEN estado_asignacion = 'rechazada' THEN 1 ELSE 0 END), 0) AS rechazadas
FROM dbo.asignacion_vacaciones
"""

# La UNES se compara por sus tres últimos dígitos: la misma convención que el
# resto del sistema, que acepta `109` y `2-109`. El valor viaja como parámetro,
# nunca interpolado.
_FILTRO_UNES = "WHERE RIGHT(RTRIM(LTRIM(unes)), 3) = ?"


def _a_iso(valor: Any) -> str | None:
    return valor.isoformat() if hasattr(valor, "isoformat") else (None if valor is None else str(valor))


def _sufijo_unes(unes: Any) -> str:
    """Los tres dígitos que identifican la UNES. ``''`` si no hay filtro.

    Vacío significa "sin acotar" (toda la empresa). Sólo devuelve valor cuando
    hay al menos tres dígitos: un `unes` a medias no debe ampliar ni romper nada.
    """
    digitos = "".join(caracter for caracter in str(unes or "") if caracter.isdigit())
    return digitos[-3:] if len(digitos) >= 3 else ""


class DashboardService:
    def __init__(self, database: Database) -> None:
        self._database = database

    def resumen(self, unes: str = "") -> dict[str, Any]:
        """Totales del resumen.

        Sin ``unes`` cubre la empresa completa —lo que ve Talento Humano—; con
        una UNES acota las cifras de asignaciones a esa unidad. El consolidado
        por empleado sólo se calcula en el alcance global: la vista acotada no lo
        muestra y no corresponde exponer cuentas de otras unidades por esa puerta.
        """
        sufijo = _sufijo_unes(unes)
        if sufijo:
            filas_totales = self._database.query_named(
                f"{_SELECT_TOTALES} {_FILTRO_UNES}", (sufijo,), limit=1
            )
            empleados: list[dict[str, Any]] = []
        else:
            empleados = self._consolidado_por_empleado()
            filas_totales = self._database.query_named(_SELECT_TOTALES, limit=1)

        fila_totales = filas_totales[0] if filas_totales else None

        return {
            "alcance": "unes" if sufijo else "global",
            "unes": sufijo,
            "totales": {
                "usuarios": len(empleados),
                "asignaciones": int(fila_totales["total"]) if fila_totales else 0,
                "diasProgramados": int(fila_totales["dias"]) if fila_totales else 0,
                "pendientes": int(fila_totales["pendientes"]) if fila_totales else 0,
                "aprobadas": int(fila_totales["aprobadas"]) if fila_totales else 0,
                "rechazadas": int(fila_totales["rechazadas"]) if fila_totales else 0,
            },
            "empleados": empleados,
        }

    def _consolidado_por_empleado(self) -> list[dict[str, Any]]:
        filas = self._database.query_named(_SELECT_POR_EMPLEADO)
        return [
            {
                "usuarioId": int(f["usuario_id"]),
                "nombre": str(f["nombre"] or ""),
                "correo": str(f["correo"] or ""),
                "cargo": str(f["cargo"] or ""),
                "fechaCreacion": _a_iso(f["fecha_creacion"]),
                "asignaciones": int(f["asignaciones"] or 0),
                "diasTotales": float(f["dias_totales"] or 0),
                "pendientes": int(f["pendientes"] or 0),
                "aprobadas": int(f["aprobadas"] or 0),
                "rechazadas": int(f["rechazadas"] or 0),
                "ultimaActualizacion": _a_iso(f["ultima_actualizacion"]),
            }
            for f in filas
        ]
