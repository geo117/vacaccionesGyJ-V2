"""Fechas inactivas: los días que no cuentan como vacaciones.

Un domingo o un festivo dentro de un período **no se disfruta** como vacaciones,
así que no puede sumar al total asignado. Este módulo es la versión de servidor
de la regla que la interfaz aplica en `frontend/src/hooks/fechas_inactivas.js`.

Además de la lista global, cada empleado de Colmena puede tener ``SABADO HABIL``:
si es ``NO``, los sábados tampoco cuentan (se descuentan como un domingo); si es
``SI``, cuentan como cualquier día hábil.

La lista es **una sola para todo el sistema**: vive en
``backend/fechas_inactivas.json`` y la leen las dos partes. Si estuviera
duplicada, el total que ve la persona en el modal y el que queda guardado en
``dbo.asignacion_vacaciones`` podrían discrepar, que es justo lo que hay que
evitar: el servidor es el que manda y recalcula los días.

La lista se cachea al primer uso. Al editarla hay que reiniciar el backend; el
archivo se lee una sola vez para no abrirlo en cada petición.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Archivo con la lista, junto a este módulo (misma convención que `filial.py`).
RUTA = Path(__file__).resolve().parent / "fechas_inactivas.json"


@lru_cache(maxsize=1)
def dias_inhabiles() -> frozenset[date]:
    """Fechas inactivas como ``frozenset`` de ``date``.

    Si el archivo falta o está mal formado se devuelve un conjunto vacío y se
    registra el aviso: el sistema sigue funcionando con días calendario en lugar
    de tumbar la asignación de vacaciones por un archivo de configuración.
    """
    try:
        if not RUTA.is_file():
            logger.warning("fechas_inactivas.json no encontrado en %s", RUTA)
            return frozenset()
        datos = json.loads(RUTA.read_text(encoding="utf-8"))
        crudas = datos.get("diasInhabiles") if isinstance(datos, dict) else datos
        return frozenset(date.fromisoformat(str(valor).strip()) for valor in crudas or [])
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        logger.warning("No se pudo leer %s: %s", RUTA, exc.__class__.__name__)
        return frozenset()


def dias_habiles(
    inicio: date, fin: date, *, sabado_habil: bool | None = None
) -> int:
    """Días del rango que sí son vacaciones: ambos extremos menos los inactivos.

    Del 1 al 5 son 5 días, como en la convención del frontend, salvo que alguna
    de esas fechas esté en la lista. Un rango invertido devuelve 0, igual que
    ``(fin - inicio).days + 1`` daría un número negativo que no significa nada.

    ``sabado_habil=False`` descuenta además todos los sábados del rango: el
    empleado no trabaja ese día, así que no lo disfruta como vacaciones.
    ``True`` o ``None`` mantienen el cálculo general (el sábado cuenta; si es
    festivo, igual se descuenta por la lista global).
    """
    total = (fin - inicio).days + 1
    if total <= 0:
        return 0
    inhabiles = dias_inhabiles()
    if sabado_habil is False:
        return sum(
            1
            for desplazamiento in range(total)
            if (fecha := inicio + timedelta(days=desplazamiento)) not in inhabiles
            and fecha.weekday() != 5  # 5 = sábado
        )
    if not inhabiles:
        return total
    return sum(
        1 for desplazamiento in range(total) if inicio + timedelta(days=desplazamiento) not in inhabiles
    )
