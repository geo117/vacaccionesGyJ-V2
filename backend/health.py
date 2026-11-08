"""Diagnóstico de salud del backend.

Comprueba, **sin escribir datos**, todo lo que puede impedir que la API
funcione y que no se nota hasta la primera petición:

* el entorno de Python y las dependencias de ``requirements.txt``;
* la configuración leída de ``.env`` (nunca imprime credenciales);
* la conexión a la base principal, sus tablas, columnas, tipos, permisos y
  datos mínimos (al menos una cuenta admin y una de Talento Humano activas);
* la conexión opcional a la vista corporativa de colaboradores;
* los archivos de reglas (``fechas_inactivas.json``, ``data filial`` y la
  plantilla del plano UNOEE) y el cálculo de días hábiles;
* el arranque de la aplicación Flask en memoria, sus cabeceras de seguridad,
  CORS y las guardas de autenticación, incluida ``GET /api/health``;
* opcionalmente, un servidor ya en marcha con ``--url``.

Uso:

    cd backend
    python health.py
    python health.py --verbose
    python health.py --json
    python health.py --url http://127.0.0.1:5000

Código de salida: 0 si no hay fallos (las advertencias no cuentan), 1 si algo
falla. Para la prueba funcional completa (login, roles, asignaciones,
notificaciones, reportes) está ``test_backend.py``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Con la salida redirigida (tubería, CI o captura) se fuerza UTF-8 para que un
# acento no rompa la impresión. En una consola se respeta su codificación nativa.
for _stream in (sys.stdout, sys.stderr):
    try:
        if not _stream.isatty():
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - no todas las salidas admiten reconfigure
        pass

# Dependencias declaradas en requirements.txt: módulo importable y paquete pip.
DEPENDENCIAS = (
    ("flask", "flask"),
    ("flask_cors", "flask-cors"),
    ("pyodbc", "pyodbc"),
    ("dotenv", "python-dotenv"),
    ("reportlab", "reportlab"),
    ("openpyxl", "openpyxl"),
)

# Tablas y columnas que la aplicación consulta por nombre. Si falta una, la
# petición falla con un 500 en lugar de avisar al arrancar; por eso se revisa.
# El nombre de la tabla se interpola en el COUNT(*) desde este diccionario
# cerrado, nunca desde una entrada del usuario.
TABLAS_REQUERIDAS: dict[str, tuple[str, ...]] = {
    "dbo.Usuarios": (
        "id",
        "nombre",
        "correo",
        "password_hash",
        "cargo",
        "activo",
        "fecha_creacion",
        "company",
    ),
    "dbo.asignacion_vacaciones": (
        "id",
        "identificacion",
        "empleado",
        "cargo",
        "desc_unes",
        "unes",
        "correo",
        "estado_asignacion",
        "dias_a_corte",
        "observaciones",
        "periodo1_fecha1",
        "periodo1_fecha2",
        "periodo1_dias1",
        "periodo2_fecha1",
        "periodo2_fecha2",
        "periodo2_dias2",
        "periodo3_fecha1",
        "periodo3_fecha2",
        "periodo3_dias3",
        "aprobacion_rechazo_f1",
        "aprobacion_rechazo_f2",
        "aprobacion_rechazo_f3",
        "fecha_regreso",
        "fecha_reintegro_lab",
        "total_dias_empleado",
        "motivo_rechazo",
        "th_asignacion",
        "fecha_registro",
        "fecha_update",
    ),
    "dbo.notificaciones": (
        "id",
        "unes",
        "msj_notificacion",
        "usuario_id",
        "fecha_registro",
        "fecha_update",
    ),
}

# Columnas de la vista corporativa que usa `employees.py`.
COLUMNAS_VISTA = (
    "IDCia_CO",
    "DescCO",
    "cedula",
    "Empleado",
    "fecha_ingreso",
    "Cargo",
    "dias_vacaciones_acumulado",
    "dias_vacaciones_corteDic",
    "email",
    "emailCorporativo",
)

VISTA_COLABORADORES = "dbo.PBI_Colaborador_Vacaciones_V2"

STATUS_LABEL = {"ok": " OK ", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
STATUS_NAME = {"ok": "correctas", "warn": "advertencias", "fail": "fallos", "skip": "omitidas"}


# --------------------------------------------------------------------------
# Salida
# --------------------------------------------------------------------------


def _print(text: str = "") -> None:
    """Imprime sin tumbar el script si la consola no soporta un carácter."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _clip(text: Any, limit: int = 400) -> str:
    """Deja el detalle en una línea y acotado, para que la salida se lea."""
    limpio = " ".join(str(text).split())
    return limpio if len(limpio) <= limit else limpio[: limit - 3] + "..."


def _exc_detail(exc: BaseException, verbose: bool) -> str:
    """Describe una excepción; en modo normal no revela el detalle del driver."""
    base = f"{type(exc).__name__}: {exc}".strip()
    causa = exc.__cause__ or exc.__context__
    if causa is None:
        return base
    if verbose:
        return f"{base} (causa: {type(causa).__name__}: {causa})"
    return f"{base} (causa: {type(causa).__name__})"


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


class Report:
    """Acumula comprobaciones y las imprime de forma legible o en JSON."""

    def __init__(self, *, silent: bool = False) -> None:
        self.silent = silent
        self.checks: list[dict[str, str]] = []
        self._section = "GENERAL"

    def section(self, title: str) -> None:
        self._section = title
        if not self.silent:
            _print(f"\n== {title} ==")

    def add(self, name: str, status: str, detail: Any = "", *, hint: str = "") -> None:
        if status not in STATUS_LABEL:
            raise ValueError(f"Estado desconocido: {status}")
        item = {
            "section": self._section,
            "name": name,
            "status": status,
            "detail": _clip(detail),
            "hint": _clip(hint, 500) if hint else "",
        }
        self.checks.append(item)
        if self.silent:
            return
        _print(f"  [{STATUS_LABEL[status]}] {name}" + (f" - {item['detail']}" if item["detail"] else ""))
        if hint and status in {"warn", "fail"}:
            _print(f"         -> {_clip(hint, 500)}")

    def ok(self, name: str, detail: Any = "") -> None:
        self.add(name, "ok", detail)

    def warn(self, name: str, detail: Any = "", *, hint: str = "") -> None:
        self.add(name, "warn", detail, hint=hint)

    def fail(self, name: str, detail: Any = "", *, hint: str = "") -> None:
        self.add(name, "fail", detail, hint=hint)

    def skip(self, name: str, detail: Any = "", *, hint: str = "") -> None:
        self.add(name, "skip", detail, hint=hint)

    def count(self, status: str) -> int:
        return sum(1 for item in self.checks if item["status"] == status)

    def failures(self) -> list[dict[str, str]]:
        return [item for item in self.checks if item["status"] == "fail"]

    def totals(self) -> dict[str, int]:
        return {status: self.count(status) for status in STATUS_LABEL}


# --------------------------------------------------------------------------
# Entorno
# --------------------------------------------------------------------------


def check_entorno(report: Report) -> None:
    report.section("ENTORNO")

    if sys.version_info >= (3, 10):
        report.ok("versión de Python", f"{sys.version.split()[0]} (se requiere >= 3.10)")
    else:
        report.fail(
            "versión de Python",
            f"{sys.version.split()[0]} (se requiere >= 3.10)",
            hint="El código usa tipos 'X | None' en tiempo de ejecución (dataclasses). Instala Python 3.10 o superior.",
        )

    env_file = BASE_DIR / ".env"
    if env_file.is_file():
        report.ok("archivo .env", str(env_file))
    else:
        report.warn(
            "archivo .env",
            "no existe; la configuración debe venir del entorno",
            hint="Copia backend/.env.example a backend/.env y completa los valores.",
        )

    for modulo, paquete in DEPENDENCIAS:
        try:
            importlib.import_module(modulo)
        except Exception as exc:  # noqa: BLE001 - se reporta en lugar de tumbar el script
            report.fail(
                f"dependencia {paquete}",
                _exc_detail(exc, False),
                hint="Ejecuta: pip install -r requirements.txt",
            )
            continue
        try:
            from importlib.metadata import version

            instalada = version(paquete)
        except Exception:  # noqa: BLE001 - el import ya funcionó
            instalada = "instalada"
        report.ok(f"dependencia {paquete}", instalada)

    try:
        import pyodbc

        drivers = pyodbc.drivers()
    except Exception as exc:  # noqa: BLE001
        report.skip("drivers ODBC", f"pyodbc no disponible: {type(exc).__name__}")
        return
    if drivers:
        report.ok("drivers ODBC disponibles", ", ".join(drivers))
    else:
        report.fail(
            "drivers ODBC disponibles",
            "ninguno registrado",
            hint="Instala 'ODBC Driver 17 for SQL Server' y vuelve a intentar.",
        )


# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------


def check_config(report: Report) -> Any:
    """Carga la configuración. Devuelve ``Settings`` o ``None`` si no se pudo."""
    report.section("CONFIGURACIÓN")

    try:
        from config import load_settings
    except Exception as exc:  # noqa: BLE001
        report.fail(
            "importar config.py",
            _exc_detail(exc, False),
            hint="Revisa que estés ejecutando desde backend/ y que las dependencias estén instaladas.",
        )
        return None

    try:
        # strict_pepper=False: el chequeo se hace aquí para poder seguir
        # diagnosticando la base aunque falte el pepper.
        settings = load_settings(strict_pepper=False)
    except Exception as exc:  # noqa: BLE001
        report.fail(
            "cargar el .env",
            _exc_detail(exc, False),
            hint="Compara backend/.env con backend/.env.example: falta un valor obligatorio o hay uno inseguro.",
        )
        return None

    report.ok("configuración válida", f"base principal: {settings.database.safe_target()}")

    if len(settings.session_pepper) >= 32:
        report.ok("SESSION_PEPPER2", f"{len(settings.session_pepper)} caracteres")
    else:
        report.fail(
            "SESSION_PEPPER2",
            f"{len(settings.session_pepper)} caracteres (mínimo 32)",
            hint='Genera uno con: python -c "import secrets; print(secrets.token_urlsafe(48))"',
        )

    if settings.debug:
        report.fail(
            "DEBUG2 desactivado",
            "está activo",
            hint="El depurador de Werkzeug ejecuta código arbitrario desde el navegador (SEC-17).",
        )
    else:
        report.ok("DEBUG2 desactivado", "False")

    if settings.directorio is None:
        report.skip(
            "conexión al directorio corporativo",
            "DB_SERVER no configurado",
            hint="Es opcional: sin ella la API arranca y /api/asignaciones degrada al listado local.",
        )
    else:
        report.ok("conexión al directorio corporativo", settings.directorio.safe_target())

    faltantes = [
        origen
        for origen in ("http://localhost:5173", "http://127.0.0.1:5173")
        if origen not in settings.cors_origins
    ]
    if faltantes:
        report.warn(
            "orígenes CORS del frontend",
            "falta " + ", ".join(faltantes),
            hint="El frontend de desarrollo corre en Vite (5173); agregúelo a CORS_ORIGINS2 solo si lo usa.",
        )
    else:
        report.ok("orígenes CORS del frontend", "localhost y 127.0.0.1 en el puerto 5173 permitidos")

    if settings.database.user:
        report.ok("usuario de la base principal", "configurado")
    else:
        report.warn(
            "usuario de la base principal",
            "vacío: se usará autenticación de Windows o la cadena del driver",
        )

    try:
        import pyodbc

        disponibles = {d.lower() for d in pyodbc.drivers()}
        esperado = settings.database.driver.strip("{}").lower()
        if esperado in disponibles:
            report.ok("driver ODBC configurado", settings.database.driver)
        else:
            report.fail(
                "driver ODBC configurado",
                f"{settings.database.driver} no está instalado",
                hint="Ajusta DB_DRIVER2 al nombre exacto de un driver de la lista, o instala el Driver 17.",
            )
    except Exception:  # noqa: BLE001 - pyodbc ya se reportó en ENTORNO
        pass

    return settings


# --------------------------------------------------------------------------
# Base principal
# --------------------------------------------------------------------------


def check_base_principal(report: Report, settings: Any, verbose: bool) -> None:
    from db import Database

    report.section("BASE DE DATOS PRINCIPAL")
    database = Database(settings.database)

    started = time.perf_counter()
    try:
        database.query_one("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        report.fail(
            "conexión a la base principal",
            _exc_detail(exc, verbose),
            hint=(
                "Revisa DB_SERVER2, DB_NAME2, DB_USER2 y DB_PASSWORD2 en backend/.env. "
                "Confirma que SQL Server esté arriba, que TCP/IP esté habilitado y que el "
                "driver ODBC exista con ese nombre exacto."
            ),
        )
        return
    report.ok("conexión a la base principal", f"{_ms(started):.0f} ms - {settings.database.safe_target()}")

    try:
        fila = database.query_one("SELECT DB_NAME(), @@VERSION")
    except Exception as exc:  # noqa: BLE001
        fila = None
        report.fail("consulta de contexto", _exc_detail(exc, verbose))
    if fila is not None:
        nombre_actual = str(fila[0]) if fila[0] is not None else ""
        configurado = settings.database.name
        if configurado and nombre_actual.lower() != configurado.lower():
            report.warn(
                "base de datos activa",
                f"conectó a {nombre_actual!r} y DB_NAME2 dice {configurado!r}",
                hint="La cadena de conexión puede estar apuntando a otra base.",
            )
        else:
            report.ok("base de datos activa", nombre_actual or "sin nombre")

        if fila[1]:
            motor = str(fila[1]).splitlines()[0].strip()
            report.ok("motor SQL Server", _clip(motor, 160))

    try:
        fila = database.query_one("SELECT IS_SRVROLEMEMBER('sysadmin')")
        sysadmin = fila is not None and fila[0] is not None and int(fila[0]) == 1
        if sysadmin:
            report.warn(
                "privilegios de la cuenta de base",
                "es sysadmin: la API no necesita ese poder",
                hint="Usa una cuenta con permisos solo sobre las tres tablas (ver SECURITY-NOTES.md).",
            )
        else:
            report.ok("privilegios de la cuenta de base", "sin rol sysadmin")
    except Exception as exc:  # noqa: BLE001
        report.skip("privilegios de la cuenta de base", _exc_detail(exc, verbose))

    try:
        sano, motivo = database.health()
        if sano:
            report.ok("Database.health()", motivo)
        else:
            report.fail("Database.health()", motivo)
    except Exception as exc:  # noqa: BLE001
        report.fail("Database.health()", _exc_detail(exc, verbose))

    for tabla, esperadas in TABLAS_REQUERIDAS.items():
        nombre = tabla.split(".", 1)[1]
        try:
            filas = database.query_all(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?",
                (nombre,),
                limit=0,
            )
        except Exception as exc:  # noqa: BLE001
            report.fail(f"columnas de {tabla}", _exc_detail(exc, verbose))
            continue

        actuales = {str(f[0]).lower() for f in filas}
        if not actuales:
            report.fail(
                f"tabla {tabla}",
                "no existe o la cuenta no la ve",
                hint="Crea la tabla con el esquema del README o revisa los permisos de la cuenta.",
            )
            continue

        faltantes = [columna for columna in esperadas if columna.lower() not in actuales]
        if faltantes:
            report.fail(
                f"columnas de {tabla}",
                "faltan: " + ", ".join(faltantes),
                hint="La consulta de la API nombra esas columnas; sin ellas la petición responde 500.",
            )
        else:
            report.ok(f"columnas de {tabla}", f"{len(actuales)} columnas; no falta ninguna requerida")

        permisos_faltantes = []
        for permiso in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            try:
                fila = database.query_one(
                    "SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', ?)", (tabla, permiso)
                )
                concedido = fila is not None and fila[0] == 1
            except Exception:  # noqa: BLE001
                concedido = True  # si no se puede averiguar, no se inventa un fallo
            if not concedido:
                permisos_faltantes.append(permiso)
        if permisos_faltantes:
            report.fail(
                f"permisos en {tabla}",
                "faltan: " + ", ".join(permisos_faltantes),
                hint="La API lee y escribe en esta tabla; concédele SELECT/INSERT/UPDATE/DELETE.",
            )
        else:
            report.ok(f"permisos en {tabla}", "SELECT, INSERT, UPDATE y DELETE")

        try:
            fila = database.query_one(f"SELECT COUNT(*) FROM {tabla}")
            total = int(fila[0]) if fila is not None and fila[0] is not None else 0
            report.ok(f"filas en {tabla}", total)
        except Exception as exc:  # noqa: BLE001
            report.fail(f"filas en {tabla}", _exc_detail(exc, verbose))

    # El resultado se guarda con un decimal (DECIMAL(6,1)); si la columna fuera
    # entera, la pantalla y la base discreparían en los días a usar.
    try:
        fila = database.query_one(
            "SELECT DATA_TYPE, NUMERIC_SCALE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'asignacion_vacaciones' "
            "AND COLUMN_NAME = 'dias_a_corte'"
        )
        if fila is None:
            report.fail("tipo de dias_a_corte", "columna no encontrada")
        else:
            tipo = str(fila[0]).lower()
            escala = int(fila[1]) if fila[1] is not None else 0
            if tipo in {"decimal", "numeric"} and escala >= 1:
                report.ok("tipo de dias_a_corte", f"{tipo}(escala {escala})")
            else:
                report.fail(
                    "tipo de dias_a_corte",
                    f"{tipo} con escala {escala}; se espera decimal con escala >= 1",
                    hint="ALTER TABLE dbo.asignacion_vacaciones ALTER COLUMN dias_a_corte DECIMAL(6,1);",
                )
    except Exception as exc:  # noqa: BLE001
        report.skip("tipo de dias_a_corte", _exc_detail(exc, verbose))

    # El correo duplicado se responde como 409 apoyándose en el índice único.
    try:
        fila = database.query_one(
            "SELECT TOP 1 i.name FROM sys.indexes i "
            "JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
            "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
            "WHERE i.object_id = OBJECT_ID('dbo.Usuarios') AND i.is_unique = 1 AND c.name = 'correo'"
        )
        if fila is None:
            report.warn(
                "índice único de Usuarios.correo",
                "no se encontró",
                hint="Sin él, dos cuentas pueden compartir correo y el login se vuelve ambiguo.",
            )
        else:
            report.ok("índice único de Usuarios.correo", str(fila[0]))
    except Exception as exc:  # noqa: BLE001
        report.skip("índice único de Usuarios.correo", _exc_detail(exc, verbose))

    # Sin un admin o un Talento Humano activo, la aplicación arranca pero nadie
    # puede administrar cuentas o aprobar vacaciones.
    try:
        fila = database.query_one(
            "SELECT "
            "SUM(CASE WHEN LOWER(cargo) = ? THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN LOWER(cargo) = ? THEN 1 ELSE 0 END) "
            "FROM dbo.Usuarios "
            "WHERE LOWER(ISNULL(activo, '')) IN ('si', 'sí', '1', 'true')",
            ("admin", "talento humano"),
        )
        admins = int(fila[0] or 0) if fila is not None else 0
        ths = int(fila[1] or 0) if fila is not None else 0
        if admins == 0:
            report.warn(
                "cuentas admin activas",
                "ninguna: nadie podrá administrar usuarios",
                hint="Crea o activa una cuenta con cargo 'admin'.",
            )
        else:
            report.ok("cuentas admin activas", admins)
        if ths == 0:
            report.warn(
                "cuentas de Talento Humano activas",
                "ninguna: nadie podrá aprobar ni rechazar",
                hint="Crea o activa una cuenta con cargo 'talento humano'.",
            )
        else:
            report.ok("cuentas de Talento Humano activas", ths)
    except Exception as exc:  # noqa: BLE001
        report.skip("cuentas activas por cargo", _exc_detail(exc, verbose))


# --------------------------------------------------------------------------
# Directorio corporativo (opcional)
# --------------------------------------------------------------------------


def check_directorio(report: Report, settings: Any, verbose: bool) -> None:
    from db import Database

    report.section("DIRECTORIO CORPORATIVO (OPCIONAL)")

    if settings.directorio is None:
        report.skip(
            "conexión al directorio",
            "DB_SERVER no configurado",
            hint="Sin esta conexión /api/asignaciones devuelve el listado local (origen='local').",
        )
        return

    database = Database(settings.directorio)
    started = time.perf_counter()
    try:
        fila = database.query_one(
            f"SELECT TOP 1 cedula, IDCia_CO, Empleado FROM {VISTA_COLABORADORES}"
        )
    except Exception as exc:  # noqa: BLE001
        report.fail(
            "conexión al directorio",
            _exc_detail(exc, verbose),
            hint=(
                "Revisa DB_SERVER, DB_NAME y DB_PASSWORD. La API sigue funcionando sin "
                "esta conexión, pero el tablero mostrará solo el listado local."
            ),
        )
        return

    report.ok("conexión al directorio", f"{_ms(started):.0f} ms - {settings.directorio.safe_target()}")
    if fila is None:
        report.warn(
            "vista de colaboradores",
            "respondió vacía",
            hint="La pantalla no tendrá colaboradores que mostrar aunque la conexión funcione.",
        )
    else:
        report.ok(
            "vista de colaboradores",
            f"primera cédula {fila[0]!r} de la UNES {fila[1]!r}",
        )

    try:
        filas = database.query_all(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'PBI_Colaborador_Vacaciones_V2'",
            limit=0,
        )
        actuales = {str(f[0]).lower() for f in filas}
        if not actuales:
            report.fail("columnas de la vista", "la vista no existe o la cuenta no la ve")
        else:
            faltantes = [columna for columna in COLUMNAS_VISTA if columna.lower() not in actuales]
            if faltantes:
                report.fail(
                    "columnas de la vista",
                    "faltan: " + ", ".join(faltantes),
                    hint="La vista la mantiene otro proceso; avisa antes de cambiar el código.",
                )
            else:
                report.ok("columnas de la vista", f"{len(COLUMNAS_VISTA)} columnas requeridas presentes")
    except Exception as exc:  # noqa: BLE001
        report.skip("columnas de la vista", _exc_detail(exc, verbose))


# --------------------------------------------------------------------------
# Archivos y reglas de negocio
# --------------------------------------------------------------------------


def check_archivos(report: Report) -> None:
    report.section("ARCHIVOS Y REGLAS DE NEGOCIO")

    # -- fechas inactivas ---------------------------------------------------
    try:
        from dias_inhabiles import RUTA, dias_habiles, dias_inhabiles

        datos = json.loads(RUTA.read_text(encoding="utf-8"))
        crudas = datos.get("diasInhabiles") if isinstance(datos, dict) else datos
        lista = list(crudas or [])

        fechas: list[date] = []
        invalidas: list[str] = []
        for valor in lista:
            try:
                fechas.append(date.fromisoformat(str(valor).strip()))
            except ValueError:
                invalidas.append(str(valor))

        if invalidas:
            report.fail(
                "fechas_inactivas.json",
                f"{len(invalidas)} fechas no son ISO: " + ", ".join(invalidas[:5]),
            )
        else:
            report.ok("fechas_inactivas.json", f"{len(fechas)} fechas, todas ISO válidas")

        if len(dias_inhabiles()) == len(set(fechas)):
            report.ok("la caché del backend coincide con el archivo", f"{len(dias_inhabiles())} fechas")
        else:
            report.fail(
                "la caché del backend coincide con el archivo",
                f"archivo {len(set(fechas))} vs caché {len(dias_inhabiles())}",
            )

        # Se calcula con la misma función que usa la API contra el archivo real:
        # diciembre de 2026 tiene 31 días; los que estén listados no cuentan.
        conteo_diciembre = sum(1 for fecha in fechas if fecha.year == 2026 and fecha.month == 12)
        esperado = 31 - conteo_diciembre
        calculado = dias_habiles(date(2026, 12, 1), date(2026, 12, 31))
        if calculado == esperado:
            report.ok(
                "cálculo de días hábiles",
                f"diciembre 2026: {calculado} de 31 (descuenta {conteo_diciembre} listadas)",
            )
        else:
            report.fail(
                "cálculo de días hábiles",
                f"la función devolvió {calculado} y el archivo implica {esperado}",
                hint="Revisa dias_inhabiles.py y el formato de fechas_inactivas.json.",
            )

        detalle = datos.get("detalle") if isinstance(datos, dict) else None
        if isinstance(detalle, dict):
            domingos_mal = []
            for clave, descripcion in detalle.items():
                try:
                    fecha = date.fromisoformat(str(clave).strip())
                except ValueError:
                    continue
                if "domingo" in str(descripcion).lower() and fecha.weekday() != 6:
                    domingos_mal.append(str(clave))
            if domingos_mal:
                report.warn(
                    "coherencia de las fechas inactivas",
                    "marcadas como domingo pero no caen en domingo: " + ", ".join(domingos_mal[:5]),
                )
            else:
                report.ok("coherencia de las fechas inactivas", "las marcadas como domingo caen en domingo")
    except Exception as exc:  # noqa: BLE001
        report.fail(
            "fechas_inactivas.json",
            _exc_detail(exc, False),
            hint="El archivo debe existir junto a dias_inhabiles.py y ser JSON válido.",
        )

    # -- filial -------------------------------------------------------------
    try:
        from filial import FILIAL_JSON_PATH, obtener_cedulas_filial

        datos = json.loads(FILIAL_JSON_PATH.read_text(encoding="utf-8"))
        if not isinstance(datos, dict):
            report.fail("filial.json", "la raíz no es un diccionario correo → colaboradores")
        else:
            errores = []
            total = 0
            for correo, registros in datos.items():
                if not isinstance(registros, list):
                    errores.append(str(correo))
                    continue
                total += len(registros)
                for item in registros:
                    if not isinstance(item, dict) or not item.get("cedula"):
                        errores.append(str(correo))
                        break
            if errores:
                report.warn(
                    "filial.json",
                    f"{len(errores)} entradas sin lista o sin cédula",
                    hint="Esas entradas no aplicarán el filtro de filial, pero la API sigue funcionando.",
                )
            else:
                report.ok("filial.json", f"{len(datos)} jefes, {total} colaboradores")

            primer_correo = next(iter(datos), None)
            if primer_correo is not None:
                cedulas = obtener_cedulas_filial(primer_correo)
                if cedulas:
                    report.ok(
                        "lectura de filial.json por correo",
                        f"{len(cedulas)} cédulas para {primer_correo}",
                    )
                else:
                    report.fail("lectura de filial.json por correo", f"no devolvió cédulas para {primer_correo}")
    except Exception as exc:  # noqa: BLE001
        report.fail("filial.json", _exc_detail(exc, False))

    # -- jefes de Colmena ----------------------------------------------------
    # Los archivos deciden qué cédulas ve cada jefe. Los correos de dirección ven
    # la unión de **su propia** entrada en `colmena.json` y `filial.json`. Si
    # falta un archivo, esas cuentas vuelven a la regla de UNES y el filtro por
    # equipo no se aplica.
    try:
        from colmena import (
            COLMENA_JSON_PATH,
            DIRECCION_GRUPO,
            TIPO_EQUIPO,
            TIPO_GRUPO,
            alcance_de,
            cargar_jefes,
            cargar_sabados,
        )

        datos = json.loads(COLMENA_JSON_PATH.read_text(encoding="utf-8"))
        jefes = cargar_jefes()
        if not isinstance(datos, dict) or not jefes:
            report.fail("colmena.json", "sin jefes legibles")
        else:
            total_cedulas = sum(len(cedulas) for cedulas in jefes.values())
            report.ok("colmena.json", f"{len(jefes)} jefes, {total_cedulas} cédulas")

        sabados = cargar_sabados()
        if sabados:
            habiles = sum(1 for valor in sabados.values() if valor)
            report.ok(
                "SABADO HABIL en colmena.json",
                f"{habiles} hábiles, {len(sabados) - habiles} no hábiles",
            )
        else:
            report.warn(
                "SABADO HABIL en colmena.json",
                "sin datos; los sábados se cuentan para todos",
            )

        faltan_direccion = [correo for correo in DIRECCION_GRUPO if correo not in jefes]
        if faltan_direccion:
            report.warn(
                "dirección del grupo en colmena.json",
                "faltan: " + ", ".join(sorted(faltan_direccion)),
                hint="Esos correos no podrán iniciar sesión con el alcance de dirección.",
            )
        else:
            report.ok("dirección del grupo en colmena.json", "los tres correos están")

        ejemplo_equipo = next((correo for correo in jefes if correo not in DIRECCION_GRUPO), "")
        if ejemplo_equipo:
            alcance = alcance_de(ejemplo_equipo)
            if alcance is not None and alcance.tipo == TIPO_EQUIPO:
                report.ok(
                    "alcance por cédula de un jefe",
                    f"{ejemplo_equipo}: {len(alcance.cedulas)} cédulas",
                )
            else:
                report.fail("alcance por cédula de un jefe", "no se resolvió como equipo")

        for correo in sorted(DIRECCION_GRUPO):
            alcance = alcance_de(correo)
            if (
                alcance is not None
                and alcance.tipo == TIPO_GRUPO
                and alcance.cedulas
            ):
                report.ok(
                    f"conjunto de dirección · {correo}",
                    f"{len(alcance.cedulas)} cédulas en colmena.json + filial.json",
                )
            else:
                report.fail(
                    f"conjunto de dirección · {correo}",
                    "sin cédulas propias en colmena.json + filial.json",
                )
    except Exception as exc:  # noqa: BLE001
        report.fail("colmena.json", _exc_detail(exc, False))

    # -- áreas --------------------------------------------------------------
    # Dos archivos, uno por empresa: GyJ (company 2) y Colmena (company 4).
    try:
        from areas import (
            AREAS_COLMENA_JSON_PATH,
            AREAS_FILIAL_JSON_PATH,
            cargar_indice,
            cargar_indice_admin,
            cargar_indice_colmena,
            cargar_indice_empresa,
        )

        for etiqueta, ruta, cargar in (
            ("areas_filial.json", AREAS_FILIAL_JSON_PATH, cargar_indice),
            ("areas_colmena.json", AREAS_COLMENA_JSON_PATH, cargar_indice_colmena),
        ):
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            indice = cargar()
            if not isinstance(datos, dict) or not indice.areas:
                report.fail(etiqueta, "sin áreas legibles")
            else:
                report.ok(
                    etiqueta,
                    f"{len(indice.areas)} áreas, {len(indice.por_cedula)} cédulas",
                )

        # La lista que recibe cada empresa y la que recibe el admin.
        gyj = cargar_indice_empresa(2)
        colmena = cargar_indice_empresa(4)
        admin = cargar_indice_admin()
        if gyj.areas and colmena.areas:
            report.ok(
                "áreas por empresa",
                f"GyJ {len(gyj.areas)}, Colmena {len(colmena.areas)}, admin {len(admin.areas)}",
            )
        else:
            report.fail(
                "áreas por empresa",
                f"GyJ {len(gyj.areas)}, Colmena {len(colmena.areas)}",
                hint="Revisa que estén los dos archivos y tengan la forma área → colaboradores.",
            )
    except Exception as exc:  # noqa: BLE001
        report.fail("áreas por empresa", _exc_detail(exc, False))

    # -- plantilla del plano UNOEE -----------------------------------------
    try:
        from reports import PLANTILLA_PLANO

        if not PLANTILLA_PLANO.is_file():
            report.fail(
                "plantilla del plano UNOEE",
                f"no existe {PLANTILLA_PLANO}",
                hint="El endpoint /api/reportes/plano-unoee no podrá generar el Excel.",
            )
        else:
            from openpyxl import load_workbook

            libro = load_workbook(PLANTILLA_PLANO, read_only=True)
            hojas = list(libro.sheetnames)
            libro.close()
            report.ok(
                "plantilla del plano UNOEE",
                f"{PLANTILLA_PLANO.name}: {len(hojas)} hoja(s), {', '.join(hojas[:3])}",
            )
    except Exception as exc:  # noqa: BLE001
        report.fail("plantilla del plano UNOEE", _exc_detail(exc, False))


# --------------------------------------------------------------------------
# Aplicación Flask en memoria
# --------------------------------------------------------------------------


def check_aplicacion(report: Report, settings: Any) -> None:
    report.section("APLICACIÓN FLASK (EN MEMORIA)")

    try:
        from app import API_VERSION, create_app

        app = create_app(settings)
    except Exception as exc:  # noqa: BLE001
        report.fail(
            "create_app()",
            _exc_detail(exc, False),
            hint="Es el mismo arranque de python app.py; revisa la traza del servidor.",
        )
        return

    report.ok("la aplicación se construye", f"versión {API_VERSION}")
    client = app.test_client()

    textos: list[str] = []

    try:
        respuesta = client.get("/api")
        cuerpo = respuesta.get_json() or {}
        textos.append(respuesta.get_data(as_text=True))
        if respuesta.status_code == 200 and cuerpo.get("ok"):
            report.ok("GET /api", f"HTTP 200, {len(cuerpo.get('endpoints') or [])} endpoints")
        else:
            report.fail("GET /api", f"HTTP {respuesta.status_code}: {_clip(cuerpo, 200)}")
    except Exception as exc:  # noqa: BLE001
        report.fail("GET /api", _exc_detail(exc, False))

    try:
        respuesta = client.get("/api/health")
        cuerpo = respuesta.get_json() or {}
        textos.append(respuesta.get_data(as_text=True))
        if respuesta.status_code == 200 and cuerpo.get("db") == "ok":
            report.ok(
                "GET /api/health",
                f"db=ok, directorio={cuerpo.get('directorio')}, versión={cuerpo.get('version')}",
            )
        else:
            report.fail(
                "GET /api/health",
                f"HTTP {respuesta.status_code}: {_clip(cuerpo, 240)}",
                hint="La API no pudo consultar la base principal; revisa la sección anterior.",
            )

        cabeceras = respuesta.headers
        valores = {
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
        faltantes = [h for h, valor in valores.items() if cabeceras.get(h) != valor]
        if faltantes:
            report.fail("cabeceras de seguridad", "faltan o no coinciden: " + ", ".join(faltantes))
        elif not cabeceras.get("Content-Security-Policy"):
            report.warn("cabeceras de seguridad", "no se envió Content-Security-Policy")
        else:
            report.ok("cabeceras de seguridad", "nosniff, no-store y CSP presentes")
    except Exception as exc:  # noqa: BLE001
        report.fail("GET /api/health", _exc_detail(exc, False))

    try:
        respuesta = client.get("/api/usuarios")
        cuerpo = respuesta.get_json() or {}
        textos.append(respuesta.get_data(as_text=True))
        if respuesta.status_code == 401 and cuerpo.get("code") == "SESSION_REQUIRED":
            report.ok("las rutas de datos exigen sesión", "GET /api/usuarios sin token responde 401")
        else:
            report.fail(
                "las rutas de datos exigen sesión",
                f"HTTP {respuesta.status_code} ({cuerpo.get('code')})",
                hint="Una ruta protegida sin token debe responder 401 SESSION_REQUIRED.",
            )
    except Exception as exc:  # noqa: BLE001
        report.fail("las rutas de datos exigen sesión", _exc_detail(exc, False))

    # Un correo aleatorio no existe: se comprueba el flujo de credenciales sin
    # tocar ninguna cuenta real ni bloquear a nadie por intentos fallidos.
    try:
        correo = f"health.{uuid.uuid4().hex[:10]}@invalid.local"
        respuesta = client.post(
            "/api/auth/login", json={"correo": correo, "password": "ClaveDePrueba1*"}
        )
        cuerpo = respuesta.get_json() or {}
        textos.append(respuesta.get_data(as_text=True))
        if respuesta.status_code == 401 and cuerpo.get("code") == "INVALID_CREDENTIALS":
            report.ok("login con credenciales inválidas", "responde 401 INVALID_CREDENTIALS")
        else:
            report.fail(
                "login con credenciales inválidas",
                f"HTTP {respuesta.status_code}: {_clip(cuerpo, 240)}",
                hint="Si la base está caída, la API responderá 503 en lugar de 401.",
            )
    except Exception as exc:  # noqa: BLE001
        report.fail("login con credenciales inválidas", _exc_detail(exc, False))

    try:
        origen = settings.cors_origins[0] if settings.cors_origins else ""
        if origen:
            respuesta = client.options(
                "/api/health",
                headers={"Origin": origen, "Access-Control-Request-Method": "GET"},
            )
            permitido = respuesta.headers.get("Access-Control-Allow-Origin")
            if permitido == origen:
                report.ok("CORS", f"{origen} permitido")
            else:
                report.warn(
                    "CORS",
                    f"el preflight no devolvió Access-Control-Allow-Origin para {origen}",
                    hint="Revisa CORS_ORIGINS2 y que flask-cors esté instalado.",
                )
    except Exception as exc:  # noqa: BLE001
        report.skip("CORS", _exc_detail(exc, False))

    # Ninguna respuesta debe repetir la contraseña de la base ni una traza.
    fuga = [texto for texto in textos if "Traceback" in texto or "pyodbc." in texto]
    if settings.database.password:
        fuga += [texto for texto in textos if settings.database.password in texto]
    if fuga:
        report.fail(
            "las respuestas no filtran detalles internos",
            "se encontró una traza, el nombre del driver o la contraseña",
        )
    else:
        report.ok("las respuestas no filtran detalles internos", "sin trazas ni credenciales")


# --------------------------------------------------------------------------
# Servidor HTTP en marcha (opcional)
# --------------------------------------------------------------------------


def check_servidor(report: Report, url: str | None, verbose: bool) -> None:
    report.section("SERVIDOR HTTP")

    if not url:
        report.skip(
            "servidor en marcha",
            "no se pasó --url",
            hint="Con el backend corriendo: python health.py --url http://127.0.0.1:5000",
        )
        return

    import urllib.error
    import urllib.request

    endpoint = url.rstrip("/") + "/api/health"
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(endpoint, timeout=5) as respuesta:
            codigo = respuesta.status
            crudo = respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        codigo = exc.code
        crudo = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        report.fail(
            f"GET {endpoint}",
            _exc_detail(exc, verbose),
            hint="Arranca el backend con: python app.py",
        )
        return

    try:
        cuerpo = json.loads(crudo)
    except ValueError:
        cuerpo = {}

    if 200 <= codigo < 300 and cuerpo.get("db") == "ok":
        report.ok(f"GET {endpoint}", f"{codigo} en {_ms(started):.0f} ms, versión {cuerpo.get('version')}")
    else:
        report.fail(
            f"GET {endpoint}",
            f"HTTP {codigo}: {_clip(cuerpo or crudo, 240)}",
            hint="El servidor responde, pero no puede consultar la base o la ruta no existe.",
        )


# --------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnóstico de salud del backend (no escribe datos).",
        epilog="La prueba funcional completa está en test_backend.py.",
    )
    parser.add_argument("--json", action="store_true", help="emite el resultado como JSON")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="muestra la causa completa de los errores del driver",
    )
    parser.add_argument(
        "--url",
        help="comprueba también un servidor en marcha, p. ej. http://127.0.0.1:5000",
    )
    args = parser.parse_args(argv)

    report = Report(silent=args.json)
    if not args.json:
        _print("Diagnóstico de salud del backend")
        _print(f"Carpeta: {BASE_DIR}")

    check_entorno(report)
    settings = check_config(report)

    if settings is None:
        report.section("BASE DE DATOS PRINCIPAL")
        report.skip("conexión a la base principal", "configuración inválida")
        report.section("DIRECTORIO CORPORATIVO (OPCIONAL)")
        report.skip("conexión al directorio", "configuración inválida")
    else:
        check_base_principal(report, settings, args.verbose)
        check_directorio(report, settings, args.verbose)

    check_archivos(report)

    if settings is not None:
        check_aplicacion(report, settings)
    else:
        report.section("APLICACIÓN FLASK (EN MEMORIA)")
        report.skip("create_app()", "configuración inválida")

    check_servidor(report, args.url, args.verbose)

    fallos = report.failures()
    totales = report.totals()

    if args.json:
        salida = {
            "ok": not fallos,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "summary": totales,
            "checks": report.checks,
        }
        print(json.dumps(salida, ensure_ascii=True, indent=2))
    else:
        _print("\n== RESUMEN ==")
        _print(
            f"  {totales['ok']} correctas, {totales['warn']} advertencias, "
            f"{totales['fail']} fallos, {totales['skip']} omitidas"
        )
        if fallos:
            _print("\n  Fallos:")
            for item in fallos:
                _print(f"   - [{item['section']}] {item['name']}: {item['detail']}")
            _print("\n  Estado: CON FALLOS")
        else:
            sufijo = " (con advertencias)" if totales["warn"] else ""
            _print(f"\n  Estado: SANO{sufijo}")
        _print("\n  Prueba funcional completa: python test_backend.py")

    return 1 if fallos else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _print("\nInterrumpido.")
        sys.exit(130)
