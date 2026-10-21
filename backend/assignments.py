"""Asignaciones de vacaciones: repositorio y reglas de negocio.

La tabla ``dbo.asignacion_vacaciones`` tiene una fila por asignación con los tres
períodos "aplanados" (``periodo1_fecha1``... ``periodo3_dias3``). La interfaz, en
cambio, trabaja con una lista de períodos. Este módulo traduce en los dos
sentidos para que el resto del sistema no sepa de esa forma aplanada.

Los datos que llegan del navegador **nunca** se escriben sin validar: los días y
los totales se recalculan aquí a partir de las fechas, no se aceptan del cliente.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from db import Database, DatabaseUnavailable
from security import ValidationError

logger = logging.getLogger(__name__)

TABLA = "dbo.asignacion_vacaciones"

ESTADO_PENDIENTE = "pendiente"
ESTADO_APROBADA = "aprobada"
ESTADO_RECHAZADA = "rechazada"
ESTADOS_VALIDOS = (ESTADO_PENDIENTE, ESTADO_APROBADA, ESTADO_RECHAZADA)

# Anchos reales de las columnas de texto que recibe este módulo.
IDENTIFICACION_MAX = 50
EMPLEADO_MAX = 150
CARGO_MAX = 100
DESC_UNES_MAX = 255
UNES_MAX = 10
CORREO_MAX = 150
OBSERVACIONES_MAX = 4000
MOTIVO_MAX = 4000
TH_MAX = 100

_COLUMNAS = (
    "id, identificacion, empleado, cargo, desc_unes, unes, correo, estado_asignacion, "
    "dias_a_corte, observaciones, "
    "periodo1_fecha1, periodo1_fecha2, periodo1_dias1, "
    "periodo2_fecha1, periodo2_fecha2, periodo2_dias2, "
    "periodo3_fecha1, periodo3_fecha2, periodo3_dias3, "
    "fecha_regreso, fecha_reintegro_lab, total_dias_empleado, motivo_rechazo, th_asignacion, "
    "fecha_registro, fecha_update"
)

_SELECT_TODAS = f"SELECT {_COLUMNAS} FROM {TABLA} ORDER BY fecha_registro DESC, id DESC"
_SELECT_UNA = f"SELECT {_COLUMNAS} FROM {TABLA} WHERE id = ?"

_INSERT = (
    f"INSERT INTO {TABLA} ("
    "identificacion, empleado, cargo, desc_unes, unes, correo, estado_asignacion, "
    "dias_a_corte, observaciones, "
    "periodo1_fecha1, periodo1_fecha2, periodo1_dias1, "
    "periodo2_fecha1, periodo2_fecha2, periodo2_dias2, "
    "periodo3_fecha1, periodo3_fecha2, periodo3_dias3, "
    "fecha_regreso, fecha_reintegro_lab, "
    "total_dias_empleado, motivo_rechazo, th_asignacion, "
    "fecha_registro, fecha_update"
    ") OUTPUT INSERTED.id VALUES (" + ", ".join(["?"] * 25) + ")"
)

_UPDATE_PERIODOS = (
    f"UPDATE {TABLA} SET "
    "observaciones = ?, "
    "periodo1_fecha1 = ?, periodo1_fecha2 = ?, periodo1_dias1 = ?, "
    "periodo2_fecha1 = ?, periodo2_fecha2 = ?, periodo2_dias2 = ?, "
    "periodo3_fecha1 = ?, periodo3_fecha2 = ?, periodo3_dias3 = ?, "
    "fecha_regreso = ?, fecha_reintegro_lab = ?, total_dias_empleado = ?, dias_a_corte = ?, "
    "estado_asignacion = ?, motivo_rechazo = NULL, "
    "th_asignacion = ?, fecha_update = GETDATE() "
    "WHERE id = ?"
)

_UPDATE_DECISION = (
    f"UPDATE {TABLA} SET estado_asignacion = ?, motivo_rechazo = ?, "
    "observaciones = COALESCE(?, observaciones), th_asignacion = ?, "
    "fecha_update = GETDATE() WHERE id = ?"
)

_DELETE = f"DELETE FROM {TABLA} WHERE id = ?"


# --------------------------------------------------------------------------
# Conversión de valores
# --------------------------------------------------------------------------


def _a_iso(valor: Any) -> str | None:
    """``date``/``datetime`` → ``aaaa-mm-dd``; el resto se deja pasar."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _a_iso_completo(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _a_date(valor: Any, campo: str) -> date | None:
    """``aaaa-mm-dd`` → ``date``. Se valida aquí, no en el driver."""
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError as exc:
        raise ValidationError("FECHA_INVALIDA", f"La fecha de {campo} no es válida.") from exc


def _texto(valor: Any, campo: str, maximo: int, *, obligatorio: bool = False) -> str | None:
    if valor is None:
        if obligatorio:
            raise ValidationError("CAMPO_REQUERIDO", f"Falta {campo}.")
        return None
    texto = " ".join(str(valor).split()) if "\n" not in str(valor) else str(valor).strip()
    if not texto:
        if obligatorio:
            raise ValidationError("CAMPO_REQUERIDO", f"Falta {campo}.")
        return None
    if len(texto) > maximo:
        raise ValidationError("CAMPO_LARGO", f"{campo} no puede superar {maximo} caracteres.")
    return texto


def _numero(valor: Any, campo: str, *, maximo: float = 3650.0) -> float | None:
    """Número con decimales, no negativo y dentro de rango.

    Los días a corte llegan con un decimal desde la vista (7.2), así que el
    validador de enteros los truncaría en silencio.
    """
    if valor in (None, ""):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValidationError("NUMERO_INVALIDO", f"{campo} debe ser un número.") from exc
    if numero != numero or numero in (float("inf"), float("-inf")):  # NaN o infinito
        raise ValidationError("NUMERO_INVALIDO", f"{campo} debe ser un número.")
    if numero < 0 or numero > maximo:
        raise ValidationError("NUMERO_FUERA_RANGO", f"{campo} está fuera del rango permitido.")
    return numero


# --------------------------------------------------------------------------
# Modelo de lectura
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Periodo:
    inicio: str | None
    fin: str | None
    dias: int | None


def _periodos_desde_fila(fila: Any) -> list[Periodo]:
    """Arma los tres períodos desde las columnas aplanadas."""
    generados = []
    for numero, col_dias in ((1, "periodo1_dias1"), (2, "periodo2_dias2"), (3, "periodo3_dias3")):
        generados.append(
            Periodo(
                inicio=_a_iso(fila[f"periodo{numero}_fecha1"]),
                fin=_a_iso(fila[f"periodo{numero}_fecha2"]),
                dias=fila[col_dias],
            )
        )
    return generados


def fila_a_dict(fila: Any) -> dict[str, Any]:
    """Fila de la tabla → objeto que consume el frontend.

    ``dias_a_corte`` guarda **el resultado del cálculo**: días a corte menos días
    asignados, en ese orden. Positivo significa que al colaborador le quedan días
    por disfrutar sobre lo programado; negativo, que programó más de los que
    tiene. Se calcula en el servidor y se persiste al crear la asignación y al
    cambiar sus períodos, para que la tabla, los modales, el reporte y la base no
    puedan discrepar.

    El campo se llama ``diasAUsar`` en la respuesta porque es el nombre con el
    que se muestra; en la base conserva el nombre de la columna.
    """
    total = fila["total_dias_empleado"]
    guardado = fila["dias_a_corte"]
    total_dias = float(total) if total is not None else 0.0
    dias_a_corte = float(guardado) if guardado is not None else 0.0

    return {
        "id": int(fila["id"]),
        "identificacion": str(fila["identificacion"] or ""),
        "empleado": str(fila["empleado"] or ""),
        "cargo": str(fila["cargo"] or ""),
        "descUnes": str(fila["desc_unes"] or ""),
        "unes": str(fila["unes"] or ""),
        "correo": str(fila["correo"] or ""),
        "estado": str(fila["estado_asignacion"] or ESTADO_PENDIENTE),
        "diasACorte": round(dias_a_corte, 1),
        "diasAUsar": round(dias_a_corte, 1),
        "observaciones": fila["observaciones"],
        "periodos": [
            {"inicio": p.inicio, "fin": p.fin, "dias": p.dias} for p in _periodos_desde_fila(fila)
        ],
        "fechaRegreso": _a_iso(fila["fecha_regreso"]),
        # El mismo valor con el nombre que usa la interfaz, que es también el que
        # acepta el payload de entrada.
        "fechaIngreso": _a_iso(fila["fecha_regreso"]),
        # Fecha elegida a mano para el reintegro a labores; no se deriva de los
        # períodos porque puede diferir del día siguiente al último.
        "fechaReintegroLab": _a_iso(fila["fecha_reintegro_lab"]),
        "totalDias": round(total_dias, 1),
        "motivoRechazo": fila["motivo_rechazo"],
        "thAsignacion": fila["th_asignacion"],
        "fechaRegistro": _a_iso_completo(fila["fecha_registro"]),
        "fechaUpdate": _a_iso_completo(fila["fecha_update"]),
    }


# --------------------------------------------------------------------------
# Validación de la entrada
# --------------------------------------------------------------------------


def normalizar_periodos(periodos: Any, *, minimo: int = 1) -> tuple[list[dict[str, Any]], int]:
    """Valida los tres períodos y **calcula los días a partir de las fechas**.

    El total no se acepta del cliente: se recalcula aquí. Si se confiara en el
    número que envía el navegador, cualquiera podría guardar "0 días" para un
    período de dos semanas.

    Devuelve ``(periodos, total_dias)``.
    """
    if not isinstance(periodos, list) or len(periodos) > 3:
        raise ValidationError("PERIODOS_INVALIDOS", "Se esperan hasta tres períodos.")

    normalizados: list[dict[str, Any]] = []
    for indice, bruto in enumerate(periodos):
        if not isinstance(bruto, dict):
            raise ValidationError("PERIODOS_INVALIDOS", "El formato de los períodos no es válido.")
        inicio = _a_date(bruto.get("inicio"), f"inicio del período {indice + 1}")
        fin = _a_date(bruto.get("fin"), f"fin del período {indice + 1}")

        if inicio is None and fin is None:
            normalizados.append({"inicio": None, "fin": None, "dias": None})
            continue
        if inicio is None or fin is None:
            raise ValidationError(
                "PERIODO_INCOMPLETO",
                f"El período {indice + 1} necesita fecha de inicio y de fin.",
            )
        if fin < inicio:
            raise ValidationError(
                "RANGO_INVERTIDO",
                f"La fecha de fin del período {indice + 1} es anterior a la de inicio.",
            )
        # Días inclusivos: del 1 al 5 son 5 días, que es la convención de una
        # asignación de vacaciones.
        normalizados.append({"inicio": inicio, "fin": fin, "dias": (fin - inicio).days + 1})

    while len(normalizados) < 3:
        normalizados.append({"inicio": None, "fin": None, "dias": None})

    programados = [p for p in normalizados if p["dias"] is not None]
    if len(programados) < minimo:
        raise ValidationError("SIN_PERIODOS", "Programa al menos un período de vacaciones.")

    # Cruces: el error que descuadra el total y la nómina.
    for i in range(len(programados)):
        for j in range(i + 1, len(programados)):
            a, b = programados[i], programados[j]
            if a["inicio"] <= b["fin"] and b["inicio"] <= a["fin"]:
                raise ValidationError(
                    "PERIODOS_CRUZADOS",
                    "Dos períodos se cruzan. Revisa las fechas antes de guardar.",
                )

    total = sum(p["dias"] for p in programados)
    return normalizados, total


def validar_datos_empleado(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida los datos del colaborador de una asignación nueva.

    ``diasACorte`` es el corte que trae la vista del colaborador. Es la entrada
    del cálculo; lo que se persiste en la columna ``dias_a_corte`` es el
    resultado, y de eso se encarga el servicio.
    """
    identificacion = _texto(
        payload.get("identificacion"), "la identificación", IDENTIFICACION_MAX, obligatorio=True
    )
    empleado = _texto(payload.get("empleado"), "el nombre del colaborador", EMPLEADO_MAX, obligatorio=True)
    return {
        "identificacion": identificacion,
        "empleado": empleado,
        "cargo": _texto(payload.get("cargo"), "el cargo", CARGO_MAX) or "",
        "desc_unes": _texto(payload.get("descUnes"), "la descripción de UNES", DESC_UNES_MAX) or "",
        "unes": _texto(payload.get("unes"), "la UNES", UNES_MAX) or "",
        "correo": _texto(payload.get("correo"), "el correo", CORREO_MAX),
        # El corte puede traer decimales (7.2 en la vista), así que se acepta
        # como número, no como entero.
        "dias_a_corte": _numero(payload.get("diasACorte"), "los días a corte") or 0.0,
        "observaciones": _texto(payload.get("observaciones"), "las observaciones", OBSERVACIONES_MAX),
        # Fecha de reintegro a labores: la elige quien registra la asignación.
        # Es opcional, pero si viene se valida aquí para no guardar basura.
        "fecha_reintegro_lab": _a_date(payload.get("fechaReintegroLab"), "reintegro a labores"),
    }


def fecha_regreso_sugerida(periodos: list[dict[str, Any]]) -> date | None:
    """Día siguiente al último día programado.

    Se calcula, no se pide: la persona vuelve a trabajar al día siguiente de
    terminar sus vacaciones salvo que indique otra cosa.
    """
    fines = [p["fin"] for p in periodos if p.get("fin") is not None]
    if not fines:
        return None
    return max(fines) + timedelta(days=1)


def validar_periodos_entrantes(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida lo que llega al guardar períodos de una asignación existente."""
    periodos, total = normalizar_periodos(payload.get("periodos"))
    fecha_regreso = _a_date(payload.get("fechaIngreso"), "ingreso") or fecha_regreso_sugerida(periodos)
    return {
        "periodos": periodos,
        "total_dias": total,
        "fecha_regreso": fecha_regreso,
        # Reintegro a labores elegido a mano; no se deriva de los períodos.
        "fecha_reintegro_lab": _a_date(payload.get("fechaReintegroLab"), "reintegro a labores"),
        "observaciones": _texto(payload.get("observaciones"), "las observaciones", OBSERVACIONES_MAX),
    }


# --------------------------------------------------------------------------
# Repositorio
# --------------------------------------------------------------------------


class AssignmentRepository:
    """Único punto que lee y escribe ``dbo.asignacion_vacaciones``."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def listar(self) -> list[dict[str, Any]]:
        return [fila_a_dict(fila) for fila in self._database.query_named(_SELECT_TODAS)]

    def obtener(self, assignment_id: int) -> dict[str, Any] | None:
        filas = self._database.query_named(_SELECT_UNA, (assignment_id,))
        return fila_a_dict(filas[0]) if filas else None

    def crear(self, datos: dict[str, Any], periodos: list[dict[str, Any]], total: int, fecha_regreso: date, th: str) -> int:
        valores = (
            datos["identificacion"],
            datos["empleado"],
            datos["cargo"],
            datos["desc_unes"],
            datos["unes"],
            datos["correo"],
            ESTADO_PENDIENTE,
            datos["dias_a_corte"],
            datos["observaciones"],
            periodos[0]["inicio"], periodos[0]["fin"], periodos[0]["dias"],
            periodos[1]["inicio"], periodos[1]["fin"], periodos[1]["dias"],
            periodos[2]["inicio"], periodos[2]["fin"], periodos[2]["dias"],
            fecha_regreso,
            datos.get("fecha_reintegro_lab"),
            total,
            None,
            th,
            datetime.now(),
            datetime.now(),
        )
        with self._database.cursor(commit=True) as cursor:
            cursor.execute(_INSERT, valores)
            fila = cursor.fetchone()
        if fila is None:
            raise DatabaseUnavailable("No se pudo registrar la asignación.")
        return int(fila[0])

    def guardar_periodos(self, assignment_id: int, datos: dict[str, Any], th: str) -> int:
        """Actualiza períodos y **recalcula el resultado** de días a corte.

        El valor guardado es ``corte − total``. El corte original no vive en esta
        tabla, así que se despeja del valor almacenado (``resultado + total``) y
        se vuelve a aplicar con el total nuevo. Sin ese paso, editar los períodos
        dejaría el resultado viejo y la base contradiría a la pantalla.
        """
        periodos = datos["periodos"]
        total_nuevo = datos["total_dias"]
        actual = self.obtener(assignment_id) or {}
        corte_original = float(actual.get("diasAUsar") or 0) + float(
            actual.get("totalDias") or 0
        )
        resultado = round(corte_original - total_nuevo, 1)
        return self._database.execute(
            _UPDATE_PERIODOS,
            (
                datos["observaciones"],
                periodos[0]["inicio"], periodos[0]["fin"], periodos[0]["dias"],
                periodos[1]["inicio"], periodos[1]["fin"], periodos[1]["dias"],
                periodos[2]["inicio"], periodos[2]["fin"], periodos[2]["dias"],
                datos["fecha_regreso"],
                datos.get("fecha_reintegro_lab"),
                total_nuevo,
                resultado,
                ESTADO_PENDIENTE,
                th,
                assignment_id,
            ),
        )

    def registrar_decision(
        self, assignment_id: int, *, estado: str, motivo: str | None, observaciones: str | None, th: str
    ) -> int:
        return self._database.execute(
            _UPDATE_DECISION, (estado, motivo, observaciones, th, assignment_id)
        )

    def eliminar(self, assignment_id: int) -> int:
        return self._database.execute(_DELETE, (assignment_id,))


# --------------------------------------------------------------------------
# Servicio
# --------------------------------------------------------------------------


class AssignmentService:
    """Reglas de negocio de las asignaciones."""

    def __init__(self, database: Database) -> None:
        self._repository = AssignmentRepository(database)

    @property
    def repository(self) -> AssignmentRepository:
        return self._repository

    def listar(self) -> list[dict[str, Any]]:
        return self._repository.listar()

    def obtener(self, assignment_id: int) -> dict[str, Any] | None:
        return self._repository.obtener(assignment_id)

    def crear(self, payload: dict[str, Any], usuario: Any) -> tuple[int, dict[str, Any]]:
        """Registra una asignación nueva con sus tres períodos.

        Antes de guardar se calcula y se persiste el resultado de
        ``días a corte − días asignados`` en la columna ``dias_a_corte``.
        """
        datos = validar_datos_empleado(payload)
        periodos, total = normalizar_periodos(payload.get("periodos"), minimo=1)
        # La fecha de regreso se toma de la petición si viene; si no, se calcula.
        fecha_regreso = (
            _a_date(payload.get("fechaIngreso"), "ingreso") or fecha_regreso_sugerida(periodos)
        )
        if fecha_regreso is None:
            raise ValidationError("SIN_PERIODOS", "Programa al menos un período de vacaciones.")
        observaciones = _texto(
            payload.get("observaciones"), "las observaciones", OBSERVACIONES_MAX
        )
        datos["observaciones"] = observaciones
        # El resultado se calcula sobre el corte que llega (el de la vista del
        # colaborador) y el total que el servidor acaba de calcular.
        datos["dias_a_corte"] = round(float(datos["dias_a_corte"]) - float(total), 1)

        nuevo_id = self._repository.crear(datos, periodos, total, fecha_regreso, usuario.nombre)
        return nuevo_id, self._repository.obtener(nuevo_id) or {}

    def guardar_periodos(self, assignment_id: int, payload: dict[str, Any], usuario: Any) -> dict[str, Any]:
        if self._repository.obtener(assignment_id) is None:
            raise ValidationError("ASIGNACION_NO_EXISTE", "La asignación ya no existe.")
        validado = validar_periodos_entrantes(payload)
        afectadas = self._repository.guardar_periodos(assignment_id, validado, usuario.nombre)
        if afectadas == 0:
            raise ValidationError("ASIGNACION_NO_EXISTE", "La asignación ya no existe.")
        return self._repository.obtener(assignment_id) or {}

    def registrar_decision(
        self, assignment_id: int, payload: dict[str, Any], usuario: Any
    ) -> dict[str, Any]:
        actual = self._repository.obtener(assignment_id)
        if actual is None:
            raise ValidationError("ASIGNACION_NO_EXISTE", "La asignación ya no existe.")

        decision = str(payload.get("decision") or "").strip().lower()
        if decision not in (ESTADO_APROBADA, ESTADO_RECHAZADA):
            raise ValidationError(
                "DECISION_INVALIDA", "La decisión debe ser aprobar o rechazar."
            )

        motivo = _texto(payload.get("motivo"), "el motivo del rechazo", MOTIVO_MAX)
        if decision == ESTADO_RECHAZADA and not motivo:
            # Rechazar sin motivo obliga a la persona a preguntar por correo, que
            # es justo el trámite que esta herramienta viene a quitar.
            raise ValidationError(
                "MOTIVO_REQUERIDO", "Escribe el motivo del rechazo antes de continuar."
            )

        observaciones = _texto(payload.get("observaciones"), "las observaciones", OBSERVACIONES_MAX)
        self._repository.registrar_decision(
            assignment_id,
            estado=decision,
            motivo=motivo if decision == ESTADO_RECHAZADA else None,
            observaciones=observaciones,
            th=usuario.nombre,
        )
        return self._repository.obtener(assignment_id) or {}

    # -- cruce con el directorio de colaboradores ---------------------------

    def _clave_correo(self, valor: Any) -> str:
        """Correo normalizado para cruzar la vista con `dbo.Usuarios`.

        Acepta una cadena o un diccionario de asignación: los dos lados del
        cruce tienen el correo, pero en sitios distintos.
        """
        if isinstance(valor, dict):
            valor = valor.get("correo")
        return str(valor or "").strip().lower()

    def tablero_de_unes(
        self,
        colaboradores: list[Any],
        *,
        propietarios: dict[str, int | None] | None = None,
        unes: str = "",
    ) -> list[dict[str, Any]]:
        """Tablero de una UNES: sus colaboradores con la asignación que tengan.

        Cada fila es **un colaborador de la UNES**, no una asignación. Los que
        todavía no tienen fechas programadas aparecen igual —con `sinAsignacion`
        en `True`— porque son justamente a quienes hay que asignárselas.

        Los campos que vienen de la vista (descripción de UNES, colaborador,
        identificación, UNES, cargo, días a corte) se toman de la vista, que es
        la fuente autoritativa de la plantilla. La asignación aporta el estado,
        los períodos y las fechas.

        ``unes`` acota también las asignaciones huérfanas —las de colaboradores
        que ya no están en la vista—: sin ese filtro se colarían registros de
        otras UNES, que es justo lo que el filtro por UNES debe impedir.
        """
        porIdentificacion: dict[str, dict[str, Any]] = {}
        for asignacion in self._repository.listar():
            clave = str(asignacion.get("identificacion") or "").strip()
            if clave:
                porIdentificacion[clave] = asignacion

        tablero: list[dict[str, Any]] = []

        for colaborador in colaboradores:
            datos = colaborador.to_dict()
            identificacion = str(datos["identificacion"]).strip()
            asignacion = porIdentificacion.pop(identificacion, None)

            totalAsignado = float(asignacion["totalDias"]) if asignacion else 0.0
            # El corte bueno es el de la vista: es la fuente autoritativa y el
            # dato con el que se calculó el resultado que se guardó. El valor
            # almacenado se usa sólo para quien ya no está en la plantilla.
            corteEsDeLaVista = True
            diasACorte = float(datos["diasACorte"])
            if asignacion is not None and datos["diasACorte"] is None:
                diasACorte = float(asignacion["diasAUsar"]) + totalAsignado
                corteEsDeLaVista = False

            fila = {
                # Sin asignación todavía: el `id` del colaborador no es un
                # radicado. `sinAsignacion` lo deja explícito para que la
                # interfaz no lo confunda con una asignación real.
                "id": asignacion["id"] if asignacion else None,
                "sinAsignacion": asignacion is None,
                "identificacion": identificacion,
                "empleado": datos["empleado"],
                "cargo": datos["cargo"],
                "descUnes": datos["descUnes"],
                "unes": datos["unes"],
                "correo": datos["correoParaUsar"],
                "estado": asignacion["estado"] if asignacion else ESTADO_PENDIENTE,
                "diasACorte": round(diasACorte, 1),
                "diasAsignados": round(totalAsignado, 1),
                # Días a corte menos días asignados, en ese orden. Positivo si le
                # quedan días por disfrutar sobre lo programado; negativo si
                # programó más de los que tiene. Es el mismo valor que se
                # persiste en `dias_a_corte` al guardar.
                "diasAUsar": round(diasACorte - totalAsignado, 1),
                "corteDesdeLaVista": corteEsDeLaVista,
                "periodos": asignacion["periodos"] if asignacion else [],
                "fechaRegreso": asignacion["fechaRegreso"] if asignacion else None,
                "fechaIngreso": asignacion["fechaIngreso"] if asignacion else None,
                "fechaReintegroLab": asignacion["fechaReintegroLab"] if asignacion else None,
                "observaciones": asignacion["observaciones"] if asignacion else None,
                "motivoRechazo": asignacion["motivoRechazo"] if asignacion else None,
                "thAsignacion": asignacion["thAsignacion"] if asignacion else None,
                "diasAcumulados": datos["diasAcumulados"],
                # Fecha de ingreso a la empresa (de la vista). Sólo la usa la
                # planilla en PDF; no forma parte de la asignación.
                "fechaIngresoLaboral": datos.get("fechaIngresoLaboral"),
                "fechaRegistro": asignacion["fechaRegistro"] if asignacion else None,
                "fechaUpdate": asignacion["fechaUpdate"] if asignacion else None,
                # Usuario dueño de estas fechas, para poder notificarle. El
                # correo es el dato que comparten la vista y `dbo.Usuarios`.
                "usuarioId": (propietarios or {}).get(
                    self._clave_correo(
                        asignacion["correo"] if asignacion else datos["correoParaUsar"]
                    )
                ),
            }
            if asignacion:
                fila["asignacionId"] = asignacion["id"]
            tablero.append(fila)

        # Asignaciones cuyo colaborador ya no está en la vista (retirado, o de la
        # plantilla actualizada). Se agregan al final para no perder el registro,
        # pero **sólo si son de esta UNES**: si no, un usuario vería movimientos
        # de otras UNES por la vía de un colaborador retirado.
        for asignacion in porIdentificacion.values():
            if unes and not str(asignacion.get("unes") or "").strip().endswith(unes):
                continue
            tablero.append(
                {
                    **asignacion,
                    "sinAsignacion": False,
                    "diasAsignados": asignacion["totalDias"],
                    "sinColaborador": True,
                }
            )

        return tablero
