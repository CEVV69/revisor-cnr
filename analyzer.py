"""Análisis de documentos con Claude API según normativa CNR Ley 18.450"""
import os
import json
from pathlib import Path
import anthropic

def _get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no está definida en las variables de entorno")
    return anthropic.Anthropic(api_key=api_key)

BASE_DIR = Path(__file__).parent
NORMATIVA_DIR = BASE_DIR / "normativa"

# ─── Modelo y configuración de costos ─────────────────────────────────────────
# Modelos disponibles en esta cuenta (confirmado)
MODELO_SONNET = "claude-sonnet-5"     # Revisión por ejes, chat y consultas (última generación)
MODELO_HAIKU  = "claude-haiku-4-5"    # Reservado para tareas simples (actualmente sin uso activo)

# Tipos de documento que requieren mayor capacidad analítica
DOCS_COMPLEJOS = {
    "diseno_hidraulico",       # Cálculos hidráulicos
    "diseno_agronomico",       # Diseño agronómico / demanda hídrica
    "diseno_fotovoltaico",     # Sistema fotovoltaico de bombeo
    # reporte_explorador_solar → Haiku (formato estandarizado CNR, no requiere Sonnet)
    "estudio_hidrologico",     # Metodología y caudales
    "estudio_suelos",          # Capacidad de uso, clasificación
    "presupuesto",             # APU, coherencia de cifras
    "presupuesto_electrico",   # Ídem electrificación
    "evaluacion_social",       # MIDESO, cálculo socioeconómico
    "memoria_superficies",     # Geometría y cálculos de área
    "pruebas_bombeo",          # Curvas, eficiencia, datos técnicos
    "estudios_complementarios",# Variable — mejor Sonnet por precaución
}

def _texto_respuesta(response) -> str:
    """
    Extrae el texto de la respuesta de Claude. Sonnet 5 puede incluir bloques de
    'thinking' antes del texto, así que no se puede asumir content[0].text.
    """
    partes = []
    for bloque in response.content:
        if getattr(bloque, "type", None) == "text":
            partes.append(bloque.text)
        elif hasattr(bloque, "text"):
            partes.append(bloque.text)
    return "\n".join(partes).strip()


def seleccionar_modelo(tipo_doc: str, es_escaneado: bool = False) -> str:
    """Elige el modelo según complejidad del documento."""
    if tipo_doc in DOCS_FORZAR_HAIKU:
        return MODELO_HAIKU   # Formato estandarizado — Haiku suficiente aunque sea imagen
    if es_escaneado or tipo_doc in DOCS_COMPLEJOS:
        return MODELO_SONNET
    return MODELO_HAIKU
MAX_TOKENS_HAIKU  = 2000   # Documentos simples
MAX_TOKENS_SONNET = 12000  # Documentos complejos — Sonnet 5 gasta parte del cupo en thinking
MIN_CHARS_TEXTO   = 300    # Menos de esto → tratar como imagen aunque haya "texto"

# Páginas máximas para visión (PDFs escaneados / con imágenes)
MAX_PAGINAS_ESCANEADO = 5   # Mapas, planos, documentos generales
MAX_PAGINAS_POR_TIPO = {
    "reporte_explorador_solar": 15,  # 21 páginas — necesita más cobertura
    "diseno_fotovoltaico":      8,
    "diseno_hidraulico":        8,
    "diseno_agronomico":        8,
}

# Tipos que usan Haiku incluso si son escaneados (formatos estandarizados)
DOCS_FORZAR_HAIKU = {"reporte_explorador_solar"}

# Tipos que SIEMPRE usan visión (aunque tengan texto extraíble)
# porque su contenido clave está en gráficos/tablas como imágenes
DOCS_FORZAR_VISION = {"reporte_explorador_solar"}

# Límite de caracteres por tipo (optimizados por costo/calidad)
MAX_CHARS_POR_TIPO = {
    "reporte_explorador_solar": 40000,  # Haiku — 21 págs, formato CNR estandarizado
    "diseno_agronomico":        35000,  # Puede ser muy largo
    "diseno_fotovoltaico":      25000,
    "diseno_hidraulico":        25000,
    "presupuesto":              30000,  # Excel con hasta 13 hojas
    "presupuesto_electrico":    30000,
    "estudio_hidrologico":      15000,
    "estudio_suelos":           15000,
    "evaluacion_social":        12000,
    "memoria_superficies":      12000,
    "pruebas_bombeo":           12000,
    "estudios_complementarios": 12000,
}
MAX_CHARS_COMPLEJO_DEFAULT = 12000   # Sonnet para tipos complejos sin límite específico
MAX_CHARS_SIMPLE           =  5000   # Haiku para tipos simples

# ─── Carga de normativa real desde archivos ────────────────────────────────────

MAX_CHARS_POR_NORMATIVA = 4000   # ~1.000 tokens por archivo — parte más relevante va al inicio

def cargar_normativa() -> str:
    """Carga los documentos normativos disponibles en /normativa, limitando por archivo."""
    textos = []
    if not NORMATIVA_DIR.exists():
        return ""
    for archivo in sorted(NORMATIVA_DIR.glob("*.txt")):
        contenido = archivo.read_text(encoding="utf-8")
        truncado = len(contenido) > MAX_CHARS_POR_NORMATIVA
        contenido = contenido[:MAX_CHARS_POR_NORMATIVA]
        sufijo = "\n[...extracto — ver documento completo para detalles]" if truncado else ""
        textos.append(f"\n{'='*60}\n{archivo.stem}\n{'='*60}\n{contenido}{sufijo}")
    return "\n".join(textos)

NORMATIVA_CNR = cargar_normativa()

# ─── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""Eres un revisor experto de la Comisión Nacional de Riego (CNR) de Chile,
especializado en la evaluación de proyectos de riego y drenaje bajo la Ley N° 18.450.

Tienes acceso a la normativa técnica y legal oficial de la CNR:

{NORMATIVA_CNR}

═══════════════════════════════════════════════════════
CRITERIO DE REVISIÓN — LEE ESTO ANTES DE ANALIZAR
═══════════════════════════════════════════════════════
Eres un revisor técnico con criterio de ingeniero experimentado en riego, NO un
auditor burocrático. Tu objetivo central es responder tres preguntas:

  1. ¿El proyecto va a funcionar correctamente como sistema de riego?
  2. ¿Los precios y presupuesto son razonables, sin sobreprecios evidentes?
  3. ¿El diseño tiene lógica técnica y es proporcional a la escala del proyecto?

Si la respuesta a las tres es "sí", el proyecto es admisible aunque tenga imperfecciones
menores de forma. No busques defectos para justificar observaciones.

GENERA observación solo cuando cumpla AL MENOS UNO de estos criterios:
• El problema impide o compromete el funcionamiento real del sistema de riego
• Hay incumplimiento explícito y verificable de normativa CNR o bases del concurso
• El presupuesto tiene inconsistencias o sobreprecios que afectan la viabilidad
• Faltan antecedentes legales obligatorios sin los cuales no puede aprobarse
• Los datos técnicos clave (caudales, eficiencias, potencia) están fuera de rango normativo
• La información es contradictoria entre documentos de forma que afecta la coherencia técnica
• El diseño incluye elementos injustificados, desproporcionados o técnicamente inviables

NO GENERES observación cuando:
• Es un asunto de formato, presentación o estética
• La información se puede deducir del contexto o de otros documentos del expediente
• Es una diferencia menor de nomenclatura sin impacto en el contenido técnico
• Es una buena práctica recomendable pero sin base normativa obligatoria
• El detalle faltante no afecta ni la admisión ni la ejecución del proyecto
• No estás seguro — la duda no es suficiente para generar observación

REGLA DE ORO: Si un revisor experimentado aprobaría ese punto sin pedirle corrección
al consultor, NO lo marques. Prefiere omitir un problema menor a generar ruido que
el revisor va a descartar. Máximo 10-15 observaciones por documento salvo casos excepcionales.

═══════════════════════════════════════════════════════
NOTACIÓN NUMÉRICA CHILENA — OBLIGATORIO RESPETAR
═══════════════════════════════════════════════════════
- La COMA (,) es separador decimal → "34,56" = 34.56
- El PUNTO (.) es separador de miles → "1.234.567" = 1,234,567
Ejemplos: "0,4 l/s" = 0.4 l/s; "34.560 m³" = 34,560 m³; "34,560 m³" = 34.56 m³
Antes de marcar cualquier error de cálculo, interpreta los números con esta convención.
NUNCA marques como error un número correctamente escrito en notación chilena.

═══════════════════════════════════════════════════════
CHECKLIST POR TIPO DE DOCUMENTO
═══════════════════════════════════════════════════════
REVISIÓN TÉCNICA — CRITERIO DE INGENIERO:
Al revisar cada documento, aplica este juicio práctico:
  a) ¿El proyecto físicamente puede construirse y operarse con esta información?
  b) ¿Los precios unitarios son razonables para el mercado de obras de riego en Chile?
  c) ¿Las dimensiones, caudales y potencias son proporcionales a la superficie regada?
  d) ¿Hay algo que un técnico de terreno no podría ejecutar por falta de información?

Checklist técnico esencial:
- Estudio hidrológico: caudales al 85% de seguridad, fuente (DT-01/DT-02), metodología
- Demanda hídrica: ETP correcta, Kc en rango (DT-05), eficiencia ponderada (DT-04)
- Diseño hidráulico: cumplimiento especificaciones técnicas (DT-06)
- Estudio de suelos: capacidad de uso (DT-03), categoría riego
- Presupuesto: coherencia con obras, APU (DT-18) — enfócate en ítems mayores y sobreprecios
- Planos: información mínima para ejecutar la obra en terreno

REVISIÓN LEGAL (solo lo que bloquea admisión):
- Documentos de postulación: lista según IL-01 — solo faltantes reales
- Estrato del postulante: correctamente declarado (IL-10)
- F22: verificación códigos SII (18, 36, 158, 305, 611)
- Derechos de agua: vigencia y caudal suficiente para el proyecto
- Títulos de dominio: vigentes y concordantes
- OUA: acta asamblea, poder representante, listado beneficiarios (FL-07)
- Consultor: habilitado en Registro MOP

═══════════════════════════════════════════════════════
CHECKLIST ADICIONAL
═══════════════════════════════════════════════════════
- Diseño agronómico: módulo de riego, demanda neta y bruta, eficiencia de aplicación,
  caudal de diseño, tiempo de riego, dotación por hectárea, concordancia con estudio de suelos
- Diseño fotovoltaico: potencia requerida vs instalada, curva bomba vs curva sistema,
  punto de operación, radiación usada, autonomía, protecciones eléctricas (SEC)
- Reporte Explorador Solar: radiación en plano inclinado, PR (Performance Ratio),
  energía generada vs demanda del sistema de bombeo, concordancia con diseño fotovoltaico

═══════════════════════════════════════════════════════
FORMATO DE RESPUESTA
═══════════════════════════════════════════════════════
CRÍTICO — REGLA ABSOLUTA DEL FORMATO:
Cada observación describe ÚNICAMENTE un incumplimiento, deficiencia o dato faltante.
NUNCA menciones dentro del texto de una observación lo que sí cumple, lo que sí está
correcto, ni hagas frases como "si bien X cumple, falta Y". Si un aspecto cumple,
simplemente NO generes observación para ese aspecto. Cero validaciones positivas en observaciones.

Responde SIEMPRE en formato JSON exacto:
{{
  "observaciones": [
    {{
      "numero": 1,
      "categoria": "técnica|legal|presupuesto|administrativa",
      "severidad": "mayor|menor|informativa",
      "texto": "Descripción directa de qué falta o qué está incorrecto y por qué importa",
      "referencia_normativa": "IL-01, DT-04, Art. X Ley 18.450, etc."
    }}
  ],
  "resumen": "Evaluación general del documento en 2-3 oraciones"
}}

Severidades:
- mayor: impide la admisión del proyecto, debe subsanarse obligatoriamente
- menor: debe corregirse pero no impide la admisión
- informativa: recomendación sin impacto en admisión (úsala con moderación)

REDACCIÓN DEL CAMPO "texto" (OBLIGATORIO):
- BREVE y DIRECTO: máximo 2-3 líneas. No relates antecedentes largos ni contexto;
  ve directo a qué falta o qué está mal. Escribe como un revisor CNR redacta una
  observación para el SEP, no como un informe.
- CIERRE OBLIGATORIO: cada observación (mayor o menor) DEBE terminar con una de estas
  dos instrucciones explícitas, según corresponda:
    • "Debe aclarar."   → cuando se requiere precisar o resolver una discrepancia/ambigüedad.
    • "Debe justificar." → cuando se requiere fundamento técnico o normativo adicional.
  Las notas informativas no requieren este cierre.

Si el documento está correcto o cumple con lo esencial, devuelve lista vacía en observaciones."""


TIPOS_DOC = {
    "memoria_explicativa":    "Memoria explicativa del proyecto",
    "estudio_hidrologico":    "Estudio hidrológico",
    "diseno_hidraulico":      "Diseño hidráulico de obras",
    "diseno_agronomico":      "Diseño agronómico",
    "diseno_fotovoltaico":    "Diseño fotovoltaico",
    "reporte_explorador_solar": "Reporte Explorador Solar CNR",
    "estudio_suelos":         "Estudio de suelos y capacidad de uso",
    "presupuesto":            "Presupuesto y análisis de precios unitarios",
    "presupuesto_electrico":  "Presupuesto sistema eléctrico/fotovoltaico",
    "planos":                 "Planos y especificaciones técnicas",
    "evaluacion_social":      "Evaluación socioeconómica",
    "antecedentes_legales":   "Antecedentes legales (derechos de agua, títulos)",
    "lista_beneficiarios":    "Lista de beneficiarios",
    "otro":                   "Documento complementario"
}


# ─── EJES DE REVISIÓN TEMÁTICA ─────────────────────────────────────────────────
# Cada eje cruza varios documentos complementarios y los revisa en conjunto.
# tipo_docs: qué documentos alimentan el eje. checklist: guía específica para el prompt.

EJES_REVISION = {
    "superficie": {
        "nombre": "Superficie",
        "emoji": "📐",
        "tipo_docs": ["memoria_superficies", "identificacion_riego", "planos_tecnificacion",
                      "planos_obras_civiles", "estudio_suelos", "antecedentes_legales"],
        "checklist": """EJE SUPERFICIE — es la base técnica de todo el proyecto.
El FOCO de este eje es el CÁLCULO de superficies, no los papeles legales. Céntrate en:

1. CÁLCULO DE LA SUPERFICIE (lo más importante):
   - Revisa el método y los números de la Memoria de Cálculo de Superficies: cómo se obtuvo
     cada superficie, coherencia geométrica (polígonos, coordenadas, sumatorias de cuarteles).
   - Verifica que las sumas parciales cuadren con los totales declarados.
   - La superficie de la memoria debe coincidir con la dibujada/acotada en los planos y con
     la Identificación del área de riego.

2. TIPOS DE SUPERFICIE — distíngue y valida cada una (son distintas y clave para el bono):
   - Superficie física (predial total).
   - Superficie de riego ACTUAL (la que ya se riega hoy).
   - Superficie de NUEVO RIEGO (la que el proyecto incorpora) — revisa cómo se calculó, es
     la que más incide en el monto bonificable.
   - Superficie tecnificada / mejorada.
   Si estos valores no cuadran entre memoria, planos e identificación de riego → observación mayor.

3. CONSISTENCIA CON EL RESTO DEL PROYECTO:
   - Esta superficie es el insumo del eje Agronómico (demanda) y del Presupuesto (costo/ha).
   - La superficie de riego no debe exceder la capacidad de uso del suelo (estudio de suelos).

4. TOPE LEGAL (verificación SECUNDARIA, no el foco):
   - La superficie no debe exceder la del título de dominio. Si el título está EN TRÁMITE y las
     bases lo permiten, NO es observación — a lo sumo una NOTA. No conviertas este eje en una
     revisión legal; para eso está el eje Legal.""",
    },
    "agronomico": {
        "nombre": "Diseño Agronómico",
        "emoji": "🌱",
        "tipo_docs": ["diseno_agronomico", "estudio_suelos", "memoria_superficies"],
        "checklist": """EJE AGRONÓMICO.
- Cultivos declarados coherentes con la zona y el estudio de suelos.
- Kc en rango (DT-05), ETP correcta, demanda neta y bruta bien calculadas.
- Eficiencia de aplicación y eficiencia ponderada (DT-04) razonables para el método de riego.
- Módulo de riego, caudal de diseño, tiempo de riego y dotación por hectárea consistentes
  con la superficie del eje Superficie.
- La demanda hídrica resultante es el insumo del eje Hidráulico e Hidrológico: debe cerrar.""",
    },
    "hidrologico": {
        "nombre": "Hidrológico",
        "emoji": "💧",
        "tipo_docs": ["estudio_hidrologico", "pruebas_bombeo", "antecedentes_legales"],
        "checklist": """EJE HIDROLÓGICO.
- Caudal disponible al 85% de seguridad, fuente y metodología (DT-01/DT-02).
- El derecho de agua (antecedentes legales) debe respaldar el caudal usado en el diseño.
- La prueba de bombeo (si aplica) confirma el caudal y nivel dinámico del pozo.
- El agua disponible debe cubrir la demanda hídrica del eje Agronómico. Si no la cubre,
  el proyecto no es viable — observación mayor.""",
    },
    "hidraulico": {
        "nombre": "Diseño Hidráulico",
        "emoji": "🔧",
        "tipo_docs": ["diseno_hidraulico", "planos_tecnificacion", "especificaciones_tecnicas",
                      "pruebas_bombeo"],
        "checklist": """EJE HIDRÁULICO.
- Caudal de diseño coherente con la demanda del eje Agronómico.
- Nodos, tuberías, diámetros, presiones y velocidades dentro de norma (DT-06).
- Verifica que lo dibujado en los planos (nodos, trazado de tuberías) coincida con los
  cálculos del diseño hidráulico.
- Selección de bomba coherente con la prueba de bombeo y con la potencia del eje Energético.
- Especificaciones técnicas respaldan los materiales del diseño.""",
    },
    "energetico": {
        "nombre": "Energético / Fotovoltaico",
        "emoji": "☀️",
        "tipo_docs": ["diseno_fotovoltaico", "reporte_explorador_solar", "presupuesto_electrico",
                      "diseno_hidraulico"],
        "checklist": """EJE ENERGÉTICO / FOTOVOLTAICO.
- Potencia requerida por la bomba (eje Hidráulico) vs potencia instalada del sistema FV.
- Curva de la bomba vs curva del sistema, punto de operación.
- Radiación del Explorador Solar coherente con el diseño FV; energía generada cubre la
  demanda de bombeo.
- Protecciones eléctricas y normativa SEC.
- El presupuesto eléctrico corresponde a los equipos del diseño FV.""",
    },
    "obras_civiles": {
        "nombre": "Obras Civiles",
        "emoji": "🏗️",
        "tipo_docs": ["planos_obras_civiles", "especificaciones_tecnicas", "cubicaciones"],
        "checklist": """EJE OBRAS CIVILES.
- Obras (bocatomas, acumuladores, revestimientos, cámaras) bien definidas y constructibles.
- Las cubicaciones corresponden a las dimensiones de los planos de obras civiles.
- Especificaciones técnicas respaldan los materiales y procedimientos.
- Constructibilidad: ¿un contratista podría ejecutar con esta información?""",
    },
    "presupuesto": {
        "nombre": "Presupuesto y Costos",
        "emoji": "💰",
        "tipo_docs": ["presupuesto", "presupuesto_electrico", "cubicaciones",
                      "cotizaciones_facturas", "cotizaciones", "planos_tecnificacion",
                      "planos_obras_civiles"],
        "checklist": """EJE PRESUPUESTO Y COSTOS.
- Las partidas del presupuesto corresponden a las obras dibujadas y cubicadas.
- Cantidades del presupuesto cuadran con las cubicaciones.
- Precios unitarios (APU, DT-18) razonables para el mercado chileno — detecta SOBREPRECIOS
  y también precios anormalmente bajos.
- Cotizaciones/facturas respaldan los ítems relevantes.
- Costo por hectárea proporcional a la escala del proyecto. Nada injustificado ni desproporcionado.""",
    },
    "legal": {
        "nombre": "Legal / Administrativo",
        "emoji": "⚖️",
        "tipo_docs": ["antecedentes_legales", "declaracion_iva", "lista_beneficiarios"],
        "checklist": """EJE LEGAL / ADMINISTRATIVO.
- Documentos de postulación según IL-01 — solo faltantes reales.
- Derechos de agua vigentes y con caudal suficiente.
- Títulos de dominio vigentes y concordantes con la superficie.
- Estrato del postulante (IL-10), F22 con códigos SII correctos.
- OUA: acta de asamblea, poder del representante, listado de beneficiarios (FL-07).
- Consultor habilitado en Registro MOP.
- IMPORTANTE: documentos EN TRÁMITE (títulos, regularización de derechos, etc.) que las bases
  del concurso permiten postular en esa condición NO son observación — a lo sumo NOTA informativa.
  Verifica siempre lo que permiten las bases antes de marcar un antecedente en trámite.""",
    },
    "coherencia": {
        "nombre": "Coherencia Global",
        "emoji": "🔗",
        "tipo_docs": [],   # usa TODOS los documentos del proyecto
        "checklist": """EJE COHERENCIA GLOBAL — cierre transversal de todo el expediente.
Este eje NO revisa un documento; verifica que TODO el proyecto sea internamente coherente:
- Superficie ↔ demanda hídrica ↔ caudal disponible ↔ caudal de diseño ↔ presupuesto.
- La superficie de la memoria coincide con la de los planos y la identificación de riego.
- El caudal de diseño no excede el derecho de agua ni el caudal disponible al 85%.
- La potencia del sistema FV cubre la bomba del diseño hidráulico.
- El presupuesto corresponde a las obras dibujadas y cubicadas.
- El monto solicitado de bonificación es proporcional a la superficie de nuevo riego.
Marca cualquier CONTRADICCIÓN entre documentos. Este es el eje que atrapa los errores
que se escapan al revisar documento por documento.""",
    },
}

# Orden de presentación de los ejes
EJES_ORDEN = ["superficie", "agronomico", "hidrologico", "hidraulico", "energetico",
              "obras_civiles", "presupuesto", "legal", "coherencia"]

# Presupuesto total de caracteres para el prompt combinado de un eje
MAX_CHARS_EJE_TOTAL = 45000


def _documentos_del_eje(eje_key: str, documentos: list) -> list:
    """Retorna los documentos del proyecto que alimentan un eje."""
    eje = EJES_REVISION.get(eje_key)
    if not eje:
        return []
    # Coherencia global usa todos los documentos con texto
    if eje_key == "coherencia":
        return [d for d in documentos
                if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]
    tipos = set(eje["tipo_docs"])
    return [d for d in documentos if d.get("tipo_doc") in tipos]


MAX_IMG_EJE = 10   # tope de imágenes (páginas) por revisión de eje, para controlar costo


async def analizar_eje(eje_key: str, documentos: list, bases_texto: str = "",
                       concurso_id: str = "", feedback_concurso: list = None,
                       tipo_revision: str = "tecnica", ruta_uploads: str = None) -> dict:
    """
    Analiza un eje temático cruzando TODOS sus documentos en una sola llamada.
    Usa texto extraído + VISIÓN para documentos escaneados/planos (si el archivo existe).
    Retorna dict: {observaciones: [...], docs_incluidos: [...], sin_documentos: bool}.
    """
    import os as _os
    eje = EJES_REVISION.get(eje_key)
    if not eje:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}

    docs_eje = _documentos_del_eje(eje_key, documentos)

    # Separar documentos con texto de documentos-imagen (escaneados / planos)
    docs_texto  = []
    docs_imagen = []   # (doc, filepath)
    for d in docs_eje:
        t = d.get("texto_extraido", "").strip()
        es_imagen = (t == "__PDF_ESCANEADO__" or len(t) < MIN_CHARS_TEXTO)
        if (es_imagen and ruta_uploads and eje_key != "coherencia"
                and d.get("filename", "").lower().endswith(".pdf")):
            fp = _os.path.join(ruta_uploads, d["filename"])
            if _os.path.exists(fp):
                docs_imagen.append((d, fp))
                continue
        if t not in ("", "__PDF_ESCANEADO__"):
            docs_texto.append(d)

    if not docs_texto and not docs_imagen:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}

    client = _get_client()

    # Bloque de texto de los documentos con texto (presupuesto repartido)
    budget_por_doc = max(3000, MAX_CHARS_EJE_TOTAL // max(1, len(docs_texto)))
    bloque_docs = ""
    docs_incluidos = []
    for d in docs_texto:
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        texto = _truncar_inteligente(d.get("texto_extraido", ""), budget_por_doc)
        bloque_docs += f"\n\n{'─'*55}\nDOCUMENTO: {label}  ({d.get('nombre_original','')})\n{'─'*55}\n{texto}"
        docs_incluidos.append({"id": d.get("id"), "nombre": d.get("nombre_original"),
                               "label": label})

    # Renderizar imágenes de los documentos escaneados/planos (con tope global)
    from extractor import render_pdf_as_images
    imagenes_por_doc = []
    restante = MAX_IMG_EJE
    for d, fp in docs_imagen:
        if restante <= 0:
            break
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        pags = min(restante, MAX_PAGINAS_POR_TIPO.get(d.get("tipo_doc"), 4))
        try:
            imgs = render_pdf_as_images(fp, max_pages=pags)
        except Exception:
            imgs = []
        if imgs:
            imagenes_por_doc.append((label, d.get("nombre_original", ""), imgs))
            restante -= len(imgs)
            docs_incluidos.append({"id": d.get("id"), "nombre": d.get("nombre_original"),
                                   "label": label + " (imagen)"})

    if not bloque_docs and not imagenes_por_doc:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}

    bloque_bases    = _construir_bloque_bases(bases_texto, concurso_id)
    bloque_feedback = _construir_bloque_feedback(feedback_concurso or [], eje_key)

    system_con_cache = [{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}]
    if bloque_bases.strip():
        system_con_cache.append({"type": "text", "text": bloque_bases,
                                 "cache_control": {"type": "ephemeral"}})
        bloque_bases = ""

    revision_nombre = "técnica" if tipo_revision == "tecnica" else "legal"

    nota_imagenes = ""
    if imagenes_por_doc:
        nombres_img = ", ".join(f"{lbl} ({nom})" for lbl, nom, _ in imagenes_por_doc)
        nota_imagenes = (f"\n\nADEMÁS, al final se adjuntan como IMÁGENES estos documentos "
                         f"(planos o escaneados) — analízalos visualmente: {nombres_img}")

    prompt = f"""{bloque_bases}{bloque_feedback}Realiza una REVISIÓN POR EJE TEMÁTICO del expediente CNR.

EJE A REVISAR: {eje['nombre']}
Tipo de revisión: Revisión {revision_nombre}

{eje['checklist']}

⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles. Ej: "1.234,56" = 1234.56
Interpreta TODOS los números con esta convención.

INSTRUCCIÓN CLAVE: Estás revisando VARIOS documentos complementarios juntos. Tu tarea es
detectar problemas del eje considerando la RELACIÓN entre ellos, no cada uno por separado.
Presta especial atención a incoherencias entre documentos. Aplica el criterio de las tres
preguntas (¿funciona?, ¿precios razonables?, ¿diseño con lógica?) y la regla de oro
(ante la duda, no observar; máx ~10-15 observaciones).{nota_imagenes}

DOCUMENTOS DEL EJE (texto):
{bloque_docs if bloque_docs else '(Los documentos de este eje se adjuntan como imágenes más abajo.)'}"""

    # Construir contenido: texto + imágenes de los documentos escaneados/planos
    content_blocks = [{"type": "text", "text": prompt}]
    for label, nombre, imgs in imagenes_por_doc:
        content_blocks.append({"type": "text",
                               "text": f"\n═══ IMÁGENES: {label} ({nombre}) ═══"})
        for b64 in imgs:
            content_blocks.append({"type": "image",
                                   "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": b64}})

    response = client.messages.create(
        model=MODELO_SONNET,
        max_tokens=MAX_TOKENS_SONNET,
        system=system_con_cache,
        messages=[{"role": "user", "content": content_blocks}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )

    content = _texto_respuesta(response)
    observaciones = []
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            obs = data.get("observaciones", [])
            if isinstance(obs, list):
                observaciones = obs
    except json.JSONDecodeError:
        # Reintento cerrando estructuras abiertas
        try:
            frag = content[content.find("{"):]
            frag += "]" * (frag.count("[") - frag.count("]"))
            frag += "}" * (frag.count("{") - frag.count("}"))
            data = json.loads(frag)
            observaciones = data.get("observaciones", []) or []
        except Exception:
            observaciones = []

    if not observaciones:
        print(f"⚠️ Eje '{eje_key}': 0 observaciones — stop_reason={response.stop_reason}, "
              f"content_len={len(content)}, preview={content[:200]!r}")

    return {"observaciones": observaciones, "docs_incluidos": docs_incluidos,
            "sin_documentos": False}


async def chatear_eje(eje_key: str, documentos: list, observaciones_eje: list,
                      historial: list, mensaje: str, bases_texto: str = "",
                      concurso_id: str = "") -> str:
    """
    Chat de refinamiento sobre un eje ya revisado. El revisor debate una observación
    y la IA responde con el contexto completo del eje (documentos + observaciones + bases).
    """
    eje = EJES_REVISION.get(eje_key)
    if not eje:
        return "Eje no válido."

    client = _get_client()

    # Contexto de documentos del eje (presupuesto acotado para controlar costo)
    docs_eje = _documentos_del_eje(eje_key, documentos)
    docs_con_texto = [d for d in docs_eje
                      if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]
    budget = max(2500, 25000 // max(1, len(docs_con_texto)))
    bloque_docs = ""
    for d in docs_con_texto:
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        bloque_docs += f"\n\n--- {label} ({d.get('nombre_original','')}) ---\n{_truncar_inteligente(d.get('texto_extraido',''), budget)}"

    # Observaciones actuales del eje
    bloque_obs = ""
    for i, o in enumerate(observaciones_eje, 1):
        bloque_obs += f"\n[{i}] ({o.get('severidad','')}) {o.get('texto','')}"
    if not bloque_obs:
        bloque_obs = "\n(No hay observaciones registradas para este eje todavía.)"

    bloque_bases = _construir_bloque_bases(bases_texto, concurso_id)
    system_con_cache = [{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}]
    if bloque_bases.strip():
        system_con_cache.append({"type": "text", "text": bloque_bases,
                                 "cache_control": {"type": "ephemeral"}})

    # Reconstruir la conversación previa como turnos
    mensajes = []
    contexto_inicial = f"""Estás asistiendo a un revisor CNR en el eje de revisión "{eje['nombre']}".
Ya realizaste una revisión de este eje. Ahora el revisor quiere DEBATIR contigo las
observaciones: aclarar, corregir, reclasificar (ej. bajar una observación a nota si las
bases lo permiten) o profundizar en un punto técnico.

{eje['checklist']}

⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles.

DOCUMENTOS DEL EJE:{bloque_docs}

OBSERVACIONES ACTUALES DEL EJE:{bloque_obs}

Responde de forma directa y práctica. Si el revisor tiene razón (ej. un antecedente en
trámite que las bases permiten), reconócelo y sugiere la acción concreta (descartar la
observación, bajarla a nota, o editarla). Si mantienes tu criterio, explica por qué con
fundamento normativo. Sé breve y concreto."""

    mensajes.append({"role": "user", "content": contexto_inicial})
    mensajes.append({"role": "assistant", "content": "Entendido. Dime qué observación quieres revisar o qué duda tienes sobre este eje."})

    for turno in historial[-10:]:   # últimos 10 turnos para acotar tokens
        rol = "user" if turno.get("rol") == "revisor" else "assistant"
        mensajes.append({"role": rol, "content": turno.get("texto", "")})

    mensajes.append({"role": "user", "content": mensaje})

    response = client.messages.create(
        model=MODELO_SONNET,
        max_tokens=4000,
        system=system_con_cache,
        messages=mensajes,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    texto = _texto_respuesta(response)
    if not texto:
        print(f"⚠️ Chat eje '{eje_key}': respuesta vacía — stop_reason={response.stop_reason}")
    return texto


MAX_CHARS_BASES = 85000   # texto completo de bases — se cachea en prompt para reducir costo


def _truncar_inteligente(texto: str, max_chars: int) -> str:
    """
    Para documentos largos: toma 75% del inicio + 25% del final.
    Así captura tanto la introducción/metodología como las conclusiones/resultados.
    """
    if len(texto) <= max_chars:
        return texto
    inicio = int(max_chars * 0.75)
    fin = max_chars - inicio
    omitidos = len(texto) - max_chars
    return (texto[:inicio]
            + f"\n\n[... {omitidos:,} caracteres omitidos — documento muy largo ...]\n\n"
            + texto[-fin:])

def _construir_bloque_bases(bases_texto: str, concurso_id: str) -> str:
    """Construye el bloque de contexto con las bases del concurso."""
    if not bases_texto or not bases_texto.strip():
        return ""
    texto = bases_texto.strip()
    truncado = len(texto) > MAX_CHARS_BASES
    if truncado:
        texto = texto[:MAX_CHARS_BASES]
    bloque = f"""
{'═'*60}
BASES DEL CONCURSO {concurso_id} — PRIORIDAD MÁXIMA
{'═'*60}
Las siguientes bases son específicas de este concurso y tienen PRIORIDAD sobre
la normativa general. Verifica su cumplimiento en el documento analizado:

{texto}
"""
    if truncado:
        bloque += "\n[... texto de bases truncado por longitud — se muestran los primeros 20.000 caracteres]\n"
    bloque += "\n"
    return bloque


def _construir_bloque_feedback(feedback: list, tipo_doc_actual: str) -> str:
    """
    Construye el bloque de aprendizaje basado en decisiones reales de revisores.
    Prioriza feedback del mismo tipo de documento, max 10 aprobadas + 10 descartadas.
    """
    if not feedback:
        return ""

    # Ordenar: mismo tipo_doc primero, luego por fecha más reciente
    def prioridad(f):
        es_mismo = f.get("tipo_doc") == tipo_doc_actual
        return (0 if es_mismo else 1, f.get("fecha", ""))

    feedback_ord = sorted(feedback, key=prioridad)

    aprobadas = [f for f in feedback_ord if f.get("accion") == "aprobada"][:10]
    descartadas = [f for f in feedback_ord if f.get("accion") == "descartada"][:10]

    if not aprobadas and not descartadas:
        return ""

    bloque = f"\n{'═'*60}\nAPRENDIZAJE DE REVISIONES ANTERIORES EN ESTE CONCURSO\n{'═'*60}\n"
    bloque += "(Decisiones reales de revisores — calibra tu criterio con esto)\n"

    if aprobadas:
        bloque += "\nOBSERVACIONES VALIDADAS POR EL REVISOR (eran correctas, comunícalas al postulante):\n"
        for f in aprobadas:
            tipo = f.get("tipo_doc", "")
            bloque += f"  ✓ [{tipo}] {f.get('texto_obs', '')[:150]}\n"

    if descartadas:
        bloque += "\nOBSERVACIONES DESCARTADAS POR EL REVISOR (no eran relevantes — evita este tipo):\n"
        for f in descartadas:
            tipo = f.get("tipo_doc", "")
            bloque += f"  ✗ [{tipo}] {f.get('texto_obs', '')[:150]}\n"

    bloque += "\n"
    return bloque


# ─── Consulta libre sobre el expediente ───────────────────────────────────────

async def consultar_expediente(pregunta: str, documentos: list) -> str:
    """
    Responde una pregunta del revisor usando los documentos del expediente
    y la normativa CNR disponible.
    """
    client = _get_client()

    # Construir contexto con texto de todos los documentos analizados
    contexto_docs = ""
    for doc in documentos:
        texto = doc.get("texto_extraido", "").strip()
        if texto and texto != "__PDF_ESCANEADO__":
            label = doc.get("tipo_doc_label") or doc.get("tipo_doc", "Documento")
            contexto_docs += f"\n\n--- {label} ({doc.get('nombre_original','')}) ---\n{texto[:3000]}"

    if not contexto_docs:
        return "No hay documentos con texto extraíble en este expediente. Sube los archivos y asegúrate de que tengan contenido legible."

    prompt = f"""Un revisor CNR tiene la siguiente consulta sobre este expediente:

PREGUNTA DEL REVISOR:
{pregunta}

DOCUMENTOS DISPONIBLES EN EL EXPEDIENTE:
{contexto_docs}

Responde la pregunta del revisor de forma clara y fundamentada, citando la normativa CNR aplicable cuando corresponda.
Si la respuesta requiere revisar algo que no está en los documentos disponibles, indícalo explícitamente.
Sé directo y práctico — el revisor necesita saber qué hacer con esta información."""

    response = client.messages.create(
        model=MODELO_SONNET,
        max_tokens=1500,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    return _texto_respuesta(response)
