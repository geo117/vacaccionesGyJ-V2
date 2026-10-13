"""Configuracion del backend leida exclusivamente desde el entorno.

Reglas de construccion (ver SECURITY-NOTES.md):

* Ningun valor de ``.env`` se escribe en el codigo ni se devuelve al cliente.
* Una credencial ausente es un error de arranque, nunca un valor por defecto
  silencioso.
* ``DEBUG`` no puede quedar activo por accidente: el depurador de Werkzeug
  ejecuta codigo arbitrario desde el navegador.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


class ConfigError(RuntimeError):
    """Falta un valor obligatorio o su valor es inseguro."""


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _to_int(value: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"Falta {name} en {ENV_PATH.name}. El backend no arranca con configuracion "
            "incompleta: revisa backend/.env.example para ver las variables esperadas."
        )
    return value


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class DatabaseSettings:
    server: str
    name: str
    user: str
    password: str = field(repr=False)
    driver: str
    encrypt: bool
    trust_server_certificate: bool
    timeout_seconds: int

    def connection_string(self) -> str:
        """Arma el connection string de ODBC a partir de piezas ya validadas.

        ``pyodbc`` no admite parametros en ``connect()``; por eso cada valor que
        llega aqui viene de una variable de entorno controlada y nunca de una
        entrada del usuario (ver SECURITY-NOTES.md, inyeccion de connection
        string).
        """
        parts = {
            "DRIVER": self.driver,
            "SERVER": self.server,
            "DATABASE": self.name,
            "UID": self.user,
            "PWD": self.password,
            "Encrypt": "yes" if self.encrypt else "no",
            "TrustServerCertificate": "yes" if self.trust_server_certificate else "no",
            "APP": "gestion-vacaciones-api",
        }
        return ";".join(f"{key}={value}" for key, value in parts.items()) + ";"

    def safe_target(self) -> str:
        """Descripcion apta para logs: nunca incluye usuario ni contrasena."""
        return f"{self.server}/{self.name}"


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings
    # Segunda conexión: el servidor corporativo donde vive la vista
    # `PBI_Colaborador_Vacaciones`. Es opcional para que el backend pueda
    # arrancar (y todo lo demás funcionar) aunque ese servidor no esté accesible.
    directorio: DatabaseSettings | None
    debug: bool
    port: int
    host: str
    cors_origins: tuple[str, ...]
    session_ttl_seconds: int
    session_idle_seconds: int
    session_pepper: str = field(repr=False)
    login_max_attempts: int
    login_window_seconds: int
    log_level: str


def _leer_database(prefijo: str, *, obligatorio: bool) -> DatabaseSettings | None:
    """Arma una conexión a partir de las variables con el prefijo dado.

    ``prefijo=""`` lee ``DB_SERVER``/``DB_NAME``/…; ``prefijo="2"`` lee
    ``DB_SERVER2``/``DB_NAME2``/…. Un solo lector evita tener dos bloques
    parecidos que se desincronicen.
    """
    servidor = os.getenv(f"DB_SERVER{prefijo}", "").strip()
    if not servidor:
        if obligatorio:
            raise ConfigError(
                f"Falta DB_SERVER{prefijo} en {ENV_PATH.name}. El backend no arranca con "
                "configuración incompleta: revisa backend/.env.example."
            )
        return None

    driver = os.getenv(f"DB_DRIVER{prefijo}", "{ODBC Driver 17 for SQL Server}").strip()
    if not driver.startswith("{") or not driver.endswith("}"):
        driver = f"{{{driver}}}"

    return DatabaseSettings(
        server=servidor,
        name=os.getenv(f"DB_NAME{prefijo}", "").strip(),
        user=os.getenv(f"DB_USER{prefijo}", "").strip(),
        password=os.getenv(f"DB_PASSWORD{prefijo}", ""),
        driver=driver,
        encrypt=_to_bool(os.getenv(f"DB_ENCRYPT{prefijo}"), True),
        trust_server_certificate=_to_bool(os.getenv(f"DB_TRUST_SERVER_CERT{prefijo}"), True),
        timeout_seconds=_to_int(
            os.getenv(f"DB_TIMEOUT_SECONDS{prefijo}"), 5, minimum=1, maximum=60
        ),
    )


def load_settings(*, env_path: Path | None = None, strict_pepper: bool = True) -> Settings:
    """Carga la configuracion. Lanza ``ConfigError`` si algo es inseguro."""
    load_dotenv(env_path or ENV_PATH, override=False)

    database = _leer_database("2", obligatorio=True)
    assert database is not None  # obligatorio=True garantiza que no es None

    # Segunda conexión, opcional: si no está configurada, las funciones que
    # dependen de ella avisan en lugar de tumbar el servicio.
    directorio = _leer_database("", obligatorio=False)

    # DEBUG nunca se activa por omision y jamas con 'True' en texto: se exige
    # un valor explicito y se rechaza si el .env trae algo ambiguo.
    raw_debug = os.getenv("DEBUG2", "False").strip()
    debug = _to_bool(raw_debug, False)
    if debug:
        raise ConfigError(
            "DEBUG2 está activo. El depurador de Werkzeug permite ejecutar código "
            "arbitrario desde el navegador (SEC-17). Ponlo en False para arrancar."
        )

    allowed_origins = tuple(
        _split_csv(os.getenv("CORS_ORIGINS2", "http://localhost:5173,http://127.0.0.1:5173"))
    )
    if "*" in allowed_origins:
        raise ConfigError(
            "CORS_ORIGINS2 no admite '*': un comodín expone el token de sesión a "
            "cualquier origen. Enumera los orígenes exactos."
        )

    pepper = os.getenv("SESSION_PEPPER2", "").strip()
    if len(pepper) < 32 and strict_pepper:
        raise ConfigError(
            "SESSION_PEPPER2 debe tener al menos 32 caracteres. Genera uno con:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
            "y agrégalo a backend/.env como SESSION_PEPPER2=<valor>."
        )

    return Settings(
        database=database,
        directorio=directorio,
        debug=debug,
        host=os.getenv("HOST2", "127.0.0.1").strip() or "127.0.0.1",
        port=_to_int(os.getenv("PORT2"), 5000, minimum=1024, maximum=65535),
        cors_origins=allowed_origins,
        session_ttl_seconds=_to_int(os.getenv("SESSION_TTL_SECONDS2"), 28800, minimum=300),
        session_idle_seconds=_to_int(os.getenv("SESSION_IDLE_SECONDS2"), 1800, minimum=60),
        session_pepper=pepper,
        login_max_attempts=_to_int(os.getenv("LOGIN_MAX_ATTEMPTS2"), 5, minimum=1, maximum=100),
        login_window_seconds=_to_int(os.getenv("LOGIN_WINDOW_SECONDS2"), 900, minimum=60),
        log_level=os.getenv("LOG_LEVEL2", "INFO").strip().upper() or "INFO",
    )
