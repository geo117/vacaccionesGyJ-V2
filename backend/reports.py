"""Reportes descargables: planilla de vacaciones (PDF) y plano UNOEE (Excel).

Estas funciones se extrajeron de ``tomar_funciones_ok.py`` para que vivan en el
backend modular, junto al resto del dominio. Son las dos descargas que ofrece la
vista de asignaciones:

* :func:`generar_pdf_reporte_vacaciones` reproduce la plantilla institucional
  (A4 horizontal, super-encabezados verde/azul, 23 columnas) a partir de las
  filas del tablero de colaboradores.
* :func:`generar_plano_excel` escribe la plantilla UNOEE oficial
  (``planos_unoee/ARCHIVO PLANO TNL-VACACIONES.xlsx``) a partir de las filas de
  períodos.

Ninguna de las dos toca la base de datos: reciben filas **ya resueltas** y
devuelven bytes o escriben en un destino. Quién ve qué —el filtro por UNES y el
cargo de Talento Humano para el plano— lo decide la ruta en :mod:`app`, que es
donde vive el control de acceso.

Las dependencias ``reportlab`` y ``openpyxl`` se importan dentro de cada función
para no cargar dos librerías pesadas en el arranque del servicio.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# Plantilla Excel oficial del plano UNOEE. Vive junto a este módulo.
PLANTILLA_PLANO = (
    Path(__file__).resolve().parent / "planos_unoee" / "ARCHIVO PLANO TNL-VACACIONES.xlsx"
)


# --------------------------------------------------------------------------
# Utilidades compartidas
# --------------------------------------------------------------------------


def _texto(fila: Any, *claves: str) -> str:
    """Primer valor no vacío de la fila entre las claves dadas, como texto."""
    for clave in claves:
        valor = fila.get(clave)
        if valor not in (None, ""):
            return str(valor)
    return ""


def _fmt_date(valor: Any) -> str:
    """``date``/``datetime`` o texto ISO → ``aaaa-mm-dd``."""
    if valor is None or valor == "":
        return ""
    if hasattr(valor, "strftime"):
        try:
            return valor.strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return str(valor)
    texto = str(valor)
    if len(texto) >= 10 and texto[4:5] == "-":
        return texto[:10]
    return texto


def _a_yyyymmdd(valor: Any) -> str | None:
    """``date``/``datetime`` o texto de fecha → ``aaaammdd`` para el plano."""
    if valor is None or valor == "":
        return None
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y%m%d")
    texto = str(valor).split(".")[0].strip()
    for formato in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(texto, formato).strftime("%Y%m%d")
        except ValueError:
            continue
    if len(texto) == 8 and texto.isdigit():
        return texto
    return None


def _safe_num(valor: Any, por_defecto: float = 0.0) -> float:
    if valor is None or valor == "":
        return por_defecto
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def _fmt_num(valor: Any) -> str:
    numero = _safe_num(valor)
    if numero == 0:
        return "0"
    if numero == int(numero):
        return str(int(numero))
    return f"{numero:g}"


def filas_plano_unoee(filas: Sequence[Any]) -> list[dict[str, Any]]:
    """Aplana los períodos de cada colaborador a las filas del plano UNOEE.

    Una fila por período con fechas. Los períodos incompletos se omiten: el
    plano no admite medio período y la plantilla oficial espera ambas fechas.
    """
    resultado: list[dict[str, Any]] = []
    for fila in filas:
        identificacion = str(fila.get("identificacion") or "").strip()
        if not identificacion:
            continue
        for periodo in fila.get("periodos") or []:
            inicio = _a_yyyymmdd(periodo.get("inicio"))
            fin = _a_yyyymmdd(periodo.get("fin"))
            if not inicio or not fin:
                continue
            resultado.append(
                {
                    "identificacion": identificacion,
                    "fecha_inicio": inicio,
                    "fecha_fin": fin,
                    "dias": int(_safe_num(periodo.get("dias"))),
                }
            )
    return resultado


# --------------------------------------------------------------------------
# Plantilla PDF (formato vacaciones institucional)
# --------------------------------------------------------------------------


def generar_pdf_reporte_vacaciones(
    employees: Sequence[Any], unes_filter: str, desc_unes: str
) -> bytes:
    """Genera la planilla de vacaciones en PDF según la plantilla institucional.

    Cumple la especificación del formato original:

      - A4 horizontal (landscape), margen 6 mm.
      - 23 columnas con los porcentajes exactos del HTML de referencia.
      - Super-encabezados verdes (#00B050) y azul (#0070C0) con colspans.
      - Estilo equivalente: ``nowrap`` en cédulas/fechas/totales, zebra en las
        filas y tabla de ancho fijo.
      - Fórmulas: ``Total tomados = P1 + P2 + P3`` y
        ``Saldo final = 0 si Total = 0, si no Pendientes − Total``.

    Acepta tanto las filas del tablero (``identificacion``/``empleado``/…) como
    las del listado local. Devuelve los bytes del PDF.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    buffer = io.BytesIO()

    # Página A4 horizontal con margen 6 mm.
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=6 * mm,
        rightMargin=6 * mm,
        topMargin=6 * mm,
        bottomMargin=6 * mm,
        title="Reporte Vacaciones",
        author="GYJ",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=11,
        textColor=colors.HexColor("#003366"),
        alignment=TA_CENTER,
        spaceAfter=2,
        fontName="Helvetica-Bold",
        leading=13,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Normal"],
        fontSize=7,
        textColor=colors.HexColor("#003366"),
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName="Helvetica-Bold",
        leading=9,
    )

    super_green_style = ParagraphStyle(
        "SuperGreen",
        parent=styles["Normal"],
        fontSize=6.5,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        leading=8,
    )
    super_blue_style = ParagraphStyle(
        "SuperBlue",
        parent=styles["Normal"],
        fontSize=7.5,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        leading=9,
    )
    col_header_style = ParagraphStyle(
        "ColHeader",
        parent=styles["Normal"],
        fontSize=6,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        leading=7,
    )
    cell_nowrap_style = ParagraphStyle(
        "CellNoWrap",
        parent=styles["Normal"],
        fontSize=6.2,
        textColor=colors.black,
        alignment=TA_CENTER,
        fontName="Helvetica",
        leading=7.5,
        wordWrap="CJK",
    )
    cell_nowrap_total_style = ParagraphStyle(
        "CellNoWrapTotal",
        parent=cell_nowrap_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#003366"),
    )
    cell_left_style = ParagraphStyle(
        "CellLeft", parent=cell_nowrap_style, alignment=TA_LEFT
    )

    def html_escape(val: Any) -> str:
        if val is None:
            return ""
        return (
            str(val)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    # -----------------------------------------------------------------
    # Título fuera de la tabla
    # -----------------------------------------------------------------
    elements = []
    unes_label = unes_filter or "TODAS"
    desc_label = desc_unes or ""
    titulo = f"FORMATO VACACIONES - UNES {unes_label}"
    if desc_label:
        titulo += f" ({desc_label})"
    elements.append(Paragraph(titulo, title_style))
    elements.append(
        Paragraph(
            f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            subtitle_style,
        )
    )

    # -----------------------------------------------------------------
    # Fila 1: super-encabezados (23 columnas exactas)
    # -----------------------------------------------------------------
    super_row = [Paragraph("", super_green_style) for _ in range(23)]
    super_row[0] = Paragraph("FORMATO VACACIONES", super_blue_style)
    super_row[7] = Paragraph(
        "PRIMER CORTE 28 DE NOVIEMBRE AL 6 DICIEMBRE<br/>FECHA DE PAGO 28 DE NOVIEMBRE",
        super_green_style,
    )
    super_row[10] = Paragraph(
        "SEGUNDO CORTE 7 AL 18 DE DICIEMBRE<br/>FECHA DE PAGO 15 DE DICIEMBRE",
        super_green_style,
    )
    super_row[13] = Paragraph("24 DE DICIEMBRE UNES", super_green_style)
    super_row[14] = Paragraph(
        "TERCER CORTE 19 DE DICEMBRE AL 12 DE ENERO<br/>FECHA DE PAGO 29 DICIEMBRE",
        super_green_style,
    )
    super_row[17] = Paragraph("31 DE DICIEMBRE UNES", super_green_style)

    # -----------------------------------------------------------------
    # Fila 2: encabezados de columna
    # -----------------------------------------------------------------
    column_headers = [
        "CEDULA",
        "APELLIDOS Y NOMBRES",
        "CARGO",
        "UNES",
        "FECHA DE INGRESO",
        "Correo personal de la persona (notificacion)",
        "DIAS PENDIENTES DE VACACIONES",
        "FECHA DE INICIO DE VACACIONES",
        "FECHA FIN DE VACACIONES",
        "TOTAL DÍAS",
        "FECHA DE INICIO DE VACACIONES2",
        "FECHA DE TERMINACIÓN DE VACACIONES",
        "TOTAL DÍAS3",
        "DIA DE LA FAMILIA",
        "FECHA DE INICIO DE VACACIONES4",
        "FECHA DE TERMINACIÓN DE VACACIONES5",
        "TOTAL DÍAS6",
        "DÍA DE LA FAMILIA 7",
        "TOTAL DIAS TOMADOS",
        "SALDO FINAL A 30 ENERO",
        "FECHA DE INGRESO LABORAL (REGRESO A TU LUGAR DE TRABAJO)",
        "OBSERVACIONES",
        "FIRMA",
    ]
    col_row = [
        Paragraph(html_escape(h), col_header_style) for h in column_headers
    ]

    # -----------------------------------------------------------------
    # Anchos de columna
    # -----------------------------------------------------------------
    col_pct = [
        6.1, 12.5, 10.0, 3.5, 5.5, 9.0, 4.0,
        5.0, 5.0, 3.0,
        5.0, 5.0, 3.0,
        4.5,
        5.0, 5.0, 3.0,
        4.5,
        3.5, 3.5, 5.5, 8.0, 4.0,
    ]
    total_pct = sum(col_pct)
    usable_w_pt = (297.0 - 12.0) / 25.4 * 72.0
    col_widths = [round(usable_w_pt * p / total_pct, 2) for p in col_pct]

    # -----------------------------------------------------------------
    # Filas de datos
    # -----------------------------------------------------------------
    rows = [super_row, col_row]

    for emp in employees:
        cedula = _texto(emp, "identificacion", "cedula")
        nombre = _texto(emp, "empleado", "Empleado").upper()
        cargo = _texto(emp, "cargo", "Cargo").upper()
        unes = _texto(emp, "unes", "IDCia_CO")
        fecha_ingreso = _fmt_date(
            emp.get("fechaIngresoLaboral")
            or emp.get("fecha_ingreso")
            or emp.get("Fecha_Ingreso")
        )
        correo = _texto(emp, "correo", "email").lower()
        dias_pendientes = _safe_num(
            emp.get("diasACorte")
            if emp.get("diasACorte") is not None
            else emp.get("dias_vacaciones_corteDic")
        )

        periodos = emp.get("periodos") or [{}, {}, {}]
        p1 = periodos[0] if len(periodos) > 0 else {}
        p2 = periodos[1] if len(periodos) > 1 else {}
        p3 = periodos[2] if len(periodos) > 2 else {}

        p1_ini = _fmt_date(p1.get("inicio"))
        p1_fin = _fmt_date(p1.get("fin"))
        p1_dias = _safe_num(p1.get("dias"))

        p2_ini = _fmt_date(p2.get("inicio"))
        p2_fin = _fmt_date(p2.get("fin"))
        p2_dias = _safe_num(p2.get("dias"))
        dia_fam1 = _fmt_date(emp.get("diaFamilia1"))

        p3_ini = _fmt_date(p3.get("inicio"))
        p3_fin = _fmt_date(p3.get("fin"))
        p3_dias = _safe_num(p3.get("dias"))
        dia_fam2 = _fmt_date(emp.get("diaFamilia2"))

        total_tomados = p1_dias + p2_dias + p3_dias
        saldo_final = 0 if total_tomados == 0 else (dias_pendientes - total_tomados)

        fecha_regreso = _fmt_date(
            emp.get("fechaRegreso")
            or emp.get("fechaIngreso")
            or emp.get("fecha_regreso")
        )
        observaciones = _texto(emp, "observaciones")

        rows.append(
            [
                Paragraph(html_escape(cedula), cell_nowrap_style),
                Paragraph(html_escape(nombre), cell_left_style),
                Paragraph(html_escape(cargo), cell_left_style),
                Paragraph(html_escape(unes), cell_nowrap_style),
                Paragraph(html_escape(fecha_ingreso), cell_nowrap_style),
                Paragraph(html_escape(correo), cell_left_style),
                Paragraph(_fmt_num(dias_pendientes), cell_nowrap_style),
                Paragraph(html_escape(p1_ini), cell_nowrap_style),
                Paragraph(html_escape(p1_fin), cell_nowrap_style),
                Paragraph(_fmt_num(p1_dias), cell_nowrap_style),
                Paragraph(html_escape(p2_ini), cell_nowrap_style),
                Paragraph(html_escape(p2_fin), cell_nowrap_style),
                Paragraph(_fmt_num(p2_dias), cell_nowrap_style),
                Paragraph(html_escape(dia_fam1), cell_nowrap_style),
                Paragraph(html_escape(p3_ini), cell_nowrap_style),
                Paragraph(html_escape(p3_fin), cell_nowrap_style),
                Paragraph(_fmt_num(p3_dias), cell_nowrap_style),
                Paragraph(html_escape(dia_fam2), cell_nowrap_style),
                Paragraph(_fmt_num(total_tomados), cell_nowrap_total_style),
                Paragraph(_fmt_num(saldo_final), cell_nowrap_total_style),
                Paragraph(html_escape(fecha_regreso), cell_nowrap_style),
                Paragraph(html_escape(observaciones), cell_left_style),
                Paragraph("", cell_nowrap_style),
            ]
        )

    if len(employees) == 0:
        empty_row = [Paragraph("-", cell_nowrap_style)] * 23
        empty_row[1] = Paragraph("Sin datos para mostrar", cell_left_style)
        rows.append(empty_row)

    # -----------------------------------------------------------------
    # Tabla con repeatRows=2
    # -----------------------------------------------------------------
    table = Table(rows, colWidths=col_widths, repeatRows=2)

    colspan_specs = [
        ("SPAN", (0, 0), (6, 0)),    # A:G - FORMATO VACACIONES (azul)
        ("SPAN", (7, 0), (9, 0)),    # H:J - PRIMER CORTE (verde)
        ("SPAN", (10, 0), (12, 0)),  # K:M - SEGUNDO CORTE (verde)
        ("SPAN", (13, 0), (13, 0)),  # N   - 24 DE DICIEMBRE UNES (verde)
        ("SPAN", (14, 0), (16, 0)),  # O:Q - TERCER CORTE (verde)
        ("SPAN", (17, 0), (17, 0)),  # R   - 31 DE DICIEMBRE UNES (verde)
        ("SPAN", (18, 0), (22, 0)),  # S:W - transparente
    ]

    ts = TableStyle(
        [
            ("BACKGROUND", (0, 0), (6, 0), colors.HexColor("#0070C0")),
            ("BACKGROUND", (7, 0), (9, 0), colors.HexColor("#00B050")),
            ("BACKGROUND", (10, 0), (12, 0), colors.HexColor("#00B050")),
            ("BACKGROUND", (13, 0), (13, 0), colors.HexColor("#00B050")),
            ("BACKGROUND", (14, 0), (16, 0), colors.HexColor("#00B050")),
            ("BACKGROUND", (17, 0), (17, 0), colors.HexColor("#00B050")),
            ("TEXTCOLOR", (0, 0), (17, 0), colors.white),
            ("FONTNAME", (0, 0), (17, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (22, 0), "CENTER"),
            ("VALIGN", (0, 0), (22, 0), "MIDDLE"),
            ("BACKGROUND", (0, 1), (22, 1), colors.HexColor("#0070C0")),
            ("TEXTCOLOR", (0, 1), (22, 1), colors.white),
            ("FONTNAME", (0, 1), (22, 1), "Helvetica-Bold"),
            ("ALIGN", (0, 1), (22, 1), "CENTER"),
            ("VALIGN", (0, 1), (22, 1), "MIDDLE"),
            ("VALIGN", (0, 2), (22, -1), "MIDDLE"),
            ("ALIGN", (0, 2), (22, -1), "CENTER"),
            ("ALIGN", (1, 2), (1, -1), "LEFT"),
            ("ALIGN", (2, 2), (2, -1), "LEFT"),
            ("ALIGN", (5, 2), (5, -1), "LEFT"),
            ("ALIGN", (21, 2), (21, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 2), (22, -1), [colors.white, colors.HexColor("#F4F7FA")]),
            ("BACKGROUND", (18, 2), (19, -1), colors.HexColor("#EBF3FA")),
            ("GRID", (0, 0), (22, -1), 0.5, colors.HexColor("#B0C4DE")),
            ("LINEBELOW", (0, 1), (22, 1), 0.75, colors.HexColor("#003366")),
            ("TOPPADDING", (0, 0), (22, -1), 2),
            ("BOTTOMPADDING", (0, 0), (22, -1), 2),
            ("LEFTPADDING", (0, 0), (22, -1), 2),
            ("RIGHTPADDING", (0, 0), (22, -1), 2),
        ]
    )
    for spec in colspan_specs:
        ts.add(*spec)

    table.setStyle(ts)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Plano UNOEE (Excel)
# --------------------------------------------------------------------------


def generar_plano_excel(rows_data: Sequence[Any], template_path: Any, output_path: Any) -> None:
    """Escribe las filas del plano sobre la plantilla Excel y guarda el resultado.

    Abre la plantilla existente y escribe a partir de la fila 2 (la fila 1 es el
    encabezado), preservando el resto de columnas.

    Mapeo de columnas (el que trae la plantilla oficial):

      - Columna A: constante ``2``.
      - Columna B: consecutivo numérico autoincremental.
      - Columna C: identificación del empleado.
      - Columna F: constante ``153``.
      - Columna G: fecha de inicio (texto ``aaaammdd``).
      - Columna H: días del período.
      - Columna I: fecha de fin (texto ``aaaammdd``).
      - Columnas J, L, S, T, U, W, X: ceros; Y: uno.

    ``output_path`` admite una ruta o un objeto con ``write`` (por ejemplo un
    ``BytesIO``), que es como lo usa la ruta para devolver el archivo sin pasar
    por disco.
    """
    from openpyxl import load_workbook

    wb = load_workbook(template_path)
    ws = wb.active

    for idx, row in enumerate(rows_data):
        excel_row = 2 + idx  # Comienza en fila 2 (fila 1 = encabezados)

        ws.cell(row=excel_row, column=1, value=2)
        ws.cell(row=excel_row, column=2, value=idx + 1)
        ws.cell(row=excel_row, column=3, value=row["identificacion"])
        ws.cell(row=excel_row, column=6, value=153)

        if row.get("fecha_inicio"):
            ws.cell(row=excel_row, column=7, value=row["fecha_inicio"])
        if row.get("fecha_fin"):
            ws.cell(row=excel_row, column=9, value=row["fecha_fin"])
        ws.cell(row=excel_row, column=8, value=row["dias"])

        ws.cell(row=excel_row, column=10, value=0)
        ws.cell(row=excel_row, column=12, value=0)
        ws.cell(row=excel_row, column=19, value=0)
        ws.cell(row=excel_row, column=20, value=0)
        ws.cell(row=excel_row, column=21, value=0)
        ws.cell(row=excel_row, column=23, value=0)
        ws.cell(row=excel_row, column=24, value=0)
        ws.cell(row=excel_row, column=25, value=1)

    wb.save(output_path)


def generar_plano_unoee(filas: Sequence[Any], template_path: Any = None) -> bytes:
    """Atajo: tablero → filas del plano → bytes del Excel."""
    plantilla = Path(template_path) if template_path else PLANTILLA_PLANO
    if not plantilla.exists():
        raise FileNotFoundError(f"No se encontró la plantilla del plano: {plantilla}")
    filas_plano = filas_plano_unoee(filas)
    logger.info("Generando el plano UNOEE con %d período(s).", len(filas_plano))
    buffer = io.BytesIO()
    generar_plano_excel(filas_plano, plantilla, buffer)
    buffer.seek(0)
    return buffer.getvalue()
