"""Capa de acceso a SQL Server.

Responsabilidades, y nada mas:

* construir la conexion a partir de :mod:`config`;
* entregar cursores con consultas **siempre parametrizadas**;
* traducir errores del driver a un error de dominio sin filtrar detalles.

Ninguna consulta de este proyecto concatena valores de entrada. Cuando un
identificador (nombre de tabla o columna) viene de codigo, se valida ademas
contra un conjunto cerrado antes de interpolarse.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import pyodbc

from config import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseUnavailable(RuntimeError):
    """La base no responde o rechaza la conexion."""


class SchemaError(RuntimeError):
    """La base responde pero no tiene la forma que el backend espera."""


# Marcador para abrir un cursor solo cuando se necesita.
class _NoCursor:
    pass


NO_CURSOR = _NoCursor()


@dataclass
class _PooledConnection:
    connection: pyodbc.Connection
    created_at: float
    returned_at: float


class Database:
    """Fabrica de conexiones con reutilizacion acotada.

    Se reutiliza una conexion solo si es reciente, si estuvo inactiva poco
    tiempo y si responde a un ``SELECT 1``. Cualquier fallo la descarta y se
    abre una nueva. Es preferible abrir de mas que devolverle a la aplicacion
    una conexion muerta.
    """

    MAX_REUSE_AGE_SECONDS = 180
    MAX_IDLE_SECONDS = 30

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._connection_string = settings.connection_string()
        self._pooled: _PooledConnection | None = None
        self._lock = threading.Lock()

    # -- gestion del pool ---------------------------------------------------

    def _take_connection(self) -> pyodbc.Connection:
        with self._lock:
            pooled = self._pooled
            self._pooled = None
        if pooled is None:
            return self._open()
        age = time.monotonic() - pooled.created_at
        idle = time.monotonic() - pooled.returned_at
        if age > self.MAX_REUSE_AGE_SECONDS or idle > self.MAX_IDLE_SECONDS:
            self._discard(pooled.connection)
            return self._open()
        try:
            pooled.connection.cursor().execute("SELECT 1").fetchone()
            return pooled.connection
        except pyodbc.Error:
            self._discard(pooled.connection)
            return self._open()

    def _return_connection(self, connection: pyodbc.Connection, *, healthy: bool) -> None:
        if not healthy:
            self._discard(connection)
            return
        with self._lock:
            if self._pooled is None:
                self._pooled = _PooledConnection(
                    connection=connection,
                    created_at=time.monotonic(),
                    returned_at=time.monotonic(),
                )
                return
        self._discard(connection)

    @staticmethod
    def _discard(connection: pyodbc.Connection) -> None:
        try:
            connection.close()
        except Exception:  # noqa: BLE001 - cerrar nunca debe tumbar la peticion
            pass

    def _open(self) -> pyodbc.Connection:
        try:
            # autocommit=False: cada escritura se confirma de forma explicita.
            connection = pyodbc.connect(
                self._connection_string,
                timeout=self._settings.timeout_seconds,
                autocommit=False,
            )
            connection.timeout = self._settings.timeout_seconds
            return connection
        except pyodbc.Error as exc:
            # El detalle del driver puede contener el servidor y la base; se
            # registra en el servidor, nunca se devuelve al cliente.
            logger.error(
                "No se pudo conectar a SQL Server en %s: %s",
                self._settings.safe_target(),
                exc.__class__.__name__,
            )
            raise DatabaseUnavailable("La base de datos no está disponible.") from exc

    # -- API publica --------------------------------------------------------

    @contextmanager
    def cursor(self, *, commit: bool = False, named: bool = False) -> Iterator[pyodbc.Cursor]:
        """Entrega un cursor y devuelve la conexion al pool.

        Con ``commit=True`` confirma al salir sin error y revierte si algo
        falla, de modo que una escritura parcial no quede en la base.

        Con ``named=True`` las filas se leen por nombre de columna
        (``fila.correo``). Es lo que se usa en consultas anchas como
        ``asignacion_vacaciones`` (25 columnas): mapear por posicion se rompe en
        cuanto alguien reordena o agrega una columna.
        """
        connection = self._take_connection()
        cursor = None
        healthy = True
        try:
            cursor = connection.cursor()
            if named:
                cursor = _cursor_con_nombres(cursor)
            yield cursor
            if commit:
                connection.commit()
        except pyodbc.Error as exc:
            healthy = False
            try:
                connection.rollback()
            except Exception:  # noqa: BLE001
                pass
            logger.error("Error de SQL Server: %s", exc.__class__.__name__)
            raise DatabaseUnavailable("La base de datos no respondió como se esperaba.") from exc
        except Exception:
            if commit:
                try:
                    connection.rollback()
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:  # noqa: BLE001
                    healthy = False
            self._return_connection(connection, healthy=healthy)

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> tuple[Any, ...] | None:
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    def query_all(self, sql: str, params: Sequence[Any] = (), *, limit: int = 500) -> list[tuple[Any, ...]]:
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            if limit > 0:
                return cursor.fetchmany(limit)
            return cursor.fetchall()

    def query_named(self, sql: str, params: Sequence[Any] = (), *, limit: int = 500) -> list[Any]:
        """Filas legibles por nombre de columna. Ver ``cursor(named=True)``."""
        with self.cursor(named=True) as cursor:
            cursor.execute(sql, params)
            if limit > 0:
                return cursor.fetchmany(limit)
            return cursor.fetchall()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Ejecuta una escritura y devuelve las filas afectadas."""
        with self.cursor(commit=True) as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    # -- diagnostico --------------------------------------------------------

    def health(self) -> tuple[bool, str]:
        """Comprueba conexion y presencia de las tablas que usa la aplicacion."""
        try:
            with self.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except (DatabaseUnavailable, pyodbc.Error):
            return False, "sin conexión"

        # Las tres tablas del dominio. Si falta alguna, el servicio arranca pero
        # avisa por el diagnóstico en lugar de fallar en la primera petición.
        requeridas = ("Usuarios", "asignacion_vacaciones", "notificaciones")
        try:
            with self.cursor() as cursor:
                for tabla in requeridas:
                    cursor.execute(
                        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
                        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?",
                        tabla,
                    )
                    if cursor.fetchone() is None:
                        return False, f"falta la tabla dbo.{tabla}"
        except (DatabaseUnavailable, pyodbc.Error):
            return False, "sin permisos para leer el catálogo"
        return True, "ok"


def _cursor_con_nombres(cursor: pyodbc.Cursor) -> pyodbc.Cursor:
    """Devuelve un cursor cuyas filas se leen por nombre de columna.

    Se implementa con ``pyodbc.Row`` y un envoltorio: ``pyodbc`` no permite
    pedir ``row.correo`` sin fijar el ``cursor_factory`` en la conexión, y
    fijarlo afectaría a todo el proceso. El envoltorio mantiene la lectura por
    índice —para no romper el código existente— y añade el acceso por nombre.
    """

    class FilaConNombres:
        __slots__ = ("_row", "_columnas")

        def __init__(self, row: pyodbc.Row, columnas: list[str]) -> None:
            self._row = row
            self._columnas = columnas

        def __getitem__(self, key: Any) -> Any:
            if isinstance(key, str):
                try:
                    key = self._columnas.index(key)
                except ValueError as exc:
                    raise KeyError(f"La consulta no devolvió la columna {key!r}.") from exc
            return self._row[key]

        def __getattr__(self, nombre: str) -> Any:
            try:
                return self[nombre]
            except KeyError as exc:
                raise AttributeError(nombre) from exc

        def __iter__(self) -> Any:
            return iter(self._row)

        def __len__(self) -> int:
            return len(self._row)

        def keys(self) -> list[str]:
            return list(self._columnas)

        def get(self, nombre: str, default: Any = None) -> Any:
            try:
                return self[nombre]
            except KeyError:
                return default

    class CursorConNombres:
        def __init__(self, inner: pyodbc.Cursor) -> None:
            self._inner = inner
            self._columnas: list[str] = []

        def execute(self, sql: str, params: Sequence[Any] = ()) -> "CursorConNombres":
            self._inner.execute(sql, params)
            self._columnas = [d[0] for d in (self._inner.description or [])]
            return self

        def _envolver(self, row: Any) -> Any:
            return None if row is None else FilaConNombres(row, self._columnas)

        def fetchone(self) -> Any:
            return self._envolver(self._inner.fetchone())

        def fetchmany(self, size: int = 0) -> list[Any]:
            return [self._envolver(r) for r in self._inner.fetchmany(size)]

        def fetchall(self) -> list[Any]:
            return [self._envolver(r) for r in self._inner.fetchall()]

        @property
        def rowcount(self) -> int:
            return self._inner.rowcount

        def close(self) -> None:
            self._inner.close()

    return CursorConNombres(cursor)  # type: ignore[return-value]
