"""Autenticacion: almacen de sesiones y servicio de login.

Separacion de responsabilidades:

* :mod:`users` — el modelo de usuario, su repositorio y las reglas del cargo.
* :class:`SessionStore` — emite y valida tokens de sesion opacos.
* :class:`AuthService` — orquesta el login, el limitador y el re-hash.

El cliente nunca recibe ``password_hash`` ni la cadena de conexion.

Nota: el usuario y su repositorio viven en :mod:`users`, no aqui. Este modulo
responde "¿es quien dice ser?"; aquel responde "¿que es y que puede hacer?".
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from config import Settings
from db import Database
from security import (
    RateLimiter,
    client_key,
    constant_time_token_equals,
    generate_session_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_email,
    spend_verification_time,
    validate_password,
    verify_password,
)
# Se reexportan para no romper a quien ya importaba desde aqui.
from users import User, UserRepository  # noqa: F401

logger = logging.getLogger(__name__)

# El usuario y su repositorio viven en `users.py`; aquí sólo se usan.


@dataclass
class Session:
    user: User
    created_at: float
    last_seen_at: float
    origin: str = ""
    # UNES con la que la persona entró. Se digita en el login y **no** se guarda
    # en `Usuarios`: vive sólo mientras dure la sesión. Queda vacía para Talento
    # Humano, que entra sin UNES y ve la plantilla completa.
    unes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, ttl_seconds: int, idle_seconds: int, now: float | None = None) -> bool:
        moment = now if now is not None else time.monotonic()
        return (moment - self.created_at) > ttl_seconds or (moment - self.last_seen_at) > idle_seconds


@dataclass(frozen=True)
class SesionActiva:
    """Lo que se recupera de una sesión válida: quién es y con qué UNES entró."""

    user: User
    unes: str = ""


class SessionStore:
    """Sesiones en memoria indexadas por el digest del token.

    En la base no se guarda nada: el token en claro solo existe en el cliente
    y en memoria del proceso queda unicamente su SHA-256 con peper. El costo de
    esta decision (las sesiones se pierden al reiniciar y no se comparten entre
    workers) esta documentado en SECURITY-NOTES.md.
    """

    MAX_SESSIONS = 5_000

    def __init__(self, settings: Settings) -> None:
        self._ttl = settings.session_ttl_seconds
        self._idle = settings.session_idle_seconds
        self._pepper = settings.session_pepper
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, user: User, origin: str, unes: str = "") -> str:
        token = generate_session_token()
        digest = hash_session_token(token, self._pepper)
        now = time.monotonic()
        with self._lock:
            if len(self._sessions) >= self.MAX_SESSIONS:
                self._prune(now)
                if len(self._sessions) >= self.MAX_SESSIONS:
                    # Techo duro: se descarta la sesion mas antigua en lugar de
                    # crecer sin limite en memoria.
                    oldest = min(self._sessions, key=lambda k: self._sessions[k].last_seen_at)
                    del self._sessions[oldest]
            self._sessions[digest] = Session(
                user=user, created_at=now, last_seen_at=now, origin=origin, unes=unes
            )
        return token

    def resolve(self, token: str) -> SesionActiva | None:
        """Valida el token y renueva su marca de actividad."""
        if not token:
            return None
        digest = hash_session_token(token, self._pepper)
        now = time.monotonic()
        with self._lock:
            # Se recorre el indice con comparacion en tiempo constante: el
            # digest no se busca por igualdad directa para no filtrar por
            # diferencia de tiempo si el diccionario cambiara de estructura.
            session = None
            for stored_digest, candidate in self._sessions.items():
                if constant_time_token_equals(stored_digest, digest):
                    session = candidate
                    break
            if session is None:
                return None
            if session.is_expired(self._ttl, self._idle, now):
                self._sessions.pop(digest, None)
                return None
            session.last_seen_at = now
            return SesionActiva(user=session.user, unes=session.unes)

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        digest = hash_session_token(token, self._pepper)
        with self._lock:
            return self._sessions.pop(digest, None) is not None

    def revoke_all_for_user(self, user_id: int) -> int:
        with self._lock:
            targets = [d for d, s in self._sessions.items() if s.user.id == user_id]
            for digest in targets:
                del self._sessions[digest]
            return len(targets)

    def _prune(self, now: float) -> None:
        for digest in [d for d, s in self._sessions.items() if s.is_expired(self._ttl, self._idle, now)]:
            del self._sessions[digest]

    def active_count(self) -> int:
        with self._lock:
            self._prune(time.monotonic())
            return len(self._sessions)


@dataclass
class LoginOutcome:
    # ok | invalid | rate_limited | unes_required
    #
    # `unes_required` es un caso propio: las credenciales eran correctas pero la
    # cuenta **no** es de Talento Humano y no se digitó la UNES. No se crea
    # sesión y el navegador vuelve a pedir ese campo.
    status: str
    token: str | None = None
    user: User | None = None
    retry_after: int = 0
    rehashed: bool = False
    unes: str = ""


class AuthService:
    """Reglas de autenticacion en un solo lugar."""

    def __init__(self, settings: Settings, database: Database) -> None:
        self._settings = settings
        self._repository = UserRepository(database)
        self._sessions = SessionStore(settings)
        self._limiter = RateLimiter(
            max_events=settings.login_max_attempts,
            window_seconds=settings.login_window_seconds,
        )

    @property
    def sessions(self) -> SessionStore:
        return self._sessions

    @property
    def repository(self) -> UserRepository:
        return self._repository

    def login(
        self, raw_email: object, raw_password: object, origin: str, unes: str = ""
    ) -> LoginOutcome:
        """Intenta iniciar sesion. Lanza ``ValidationError`` si la entrada es invalida.

        La UNES es opcional **sólo para Talento Humano**: su tablero es la
        plantilla completa de la empresa y no necesita una unidad. Para el resto
        de cargos es obligatoria, porque su listado se filtra por ella. Cuál de
        las dos cosas aplica se decide con el cargo que está en la base, no con
        nada que mande el navegador.
        """
        email = normalize_email(raw_email)
        password = validate_password(raw_password)

        key = client_key(origin, email)
        allowed, retry_after = self._limiter.check(key)
        if not allowed:
            logger.warning("Login bloqueado por límite de intentos para un correo corporativo.")
            return LoginOutcome(status="rate_limited", retry_after=retry_after)

        record = self._repository.find_by_email(email)
        if record is None:
            # Mismo trabajo criptografico que un login real: la respuesta no
            # puede delatar si el correo existe.
            spend_verification_time(password)
            return LoginOutcome(status="invalid")

        user, stored_hash = record
        if not verify_password(stored_hash, password):
            return LoginOutcome(status="invalid")

        if not user.activo:
            # Cuenta desactivada. Se responde "invalid" y no un mensaje propio:
            # decir "tu cuenta está desactivada" confirmaría que el correo existe
            # y además daría a entender que con otra contraseña sí entraría.
            # Quien la desactivó sabe por qué; la persona pregunta a Talento
            # Humano, que es el canal correcto.
            logger.info("Inicio de sesión rechazado: la cuenta está desactivada.")
            return LoginOutcome(status="invalid")

        if not unes and not user.es_talento_humano:
            # Credenciales correctas, pero el listado de esta persona se filtra
            # por UNES y no la digitó. No se crea sesión: la interfaz vuelve a
            # pedir el campo. Se reinicia el limitador porque no hubo un intento
            # de adivinar la contraseña.
            self._limiter.reset(key)
            return LoginOutcome(status="unes_required", user=user)

        rehashed = False
        if needs_rehash(stored_hash):
            # Valor heredado (texto plano o metodo viejo): se reemplaza en el
            # mismo inicio de sesion correcto. Si la escritura falla, el login
            # sigue siendo valido y solo se registra el problema.
            try:
                self._repository.actualizar_password_hash(user.id, hash_password(password))
                rehashed = True
            except Exception:  # noqa: BLE001
                logger.exception(
                    "No se pudo actualizar el hash de la contraseña de un usuario."
                )

        self._limiter.reset(key)
        token = self._sessions.create(user, origin, unes)
        return LoginOutcome(status="ok", token=token, user=user, rehashed=rehashed, unes=unes)

    def authenticate(self, token: str) -> SesionActiva | None:
        """Valida el token y **comprueba en la base que la cuenta siga activa**.

        El token vive en memoria del proceso y no sabe nada de cambios en la
        base. Si sólo se resolviera la sesión, desactivar a alguien no tendría
        efecto hasta que caducara su token (hasta 8 horas). Esta consulta hace
        que desactivar surta efecto en la siguiente petición, que es lo que se
        espera al usar ese botón.

        Cuesta una consulta por petición autenticada. Es el precio de que el
        control sea inmediato; si algún día pesa, la alternativa es cachear la
        comprobación unos segundos, nunca eliminarla.
        """
        sesion = self._sessions.resolve(token)
        if sesion is None:
            return None

        fresco = self._repository.find_by_id(sesion.user.id)
        if fresco is None or not fresco.activo:
            # Se revoca la sesión: la cuenta se desactivó o se eliminó.
            self._sessions.revoke(token)
            return None

        # El cargo también se refresca: si cambió, los permisos cambian con él
        # sin obligar a la persona a volver a entrar. La UNES se conserva: es la
        # que se digitó al entrar y no vive en la base.
        return SesionActiva(user=fresco, unes=sesion.unes)

    def logout(self, token: str) -> bool:
        return self._sessions.revoke(token)

    def revocar_sesiones(self, user_id: int) -> int:
        """Cierra todas las sesiones abiertas de un usuario.

        Se usa al desactivarlo o eliminarlo: dejar el token vivo contradiría la
        intención de la acción.
        """
        return self._sessions.revoke_all_for_user(user_id)

    def issue_password_hash(self, password: str) -> str:
        """Utilidad para crear usuarios con hash (no se expone por HTTP)."""
        return hash_password(password)

    def random_password(self, length: int = 20) -> str:
        """Genera una contrasena temporal (utilidad de administracion)."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
        return "".join(secrets.choice(alphabet) for _ in range(length))
