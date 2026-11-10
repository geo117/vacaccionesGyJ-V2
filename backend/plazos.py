"""Plazos de las vacaciones colectivas.

La fecha límite del proceso es el **1 de diciembre de 2026**. El aviso de la
interfaz se muestra desde seis días antes (`2026-11-25`) y, cuando ya pasó el
día límite, el backend desactiva las cuentas que no sean de administración ni de
Talento Humano.
"""

from __future__ import annotations

from datetime import date

FECHA_LIMITE = date(2026, 12, 1)
DIAS_AVISO = 6


def dias_restantes(hoy: date | None = None) -> int:
    """Días de calendario que faltan para la fecha límite (negativo si pasó)."""
    return (FECHA_LIMITE - (hoy or date.today())).days


def debe_avisar(hoy: date | None = None) -> bool:
    """¿Estamos en la ventana de aviso (6 días antes hasta el día límite)?"""
    return 0 <= dias_restantes(hoy) <= DIAS_AVISO


def debe_desactivar(hoy: date | None = None) -> bool:
    """¿Ya pasó el día límite? Entonces hay que aplicar el corte de cuentas."""
    return dias_restantes(hoy) < 0
