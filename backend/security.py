"""Primitivas de seguridad compartidas: validacion, hash y limitador.

Este modulo no conoce Flask ni la base de datos, de modo que su logica pueda
probarse de forma aislada (ver SECURITY-NOTES.md, reglas de construccion).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass

from werkzeug.security import check_password_hash, generate_password_hash

# --------------------------------------------------------------------------
# Validacion de entrada
# --------------------------------------------------------------------------

# Un correo razonable: sin espacios, un solo '@', dominio con etiquetas.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

EMAIL_MAX_LENGTH = 150  # coincide con Usuarios.correo VARCHAR(150)
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class ValidationError(ValueError):
    """Entrada rechazada. ``code`` es estable para que el cliente lo mapee."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_email(raw: object) -> str:
    """Normaliza y valida el correo. Nunca devuelve un valor sin validar."""
    if not isinstance(raw, str):
        raise ValidationError("EMAIL_INVALID", "Escribe tu correo corporativo.")
    email = raw.strip().lower()
    if not email or len(email) > EMAIL_MAX_LENGTH or not _EMAIL_RE.match(email):
        raise ValidationError("EMAIL_INVALID", "Escribe tu correo corporativo.")
    return email


def validate_password(raw: object) -> str:
    """Valida la contrasena recibida.

    Reglas deliberadas: se rechazan los extremos con espacios (casi siempre un
    error de tipeo o de copiado) y cualquier caracter de control, pero no se
    impone un alfabeto minimo: la contrasena ya existe en la base y forzar
    reglas aqui solo romperia inicios de sesion legitimos.
    """
    if not isinstance(raw, str):
        raise ValidationError("PASSWORD_INVALID", "Escribe tu contraseña.")
    if raw != raw.strip():
        raise ValidationError(
            "PASSWORD_WHITESPACE",
            "La contraseña empieza o termina con un espacio. Revisa que no se haya colado al pegarla.",
        )
    if len(raw) < PASSWORD_MIN_LENGTH:
        raise ValidationError("PASSWORD_INVALID", "Escribe tu contraseña.")
    if len(raw) > PASSWORD_MAX_LENGTH:
        raise ValidationError(
            "PASSWORD_TOO_LONG",
            f"La contraseña supera {PASSWORD_MAX_LENGTH} caracteres.",
        )
    if _CONTROL_CHARS_RE.search(raw):
        raise ValidationError("PASSWORD_INVALID", "Escribe tu contraseña.")
    return raw


def is_ascii_identifier(value: str) -> bool:
    return bool(value) and value.isascii()


# --------------------------------------------------------------------------
# Hash de contrasenas
# --------------------------------------------------------------------------

# Metodo de Werkzeug. scrypt es el mas costoso de los que trae Werkzeug sin
# dependencias externas, que es lo que se quiere para hashes almacenados.
HASH_METHOD = "scrypt"
HASH_PREFIXES = ("scrypt:", "pbkdf2:", "argon2")
# Ancho de Usuarios.password_hash (VARCHAR(255)); el re-hash debe caber.
HASH_COLUMN_MAX_LENGTH = 255


def hash_password(password: str) -> str:
    digest = generate_password_hash(password, method=HASH_METHOD)
    if len(digest) > HASH_COLUMN_MAX_LENGTH:
        raise RuntimeError(
            f"El hash generado ({len(digest)} caracteres) no cabe en "
            f"Usuarios.password_hash ({HASH_COLUMN_MAX_LENGTH})."
        )
    return digest


def looks_hashed(stored: str) -> bool:
    return stored.startswith(HASH_PREFIXES)


def _constant_time_equals(left: str, right: str) -> bool:
    # Se comparan bytes UTF-8 en tiempo constante. Los valores vienen de la
    # base (trusted) y del formulario (untrusted) pero nunca se interpolan.
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def verify_password(stored: str, candidate: str) -> bool:
    """Verifica ``candidate`` contra el valor almacenado.

    Acepta las dos generaciones de datos que existen en la tabla:

    * ``scrypt:``/``pbkdf2:`` — hash de Werkzeug, ruta normal.
    * cualquier otra cosa — valor heredado en texto plano. Se compara en
      tiempo constante y el llamador lo re-hashea en el mismo inicio de sesion
      correcto. Nunca se escribe de vuelta un valor en claro.
    """
    if not stored:
        return False
    if looks_hashed(stored):
        try:
            return check_password_hash(stored, candidate)
        except (ValueError, TypeError):
            # Hash con formato corrupto: se trata como credencial invalida en
            # lugar de propagar un error que revele el contenido de la fila.
            return False
    return _constant_time_equals(stored, candidate)


def needs_rehash(stored: str) -> bool:
    """True cuando el valor almacenado no cumple el estandar actual."""
    return not stored.startswith(f"{HASH_METHOD}:")


# Hash de descarte para igualar el costo de verificacion cuando el correo no
# existe. Se calcula una sola vez al importar el modulo.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(24))


def spend_verification_time(candidate: str) -> None:
    """Gasta el mismo trabajo criptografico que un login real.

    Sin esto, un correo inexistente responde en microsegundos y uno existente
    en decenas de milisegundos: la diferencia enumera las cuentas validas
    aunque el mensaje de error sea identico.
    """
    verify_password(_DUMMY_HASH, candidate)


# --------------------------------------------------------------------------
# Tokens de sesion
# --------------------------------------------------------------------------


def generate_session_token() -> str:
    """Token opaco de 256 bits. Es lo unico que viaja al cliente."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, pepper: str) -> str:
    """SHA-256 del token con peper.

    En memoria solo se guarda este digest: un volcado de memoria del proceso no
    entrega tokens utilizables, y una comparacion filtrada tampoco.
    """
    return hashlib.sha256(f"{pepper}{token}".encode("utf-8")).hexdigest()


def constant_time_token_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


# --------------------------------------------------------------------------
# Limitador de intentos
# --------------------------------------------------------------------------


@dataclass
class _Bucket:
    attempts: list[float]


class RateLimiter:
    """Limitador de ventana deslizante en memoria, seguro entre hilos.

    Se usa, entre otras cosas, para frenar la fuerza bruta sobre el login. Es
    por proceso: con varios workers hay que moverlo a un almacen compartido
    (ver SECURITY-NOTES.md, limitaciones conocidas).
    """

    def __init__(self, max_events: int, window_seconds: int, max_keys: int = 20_000) -> None:
        self._max_events = max_events
        self._window = window_seconds
        self._max_keys = max_keys
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        for key in [k for k, bucket in self._buckets.items() if not bucket.attempts or bucket.attempts[-1] < cutoff]:
            del self._buckets[key]

    def check(self, key: str) -> tuple[bool, int]:
        """Devuelve ``(permitido, segundos_para_reintentar)`` y registra el intento."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    self._prune(now)
                    if len(self._buckets) >= self._max_keys:
                        # Bajo presion no se aceptan claves nuevas: se prefiere
                        # negar el intento antes que crecer sin limite.
                        return False, self._window
                bucket = self._buckets[key] = _Bucket(attempts=[])
            cutoff = now - self._window
            bucket.attempts = [t for t in bucket.attempts if t >= cutoff]
            if len(bucket.attempts) >= self._max_events:
                retry_after = int(self._window - (now - bucket.attempts[0])) + 1
                return False, max(1, retry_after)
            bucket.attempts.append(now)
            return True, 0

    def peek(self, key: str) -> bool:
        """Solo consulta, sin registrar intento."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return True
            cutoff = now - self._window
            return len([t for t in bucket.attempts if t >= cutoff]) < self._max_events

    def reset(self, key: str) -> None:
        """Limpia el contador tras un inicio de sesion correcto."""
        with self._lock:
            self._buckets.pop(key, None)


def client_key(remote_addr: str | None, email: str) -> str:
    """Clave del limitador: origen + correo, para no bloquear a toda una IP."""
    return f"{(remote_addr or 'unknown')[:45]}|{email}"
