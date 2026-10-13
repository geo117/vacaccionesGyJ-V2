"""Prueba end-to-end del backend contra la base real.

    cd backend
    python test_backend.py

Cubre lo que puede fallar en silencio: credenciales, control de rol,
administración de usuarios, persistencia de los períodos, decisiones que generan
notificaciones y el resumen.

Deja la base con datos de prueba. Úsala contra una base de desarrollo.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta

from app import create_app
from config import load_settings
from db import Database
from security import hash_password, looks_hashed

PASSED: list[str] = []
FAILED: list[str] = []

# Contraseña de prueba que se deja a los usuarios de Talento Humano. Se fija una
# conocida porque los hashes de la base corresponden a contraseñas que no
# conocemos.
PASSWORD_TH = "Temporal1"
PASSWORD_OTRO = "Temporal9*"

# UNES de trabajo para la prueba. Existe en la vista corporativa (UNES SABANETA).
UNES_PRUEBA = "109"

TH_CARGO = "talento humano"
OTRO_CARGO = "gerente unes"


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name} {detail}".strip())
        print(f"  FAIL  {name} {detail}")


def main() -> int:
    settings = load_settings()
    app = create_app(settings)
    client = app.test_client()
    database = Database(settings.database)

    # ------------------------------------------------------------------
    # Preparación: un usuario de Talento Humano activo con contraseña conocida
    # y otro de cargo distinto para poder comprobar el control de rol.
    #
    # No se da por hecho que exista ninguno: si no hay, se crea uno. Así la
    # prueba no depende de que alguien haya dejado la base en cierto estado —y
    # tampoco se rompe si se cambia el cargo del usuario que estaba.
    # ------------------------------------------------------------------
    print("\n================ PREPARACIÓN ================")
    fila = database.query_one(
        "SELECT TOP 1 id, correo, nombre FROM dbo.Usuarios "
        "WHERE LOWER(cargo) = ? AND LOWER(ISNULL(activo, '')) IN ('si', 'sí', '1', 'true') "
        "ORDER BY id",
        (TH_CARGO,),
    )

    if fila is None:
        sufijo_th = uuid.uuid4().hex[:8]
        correo_th = f"prueba.th.{sufijo_th}@example.com"
        with database.cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO dbo.Usuarios (nombre, correo, password_hash, cargo, activo, fecha_creacion) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, 'si', GETDATE())",
                ("Talento Humano De Prueba", correo_th, hash_password(PASSWORD_TH), TH_CARGO),
            )
            th_id = int(cursor.fetchone()[0])
        th_correo = correo_th
        print(f"  No había Talento Humano activo: se creó id={th_id} correo={th_correo}")
    else:
        th_id, th_correo = int(fila[0]), str(fila[1])
        database.execute(
            "UPDATE dbo.Usuarios SET password_hash = ?, activo = 'si' WHERE id = ?",
            (hash_password(PASSWORD_TH), th_id),
        )
        print(f"  Talento Humano: id={th_id} correo={th_correo} (contraseña fijada para la prueba)")

    sufijo = uuid.uuid4().hex[:8]
    otro_correo = f"prueba.otro.{sufijo}@example.com"

    # ------------------------------------------------------------------
    print("\n================ LOGIN ================")
    # La UNES se digita al entrar y viaja en el cuerpo; es obligatoria.
    respuesta = client.post(
        "/api/auth/login", json={"correo": th_correo, "password": PASSWORD_TH}
    )
    check("el login exige la UNES", respuesta.status_code == 400, str(respuesta.status_code))
    check("código UNES_REQUERIDA", (respuesta.get_json() or {}).get("code") == "UNES_REQUERIDA")

    respuesta = client.post(
        "/api/auth/login",
        json={"correo": th_correo, "password": PASSWORD_TH, "unes": "abc"},
    )
    check("rechaza una UNES con formato inválido", respuesta.status_code == 400, str(respuesta.status_code))
    check("código UNES_INVALIDA", (respuesta.get_json() or {}).get("code") == "UNES_INVALIDA")

    respuesta = client.post(
        "/api/auth/login",
        json={"correo": th_correo, "password": PASSWORD_TH, "unes": UNES_PRUEBA},
    )
    cuerpo = respuesta.get_json() or {}
    check("login de Talento Humano con UNES", respuesta.status_code == 200, str(respuesta.status_code))
    usuario = cuerpo.get("usuario") or {}
    check("la sesión declara el cargo", usuario.get("cargo", "").lower() == TH_CARGO, str(usuario.get("cargo")))
    check("la sesión dice que es Talento Humano", usuario.get("esTalentoHumano") is True)
    check("la sesión dice que puede aprobar", usuario.get("puedeAprobar") is True)
    check("la sesión conserva la UNES digitada", usuario.get("unes") == UNES_PRUEBA, str(usuario.get("unes")))
    check("la respuesta NO trae password_hash", "password_hash" not in respuesta.get_data(as_text=True))
    token_th = cuerpo.get("token")
    if not token_th:
        print("Sin token de Talento Humano no se puede continuar.")
        return 1
    auth_th = {"Authorization": f"Bearer {token_th}"}

    respuesta = client.get("/api/auth/session", headers=auth_th)
    check(
        "GET /api/auth/session confirma el cargo",
        (respuesta.get_json() or {}).get("usuario", {}).get("cargo", "").lower() == TH_CARGO,
    )
    check(
        "la sesión no se emite para una cuenta inactiva",
        (respuesta.get_json() or {}).get("usuario", {}).get("activo") is True,
    )

    # ------------------------------------------------------------------
    print("\n================ ADMINISTRACIÓN DE USUARIOS ================")
    respuesta = client.get("/api/usuarios", headers=auth_th)
    usuarios = (respuesta.get_json() or {}).get("usuarios", [])
    check("listar usuarios", respuesta.status_code == 200 and len(usuarios) > 0, str(respuesta.status_code))
    check("el listado no expone password_hash", "password_hash" not in respuesta.get_data(as_text=True))
    check("el listado trae el cargo", "cargo" in (usuarios[0] if usuarios else {}))

    respuesta = client.post(
        "/api/usuarios",
        headers=auth_th,
        json={
            "nombre": "Prueba Otro Cargo",
            "correo": otro_correo,
            "cargo": OTRO_CARGO,
            "password": PASSWORD_OTRO,
        },
    )
    creado = (respuesta.get_json() or {}).get("usuario") or {}
    check("crear usuario", respuesta.status_code == 201, f"{respuesta.status_code} {respuesta.get_data(as_text=True)[:120]}")
    check("el usuario creado queda con su cargo", creado.get("cargo") == OTRO_CARGO)
    check("el usuario creado NO es Talento Humano", creado.get("esTalentoHumano") is False)
    otro_id = creado.get("id")
    if not otro_id:
        print("Sin el usuario creado no se puede continuar.")
        return 1

    respuesta = client.post(
        "/api/usuarios",
        headers=auth_th,
        json={"nombre": "Duplicado", "correo": otro_correo, "cargo": OTRO_CARGO, "password": PASSWORD_OTRO, "unes": UNES_PRUEBA},
    )
    check("rechaza un correo duplicado", respuesta.status_code == 409, str(respuesta.status_code))

    respuesta = client.post(
        "/api/usuarios", headers=auth_th, json={"nombre": "", "correo": "no-es-correo", "cargo": "", "password": "corta"}
    )
    check("rechaza datos incompletos", respuesta.status_code == 400, str(respuesta.status_code))

    respuesta = client.put(
        f"/api/usuarios/{otro_id}", headers=auth_th, json={"nombre": "Prueba Editada", "cargo": "analista"}
    )
    check("editar usuario", respuesta.status_code == 200, str(respuesta.status_code))
    check(
        "el cambio se guardó",
        ((respuesta.get_json() or {}).get("usuario") or {}).get("nombre") == "Prueba Editada",
    )

    # ------------------------------------------------------------------
    print("\n================ CONTROL DE ROL ================")
    respuesta = client.post(
        "/api/auth/login",
        json={"correo": otro_correo, "password": PASSWORD_OTRO, "unes": UNES_PRUEBA},
    )
    cuerpo_otro = respuesta.get_json() or {}
    check("login del usuario de otro cargo", respuesta.status_code == 200, str(respuesta.status_code))
    check("la sesión dice que no puede aprobar", (cuerpo_otro.get("usuario") or {}).get("puedeAprobar") is False)
    token_otro = cuerpo_otro.get("token")
    auth_otro = {"Authorization": f"Bearer {token_otro}"}

    respuesta = client.get("/api/usuarios", headers=auth_otro)
    check("otro cargo NO puede listar usuarios (403)", respuesta.status_code == 403, str(respuesta.status_code))
    check("código FORBIDDEN_ROLE", (respuesta.get_json() or {}).get("code") == "FORBIDDEN_ROLE")

    respuesta = client.post(
        "/api/usuarios",
        headers=auth_otro,
        json={"nombre": "Intruso", "correo": f"intruso.{sufijo}@example.com", "cargo": TH_CARGO, "password": PASSWORD_OTRO, "unes": UNES_PRUEBA},
    )
    check("otro cargo NO puede crear usuarios (403)", respuesta.status_code == 403, str(respuesta.status_code))
    check(
        "no se creó el intruso",
        database.query_one("SELECT COUNT(*) FROM dbo.Usuarios WHERE correo = ?", (f"intruso.{sufijo}@example.com",))[0] == 0,
    )

    respuesta = client.delete(f"/api/usuarios/{otro_id}", headers=auth_otro)
    check("otro cargo NO puede eliminar usuarios (403)", respuesta.status_code == 403, str(respuesta.status_code))
    check(
        "el usuario sigue existiendo",
        database.query_one("SELECT COUNT(*) FROM dbo.Usuarios WHERE id = ?", (otro_id,))[0] == 1,
    )

    # ------------------------------------------------------------------
    print("\n================ ASIGNACIONES ================")
    respuesta = client.get("/api/asignaciones", headers=auth_otro)
    check("cualquier sesión puede listar asignaciones", respuesta.status_code == 200, str(respuesta.status_code))

    hoy = date.today()
    payload = {
        "identificacion": f"9{sufijo[:6]}",
        "empleado": "Empleado De Prueba",
        "cargo": "Auxiliar",
        "descUnes": "UNES de prueba",
        "unes": "UNES 999",
        "correo": otro_correo,
        # Con decimal a propósito: los días a corte de la vista vienen así (7.2) y
        # el resultado guardado tiene que conservar ese decimal.
        "diasACorte": 7.2,
        "observaciones": "Registro creado por la prueba automática.",
        "periodos": [
            {"inicio": hoy.isoformat(), "fin": (hoy + timedelta(days=4)).isoformat()},
            {"inicio": (hoy + timedelta(days=10)).isoformat(), "fin": (hoy + timedelta(days=12)).isoformat()},
            {"inicio": None, "fin": None},
        ],
    }
    respuesta = client.post("/api/asignaciones", headers=auth_th, json=payload)
    creada = (respuesta.get_json() or {}).get("asignacion") or {}
    check("crear asignación con tres períodos", respuesta.status_code == 201, f"{respuesta.status_code} {respuesta.get_data(as_text=True)[:160]}")
    asignacion_id = creada.get("id")
    check("los días se calculan del período 1 (5)", creada.get("periodos", [{}])[0].get("dias") == 5)
    check("los días se calculan del período 2 (3)", creada.get("periodos", [{}, {}])[1].get("dias") == 3)
    check("el total es la suma (8)", creada.get("totalDias") == 8, str(creada.get("totalDias")))
    check("el estado inicial es pendiente", creada.get("estado") == "pendiente")
    check("la fecha de regreso se calcula", bool(creada.get("fechaRegreso")), str(creada.get("fechaRegreso")))

    if not asignacion_id:
        print("Sin la asignación creada no se puede continuar.")
        return 1

    # El total que envía el cliente NO debe imponerse sobre el calculado.
    respuesta = client.put(
        f"/api/asignaciones/{asignacion_id}/periodos",
        headers=auth_th,
        json={
            "periodos": [
                {"inicio": hoy.isoformat(), "fin": (hoy + timedelta(days=19)).isoformat()},
                {"inicio": None, "fin": None},
                {"inicio": None, "fin": None},
            ],
            "totalDias": 1,
            "fechaIngreso": (hoy + timedelta(days=20)).isoformat(),
        },
    )
    actualizada = (respuesta.get_json() or {}).get("asignacion") or {}
    check("guardar períodos", respuesta.status_code == 200, str(respuesta.status_code))
    check("el total se recalcula y no se acepta el del cliente", actualizada.get("totalDias") == 20, str(actualizada.get("totalDias")))

    respuesta = client.put(
        f"/api/asignaciones/{asignacion_id}/periodos",
        headers=auth_th,
        json={
            "periodos": [
                {"inicio": hoy.isoformat(), "fin": (hoy + timedelta(days=10)).isoformat()},
                {"inicio": (hoy + timedelta(days=5)).isoformat(), "fin": (hoy + timedelta(days=8)).isoformat()},
                {"inicio": None, "fin": None},
            ]
        },
    )
    check("rechaza períodos que se cruzan", respuesta.status_code == 400, str(respuesta.status_code))
    check("código PERIODOS_CRUZADOS", (respuesta.get_json() or {}).get("code") == "PERIODOS_CRUZADOS")

    respuesta = client.put(
        f"/api/asignaciones/{asignacion_id}/periodos",
        headers=auth_th,
        json={"periodos": [{"inicio": (hoy + timedelta(days=5)).isoformat(), "fin": hoy.isoformat()}]},
    )
    check("rechaza un rango invertido", respuesta.status_code == 400, str(respuesta.status_code))

    # ------------------------------------------------------------------
    print("\n================ DECISIONES Y NOTIFICACIONES ================")
    respuesta = client.post(
        f"/api/asignaciones/{asignacion_id}/decision",
        headers=auth_otro,
        json={"decision": "rechazada", "motivo": "Intento sin permiso"},
    )
    check("otro cargo NO puede aprobar ni rechazar (403)", respuesta.status_code == 403, str(respuesta.status_code))

    respuesta = client.post(
        f"/api/asignaciones/{asignacion_id}/decision",
        headers=auth_th,
        json={"decision": "rechazada"},
    )
    check("rechazar sin motivo se rechaza", respuesta.status_code == 400, str(respuesta.status_code))
    check("código MOTIVO_REQUERIDO", (respuesta.get_json() or {}).get("code") == "MOTIVO_REQUERIDO")

    respuesta = client.post(
        f"/api/asignaciones/{asignacion_id}/decision",
        headers=auth_th,
        json={"decision": "rechazada", "motivo": "Fechas superpuestas con el turno.", "observaciones": "Avisado por correo."},
    )
    rechazada = (respuesta.get_json() or {}).get("asignacion") or {}
    check("rechazar con motivo", respuesta.status_code == 200, str(respuesta.status_code))
    check("el estado queda rechazada", rechazada.get("estado") == "rechazada")
    check("el motivo se guardó", rechazada.get("motivoRechazo") == "Fechas superpuestas con el turno.")

    respuesta = client.post(
        f"/api/asignaciones/{asignacion_id}/decision",
        headers=auth_th,
        json={"decision": "aprobada"},
    )
    aprobada = (respuesta.get_json() or {}).get("asignacion") or {}
    check("aprobar", respuesta.status_code == 200, str(respuesta.status_code))
    check("el estado queda aprobada", aprobada.get("estado") == "aprobada")
    check("al aprobar se limpia el motivo de rechazo", aprobada.get("motivoRechazo") is None)

    filas = database.query_named(
        "SELECT TOP 10 msj_notificacion, unes, usuario_id FROM dbo.notificaciones ORDER BY id DESC"
    )
    mensajes = " || ".join(str(f["msj_notificacion"]) for f in filas)
    check("se generaron notificaciones", len(filas) > 0, str(len(filas)))
    check("hay aviso de asignación de fechas", "asignó las fechas" in mensajes)
    check("hay aviso de rechazo con motivo", "rechazó" in mensajes and "Fechas superpuestas" in mensajes)
    check("hay aviso de aprobación", "aprobó" in mensajes)
    check(
        "las notificaciones guardan el usuario relacionado",
        any(f["usuario_id"] is not None for f in filas),
        str([f["usuario_id"] for f in filas[:3]]),
    )

    respuesta = client.get("/api/notificaciones", headers=auth_th)
    avisos_th = (respuesta.get_json() or {}).get("notificaciones", [])
    check("Talento Humano ve las notificaciones", respuesta.status_code == 200 and len(avisos_th) > 0, str(len(avisos_th)))

    # Regla del negocio: los avisos de asignación, aprobación y rechazo son sólo
    # para Talento Humano. Para otro cargo la bandeja general llega vacía.
    respuesta = client.get("/api/notificaciones", headers=auth_otro)
    avisos_otro = (respuesta.get_json() or {}).get("notificaciones", [])
    check("otro cargo recibe la bandeja general", respuesta.status_code == 200, str(respuesta.status_code))
    check("la bandeja general del otro cargo llega vacía", avisos_otro == [], str(len(avisos_otro)))

    # Pero sí ve los avisos dirigidos a él (los que Talento Humano genera al
    # modificar sus fechas): es la notificación al usuario de esas fechas.
    respuesta = client.get("/api/notificaciones/mias", headers=auth_otro)
    mios = (respuesta.get_json() or {}).get("notificaciones", [])
    check("el afectado ve sus avisos personales", len(mios) >= 3, str(len(mios)))
    check(
        "los avisos personales son suyos",
        all(a["usuarioId"] == otro_id for a in mios),
        str({a["usuarioId"] for a in mios}),
    )
    texto_mios = " || ".join(a["mensaje"] for a in mios)
    check("le llegó el aviso de asignación", "asignó las fechas" in texto_mios)
    check("le llegó el aviso de rechazo", "rechazó" in texto_mios)
    check("le llegó el aviso de aprobación", "aprobó" in texto_mios)

    # ------------------------------------------------------------------
    print("\n================ RESUMEN ================")
    respuesta = client.get("/api/resumen", headers=auth_th)
    datos = respuesta.get_json() or {}
    check("resumen disponible", respuesta.status_code == 200, str(respuesta.status_code))
    totales = datos.get("totales") or {}
    check("trae los totales", "usuarios" in totales and "asignaciones" in totales)
    check("cuenta todos los usuarios", totales.get("usuarios", 0) >= 2, str(totales.get("usuarios")))
    check("cuenta las asignaciones", totales.get("asignaciones", 0) >= 1, str(totales.get("asignaciones")))
    check("el consolidado por empleado viene con datos", len(datos.get("empleados") or []) >= 2)
    empleado = next((e for e in datos.get("empleados", []) if e["correo"] == otro_correo), None)
    check("el empleado aparece en el consolidado", empleado is not None)
    if empleado:
        check("sus días totales se suman", empleado["diasTotales"] >= 20, str(empleado["diasTotales"]))
        check("sus aprobadas se cuentan", empleado["aprobadas"] >= 1, str(empleado["aprobadas"]))

    # ------------------------------------------------------------------
    print("\n================ TABLERO POR UNES ================")
    respuesta = client.get("/api/asignaciones", headers=auth_th)
    tablero = respuesta.get_json() or {}
    check("el tablero responde", respuesta.status_code == 200, str(respuesta.status_code))
    check("respeta la UNES de la sesión", tablero.get("unes") == UNES_PRUEBA, str(tablero.get("unes")))

    if tablero.get("origen") == "vista":
        filas_tablero = tablero.get("asignaciones") or []
        check("trae la plantilla de la UNES", len(filas_tablero) > 50, str(len(filas_tablero)))
        check(
            "todos los colaboradores son de esa UNES",
            all(str(f.get("unes", "")).endswith(UNES_PRUEBA) for f in filas_tablero),
        )
        check(
            "todos traen identificación",
            all(f.get("identificacion") for f in filas_tablero),
        )
        check(
            "los que no tienen fechas quedan pendientes y sin días asignados",
            all(
                f["estado"] == "pendiente" and float(f["diasAsignados"]) == 0
                for f in filas_tablero
                if f.get("sinAsignacion")
            ),
        )
        check(
            "días a usar = días a corte - días asignados",
            all(
                abs(float(f["diasAUsar"]) - (float(f["diasACorte"]) - float(f["diasAsignados"]))) < 0.05
                for f in filas_tablero
            ),
        )
        # El resultado del cálculo se persiste en la columna `dias_a_corte`, que
        # es de tipo DECIMAL(6,1): la base y la pantalla no pueden discrepar.
        guardado = database.query_one(
            "SELECT dias_a_corte, total_dias_empleado FROM dbo.asignacion_vacaciones WHERE id = ?",
            (asignacion_id,),
        )
        check("el resultado se guarda en la tabla", guardado is not None)
        if guardado is not None:
            en_base = float(guardado[0])
            total_en_base = float(guardado[1])
            corte_enviado = float(payload.get("diasACorte") or 0)
            check(
                "la columna dias_a_corte guarda «corte - asignados»",
                abs(en_base - (corte_enviado - total_en_base)) < 0.05,
                f"guardado={en_base}, corte={corte_enviado} − total={total_en_base}",
            )
            check(
                "el resultado guardado tiene un decimal exacto",
                abs(round(float(guardado[0]), 1) - float(guardado[0])) < 0.001,
                str(guardado[0]),
            )
            tipo_columna = database.query_one(
                "SELECT DATA_TYPE, NUMERIC_SCALE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = 'asignacion_vacaciones' AND COLUMN_NAME = 'dias_a_corte'"
            )
            check(
                "la columna dias_a_corte es decimal (no entera)",
                tipo_columna is not None
                and str(tipo_columna[0]).lower() in ("decimal", "numeric")
                and int(tipo_columna[1]) >= 1,
                str(tuple(tipo_columna)) if tipo_columna else "no encontrada",
            )
            # Si el colaborador de la prueba está en la vista, el tablero toma el
            # corte de ahí; si no, usa el guardado. En los dos casos, el número
            # que se muestra es «corte − asignados».
            fila_tablero = next((f for f in filas_tablero if f.get("id") == asignacion_id), None)
            if fila_tablero is not None:
                check(
                    "el tablero muestra el mismo resultado que la base",
                    abs(float(fila_tablero["diasAUsar"]) - en_base) < 0.05
                    or fila_tablero.get("corteDesdeLaVista") is True,
                    f"tablero={fila_tablero['diasAUsar']} base={en_base} "
                    f"desdeVista={fila_tablero.get('corteDesdeLaVista')}",
                )
        check(
            "sin fechas programadas, días a usar es el corte (positivo)",
            all(
                float(f["diasAUsar"]) == float(f["diasACorte"]) and float(f["diasAUsar"]) >= 0
                for f in filas_tablero
                if f.get("sinAsignacion")
            ),
        )
        check(
            "los días se muestran con un decimal",
            all(round(float(f["diasAUsar"]), 1) == float(f["diasAUsar"]) for f in filas_tablero),
        )
        # La asignación de prueba se creó con UNES "UNES 999", así que **no**
        # debe aparecer en el tablero de la UNES 109: el filtro no es cosmético,
        # es lo que impide ver movimientos de otras UNES.
        ajenas = [
            f for f in filas_tablero if not str(f.get("unes", "")).strip().endswith(UNES_PRUEBA)
        ]
        check("no se cuelan asignaciones de otras UNES", ajenas == [], str(len(ajenas)))
        check(
            "la asignación de prueba (de otra UNES) queda fuera del tablero",
            all(f.get("identificacion") != payload["identificacion"] for f in filas_tablero),
        )
    else:
        print(f"  (la vista corporativa no respondió; origen={tablero.get('origen')})")
        check("sin vista, se degrada al listado local", tablero.get("origen") == "local")

    # ------------------------------------------------------------------
    print("\n================ ACTIVAR / DESACTIVAR ================")
    respuesta = client.get("/api/usuarios", headers=auth_th)
    listado = (respuesta.get_json() or {}).get("usuarios", [])
    check("el listado trae el estado activo", all("activo" in u for u in listado))
    check("el usuario nuevo nace activo", next(u for u in listado if u["id"] == otro_id)["activo"] is True)

    # Desactivar al otro usuario: su sesión debe morir en el acto.
    respuesta = client.patch(
        f"/api/usuarios/{otro_id}/activo", headers=auth_th, json={"activo": False}
    )
    check("desactivar un usuario", respuesta.status_code == 200, str(respuesta.status_code))
    check(
        "la respuesta confirma que quedó inactivo",
        ((respuesta.get_json() or {}).get("usuario") or {}).get("activo") is False,
    )

    respuesta = client.get("/api/auth/session", headers=auth_otro)
    check("la sesión del desactivado muere al instante", respuesta.status_code == 401, str(respuesta.status_code))

    respuesta = client.post(
        "/api/auth/login", json={"correo": otro_correo, "password": PASSWORD_OTRO, "unes": UNES_PRUEBA}
    )
    check("la cuenta desactivada no puede entrar", respuesta.status_code == 401, str(respuesta.status_code))
    check(
        "el mensaje no revela que la cuenta existe",
        (respuesta.get_json() or {}).get("code") == "INVALID_CREDENTIALS",
    )

    respuesta = client.patch(
        f"/api/usuarios/{otro_id}/activo", headers=auth_th, json={"activo": True}
    )
    check("volver a activar", respuesta.status_code == 200, str(respuesta.status_code))
    respuesta = client.post(
        "/api/auth/login", json={"correo": otro_correo, "password": PASSWORD_OTRO, "unes": UNES_PRUEBA}
    )
    check("la cuenta reactivada vuelve a entrar", respuesta.status_code == 200, str(respuesta.status_code))
    token_otro = (respuesta.get_json() or {}).get("token")
    auth_otro = {"Authorization": f"Bearer {token_otro}"}

    respuesta = client.patch(
        f"/api/usuarios/{th_id}/activo", headers=auth_th, json={"activo": False}
    )
    check("no puede desactivarse a sí mismo", respuesta.status_code == 409, str(respuesta.status_code))
    check(
        "código NO_SE_PUEDE_DESACTIVAR_A_SI_MISMO",
        (respuesta.get_json() or {}).get("code") == "NO_SE_PUEDE_DESACTIVAR_A_SI_MISMO",
    )

    respuesta = client.patch(f"/api/usuarios/{otro_id}/activo", headers=auth_otro, json={"activo": False})
    check("otro cargo no puede cambiar el estado (403)", respuesta.status_code == 403, str(respuesta.status_code))

    # ------------------------------------------------------------------
    print("\n================ PROTECCIONES ================")
    respuesta = client.delete(f"/api/usuarios/{th_id}", headers=auth_th)
    check("no puede eliminar su propio usuario", respuesta.status_code == 409, str(respuesta.status_code))
    check("código NO_SE_PUEDE_ELIMINAR_A_SI_MISMO", (respuesta.get_json() or {}).get("code") == "NO_SE_PUEDE_ELIMINAR_A_SI_MISMO")

    respuesta = client.delete(f"/api/usuarios/{otro_id}", headers=auth_th)
    check("eliminar un usuario", respuesta.status_code == 200, str(respuesta.status_code))
    check(
        "el usuario ya no existe",
        database.query_one("SELECT COUNT(*) FROM dbo.Usuarios WHERE id = ?", (otro_id,))[0] == 0,
    )
    respuesta = client.get("/api/usuarios", headers=auth_otro)
    check("la sesión del eliminado muere", respuesta.status_code == 401, str(respuesta.status_code))

    respuesta = client.get("/api/usuarios")
    check("sin token no se puede administrar (401)", respuesta.status_code == 401, str(respuesta.status_code))

    # Limpieza: la asignación de prueba y **los avisos que generó**. Si los avisos
    # se quedaran, cada corrida de la suite iría llenando la bandeja de
    # notificaciones con datos de prueba, que es justo lo que hay que evitar.
    avisos_antes = database.query_one("SELECT COUNT(*) FROM dbo.notificaciones")[0]
    database.execute("DELETE FROM dbo.asignacion_vacaciones WHERE id = ?", (asignacion_id,))
    database.execute(
        "DELETE FROM dbo.notificaciones WHERE msj_notificacion LIKE ? OR msj_notificacion LIKE ?",
        ("%Empleado De Prueba%", "%PRUEBA%"),
    )
    avisos_despues = database.query_one("SELECT COUNT(*) FROM dbo.notificaciones")[0]
    print(
        f"\n  (limpieza: asignación {asignacion_id} eliminada; "
        f"avisos de prueba borrados: {avisos_antes - avisos_despues})"
    )

    print(f"\nResumen: {len(PASSED)} correctas, {len(FAILED)} fallidas")
    for fallo in FAILED:
        print(f"  - {fallo}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
