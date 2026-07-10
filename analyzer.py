"""Análisis de documentos con Claude API según normativa CNR Ley 18.450"""
import os
import json
import re
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
  instrucciones explícitas, según corresponda:
    • "Debe aclarar."   → cuando se requiere precisar o resolver una discrepancia/ambigüedad.
    • "Debe justificar." → cuando se requiere fundamento técnico o normativo adicional.
    • "Se sugiere declarar no admitido." → SOLO cuando falta un documento obligatorio
      exigido por las bases como imprescindible para postular.
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


# ─── ÍTEMS DEL SEP ─────────────────────────────────────────────────────────────
# Método de revisión alternativo: por los ítems tal como se ingresan al Sistema
# Electrónico de Postulación (SEP), que coinciden con el agrupamiento de archivos que
# hace el consultor. Cada ítem revisa su(s) documento(s) y produce observaciones tageadas
# con el ítem, para facilitar el ingreso al SEP. Convive con el método por ejes.
ITEMS_SEP = {
    "plano_ubicacion": {
        "nombre": "Plano de ubicación del proyecto", "emoji": "📍",
        "tipo_docs": ["plano_ubicacion"],
        "checklist": "Verifica que el plano ubique el predio con coordenadas, comuna y acceso, "
                     "coherente con los demás antecedentes del expediente.",
    },
    "identificacion_riego": {
        "nombre": "Identificación del área de riego", "emoji": "🗺️",
        "tipo_docs": ["identificacion_riego"],
        "checklist": "Verifica que delimite el área de riego actual y de nuevo riego, con "
                     "superficies coherentes con la memoria de cálculo y los planos.",
    },
    "hidrologico": {
        "nombre": "Análisis Hidrológico", "emoji": "💧",
        "tipo_docs": ["estudio_hidrologico"],
        "checklist": "Caudal disponible al 85% de seguridad, fuente y metodología (DT-01/DT-02). "
                     "Debe respaldar el caudal usado en el diseño y cubrir la demanda hídrica.",
    },
    "pruebas_bombeo": {
        "nombre": "Pruebas de Bombeo", "emoji": "⛲",
        "tipo_docs": ["pruebas_bombeo"],
        "checklist": "Caudal, nivel dinámico y eficiencia del pozo. Debe respaldar el caudal y "
                     "la selección de bomba del diseño hidráulico.",
    },
    "diseno_hidraulico": {
        "nombre": "Diseño y cálculos hidráulicos", "emoji": "🔧",
        "tipo_docs": ["diseno_hidraulico", "diseno_agronomico", "diseno_fotovoltaico",
                      "reporte_explorador_solar"],
        "checklist": "Demanda agronómica, caudal de diseño, diámetros, presiones y velocidades "
                     "en norma (DT-04/05/06). Sistema FV coherente con la potencia de la bomba.",
    },
    "estudios_complementarios": {
        "nombre": "Estudios y diseños complementarios", "emoji": "📚",
        "tipo_docs": ["estudios_complementarios"],
        "checklist": "Verifica pertinencia y consistencia técnica de los estudios complementarios "
                     "con el resto del proyecto.",
    },
    "especificaciones_tecnicas": {
        "nombre": "Especificaciones técnicas de construcción e instalación", "emoji": "📋",
        "tipo_docs": ["especificaciones_tecnicas"],
        "checklist": "Deben respaldar los materiales y procedimientos del diseño y las obras "
                     "civiles. Sin especificaciones no hay respaldo constructivo.",
    },
    "cronograma": {
        "nombre": "Cronograma", "emoji": "📅",
        "tipo_docs": ["cronograma"],
        "checklist": "Plazos coherentes con la magnitud de las obras y con el período de "
                     "ejecución que permiten las bases.",
    },
    "presupuesto": {
        "nombre": "Presupuesto detallado de obras", "emoji": "💰",
        "tipo_docs": ["presupuesto"],
        "checklist": "Partidas corresponden a las obras cubicadas; precios unitarios (APU, DT-18) "
                     "de mercado, sin sobreprecios ni valores anormalmente bajos.",
    },
    "presupuesto_electrico": {
        "nombre": "Presupuesto detallado electrificación", "emoji": "🔌",
        "tipo_docs": ["presupuesto_electrico"],
        "checklist": "Corresponde a los equipos del diseño eléctrico/FV; precios razonables y "
                     "cantidades consistentes con el diseño.",
    },
    "cotizaciones_facturas": {
        "nombre": "Cotizaciones y Facturas", "emoji": "🧾",
        "tipo_docs": ["cotizaciones_facturas", "cotizaciones"],
        "checklist": "Respaldan los ítems relevantes del presupuesto; vigentes y coherentes con "
                     "los precios usados.",
    },
    "declaracion_iva": {
        "nombre": "Declaración No Contribuyente IVA", "emoji": "📄",
        "tipo_docs": ["declaracion_iva"],
        "checklist": "Verifica que la declaración corresponda al postulante y sea coherente con "
                     "el tratamiento del IVA en el presupuesto.",
    },
    "planos_tecnificacion": {
        "nombre": "Planos Proyecto tecnificación", "emoji": "📐",
        "tipo_docs": ["planos_tecnificacion"],
        "checklist": "Trazado de redes, nodos y equipos coherente con el diseño hidráulico y las "
                     "superficies. Analiza el plano visualmente.",
    },
    "planos_obras_civiles": {
        "nombre": "Planos Obras Civiles proy. de tecnificación", "emoji": "🏗️",
        "tipo_docs": ["planos_obras_civiles"],
        "checklist": "Caseta, electrificación, embalses/estanques bien definidos y acotados, "
                     "coherentes con cubicaciones y presupuesto. Analiza el plano visualmente.",
    },
    "memoria_superficies": {
        "nombre": "Memoria de cálculo de superficies", "emoji": "📏",
        "tipo_docs": ["memoria_superficies"],
        "checklist": "Método y números del cálculo de superficies; sumas parciales cuadran con "
                     "totales; coincide con planos e identificación del área de riego.",
    },
    "estudio_suelos": {
        "nombre": "Estudio de suelo - Informe de asimilación", "emoji": "🌱",
        "tipo_docs": ["estudio_suelos"],
        "checklist": "Clasificación y capacidad de uso (DT-03); la superficie de riego no debe "
                     "exceder la capacidad de uso del suelo.",
    },
}

# Orden de presentación de los ítems SEP (tal como se ingresan en el sistema)
ITEMS_ORDEN = ["plano_ubicacion", "identificacion_riego", "hidrologico", "pruebas_bombeo",
               "diseno_hidraulico", "estudios_complementarios", "especificaciones_tecnicas",
               "cronograma", "presupuesto", "presupuesto_electrico", "cotizaciones_facturas",
               "declaracion_iva", "planos_tecnificacion", "planos_obras_civiles",
               "memoria_superficies", "estudio_suelos"]


# ─── RESUMEN DEL PROYECTO (ficha tipo formulario) ──────────────────────────────
# Campos mínimos según la ficha del revisor. La IA autocompleta lo que puede; el
# revisor completa/edita el resto. tipo: "text" | "textarea" | "sino".
RESUMEN_SECCIONES = [
    {"titulo": "Identificación", "campos": [
        {"key": "codigo",          "label": "Código proyecto",     "tipo": "text", "auto": "codigo_sep"},
        {"key": "postulante",      "label": "Postulante",          "tipo": "text", "auto": "postulante"},
        {"key": "comuna",          "label": "Comuna",              "tipo": "text"},
        {"key": "consultor",       "label": "Consultor",           "tipo": "text"},
        {"key": "nombre_proyecto", "label": "Nombre del proyecto", "tipo": "textarea", "auto": "nombre"},
        {"key": "estrato",         "label": "Estrato",             "tipo": "text"},
    ]},
    {"titulo": "1. Proyecto / Legal", "campos": [
        {"key": "servidumbres", "label": "Servidumbres", "tipo": "sino"},
        {"key": "indap",        "label": "INDAP",        "tipo": "sino"},
        {"key": "rut",          "label": "RUT",          "tipo": "text"},
        {"key": "art4",         "label": "Art. 4°",      "tipo": "sino"},
        {"key": "coord_e",      "label": "Coordenada E", "tipo": "text"},
        {"key": "coord_n",      "label": "Coordenada N", "tipo": "text"},
        {"key": "coord_h",      "label": "Huso (H)",     "tipo": "text"},
    ]},
    {"titulo": "2. Solicitante", "campos": [
        {"key": "proyectos_asociados", "label": "Proyectos asociados", "tipo": "textarea"},
    ]},
    {"titulo": "3. Predios", "campos": [
        {"key": "superficie_predial", "label": "Superficie", "tipo": "text"},
        {"key": "rol",                "label": "Rol",        "tipo": "text"},
        {"key": "clase",              "label": "Clase",      "tipo": "text"},
        {"key": "predio_bonificado",  "label": "Predio bonificado", "tipo": "text"},
        {"key": "tenencia",           "label": "Tenencia",   "tipo": "text"},
    ]},
    {"titulo": "4. Derechos de agua (DAA)", "campos": [
        {"key": "daa", "label": "Derechos de aprovechamiento de aguas", "tipo": "textarea"},
    ]},
    {"titulo": "5. Uso actual del suelo", "campos": [
        {"key": "uso_actual_suelo", "label": "Uso actual del suelo (revisar Rol)", "tipo": "textarea"},
    ]},
    {"titulo": "6. Obras", "campos": [
        {"key": "obras", "label": "Obras del proyecto", "tipo": "textarea"},
    ]},
    {"titulo": "7. Cultivo y superficie", "campos": [
        {"key": "cultivo_superficie", "label": "Cultivo y superficie", "tipo": "textarea"},
    ]},
    {"titulo": "Características de obras", "campos": [
        {"key": "volumen_embalsado",   "label": "Volumen embalsado (m³)", "tipo": "text"},
        {"key": "fv_kwp",              "label": "FV (KWp)",               "tipo": "text"},
        {"key": "n_placas",            "label": "N° placas",              "tipo": "text"},
        {"key": "electrificacion_kva", "label": "Electrificación (KVA)",  "tipo": "text"},
        {"key": "generador_kva",       "label": "Generador (KVA)",        "tipo": "text"},
        {"key": "q_extraccion",        "label": "Q extracción (l/s)",     "tipo": "text"},
    ]},
]

# Campos Sí/No (para validar/normalizar lo que devuelva la IA)
RESUMEN_CAMPOS_SINO = {c["key"] for sec in RESUMEN_SECCIONES for c in sec["campos"]
                       if c["tipo"] == "sino"}
# Todas las claves válidas del resumen
RESUMEN_KEYS = [c["key"] for sec in RESUMEN_SECCIONES for c in sec["campos"]]


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


async def _analizar_grupo(nombre: str, checklist: str, docs_grupo: list, documentos: list, *,
                          modo: str = "EJE TEMÁTICO", es_coherencia: bool = False,
                          bases_texto: str = "", concurso_id: str = "",
                          feedback_concurso: list = None, feedback_key: str = "",
                          criterios_aprendidos: str = "", criterios_enfasis: str = "",
                          consultor: dict = None,
                          tipo_revision: str = "tecnica", ruta_uploads: str = None) -> dict:
    """
    Núcleo de análisis de un grupo de documentos (eje temático o ítem del SEP).
    Cruza los documentos del grupo en UNA llamada; usa texto extraído + VISIÓN para
    documentos escaneados/planos (si el archivo físico existe y no es coherencia global).
    Retorna dict: {observaciones: [...], docs_incluidos: [...], sin_documentos: bool}.
    """
    import os as _os

    # Separar documentos con texto de documentos-imagen (escaneados / planos)
    docs_texto  = []
    docs_imagen = []   # (doc, filepath)
    for d in docs_grupo:
        t = d.get("texto_extraido", "").strip()
        es_imagen = (t == "__PDF_ESCANEADO__" or len(t) < MIN_CHARS_TEXTO)
        if (es_imagen and ruta_uploads and not es_coherencia
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
    # Aprendizaje: si hay criterios ya destilados de este eje/ítem, se usan (más compactos y
    # generalizables). Si no, se cae a los ejemplos crudos de feedback.
    if criterios_aprendidos and criterios_aprendidos.strip():
        bloque_feedback = (f"\n{'═'*60}\nCRITERIOS APRENDIDOS EN ESTE CONCURSO "
                           f"(destilados de las decisiones del revisor)\n{'═'*60}\n"
                           f"{criterios_aprendidos.strip()}\n")
    else:
        bloque_feedback = _construir_bloque_feedback(feedback_concurso or [], feedback_key)

    # Aprendizaje por consultor (patrones recurrentes de quien presenta el proyecto)
    bloque_consultor = _construir_bloque_consultor(consultor)

    system_con_cache = [{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    if bloque_bases.strip():
        system_con_cache.append({"type": "text", "text": bloque_bases,
                                 "cache_control": {"type": "ephemeral", "ttl": "1h"}})
        bloque_bases = ""

    revision_nombre = "técnica" if tipo_revision == "tecnica" else "legal"

    # Manifiesto de TODOS los documentos presentes en el expediente (no solo los del grupo).
    # Permite a la IA detectar si falta un documento obligatorio exigido por las bases.
    labels_presentes = sorted({
        (d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", "")))
        for d in documentos if d.get("tipo_doc")
    })
    manifiesto = "\n".join(f"• {l}" for l in labels_presentes if l) or "(sin documentos)"

    nota_imagenes = ""
    if imagenes_por_doc:
        nombres_img = ", ".join(f"{lbl} ({nom})" for lbl, nom, _ in imagenes_por_doc)
        nota_imagenes = (f"\n\nADEMÁS, al final se adjuntan como IMÁGENES estos documentos "
                         f"(planos o escaneados) — analízalos visualmente: {nombres_img}")

    bloque_enfasis = ""
    if criterios_enfasis and criterios_enfasis.strip():
        bloque_enfasis = (f"\n\n{'═'*60}\nCRITERIOS DE ÉNFASIS DEFINIDOS POR EL REVISOR PARA "
                          f"ESTE GRUPO EN ESTE CONCURSO — verifícalos SIEMPRE, tienen prioridad "
                          f"sobre el resto de la guía:\n{'═'*60}\n{criterios_enfasis.strip()}\n")

    prompt = f"""{bloque_bases}{bloque_feedback}{bloque_consultor}Realiza una REVISIÓN POR {modo} del expediente CNR.

GRUPO A REVISAR: {nombre}
Tipo de revisión: Revisión {revision_nombre}

{checklist}{bloque_enfasis}

⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles. Ej: "1.234,56" = 1234.56
Interpreta TODOS los números con esta convención.

INSTRUCCIÓN CLAVE: Detecta problemas considerando la RELACIÓN entre los documentos, no cada
uno por separado. Presta atención a incoherencias entre documentos. Aplica el criterio de las
tres preguntas (¿funciona?, ¿precios razonables?, ¿diseño con lógica?) y la regla de oro
(ante la duda, no observar; máx ~10-15 observaciones).{nota_imagenes}

DOCUMENTOS PRESENTES EN EL EXPEDIENTE COMPLETO (para verificar faltantes obligatorios):
{manifiesto}

ANTECEDENTES OBLIGATORIOS: Las bases del concurso definen qué antecedentes son IMPRESCINDIBLES
para postular. Antes de observar, ten claro cuáles exige. Si un documento obligatorio de este
grupo NO aparece en el listado de arriba (no fue ingresado al expediente), genera una
observación mayor y termínala con la frase exacta: "Se sugiere declarar no admitido."

DOCUMENTOS DEL GRUPO (texto):
{bloque_docs if bloque_docs else '(Los documentos de este grupo se adjuntan como imágenes más abajo.)'}"""

    # Construir contenido: texto + imágenes de los documentos escaneados/planos
    content_blocks = [{"type": "text", "text": prompt}]
    for label, nombre_img, imgs in imagenes_por_doc:
        content_blocks.append({"type": "text",
                               "text": f"\n═══ IMÁGENES: {label} ({nombre_img}) ═══"})
        for b64 in imgs:
            content_blocks.append({"type": "image",
                                   "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": b64}})

    def _llamar(max_tokens):
        return client.messages.create(
            model=MODELO_SONNET,
            max_tokens=max_tokens,
            system=system_con_cache,
            messages=[{"role": "user", "content": content_blocks}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )

    response = _llamar(MAX_TOKENS_SONNET)
    content = _texto_respuesta(response)

    # El "thinking" de Sonnet 5 a veces se come todo el cupo antes de escribir el JSON,
    # sobre todo en grupos con imágenes (más que razonar). Si la respuesta llega vacía y
    # cortada por límite de tokens, reintenta una vez con más cupo antes de rendirse.
    if not content.strip() and response.stop_reason == "max_tokens":
        print(f"⚠️ Grupo '{nombre}': respuesta vacía por max_tokens ({MAX_TOKENS_SONNET}) — "
              f"reintentando con más cupo…")
        response = _llamar(MAX_TOKENS_SONNET + 8000)
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
        print(f"⚠️ Grupo '{nombre}': 0 observaciones — stop_reason={response.stop_reason}, "
              f"content_len={len(content)}, preview={content[:200]!r}")

    return {"observaciones": observaciones, "docs_incluidos": docs_incluidos,
            "sin_documentos": False}


async def analizar_eje(eje_key: str, documentos: list, bases_texto: str = "",
                       concurso_id: str = "", feedback_concurso: list = None,
                       criterios_aprendidos: str = "", criterios_enfasis: str = "",
                       consultor: dict = None,
                       tipo_revision: str = "tecnica", ruta_uploads: str = None) -> dict:
    """Analiza un EJE TEMÁTICO (cruza documentos complementarios). Envoltorio de _analizar_grupo."""
    eje = EJES_REVISION.get(eje_key)
    if not eje:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}
    docs_grupo = _documentos_del_eje(eje_key, documentos)
    return await _analizar_grupo(
        eje["nombre"], eje["checklist"], docs_grupo, documentos,
        modo="EJE TEMÁTICO", es_coherencia=(eje_key == "coherencia"),
        bases_texto=bases_texto, concurso_id=concurso_id,
        feedback_concurso=feedback_concurso, feedback_key=eje_key,
        criterios_aprendidos=criterios_aprendidos, criterios_enfasis=criterios_enfasis,
        consultor=consultor,
        tipo_revision=tipo_revision, ruta_uploads=ruta_uploads)


async def analizar_item(item_key: str, documentos: list, bases_texto: str = "",
                        concurso_id: str = "", feedback_concurso: list = None,
                        criterios_aprendidos: str = "", criterios_enfasis: str = "",
                        consultor: dict = None,
                        tipo_revision: str = "tecnica", ruta_uploads: str = None) -> dict:
    """Analiza un ÍTEM DEL SEP (revisa el/los documento(s) de ese ítem). Envoltorio de _analizar_grupo."""
    item = ITEMS_SEP.get(item_key)
    if not item:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}
    tipos = set(item["tipo_docs"])
    docs_grupo = [d for d in documentos if d.get("tipo_doc") in tipos]
    return await _analizar_grupo(
        item["nombre"], item["checklist"], docs_grupo, documentos,
        modo="ÍTEM DEL SEP", es_coherencia=False,
        bases_texto=bases_texto, concurso_id=concurso_id,
        feedback_concurso=feedback_concurso, feedback_key="item_" + item_key,
        criterios_aprendidos=criterios_aprendidos, criterios_enfasis=criterios_enfasis,
        consultor=consultor,
        tipo_revision=tipo_revision, ruta_uploads=ruta_uploads)


ACCIONES_CHAT_VALIDAS = {"descartar", "reclasificar_nota", "editar", "eliminar", "mantener"}


def _extraer_accion(texto: str) -> tuple:
    """
    Busca al final de la respuesta del chat el marcador ACCION_JSON: {...} y lo separa del
    texto conversacional (que es lo único que ve el revisor). Devuelve (texto_limpio, accion|None).
    `accion` es un dict {id, accion, texto_nuevo} o None si no hay cambio o no se pudo parsear.
    Tolera respuestas cortadas a mitad del JSON (mismo reintento que el parser de observaciones).
    """
    marca = texto.find("ACCION_JSON:")
    if marca < 0:
        return texto.strip(), None
    texto_limpio = texto[:marca].strip()
    resto = texto[marca + len("ACCION_JSON:"):]
    start = resto.find("{")
    if start < 0:
        return texto_limpio, None

    accion = None
    end = resto.rfind("}") + 1
    if end > start:
        try:
            accion = json.loads(resto[start:end])
        except json.JSONDecodeError:
            accion = None
    if accion is None:
        # Reintento: puede haberse cortado a mitad del JSON (el thinking se comió el cupo
        # de tokens antes de terminar de escribirlo) — cerrar llaves/corchetes abiertos.
        try:
            frag = resto[start:]
            frag += "]" * (frag.count("[") - frag.count("]"))
            frag += "}" * (frag.count("{") - frag.count("}"))
            accion = json.loads(frag)
        except Exception:
            print(f"⚠️ ACCION_JSON presente pero no se pudo parsear (posible corte): {resto[:200]!r}")
            return texto_limpio, None
    if not isinstance(accion, dict) or not accion.get("id"):
        return texto_limpio, None
    if accion.get("accion") not in ACCIONES_CHAT_VALIDAS:
        return texto_limpio, None
    return texto_limpio, accion


async def _chatear_grupo(nombre: str, checklist: str, docs_grupo: list, observaciones_grupo: list,
                         historial: list, mensaje: str, bases_texto: str = "",
                         concurso_id: str = "") -> dict:
    """
    Chat de refinamiento sobre un eje/ítem ya revisado. El revisor debate una observación y la
    IA responde con el contexto completo del grupo (documentos + observaciones + bases).
    Si el revisor pide un cambio concreto y la IA está de acuerdo, puede APLICARLO: devuelve
    {"texto": str, "accion": {"id","accion","texto_nuevo"} | None}. `accion` en
    descartar|reclasificar_nota|editar|mantener; el llamador aplica el cambio a la observación.
    """
    client = _get_client()

    docs_con_texto = [d for d in docs_grupo
                      if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]
    budget = max(2500, 25000 // max(1, len(docs_con_texto)))
    bloque_docs = ""
    for d in docs_con_texto:
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        bloque_docs += f"\n\n--- {label} ({d.get('nombre_original','')}) ---\n{_truncar_inteligente(d.get('texto_extraido',''), budget)}"

    # Observaciones actuales del grupo, con su id real (para que la IA pueda referenciarlas
    # sin ambigüedad si el revisor le pide aplicar un cambio).
    bloque_obs = ""
    for o in observaciones_grupo:
        bloque_obs += (f"\n[id:{o.get('id')}] Obs.{o.get('numero')} "
                       f"({o.get('severidad','')}) {o.get('texto','')}")
    if not bloque_obs:
        bloque_obs = "\n(No hay observaciones registradas todavía.)"

    bloque_bases = _construir_bloque_bases(bases_texto, concurso_id)

    # Contexto del grupo (documentos + observaciones + guía). Se pone como bloque CACHEADO del
    # system para que en una conversación de varios turnos NO se reenvíe ni reprocese cada vez
    # (más rápido y más barato). Solo cambia si cambian el grupo o sus observaciones.
    contexto_grupo = f"""Estás asistiendo a un revisor CNR en "{nombre}".
Ya realizaste una revisión de este grupo de documentos. Ahora el revisor quiere DEBATIR
contigo las observaciones: aclarar, corregir, reclasificar (ej. bajar una observación a nota
si las bases lo permiten), descartarla, o profundizar en un punto técnico.

{checklist}

⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles.

DOCUMENTOS:{bloque_docs}

OBSERVACIONES ACTUALES (cada una con su [id:...] — úsalo para aplicar cambios):{bloque_obs}

Responde de forma directa y práctica, breve y concreta. Si mantienes tu criterio, explica por
qué con fundamento normativo.

APLICAR UN CAMBIO (IMPORTANTE): si el revisor pide un cambio CONCRETO sobre UNA observación
(descartarla, eliminarla, bajarla a nota, corregir su texto) y estás de acuerdo, DEBES
aplicarlo de verdad, no solo sugerirlo. Para eso, agrega al FINAL de tu respuesta, en una
línea aparte, exactamente este marcador (el revisor no lo ve, se procesa automáticamente):

ACCION_JSON: {{"id": "<el id de la observación entre [id:...]>", "accion": "descartar|reclasificar_nota|editar|eliminar|mantener", "texto_nuevo": "<solo si el texto cambia, si no ''>"}}

Reglas del marcador:
- "descartar": la observación no era válida, se descarta (queda registrada como descartada,
  reversible — el revisor la puede volver a poner pendiente a mano si se equivocó).
- "reclasificar_nota": se mantiene pero como nota informativa; si reescribes el texto, quita
  la frase de cierre ("Debe aclarar."/"Debe justificar."), las notas no la llevan.
- "editar": se corrige el texto en "texto_nuevo" pero sigue siendo observación; mantén el
  mismo estilo breve (máx 2-3 líneas) y su frase de cierre.
- "eliminar": borra la observación POR COMPLETO, sin dejar ningún registro (NO reversible).
  Úsala SOLO si el revisor pide explícitamente "elimínala" o "bórrala" (no solo "descártala").
  Ante la duda entre descartar y eliminar, usa SIEMPRE "descartar" — es la opción reversible.
- Solo incluye el marcador si el revisor pidió explícitamente un cambio y tú lo aceptas. Si
  solo pregunta, pide una aclaración, o mantienes tu criterio sin ceder, NO incluyas el marcador.
- Actúa sobre UNA sola observación por respuesta."""

    system_con_cache = [{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    if bloque_bases.strip():
        system_con_cache.append({"type": "text", "text": bloque_bases,
                                 "cache_control": {"type": "ephemeral", "ttl": "1h"}})
    system_con_cache.append({"type": "text", "text": contexto_grupo,
                             "cache_control": {"type": "ephemeral", "ttl": "1h"}})

    # Solo la conversación va en messages (historial + mensaje nuevo): es lo único que cambia
    # turno a turno, así el contexto pesado queda cacheado.
    mensajes = []
    for turno in historial[-10:]:   # últimos 10 turnos para acotar tokens
        rol = "user" if turno.get("rol") == "revisor" else "assistant"
        mensajes.append({"role": rol, "content": turno.get("texto", "")})

    mensajes.append({"role": "user", "content": mensaje})

    response = client.messages.create(
        model=MODELO_SONNET,
        max_tokens=8000,   # holgado: el chat ahora también debe escribir el marcador ACCION_JSON
        system=system_con_cache,
        messages=mensajes,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    texto_crudo = _texto_respuesta(response)
    if not texto_crudo:
        print(f"⚠️ Chat '{nombre}': respuesta vacía — stop_reason={response.stop_reason}")
        return {"texto": "", "accion": None}

    texto, accion = _extraer_accion(texto_crudo)
    if accion and accion.get("accion") == "mantener":
        accion = None   # "mantener" no requiere que el llamador haga nada
    return {"texto": texto, "accion": accion}


async def chatear_eje(eje_key: str, documentos: list, observaciones_eje: list,
                      historial: list, mensaje: str, bases_texto: str = "",
                      concurso_id: str = "") -> dict:
    """Chat de refinamiento sobre un EJE. Envoltorio de _chatear_grupo."""
    eje = EJES_REVISION.get(eje_key)
    if not eje:
        return {"texto": "Eje no válido.", "accion": None}
    docs_grupo = _documentos_del_eje(eje_key, documentos)
    return await _chatear_grupo(eje["nombre"], eje["checklist"], docs_grupo, observaciones_eje,
                                historial, mensaje, bases_texto=bases_texto, concurso_id=concurso_id)


async def chatear_item(item_key: str, documentos: list, observaciones_item: list,
                       historial: list, mensaje: str, bases_texto: str = "",
                       concurso_id: str = "") -> dict:
    """Chat de refinamiento sobre un ÍTEM del SEP. Envoltorio de _chatear_grupo."""
    item = ITEMS_SEP.get(item_key)
    if not item:
        return {"texto": "Ítem no válido.", "accion": None}
    tipos = set(item["tipo_docs"])
    docs_grupo = [d for d in documentos if d.get("tipo_doc") in tipos]
    return await _chatear_grupo(item["nombre"], item["checklist"], docs_grupo, observaciones_item,
                                historial, mensaje, bases_texto=bases_texto, concurso_id=concurso_id)


async def resumir_proyecto(documentos: list, bases_texto: str = "", concurso_id: str = "") -> dict:
    """
    Autocompleta el resumen del proyecto extrayendo datos de los documentos del expediente.
    Devuelve un dict {key: valor} solo con las claves válidas de RESUMEN_KEYS. No inventa:
    si un dato no aparece, devuelve "" para esa clave.
    """
    docs_texto = [d for d in documentos
                  if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]
    if not docs_texto:
        return {}

    client = _get_client()
    budget = max(2000, 40000 // max(1, len(docs_texto)))
    bloque = ""
    for d in docs_texto:
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        bloque += f"\n\n--- {label} ---\n{_truncar_inteligente(d.get('texto_extraido', ''), budget)}"

    campos_lista = "\n".join(
        f'- {c["key"]}: {c["label"]}' + (" (responde \"Sí\" o \"No\")" if c["tipo"] == "sino" else "")
        for sec in RESUMEN_SECCIONES for c in sec["campos"])

    prompt = f"""Extrae del expediente CNR los datos para el RESUMEN del proyecto.
Devuelve SOLO un objeto JSON con EXACTAMENTE estas claves. Usa "" (vacío) si el dato NO
aparece en los documentos. NO inventes ni deduzcas datos que no estén escritos.

CLAVES A COMPLETAR:
{campos_lista}

Para los campos Sí/No responde exactamente "Sí" o "No" (o "" si no consta).
⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles.

EXPEDIENTE:
{bloque}

Responde SOLO el JSON, sin texto adicional."""

    response = client.messages.create(
        model=MODELO_SONNET,
        max_tokens=3000,
        system=[{"type": "text",
                 "text": "Eres un asistente que extrae datos de expedientes CNR y responde únicamente con JSON válido.",
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )

    content = _texto_respuesta(response)
    datos = {}
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            datos = json.loads(content[start:end])
    except json.JSONDecodeError:
        try:
            frag = content[content.find("{"):]
            frag += "}" * (frag.count("{") - frag.count("}"))
            datos = json.loads(frag)
        except Exception:
            datos = {}

    if not datos:
        print(f"⚠️ resumir_proyecto: sin datos — stop_reason={response.stop_reason}, "
              f"preview={content[:200]!r}")

    # Quedarse solo con claves válidas y normalizar Sí/No
    limpio = {}
    for k in RESUMEN_KEYS:
        v = datos.get(k, "")
        v = "" if v is None else str(v).strip()
        if k in RESUMEN_CAMPOS_SINO:
            vl = v.lower()
            v = "Sí" if vl in ("sí", "si", "true", "1") else ("No" if vl in ("no", "false", "0") else "")
        limpio[k] = v
    return limpio


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

    return bloque


def _construir_bloque_consultor(consultor: dict) -> str:
    """
    Construye el bloque de aprendizaje POR CONSULTOR. Prefiere el perfil destilado; si no hay,
    arma un resumen compacto del historial de decisiones del consultor (sus fallas recurrentes y
    lo que no conviene observarle). Devuelve "" si el consultor no tiene historia suficiente.
    """
    if not consultor:
        return ""
    nombre = consultor.get("nombre", "")
    perfil = (consultor.get("perfil", "") or "").strip()
    if perfil:
        return (f"\n{'═'*60}\nPERFIL DEL CONSULTOR: {nombre}\n{'═'*60}\n"
                f"Patrones recurrentes de este consultor observados al revisar sus proyectos "
                f"anteriores. Úsalos para revisar más rápido y consistente, SIN dejar de verificar:\n"
                f"{perfil}\n")
    fb = consultor.get("feedback", [])
    if len(fb) < 3:
        return ""   # aún no hay suficiente historia de este consultor
    aprob = [f.get("texto_obs", "") for f in fb if f.get("accion") == "aprobada"][-8:]
    desc  = [f.get("texto_obs", "") for f in fb if f.get("accion") == "descartada"][-8:]
    if not aprob and not desc:
        return ""
    b = (f"\n{'═'*60}\nHISTORIAL DEL CONSULTOR: {nombre}\n{'═'*60}\n"
         f"Decisiones tomadas en proyectos anteriores del MISMO consultor (patrones a considerar):\n")
    if aprob:
        b += "Observaciones que resultaron válidas (fallas recurrentes de este consultor):\n"
        b += "".join(f"  ✓ {t[:150]}\n" for t in aprob)
    if desc:
        b += "Observaciones descartadas (no insistir en estas con este consultor):\n"
        b += "".join(f"  ✗ {t[:150]}\n" for t in desc)
    return b


async def consolidar_perfil_consultor(feedback: list, nombre: str) -> str:
    """
    Destila el historial de decisiones de un consultor en un PERFIL breve: su metodología de
    presentación, fortalezas y fallas recurrentes. Usa Haiku (barato). "" si <3 decisiones.
    """
    fb = feedback or []
    if len(fb) < 3:
        return ""
    aprob = [f.get("texto_obs", "") for f in fb if f.get("accion") == "aprobada"][:40]
    desc  = [f.get("texto_obs", "") for f in fb if f.get("accion") == "descartada"][:40]
    lista = ""
    if aprob:
        lista += "\nOBSERVACIONES VÁLIDAS EN SUS PROYECTOS (fallas recurrentes):\n" + "\n".join(f"- {t}" for t in aprob)
    if desc:
        lista += "\nOBSERVACIONES DESCARTADAS (no eran relevantes):\n" + "\n".join(f"- {t}" for t in desc)

    client = _get_client()
    prompt = f"""A partir de las decisiones reales de un revisor CNR sobre los proyectos del
consultor "{nombre}", destila un PERFIL breve (máximo 8 líneas, viñetas "-") que capture:
- su metodología de presentación y fortalezas típicas,
- sus FALLAS RECURRENTES (qué observar casi siempre en sus proyectos),
- qué NO conviene observarle (lo que el revisor suele descartar).
El objetivo es revisar más rápido y consistente sus proyectos siguientes.
{lista}

Responde SOLO el perfil, en viñetas con "-"."""

    response = client.messages.create(
        model=MODELO_HAIKU,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = _texto_respuesta(response).strip()
    if not texto:
        print(f"⚠️ consolidar_perfil_consultor '{nombre}': respuesta vacía — stop_reason={response.stop_reason}")
    return texto


async def consolidar_aprendizaje(feedback: list, clave: str, nombre: str) -> str:
    """
    Destila el feedback (decisiones reales de aprobar/descartar) de un eje o ítem en un
    conjunto BREVE de CRITERIOS APRENDIDOS (reglas concretas). Usa Haiku (barato) porque es una
    tarea de resumen. Devuelve el texto de las reglas, o "" si no hay feedback suficiente.
    `clave` es la etiqueta del feedback: el eje_key, o "item_<item_key>" para ítems.
    """
    relevantes = [f for f in (feedback or []) if f.get("tipo_doc") == clave]
    if len(relevantes) < 3:
        return ""   # con muy pocos ejemplos no vale la pena destilar

    aprob = [f.get("texto_obs", "") for f in relevantes if f.get("accion") == "aprobada"][:30]
    desc  = [f.get("texto_obs", "") for f in relevantes if f.get("accion") == "descartada"][:30]
    lista = ""
    if aprob:
        lista += "\nOBSERVACIONES QUE EL REVISOR VALIDÓ (eran correctas):\n" + "\n".join(f"- {t}" for t in aprob)
    if desc:
        lista += "\nOBSERVACIONES QUE EL REVISOR DESCARTÓ (no eran relevantes):\n" + "\n".join(f"- {t}" for t in desc)

    client = _get_client()
    prompt = f"""A partir de las decisiones reales de un revisor CNR en "{nombre}", destila un
conjunto BREVE de CRITERIOS APRENDIDOS (máximo 8 reglas, una línea cada una) que resuman:
- qué tipo de observaciones SÍ conviene generar (según las que el revisor validó), y
- qué tipo de observaciones NO conviene generar (según las que descartó).
Escribe reglas concretas y accionables; NO repitas los ejemplos textualmente.
{lista}

Responde SOLO las reglas, en viñetas con "-"."""

    response = client.messages.create(
        model=MODELO_HAIKU,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = _texto_respuesta(response).strip()
    if not texto:
        print(f"⚠️ consolidar_aprendizaje '{clave}': respuesta vacía — stop_reason={response.stop_reason}")
    return texto


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
        max_tokens=4000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral", "ttl": "1h"}
        }],
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    texto = _texto_respuesta(response)
    if not texto:
        print(f"⚠️ consultar_expediente: respuesta vacía — stop_reason={response.stop_reason}")
        texto = ("⚠️ La IA no devolvió respuesta (posible corte). Intenta reformular la "
                 "consulta de forma más breve o vuelve a intentar.")
    return texto
