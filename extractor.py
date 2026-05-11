"""Extracción de texto desde PDF, Word, Excel y ZIP"""
from pathlib import Path
import re

# ─── Mapa de anexos SEP → tipo de documento ───────────────────────────────────
ANEXOS_SEP = {
    "9.1":    ("plano_ubicacion",       "Anexo 9.1 - Plano de ubicación del proyecto"),
    "9.2":    ("identificacion_riego",  "Anexo 9.2 - Identificación del área de riego"),
    "9.4.2":  ("pruebas_bombeo",        "Anexo 9.4.2 - Prueba de bombeo"),
    "9.4":    ("estudio_hidrologico",   "Anexo 9.4 - Análisis Hidrológico"),
    "9.5":    ("diseno_hidraulico",     "Anexo 9.5 - Diseño y cálculos hidráulicos"),
    "9.6":    ("estudios_complementarios", "Anexo 9.6 - Estudios y diseño complementarios"),
    "9.8.1":  ("cronograma",            "Anexo 9.8.1 - Cronograma"),
    "9.8":    ("especificaciones_tecnicas", "Anexo 9.8 - Especificaciones técnicas"),
    "9.9":    ("cubicaciones",          "Anexo 9.9 - Cubicaciones"),
    "9.10.1": ("presupuesto",           "Anexo 9.10.1 - Presupuesto detallado de obras"),
    "9.10.2": ("presupuesto_electrico", "Anexo 9.10.2 - Presupuesto detallado electrificación"),
    "9.10.3": ("cotizaciones_facturas", "Anexo 9.10.3 - Cotizaciones y Facturas"),
    "9.10.4": ("cotizaciones",          "Anexo 9.10.4 - Cotizaciones"),
    "9.10.5": ("declaracion_iva",       "Anexo 9.10.5 - Declaración No Contribuyente IVA"),
    "9.12.1.2": ("planos_obras_civiles","Anexo 9.12.1.2 - Planos Obras Civiles"),
    "9.12.1":   ("planos_tecnificacion","Anexo 9.12.1.1 - Planos proyecto tecnificación"),
    "9.12":     ("planos_tecnificacion","Anexo 9.12 - Planos tecnificación"),
    "9.13.1": ("memoria_superficies",   "Anexo 9.13.1 - Memoria de cálculo de superficies"),
    "9.13.2": ("estudio_suelos",        "Anexo 9.13.2 - Estudio de suelos"),
    "9.14":   ("evaluacion_social",     "Anexo 9.14 - Evaluación Social MIDESO"),
}

# Orden de búsqueda: más específico primero
ANEXOS_ORDEN = sorted(ANEXOS_SEP.keys(), key=lambda x: len(x), reverse=True)


def detectar_anexo(nombre_archivo: str) -> tuple:
    """
    Detecta el tipo de anexo desde el nombre del archivo.
    Intento 1: patrón completo "9.X.Y" (ej: 9.10.1).
    Intento 2: patrón sin "9." inicial para claves multi-nivel (ej: 10.1, 8.1, 12.1.2).
    Retorna (tipo_doc, label) o ("otro", "Documento sin clasificar").
    """
    nombre = nombre_archivo.lower()

    # Intento 1: patrón completo con "9."
    for clave in ANEXOS_ORDEN:
        patron = clave.replace(".", r"[\.\-_\s]")
        if re.search(rf"9{patron[1:]}", nombre):
            return ANEXOS_SEP[clave]

    # Intento 2: sin el "9." inicial — solo para claves multi-nivel (ej: 9.10.1 → 10.1)
    for clave in ANEXOS_ORDEN:
        sufijo = clave[2:]          # quita "9."
        if "." not in sufijo:       # evitar "1","4","5"… demasiado ambiguos
            continue
        patron = sufijo.replace(".", r"[\.\-_\s]")
        if re.search(rf"(?<!\d){patron}(?!\d)", nombre):
            return ANEXOS_SEP[clave]

    return ("otro", "Documento sin clasificar")


def extract_text(filepath: str, ext: str) -> str:
    ext = ext.lower()
    try:
        if ext == ".pdf":
            return _from_pdf(filepath)
        elif ext in (".doc", ".docx"):
            return _from_word(filepath)
        elif ext in (".xls", ".xlsx"):
            return _from_excel(filepath)
        else:
            return f"[Formato {ext} no soportado para extracción de texto automática]"
    except Exception as e:
        return f"[Error al extraer texto: {str(e)}]"


def extract_zip(zip_path: str, dest_dir: str) -> list:
    """
    Extrae un ZIP y retorna lista de dicts con info de cada archivo extraído.
    Ignora archivos ocultos, directorios y formatos no soportados.
    """
    import zipfile
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    FORMATOS_SOPORTADOS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
    archivos = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            nombre = Path(member.filename).name
            # Ignorar carpetas, archivos ocultos y formatos no soportados
            if member.is_dir():
                continue
            if nombre.startswith(".") or nombre.startswith("__"):
                continue
            ext = Path(nombre).suffix.lower()
            if ext not in FORMATOS_SOPORTADOS:
                continue

            # Extraer archivo plano (sin subcarpetas)
            destino = dest / nombre
            # Si hay duplicado, añadir sufijo
            contador = 1
            while destino.exists():
                destino = dest / f"{Path(nombre).stem}_{contador}{ext}"
                contador += 1

            with zf.open(member) as src, open(destino, "wb") as dst:
                dst.write(src.read())

            tipo_doc, label = detectar_anexo(nombre)
            texto = extract_text(str(destino), ext)

            archivos.append({
                "nombre_original": nombre,
                "filename": destino.name,
                "tipo_doc": tipo_doc,
                "label": label,
                "texto_extraido": texto[:5000],
            })

    return archivos


def _from_pdf(filepath: str) -> str:
    """Extrae texto de PDF. Si el PDF es escaneado (imagen), retorna marcador especial."""
    import fitz  # pymupdf
    doc = fitz.open(filepath)
    text_pages = []
    for page in doc:
        t = page.get_text().strip()
        if t:
            text_pages.append(t)
    doc.close()

    if text_pages:
        return "\n".join(text_pages)

    # PDF escaneado — sin texto digital
    return "__PDF_ESCANEADO__"


def render_pdf_as_images(filepath: str, max_pages: int = 4) -> list:
    """
    Renderiza páginas de un PDF como imágenes base64 para visión de Claude.
    Usa JPEG al 75% de calidad para mantener cada imagen bajo ~1 MB.
    Límite API Claude: 5 MB por imagen.
    """
    import fitz
    import base64
    MAX_BYTES_POR_IMAGEN = 4 * 1024 * 1024  # 4 MB de margen
    doc = fitz.open(filepath)
    images = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        # Zoom 1.0x (~72 dpi) — suficiente para lectura, mucho más liviano que 1.5x
        mat = fitz.Matrix(1.0, 1.0)
        pix = page.get_pixmap(matrix=mat)
        # JPEG al 75% → 5-10x más pequeño que PNG
        img_bytes = pix.tobytes("jpeg", jpg_quality=75)
        if len(img_bytes) > MAX_BYTES_POR_IMAGEN:
            # Si aún excede, reducir zoom a 0.7x
            mat2 = fitz.Matrix(0.7, 0.7)
            pix2 = page.get_pixmap(matrix=mat2)
            img_bytes = pix2.tobytes("jpeg", jpg_quality=70)
        images.append(base64.standard_b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images


def _from_word(filepath: str) -> str:
    from docx import Document
    doc = Document(filepath)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _from_excel(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    if ext == ".xls":
        return _from_xls(filepath)
    import openpyxl
    wb = openpyxl.load_workbook(filepath, data_only=True)
    lines = []
    for sheet in wb.worksheets:
        lines.append(f"=== Hoja: {sheet.title} ===")
        for row in sheet.iter_rows(values_only=True):
            row_text = " | ".join(str(c) if c is not None else "" for c in row)
            if row_text.strip(" |"):
                lines.append(row_text)
    return "\n".join(lines)


def _from_xls(filepath: str) -> str:
    import xlrd
    wb = xlrd.open_workbook(filepath)
    lines = []
    for sheet in wb.sheets():
        lines.append(f"=== Hoja: {sheet.name} ===")
        for row_idx in range(sheet.nrows):
            row = sheet.row_values(row_idx)
            row_text = " | ".join(str(c) if c != "" else "" for c in row)
            if row_text.strip(" |"):
                lines.append(row_text)
    return "\n".join(lines)
