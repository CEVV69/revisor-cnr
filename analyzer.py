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
MODELO_SONNET = "claude-sonnet-4-5"   # Análisis complejos (~5× más barato que Opus)
MODELO_HAIKU  = "claude-haiku-4-5"    # Documentos simples (~18× más barato que Opus)

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

def seleccionar_modelo(tipo_doc: str, es_escaneado: bool = False) -> str:
    """Elige el modelo según complejidad del documento."""
    if tipo_doc in DOCS_FORZAR_HAIKU:
        return MODELO_HAIKU   # Formato estandarizado — Haiku suficiente aunque sea imagen
    if es_escaneado or tipo_doc in DOCS_COMPLEJOS:
        return MODELO_SONNET
    return MODELO_HAIKU
MAX_TOKENS_HAIKU  = 2000   # Documentos simples
MAX_TOKENS_SONNET = 6000   # Documentos complejos
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
        "checklist": """EJE SUPERFICIE — es la base de todo el proyecto.
- Verifica coherencia entre la superficie declarada en la Memoria de Superficies, la
  Identificación del área de riego y lo dibujado en los planos.
- Distingue y valida: superficie física, superficie de riego ACTUAL, superficie de
  NUEVO RIEGO, superficie tecnificada. Estas definen la escala y el monto bonificable.
- La superficie de riego no puede exceder la capacidad de uso del suelo (estudio de suelos).
- La superficie no puede exceder la superficie del título de dominio (antecedentes legales).
- Si la superficie de nuevo riego o tecnificada no cuadra entre documentos, es observación mayor.""",
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
- Consultor habilitado en Registro MOP.""",
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


async def analizar_eje(eje_key: str, documentos: list, bases_texto: str = "",
                       concurso_id: str = "", feedback_concurso: list = None,
                       tipo_revision: str = "tecnica") -> dict:
    """
    Analiza un eje temático cruzando TODOS sus documentos en una sola llamada.
    Retorna dict: {observaciones: [...], docs_incluidos: [...], sin_documentos: bool}.
    """
    eje = EJES_REVISION.get(eje_key)
    if not eje:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}

    docs_eje = _documentos_del_eje(eje_key, documentos)
    docs_con_texto = [d for d in docs_eje
                      if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]

    if not docs_con_texto:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}

    client = _get_client()

    # Presupuesto de caracteres por documento (repartido)
    budget_por_doc = max(3000, MAX_CHARS_EJE_TOTAL // len(docs_con_texto))

    bloque_docs = ""
    docs_incluidos = []
    for d in docs_con_texto:
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        texto = _truncar_inteligente(d.get("texto_extraido", ""), budget_por_doc)
        bloque_docs += f"\n\n{'─'*55}\nDOCUMENTO: {label}  ({d.get('nombre_original','')})\n{'─'*55}\n{texto}"
        docs_incluidos.append({"id": d.get("id"), "nombre": d.get("nombre_original"),
                               "label": label})

    bloque_bases    = _construir_bloque_bases(bases_texto, concurso_id)
    bloque_feedback = _construir_bloque_feedback(feedback_concurso or [], eje_key)

    system_con_cache = [{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}]
    if bloque_bases.strip():
        system_con_cache.append({"type": "text", "text": bloque_bases,
                                 "cache_control": {"type": "ephemeral"}})
        bloque_bases = ""

    revision_nombre = "técnica" if tipo_revision == "tecnica" else "legal"

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
(ante la duda, no observar; máx ~10-15 observaciones).

DOCUMENTOS DEL EJE:
{bloque_docs}"""

    response = client.messages.create(
        model=MODELO_SONNET,
        max_tokens=MAX_TOKENS_SONNET,
        system=system_con_cache,
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )

    content = response.content[0].text
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

    return {"observaciones": observaciones, "docs_incluidos": docs_incluidos,
            "sin_documentos": False}


def _construir_contexto_expediente(otros_documentos: list, doc_id_actual: str) -> str:
    """
    Construye dos bloques de contexto:
    1. Manifiesto de todos los documentos presentes en el expediente.
    2. Extracto de texto de los documentos ya analizados (máx. 5, 1500 chars c/u).
    """
    if not otros_documentos:
        return ""

    resto = [d for d in otros_documentos if d.get("id") != doc_id_actual]
    if not resto:
        return ""

    # Bloque 1: manifiesto completo
    lineas = []
    for d in resto:
        label = d.get("tipo_doc_label") or d.get("tipo_doc", "Documento")
        estado = "✓ analizado" if d.get("analizado") else "pendiente de análisis"
        lineas.append(f"  • {d.get('nombre_original', '')}  [{label}] — {estado}")
    manifiesto = "\n".join(lineas)

    # Bloque 2: contenido de documentos ya analizados (hasta 5)
    analizados = [d for d in resto if d.get("analizado") and
                  d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")][:5]
    extractos = ""
    for d in analizados:
        label = d.get("tipo_doc_label") or d.get("tipo_doc", "Documento")
        texto = d.get("texto_extraido", "")[:1500]
        extractos += f"\n\n--- {label} ({d.get('nombre_original','')}) ---\n{texto}"

    contexto = f"""
EXPEDIENTE — DOCUMENTOS PRESENTES EN EL PROYECTO:
{manifiesto}

REGLA CRÍTICA DE DOCUMENTOS FALTANTES:
Antes de generar una observación indicando que "falta" o "no se adjunta" algún documento,
verifica si ya está en la lista anterior. Si aparece en el expediente (aunque sea "pendiente
de análisis"), NO generes observación por documento faltante — el documento existe,
solo aún no ha sido revisado por el sistema.
"""
    if extractos:
        contexto += f"""
CONTENIDO DE OTROS DOCUMENTOS YA ANALIZADOS (para detectar inconsistencias entre ellos):
{extractos}
"""
    return contexto


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


async def analyze_document(texto: str, tipo_doc: str, tipo_revision: str, nombre_doc: str,
                           filepath: str = None, doc_id: str = "",
                           todos_documentos: list = None,
                           bases_texto: str = "",
                           concurso_id: str = "",
                           feedback_concurso: list = None) -> list:
    tipo_nombre = TIPOS_DOC.get(tipo_doc, tipo_doc)
    revision_nombre = "técnica" if tipo_revision == "tecnica" else "legal"
    client = _get_client()

    # Detectar imagen/escaneado: marcador explícito O texto insuficiente en PDF
    texto_limpio = texto.strip()
    es_escaneado = (texto_limpio == "__PDF_ESCANEADO__" or
                    (len(texto_limpio) < MIN_CHARS_TEXTO and
                     filepath and filepath.endswith(".pdf")))
    modelo    = seleccionar_modelo(tipo_doc, es_escaneado)
    max_tokens = MAX_TOKENS_SONNET if modelo == MODELO_SONNET else MAX_TOKENS_HAIKU
    # Límite de caracteres según tipo de documento
    if tipo_doc in MAX_CHARS_POR_TIPO:
        max_chars = MAX_CHARS_POR_TIPO[tipo_doc]
    elif tipo_doc in DOCS_COMPLEJOS:
        max_chars = MAX_CHARS_COMPLEJO_DEFAULT
    else:
        max_chars = MAX_CHARS_SIMPLE

    contexto_expediente = _construir_contexto_expediente(todos_documentos or [], doc_id)
    bloque_bases    = _construir_bloque_bases(bases_texto, concurso_id)
    bloque_feedback = _construir_bloque_feedback(feedback_concurso or [], tipo_doc)

    system_con_cache = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }
    ]
    # Si hay bases, añadirlas como segundo bloque cacheado del system prompt
    # Esto evita re-enviarlas completas en cada llamada (ahorro ~90% en ese bloque)
    if bloque_bases.strip():
        system_con_cache.append({
            "type": "text",
            "text": bloque_bases,
            "cache_control": {"type": "ephemeral"}
        })
        bloque_bases = ""   # ya está en system, no repetir en el prompt de usuario

    # ── PDF escaneado o con visión forzada: usar visión de Claude ────────────
    import os as _os
    archivo_existe = filepath and filepath.endswith(".pdf") and _os.path.exists(filepath)
    if (es_escaneado or tipo_doc in DOCS_FORZAR_VISION) and archivo_existe:
        from extractor import render_pdf_as_images
        max_pags = MAX_PAGINAS_POR_TIPO.get(tipo_doc, MAX_PAGINAS_ESCANEADO)
        imagenes = render_pdf_as_images(filepath, max_pages=max_pags)

        if not imagenes:
            return [{
                "numero": 1, "categoria": "administrativa", "severidad": "informativa",
                "texto": "No fue posible leer el contenido del PDF. El archivo puede estar dañado o protegido.",
                "referencia_normativa": ""
            }]

        prompt_texto = f"""{bloque_bases}{bloque_feedback}Revisa el siguiente documento escaneado presentado en el concurso CNR.

Tipo de documento: {tipo_nombre}
Nombre del archivo: {nombre_doc}
Tipo de revisión: Revisión {revision_nombre}
{contexto_expediente}
⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles. Ej: "1.234,56" = 1234.56
Lee el contenido completo de las imágenes y genera las observaciones que correspondan."""

        content_blocks = [{"type": "text", "text": prompt_texto}]
        for img_b64 in imagenes:
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}
            })

        response = client.messages.create(
            model=modelo,
            max_tokens=max_tokens,
            system=system_con_cache,
            messages=[{"role": "user", "content": content_blocks}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )

    # ── PDF con texto o Word/Excel: análisis normal ───────────────────────────
    else:
        prompt = f"""{bloque_bases}{bloque_feedback}Revisa el siguiente documento presentado en el concurso CNR.

Tipo de documento: {tipo_nombre}
Nombre del archivo: {nombre_doc}
Tipo de revisión asignada: Revisión {revision_nombre}
{contexto_expediente}
⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles. Ej: "1.234,56" = 1234.56
Interpreta TODOS los números con esta convención antes de cualquier análisis numérico.

CONTENIDO DEL DOCUMENTO:
{_truncar_inteligente(texto, max_chars)}"""

        response = client.messages.create(
            model=modelo,
            max_tokens=max_tokens,
            system=system_con_cache,
            messages=[{"role": "user", "content": prompt}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )

    content = response.content[0].text

    # Intento 1: extraer bloque JSON completo
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            obs = data.get("observaciones", [])
            if isinstance(obs, list):
                return obs
    except json.JSONDecodeError:
        pass

    # Intento 2: el JSON está truncado — reconstruir cerrando llaves abiertas
    try:
        start = content.find("{")
        if start >= 0:
            fragmento = content[start:]
            # Contar llaves y corchetes para cerrar lo que falta
            abre_llave = fragmento.count("{")
            cierra_llave = fragmento.count("}")
            abre_corchete = fragmento.count("[")
            cierra_corchete = fragmento.count("]")
            # Cerrar strings incompletos: si hay número impar de comillas, cerrar
            if fragmento.rstrip().endswith('"') is False and not fragmento.rstrip().endswith("}"):
                fragmento = fragmento.rstrip().rstrip(",") + '"'
            fragmento += "]" * (abre_corchete - cierra_corchete)
            fragmento += "}" * (abre_llave - cierra_llave)
            data = json.loads(fragmento)
            obs = data.get("observaciones", [])
            if isinstance(obs, list) and obs:
                return obs
    except (json.JSONDecodeError, Exception):
        pass

    # Fallback: registrar como nota interna que hubo un problema de formato
    return [{
        "numero": 1,
        "categoria": "administrativa",
        "severidad": "informativa",
        "texto": "⚠️ El análisis no pudo procesarse correctamente. Intenta analizar el documento nuevamente.",
        "referencia_normativa": ""
    }]


# ─── Revisión cruzada: invalidar observaciones previas ────────────────────────

async def revisar_observaciones_previas(
    texto_nuevo: str,
    nombre_doc_nuevo: str,
    tipo_doc_nuevo: str,
    observaciones_previas: list
) -> list:
    """
    Dado el contenido de un documento recién analizado, determina cuáles
    observaciones anteriores (de otros documentos) quedan resueltas o invalidadas.
    Retorna lista de IDs de observaciones a descartar.
    """
    if not observaciones_previas or not texto_nuevo.strip() or texto_nuevo.strip() == "__PDF_ESCANEADO__":
        return []

    client = _get_client()
    tipo_nombre = TIPOS_DOC.get(tipo_doc_nuevo, tipo_doc_nuevo)

    # Construir lista de observaciones previas para el prompt
    lista_obs = ""
    for obs in observaciones_previas:
        lista_obs += f'\n- ID: {obs["id"]} | Documento: {obs.get("doc_nombre","")} | Texto: {obs["texto"][:200]}'

    prompt = f"""Se acaba de analizar un nuevo documento del expediente CNR que puede resolver observaciones anteriores.

NUEVO DOCUMENTO ANALIZADO:
Tipo: {tipo_nombre}
Nombre: {nombre_doc_nuevo}
Contenido:
{texto_nuevo[:3000]}

OBSERVACIONES ANTERIORES PENDIENTES (de otros documentos):
{lista_obs}

TAREA: Determina cuáles de las observaciones anteriores quedan RESUELTAS o INVALIDADAS
por la existencia y contenido de este nuevo documento.

Una observación queda invalidada cuando:
- Señalaba que faltaba un documento que en realidad es este nuevo documento
- Indicaba una inconsistencia que este documento aclara o corrige
- Asumía ausencia de información que este documento provee

Responde SOLO en JSON:
{{
  "invalidadas": ["id_obs_1", "id_obs_2"],
  "justificaciones": {{
    "id_obs_1": "razón breve de por qué queda resuelta"
  }}
}}

Si ninguna queda invalidada, responde: {{"invalidadas": [], "justificaciones": {{}}}}"""

    try:
        response = client.messages.create(
            model=MODELO_SONNET,
            max_tokens=800,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        content = response.content[0].text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            return data.get("invalidadas", [])
    except Exception:
        pass

    return []


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
    return response.content[0].text
