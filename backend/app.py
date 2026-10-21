"""API HTTP de autenticacion y datos para el frontend (Flask).

Arranque en desarrollo:

    cd backend
    python app.py

Endpoints: ver ``/api`` o el README. Reglas de construccion aplicadas aqui:

* toda escritura/lectura de SQL Server pasa por :mod:`db` con parametros;
* toda respuesta de error es generica y con ``code`` estable, sin detalles del
  motor, del esquema ni de si una cuenta existe;
* CORS con lista exacta de origenes y sin comodin;
* cabeceras de seguridad en todas las respuestas, incluidas las de error.
"""

from __future__ import annotations

import io
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

import pyodbc
from flask import Flask, Response, g, jsonify, request, send_file
from flask_cors import CORS

from assignments import AssignmentService
from auth import AuthService
from config import ConfigError, Settings, load_settings
from dashboard import DashboardService
from db import Database, DatabaseUnavailable
from employees import EmployeeDirectory, normalizar_unes, validar_unes_login
from filial import filtrar_por_filial
from notifications import NotificationService
from reports import generar_pdf_reporte_vacaciones, generar_plano_unoee
from security import ValidationError, hash_password, normalize_email, validate_password
from users import (
    CARGO_TALENTO_HUMANO,
    User,
    UserRepository,
    a_booleano,
    normalizar_cargo,
    validar_cargo,
    validar_nombre,
    validar_usuario_nuevo,
)

F = TypeVar("F", bound=Callable[..., Any])

API_VERSION = "2.0.0"
BEARER_PREFIX = "bearer "
MAX_CONTENT_LENGTH = 64 * 1024  # 64 KB: un login o una asignación no necesitan más

# Tipo MIME del libro de Excel que devuelve el plano UNOEE.
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Cabeceras de seguridad. La CSP del backend es irrelevante para el navegador
# (sirve JSON), pero se deja explícita para que un proxy mal configurado no
# herede una política laxa si algún día sirve HTML.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Cache-Control": "no-store",
}

logger = logging.getLogger("gestion_vacaciones.api")


# --------------------------------------------------------------------------
# Respuestas
# --------------------------------------------------------------------------


def ok(payload: dict[str, Any] | None = None, status: int = 200) -> tuple[Response, int]:
    body: dict[str, Any] = {"ok": True}
    if payload:
        body.update(payload)
    return jsonify(body), status


def fail(
    message: str,
    *,
    code: str,
    status: int,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    """Error uniforme.

    ``message`` está escrito para la persona que usa la herramienta y ``code``
    para el programa. Nunca se incluye la excepción original.
    """
    body: dict[str, Any] = {"ok": False, "code": code, "message": message}
    if details:
        body["details"] = details
    return jsonify(body), status


# --------------------------------------------------------------------------
# Autenticacion
# --------------------------------------------------------------------------


def extract_bearer_token() -> str:
    """Lee el token del encabezado ``Authorization: Bearer <token>``.

    Se usa un encabezado y no una cookie a proposito: sin cookies no hay CSRF
    posible, y el token no viaja solo porque el navegador decida adjuntarlo.
    """
    header = request.headers.get("Authorization", "")
    if not header:
        return ""
    if header[: len(BEARER_PREFIX)].lower() != BEARER_PREFIX:
        return ""
    return header[len(BEARER_PREFIX) :].strip()


def require_auth(view: F) -> F:
    """Exige una sesion valida y deja el usuario y su UNES en ``flask.g``.

    Se guarda la sesión completa (``g.current_session``) y no sólo el usuario,
    porque la UNES con la que se entró no vive en la base: es un dato de la
    sesión y hay endpoints que la necesitan para filtrar.
    """

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        token = extract_bearer_token()
        if not token:
            return fail(
                "Tu sesión no está activa. Inicia sesión para continuar.",
                code="SESSION_REQUIRED",
                status=401,
            )
        sesion = current_service().authenticate(token)
        if sesion is None:
            return fail(
                "Tu sesión expiró. Vuelve a iniciar sesión.",
                code="SESSION_EXPIRED",
                status=401,
            )
        g.current_session = sesion
        g.current_user = sesion.user
        g.session_token = token
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def require_talento_humano(view: F) -> F:
    """Exige que el usuario autenticado sea de Talento Humano.

    La decisión se toma con el ``cargo`` que está **en la base**, leído en cada
    petición a través de la sesión. No se acepta un cargo enviado por el
    navegador, y ocultar la opción en la interfaz no es el control: esto sí lo
    es. Sin este decorador, cualquiera con una sesión válida podría llamar a la
    API directamente.
    """

    @require_auth
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user().es_talento_humano:
            logger.warning(
                "Acceso denegado a una ruta de administración para el cargo %r.",
                current_user().cargo,
            )
            return fail(
                "Esta opción es exclusiva de Talento Humano.",
                code="FORBIDDEN_ROLE",
                status=403,
            )
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def current_user() -> User:
    return g.current_user


def current_unes() -> str:
    """UNES con la que se inició sesión. Cadena vacía si no se digitó."""
    return getattr(g.current_session, "unes", "") or ""


# --------------------------------------------------------------------------
# Aplicacion
# --------------------------------------------------------------------------


def current_service() -> AuthService:
    return g.services.auth  # type: ignore[no-any-return]


def servicios() -> Any:
    return g.services


def _json_body() -> dict[str, Any]:
    """Cuerpo JSON con validacion estricta de tipo y tamano."""
    if not request.is_json:
        raise ValidationError(
            "CONTENT_TYPE",
            "La petición debe enviarse como JSON.",
        )
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("BODY_INVALID", "La petición no tiene el formato esperado.")
    return payload


def _entero_de_ruta(valor: Any, nombre: str) -> int:
    """Convierte un identificador de la URL y rechaza lo que no sea entero."""
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValidationError("ID_INVALIDO", f"El {nombre} de la ruta no es válido.") from exc
    if numero <= 0:
        raise ValidationError("ID_INVALIDO", f"El {nombre} de la ruta no es válido.")
    return numero


def create_app(settings: Settings | None = None) -> Flask:
    if settings is None:
        settings = load_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = Flask(__name__)
    app.config.update(
        DEBUG=False,
        TESTING=False,
        PROPAGATE_EXCEPTIONS=False,
        MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
        # Sin sesiones de Flask ni cookies: el token va en el encabezado.
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=True,
        JSON_SORT_KEYS=False,
    )

    database = Database(settings.database)
    auth_service = AuthService(settings, database)

    # Segunda conexión, opcional: la vista corporativa de colaboradores. Si no
    # está configurada, `EmployeeDirectory` queda no disponible y los endpoints
    # que dependen de ella avisan en lugar de tumbar el servicio.
    directorio_db = Database(settings.directorio) if settings.directorio else None

    class _Services:
        db = database
        users = UserRepository(database)
        auth = auth_service
        assignments = AssignmentService(database)
        notifications = NotificationService(database)
        dashboard = DashboardService(database)
        employees = EmployeeDirectory(directorio_db)
        config = settings

    services = _Services()

    # Solo los origenes exactos enumerados en la configuracion. Sin comodin:
    # '*' con credenciales permitiria a cualquier sitio leer la sesion.
    CORS(
        app,
        resources={r"/api/*": {"origins": list(settings.cors_origins)}},
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        # El navegador necesita leer el nombre del archivo (y su extensión) que
        # propone el servidor al descargar la planilla o el plano.
        expose_headers=["Content-Disposition"],
        supports_credentials=False,
        max_age=600,
        vary_header=True,
    )

    @app.before_request
    def _attach_services() -> None:
        g.services = services

    @app.after_request
    def _apply_security_headers(response: Response) -> Response:
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    # -- manejadores de error ----------------------------------------------

    @app.errorhandler(ValidationError)
    def _handle_validation(error: ValidationError):
        return fail(error.message, code=error.code, status=400)

    @app.errorhandler(DatabaseUnavailable)
    def _handle_database(error: DatabaseUnavailable):
        logger.error("Petición no atendida por fallo de base de datos.")
        return fail(
            "No pudimos consultar la información en este momento. Intenta de nuevo en unos segundos.",
            code="DATABASE_UNAVAILABLE",
            status=503,
        )

    @app.errorhandler(pyodbc.IntegrityError)
    def _handle_integrity(_error):
        """Violación de una restricción de la base.

        El caso frecuente es el correo duplicado (``correo`` tiene índice único
        en ``Usuarios``). Se responde 409 con un mensaje que la persona entiende
        en lugar de un 500 genérico, y sin repetir el texto del motor, que
        nombra la restricción y el esquema.
        """
        logger.warning("Restricción de integridad violada en %s.", request.path)
        return fail(
            "Ese dato ya existe o no cumple una restricción de la base. "
            "Revisa el correo: no puede repetirse.",
            code="CONFLICTO_DE_DATOS",
            status=409,
        )

    @app.errorhandler(404)
    def _handle_404(_error):
        return fail("La ruta solicitada no existe.", code="NOT_FOUND", status=404)

    @app.errorhandler(405)
    def _handle_405(_error):
        return fail(
            "El método HTTP no está permitido para esta ruta.",
            code="METHOD_NOT_ALLOWED",
            status=405,
        )

    @app.errorhandler(413)
    def _handle_413(_error):
        return fail("La petición es demasiado grande.", code="PAYLOAD_TOO_LARGE", status=413)

    @app.errorhandler(429)
    def _handle_429(_error):
        return fail(
            "Demasiadas solicitudes. Espera un momento antes de reintentar.",
            code="RATE_LIMITED",
            status=429,
        )

    @app.errorhandler(Exception)
    def _handle_unexpected(error: Exception):
        # El detalle va al log del servidor; al cliente solo un mensaje neutro.
        logger.exception("Error no controlado atendiendo %s", request.path)
        return fail(
            "Ocurrió un error inesperado. Intenta de nuevo o contacta a Soporte.",
            code="INTERNAL_ERROR",
            status=500,
        )

    # -- rutas --------------------------------------------------------------
    
    @app.get("/api")
    def api_index():
        return ok(
            {
                "service": "Gestión de Vacaciones G&J",
                "version": API_VERSION,
                "endpoints": [
                    "POST   /api/auth/login",
                    "POST   /api/auth/logout",
                    "GET    /api/auth/session",
                    "GET    /api/health",
                    "GET    /api/resumen",
                    "GET    /api/asignaciones",
                    "POST   /api/asignaciones",
                    "PUT    /api/asignaciones/{id}/periodos",
                    "POST   /api/asignaciones/{id}/decision",
                    "GET    /api/reportes/planilla",
                    "GET    /api/reportes/plano-unoee",
                    "GET    /api/notificaciones",
                    "GET    /api/usuarios",
                    "POST   /api/usuarios",
                    "PUT    /api/usuarios/{id}",
                    "DELETE /api/usuarios/{id}",
                ],
            }
        )

    @app.get("/api/health")
    def health():
        """Diagnóstico para desarrollo. No expone servidor, base ni usuario."""
        healthy, reason = database.health()
        if not healthy:
            return fail(
                "El servicio no puede consultar la base de datos.",
                code="DATABASE_UNAVAILABLE",
                status=503,
                details={"db": reason},
            )
        # El estado del directorio corporativo no es un fallo del servicio: la
        # aplicación funciona sin él, sólo sin el listado de colaboradores.
        directorio_ok, directorio_motivo = servicios().employees.health()
        return ok(
            {
                "db": "ok",
                "directorio": directorio_motivo if directorio_ok else f"no disponible ({directorio_motivo})",
                "version": API_VERSION,
                "sessions": auth_service.sessions.active_count(),
            }
        )

    @app.post("/api/auth/login")
    def login():
        payload = _json_body()
        # La UNES es opcional: Talento Humano entra sólo con correo y
        # contraseña. Si viene escrita, se valida antes de gastar un intento del
        # limitador —un formato equivocado no es un intento de adivinar la
        # contraseña—; si viene vacía, quien decide si hacía falta es el servicio,
        # que ya conoce el cargo de la cuenta.
        unes_cruda = payload.get("unes")
        unes = (
            validar_unes_login(unes_cruda)
            if unes_cruda is not None and str(unes_cruda).strip()
            else ""
        )

        outcome = auth_service.login(
            payload.get("correo"),
            payload.get("password"),
            origin=request.remote_addr or "",
            unes=unes,
        )

        if outcome.status == "rate_limited":
            response, status = fail(
                "Demasiados intentos fallidos. Por seguridad, espera unos minutos antes de volver a intentar.",
                code="TOO_MANY_ATTEMPTS",
                status=429,
                details={"retry_after_seconds": outcome.retry_after},
            )
            response.headers["Retry-After"] = str(outcome.retry_after)
            return response, status

        if outcome.status == "unes_required":
            # Las credenciales eran correctas, pero el cargo no es de Talento
            # Humano y su listado se filtra por UNES. No es un fallo de
            # credenciales y el mensaje lo dice.
            return fail(
                "Escribe la UNES con la que vas a trabajar.",
                code="UNES_REQUERIDA",
                status=400,
            )

        if outcome.status != "ok" or outcome.user is None or outcome.token is None:
            # Un solo mensaje para correo inexistente, contraseña incorrecta o
            # cuenta sin acceso: la respuesta no debe permitir enumerar cuentas.
            return fail(
                "El correo o la contraseña no son correctos.",
                code="INVALID_CREDENTIALS",
                status=401,
            )

        return ok(
            {
                "token": outcome.token,
                "token_type": "Bearer",
                "expires_in": settings.session_ttl_seconds,
                "usuario": {**outcome.user.to_public_dict(), "unes": outcome.unes},
            }
        )

    @app.post("/api/auth/logout")
    @require_auth
    def logout():
        token = getattr(g, "session_token", "")
        revoked = auth_service.logout(token)
        return ok({"revoked": revoked})

    @app.get("/api/auth/session")
    @require_auth
    def session_info():
        return ok({"usuario": {**current_user().to_public_dict(), "unes": current_unes()}})

    @app.get("/api/auth/me")
    @require_auth
    def me():
        return ok({"usuario": {**current_user().to_public_dict(), "unes": current_unes()}})

    # -- administración de usuarios (sólo Talento Humano) -------------------

    @app.get("/api/usuarios")
    @require_talento_humano
    def listar_usuarios():
        usuarios = servicios().users.listar()
        return ok({"usuarios": usuarios, "total": len(usuarios)})

    @app.post("/api/usuarios")
    @require_talento_humano
    def crear_usuario():
        payload = _json_body()
        datos = validar_usuario_nuevo(payload)

        repositorio: UserRepository = servicios().users
        if repositorio.correo_en_uso(datos["correo"]):
            return fail(
                "Ya existe un usuario con ese correo.",
                code="CORREO_DUPLICADO",
                status=409,
            )

        nuevo_id = repositorio.crear(
            nombre=datos["nombre"],
            correo=datos["correo"],
            password_hash=hash_password(datos["password"]),
            cargo=datos["cargo"],
            activo=datos["activo"],
        )
        creado = repositorio.find_by_id(nuevo_id)
        return ok({"usuario": creado.to_public_dict() if creado else None}, 201)

    @app.put("/api/usuarios/<int:user_id>")
    @require_talento_humano
    def actualizar_usuario(user_id: int):
        payload = _json_body()
        repositorio: UserRepository = servicios().users
        actual = repositorio.find_by_id(user_id)
        if actual is None:
            return fail("El usuario no existe.", code="USUARIO_NO_EXISTE", status=404)

        # Se valida sólo lo que llega: así el mismo endpoint sirve para editar el
        # nombre, el cargo o la contraseña por separado.
        nombre = validar_nombre(payload.get("nombre", actual.nombre))
        cargo = validar_cargo(payload.get("cargo", actual.cargo))
        correo = normalize_email(payload.get("correo", actual.correo))

        if repositorio.correo_en_uso(correo, excluir_id=user_id):
            return fail(
                "Otro usuario ya tiene ese correo.",
                code="CORREO_DUPLICADO",
                status=409,
            )

        # Evita que Talento Humano se deje sin acceso por error. Se cuentan los
        # que están **activos**: degradar a un Talento Humano ya desactivado no
        # deja el sistema sin administración.
        if actual.es_talento_humano and normalizar_cargo(cargo) != CARGO_TALENTO_HUMANO:
            if repositorio.contar_talento_humano_activo(excluir_id=user_id) == 0:
                return fail(
                    "Debe quedar al menos un usuario de Talento Humano activo con acceso.",
                    code="ULTIMO_TALENTO_HUMANO",
                    status=409,
                )

        repositorio.actualizar(user_id, nombre=nombre, correo=correo, cargo=cargo)

        if payload.get("password"):
            repositorio.actualizar_password_hash(
                user_id, hash_password(validate_password(payload.get("password")))
            )

        actualizado = repositorio.find_by_id(user_id)
        return ok({"usuario": actualizado.to_public_dict() if actualizado else None})

    @app.patch("/api/usuarios/<int:user_id>/activo")
    @require_talento_humano
    def activar_usuario(user_id: int):
        """Activa o desactiva una cuenta.

        Desactivar surte efecto de inmediato: se cierran sus sesiones abiertas y
        `authenticate` vuelve a comprobar el estado en la base en cada petición,
        así que el token deja de servir en el acto.
        """
        payload = _json_body()
        repositorio: UserRepository = servicios().users
        actual = repositorio.find_by_id(user_id)
        if actual is None:
            return fail("El usuario no existe.", code="USUARIO_NO_EXISTE", status=404)

        activo = a_booleano(payload.get("activo"), por_defecto=not actual.activo)

        if actual.id == current_user().id and not activo:
            return fail(
                "No puedes desactivar tu propio usuario.",
                code="NO_SE_PUEDE_DESACTIVAR_A_SI_MISMO",
                status=409,
            )

        # Sin esto se podría dejar el sistema sin nadie que administre.
        if (
            not activo
            and actual.es_talento_humano
            and repositorio.contar_talento_humano_activo(excluir_id=user_id) == 0
        ):
            return fail(
                "Debe quedar al menos un usuario de Talento Humano activo con acceso.",
                code="ULTIMO_TALENTO_HUMANO",
                status=409,
            )

        repositorio.actualizar_activo(user_id, activo)
        cerradas = 0
        if not activo:
            cerradas = auth_service.revocar_sesiones(user_id)

        actualizado = repositorio.find_by_id(user_id)
        return ok(
            {
                "usuario": actualizado.to_public_dict() if actualizado else None,
                "sesionesCerradas": cerradas,
            }
        )

    @app.delete("/api/usuarios/<int:user_id>")
    @require_talento_humano
    def eliminar_usuario(user_id: int):
        repositorio: UserRepository = servicios().users
        actual = repositorio.find_by_id(user_id)
        if actual is None:
            return fail("El usuario no existe.", code="USUARIO_NO_EXISTE", status=404)

        # Dos protecciones que evitan dejar el sistema sin administración o
        # cerrar la propia sesión sin querer.
        if actual.id == current_user().id:
            return fail(
                "No puedes eliminar tu propio usuario.",
                code="NO_SE_PUEDE_ELIMINAR_A_SI_MISMO",
                status=409,
            )
        if actual.es_talento_humano:
            if repositorio.contar_talento_humano_activo(excluir_id=user_id) == 0:
                return fail(
                    "Debe quedar al menos un usuario de Talento Humano activo con acceso.",
                    code="ULTIMO_TALENTO_HUMANO",
                    status=409,
                )

        repositorio.eliminar(user_id)
        # Se cierran sus sesiones abiertas: si no, el token seguiría sirviendo
        # hasta su caducidad natural.
        revocadas = auth_service.revocar_sesiones(user_id)
        return ok({"eliminado": True, "sesionesCerradas": revocadas})

    # -- asignaciones -------------------------------------------------------

    def _propietarios_por_correo() -> dict[str, int | None]:
        """Mapa ``correo (minúsculas) → id de usuario``.

        Es el puente entre la vista de colaboradores y ``dbo.Usuarios``: el
        correo es el único dato que ambos lados comparten. Se arma con una sola
        consulta y no con una por fila.
        """
        return {
            str(usuario["correo"]).strip().lower(): int(usuario["id"])
            for usuario in servicios().users.listar()
            if usuario.get("correo")
        }

    def _solo_filial(filas: list[dict[str, Any]], unes_objetivo: str) -> list[dict[str, Any]]:
        """Acota la lista a la filial del jefe cuando la UNES es 106.

        El jefe de filial entra con la UNES 106 y su **correo** (el de la sesión)
        identifica su equipo en ``data filial/filial.json``: sólo debe ver esas
        cédulas. Si el correo no figura en el archivo, no se filtra —se ve toda
        la UNES— para no dejar la pantalla en blanco.
        """
        return filtrar_por_filial(filas, current_user().correo, unes=unes_objetivo)

    def _filas_tablero(
        *,
        es_talento_humano: bool,
        unes_sesion: str,
        unes_solicitada: str = "",
        con_propietarios: bool = True,
    ) -> tuple[list[dict[str, Any]], str]:
        """Colaboradores con su asignación, aplicando la regla de acceso.

        Talento Humano recibe toda la plantilla; si además pidió una UNES
        concreta, sólo esa. Cualquier otro cargo recibe exclusivamente la UNES de
        su sesión: ``unes_solicitada`` se ignora para no ampliar lo que ve por la
        puerta del parámetro.

        Además, cuando la UNES es la de filial (106), se acota a las cédulas del
        equipo del jefe de filial que inició sesión (ver :mod:`filial`).

        Si la vista corporativa no responde, se degrada al listado local de
        asignaciones en lugar de dejar la pantalla en blanco. Devuelve
        ``(filas, origen)`` con ``origen`` en ``"vista"`` o ``"local"``.
        """
        directorio = servicios().employees
        unes_objetivo = unes_solicitada if es_talento_humano else unes_sesion
        ver_todo = es_talento_humano and not unes_objetivo

        if directorio.disponible and (ver_todo or unes_objetivo):
            try:
                colaboradores = (
                    directorio.listar_todos()
                    if ver_todo
                    else directorio.listar_por_unes(unes_objetivo)
                )
                filas = servicios().assignments.tablero_de_unes(
                    colaboradores,
                    propietarios=_propietarios_por_correo() if con_propietarios else None,
                    # Para Talento Humano sin UNES no se acota por unidad: ve
                    # también las asignaciones huérfanas de cualquier UNES.
                    unes="" if ver_todo else unes_objetivo,
                )
                return _solo_filial(filas, unes_objetivo), "vista"
            except DatabaseUnavailable:
                # El servidor corporativo no respondió. Se degrada al listado
                # local en lugar de dejar la pantalla en blanco.
                logger.warning("La vista de colaboradores no respondió; se usa el listado local.")

        return _solo_filial(servicios().assignments.listar(), unes_objetivo), "local"

    def _unes_para_reporte() -> str:
        """UNES que se aplica a un reporte, según el cargo de la sesión.

        Talento Humano puede pedir una UNES concreta con ``?unes=``; sin ella, el
        reporte cubre toda la plantilla. Para cualquier otro cargo el parámetro
        se ignora y manda la UNES de la sesión: el reporte es una regla de acceso
        y no puede ampliarse desde el navegador.
        """
        if current_user().es_talento_humano:
            return normalizar_unes(request.args.get("unes"))
        return current_unes()

    def _colaboradores_de_unes(unes: str) -> int:
        """Cuántos colaboradores tiene la UNES en la vista corporativa.

        ``dbo.Usuarios`` no guarda la UNES —es un dato de la sesión, no de la
        cuenta—, así que el total de colaboradores de una unidad sale del
        directorio. Si la vista no está configurada o no responde, devuelve 0: el
        resumen sigue siendo útil con las cifras de asignaciones, que salen de
        la base propia.
        """
        directorio = servicios().employees
        if not unes or not directorio.disponible:
            return 0
        try:
            return len(directorio.listar_por_unes(unes))
        except DatabaseUnavailable:
            logger.warning(
                "La vista de colaboradores no respondió; el total de la UNES queda en cero."
            )
            return 0

    def _enviar_archivo(contenido: bytes, nombre: str, mimetype: str):
        """Devuelve un archivo adjunto sin pasar por disco."""
        return send_file(
            io.BytesIO(contenido),
            mimetype=mimetype,
            as_attachment=True,
            download_name=nombre,
        )

    @app.get("/api/asignaciones")
    @require_auth
    def listar_asignaciones():
        """Tablero de colaboradores que le corresponde a la sesión.

        Si hay conexión con la vista corporativa, la tabla son **los
        colaboradores** con la asignación que tengan (o ninguna):

        * Talento Humano entra sin UNES y recibe **toda la plantilla de la
          empresa**.
        * Los demás cargos reciben sólo los de la UNES con la que entraron: el
          filtro es una regla de acceso y lo aplica el servidor en el ``WHERE``.

        Si la vista no responde, se devuelven sólo las asignaciones registradas:
        la pantalla sigue siendo útil aunque el servidor corporativo falle.
        """
        unes = current_unes()
        filas, origen = _filas_tablero(
            es_talento_humano=current_user().es_talento_humano,
            unes_sesion=unes,
        )
        return ok(
            {
                "asignaciones": filas,
                "total": len(filas),
                "origen": origen,
                "unes": unes,
            }
        )

    @app.get("/api/asignaciones/<int:assignment_id>")
    @require_auth
    def obtener_asignacion(assignment_id: int):
        asignacion = servicios().assignments.obtener(assignment_id)
        if asignacion is None:
            return fail("La asignación no existe.", code="ASIGNACION_NO_EXISTE", status=404)
        return ok({"asignacion": asignacion})

    @app.post("/api/asignaciones")
    @require_auth
    def crear_asignacion():
        payload = _json_body()
        _, asignacion = servicios().assignments.crear(payload, current_user())
        servicios().notifications.avisar_asignacion(asignacion, current_user())
        return ok({"asignacion": asignacion}, 201)

    @app.put("/api/asignaciones/<int:assignment_id>/periodos")
    @require_auth
    def guardar_periodos(assignment_id: int):
        payload = _json_body()
        asignacion = servicios().assignments.guardar_periodos(
            assignment_id, payload, current_user()
        )
        # Modificar fechas u observaciones genera el aviso, con el id de quien
        # lo hizo.
        servicios().notifications.avisar_asignacion(asignacion, current_user())
        return ok({"asignacion": asignacion})

    @app.post("/api/asignaciones/<int:assignment_id>/decision")
    @require_talento_humano
    def decidir_asignacion(assignment_id: int):
        """Aprobar o rechazar. Exclusivo de Talento Humano.

        El decorador es el control real: ocultar la opción en la interfaz no
        impide que alguien llame a la API directamente.
        """
        payload = _json_body()
        asignacion = servicios().assignments.registrar_decision(
            assignment_id, payload, current_user()
        )
        servicios().notifications.avisar_decision(asignacion, current_user())
        return ok({"asignacion": asignacion})

    # -- reportes descargables ----------------------------------------------

    @app.get("/api/reportes/planilla")
    @require_auth
    def exportar_reporte_pdf():
        """Planilla de vacaciones en PDF, con la plantilla institucional.

        La cubre cualquier sesión: quien entra con una UNES sólo obtiene la de su
        unidad; Talento Humano, la que pida o toda la plantilla.
        """
        unes_filtro = _unes_para_reporte()
        filas, _origen = _filas_tablero(
            es_talento_humano=current_user().es_talento_humano,
            unes_sesion=current_unes(),
            unes_solicitada=unes_filtro,
            con_propietarios=False,
        )

        # La descripción sólo tiene sentido cuando el reporte es de una UNES.
        desc_unes = ""
        if unes_filtro:
            desc_unes = next(
                (str(f.get("descUnes") or "") for f in filas if f.get("descUnes")), ""
            )

        pdf_bytes = generar_pdf_reporte_vacaciones(filas, unes_filtro or "", desc_unes)

        unes_part = unes_filtro or "todos"
        if not unes_part.lower().startswith("2-"):
            unes_part = f"2-{unes_part}"
        return _enviar_archivo(pdf_bytes, f"{unes_part}_vacaciones.pdf", "application/pdf")

    @app.get("/api/reportes/plano-unoee")
    @require_talento_humano
    def generar_plano():
        """Plano UNOEE en Excel sobre la plantilla oficial.

        El plano se arma **directamente desde las asignaciones registradas en la
        base** (``dbo.asignacion_vacaciones``, el equivalente en la V2 a
        ``inf_asignacion``), y no desde la vista corporativa. Lo que se descarga
        para importar tiene que ser exactamente lo grabado, aunque un colaborador
        ya no aparezca en la plantilla.

        Dos alcances:

        * **general** — sin ``?unes=``: todas las asignaciones.
        * **por UNES** — con ``?unes=``: sólo las de esa unidad. El filtro usa los
          tres últimos dígitos de la UNES (acepta ``106`` y ``2-106``), igual que
          el resto del sistema.

        Exclusivo de Talento Humano. El decorador es el control real: ocultar la
        opción en la interfaz no impide que alguien llame a la API directamente.
        """
        unes_filtro = _unes_para_reporte()
        filas = servicios().assignments.listar()

        if unes_filtro:
            sufijo = unes_filtro[-3:]
            filas = [
                fila
                for fila in filas
                if str(fila.get("unes") or "")[-3:] == sufijo
            ]

        try:
            xlsx_bytes = generar_plano_unoee(filas)
        except FileNotFoundError:
            logger.error("No se encontró la plantilla del plano UNOEE.")
            return fail(
                "La plantilla del plano no está disponible. Contacta a Soporte.",
                code="PLANTILLA_NO_DISPONIBLE",
                status=500,
            )

        nombre = (
            f"plano_vacaciones_unes_{unes_filtro}.xlsx"
            if unes_filtro
            else "plano_vacaciones_general.xlsx"
        )
        return _enviar_archivo(xlsx_bytes, nombre, XLSX_MIME)

    # -- notificaciones -----------------------------------------------------

    @app.get("/api/notificaciones")
    @require_auth
    def listar_notificaciones():
        """Bandeja de avisos.

        Los avisos de asignación, aprobación y rechazo son sólo para Talento
        Humano; para el resto de cargos la lista llega vacía. Lo decide el
        servicio con el cargo de la sesión, no la petición.
        """
        avisos = servicios().notifications.listar_para(current_user())
        return ok({"notificaciones": avisos, "total": len(avisos)})

    @app.get("/api/notificaciones/mias")
    @require_auth
    def listar_mis_notificaciones():
        """Avisos generados por la persona que consulta (``usuario_id``)."""
        avisos = servicios().notifications.listar_para_usuario(current_user().id)
        return ok({"notificaciones": avisos, "total": len(avisos)})

    # -- resumen ------------------------------------------------------------

    @app.get("/api/resumen")
    @require_auth
    def resumen():
        """Totales del resumen.

        Talento Humano ve la empresa completa. Cualquier otro cargo recibe sólo
        los de la UNES con la que entró: el alcance es una regla de acceso y lo
        aplica el servidor, no la interfaz.
        """
        if current_user().es_talento_humano:
            return ok(servicios().dashboard.resumen())

        unes = current_unes()
        datos = servicios().dashboard.resumen(unes=unes)
        # «Usuarios registrados» para una UNES es su plantilla de colaboradores.
        datos["totales"]["usuarios"] = _colaboradores_de_unes(unes)
        return ok(datos)

    return app


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as error:
        print(f"\n[configuración] {error}\n")
        return 2

    app = create_app(settings)
    logger.info(
        "API escuchando en http://%s:%s (base: %s)",
        settings.host,
        settings.port,
        settings.database.safe_target(),
    )
    # threaded=True: Flask atiende varias peticiones; el pool de conexiones y el
    # almacén de sesiones están protegidos con cerrojo.
    app.run(host=settings.host, port=settings.port, debug=False, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
