"""Análisis de documentos con Claude API según normativa CNR Ley 18.450"""
import os
import json
import re
import asyncio
from pathlib import Path
import anthropic
import calculos_riego

# NOTA sobre asyncio.to_thread: el cliente de Anthropic es sincrónico — llamarlo directo
# dentro de una ruta async de FastAPI BLOQUEA el event loop completo mientras dura la llamada
# (un análisis puede tardar 1-2 minutos), dejando la app entera sin responder. Toda llamada
# `client.messages.create(...)` debe ir envuelta en `await asyncio.to_thread(...)`.

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
MODELO_HAIKU  = "claude-haiku-4-5"    # Extracción de datos numéricos para verificación (barato)

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
MAX_TOKENS_SONNET = 16000  # Documentos complejos — Sonnet 5 gasta parte del cupo en thinking
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
      "referencia_normativa": "Manual/Instructivo/Base que respalda la observación (ver prioridad abajo)"
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

PRIORIDAD DE LA "referencia_normativa" (OBLIGATORIO — esta cita se copia al SEP):
La observación se sube al SEP y el consultor debe poder ir a la fuente citada. Por eso, al
llenar "referencia_normativa", cita SIEMPRE la fuente de MAYOR jerarquía que respalde el punto,
en este orden de prioridad:
  1º MANUALES oficiales CNR (ej. Manual de Supervisión de Obras) — máxima prioridad.
  2º INSTRUCTIVOS oficiales CNR (DT-##, IL-##, ITT-##, FL-##, y la Ley N° 18.450 / su reglamento).
  3º BASES del concurso (cita el punto/numeral exacto, ej. "Bases 6.3").
  4º Solo si NINGUNA de las anteriores aplica, un criterio técnico general — pero NO cites como
     referencia los "criterios aprendidos", "criterios de énfasis" ni los extractos de criterios
     destilados: son guía interna del revisor, no una fuente oficial citable ante el consultor.
Cita el código exacto del documento (no "el manual" a secas). Si un punto se respalda en varias
fuentes, cita la de mayor jerarquía primero. Si de verdad no hay respaldo normativo oficial
para el punto, deja "referencia_normativa" vacía en vez de inventar o citar guía interna.

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


# Presupuesto total de caracteres para el prompt combinado de un grupo de documentos
MAX_CHARS_EJE_TOTAL = 45000

# Ítems con documentos largos y densos en datos: límite ampliado (a pedido del usuario) para
# que 2-3 archivos grandes entren casi completos en el análisis. Solo pagan más tokens los
# ítems que realmente tengan tanto texto; el resto sigue con MAX_CHARS_EJE_TOTAL.
# "diseno_hidraulico" cubre también el diseño agronómico (mismo ítem SEP).
# "especificaciones_tecnicas" agregado jul-2026: bug real reportado por el usuario — con 8
# documentos clasificados bajo este ítem (el consultor había metido ahí, además de las
# especificaciones generales, las especificaciones y el cálculo estructural de un invernadero),
# el presupuesto por defecto (45.000 / 8 ≈ 5.600 caracteres por documento) truncaba tan fuerte
# los documentos más densos que su contenido relevante (tablas de cubicación, sobrecarga de
# nieve/viento) quedaba cortado — la IA no los "veía" pese a que el documento SÍ entraba al
# prompt, solo que gutted. Con más documentos por ítem (no solo 2-3 archivos grandes), el
# presupuesto por defecto se queda corto más rápido — mismo criterio de "denso en datos" que
# los otros 5, solo que el detonante acá es la CANTIDAD de documentos, no el tamaño de uno solo.
MAX_CHARS_POR_ITEM = {
    "diseno_hidraulico":         120000,
    "diseno_fotovoltaico":       120000,
    "presupuesto":               120000,
    "presupuesto_electrico":     120000,
    "coherencia":                120000,
    "especificaciones_tecnicas": 120000,
}


# ─── ÍTEMS DEL SEP ─────────────────────────────────────────────────────────────
# Único método de revisión: por los ítems tal como se ingresan al Sistema Electrónico de
# Postulación (SEP), que coinciden con el agrupamiento de archivos que hace el consultor.
# Cada ítem revisa su(s) documento(s) y produce observaciones tageadas con el ítem, para
# facilitar el ingreso al SEP.
ITEMS_SEP = {
    "plano_ubicacion": {
        "nombre": "Plano de ubicación del proyecto",
        "tipo_docs": ["plano_ubicacion"],
        "checklist": """Verifica que el plano ubique el predio con coordenadas UTM, comuna, deslindes y vía de
acceso, coherente con la comuna/dirección declarada en el Resumen y con las coordenadas usadas en
otros documentos (identificación del área de riego, memoria de superficies). Debe permitir
identificar sin ambigüedad el predio dentro de la comuna — no basta una imagen satelital sin
cotas ni referencias. (Ref: Manual técnico de obras de tecnificación, punto 3.1)""",
    },
    "identificacion_riego": {
        "nombre": "Identificación del área de riego",
        "tipo_docs": ["identificacion_riego"],
        "checklist": """Verificar que el mapa/plano delimite por separado la Superficie de Riego Actual (SRA) y
la Superficie de Riego Futura (SRF). La SRF no debe ser inferior a la SRA (salvo disminución
declarada explícitamente). Verificar que la superficie regable máxima respete el título de
dominio y la clasificación de capacidad de uso de suelo por rol (CIREN/SII). Si una máquina de
riego (pivote/avance frontal) cubre predios vecinos, exigir la servidumbre correspondiente. Las
superficies (SRA/SRF/superficie regable máxima) deben coincidir exactamente con las de Memoria de
cálculo de superficies. Deberá contener la disposición general de las obras asociadas al
proyecto, coherente con el plano de tecnificación. (Ref: Manual técnico de tecnificación, punto 3.2)""",
    },
    "hidrologico": {
        "nombre": "Análisis Hidrológico",
        "tipo_docs": ["estudio_hidrologico"],
        "checklist": """Verificar que el caudal de diseño esté respaldado según el orden de prevalencia del ITT-01:
(a) si el derecho está inscrito en volumen/tiempo sin equivalencia (l/s, m³/temporada), basta el
certificado de inscripción, sin análisis hidrológico;
(b) si la fuente figura en DT-01 (tabla de caudales 85% por cuenca/canal), revisar que la
equivalencia acción-canal o acción-río aplicada sea la correcta;
(c) si se usa DT-02 (estaciones SIIR), verificar que la estación sea representativa y que el
caudal sea el promedio del Q85% de los 3 meses de máxima ETo diaria;
(d) si hay análisis de frecuencia propio: mínimo 15 años de estadística consecutivos, distribución
declarada (Normal/Log-Normal/Gumbel/Pearson III/Log-Pearson III — Log-Normal es la más común en
Chile), y factor de seguridad de 0,5 sobre el caudal si el estudio NO fue elaborado por
CNR/DOH/DGA/organización de usuarios;
(e) en aguas subterráneas (pozos), el caudal disponible tiene tope en lo indicado en la
Inscripción de Dominio;
(f) en vertientes/lagos menores (art. 20 Código de Aguas), exigir 3 aforos cada 15 días durante la
temporada de riego, con informe firmado por el profesional responsable.
El resultado debe cargarse como Anexo 9.4 y ser coherente con el caudal usado en el balance de
superficie.""",
    },
    "pruebas_bombeo": {
        "nombre": "Pruebas de Bombeo",
        "tipo_docs": ["pruebas_bombeo"],
        "checklist": """Caudal, nivel dinámico y eficiencia del pozo. Debe respaldar el caudal y la selección de
bomba del diseño hidráulico.
ALCANCE: este ítem revisa SOLO estos aspectos TÉCNICOS de la prueba — NO corresponde observar
aquí el estado legal ni la inscripción del derecho de agua (eso se revisa en Antecedentes
legales, otro ítem). Tampoco asumas que la prueba de bombeo no se requiere por tener derechos
inscritos: varias bases la exigen igual, con derechos inscritos o no, para dar certeza técnica
del caudal disponible — si el expediente la presenta, revísala por sus méritos técnicos sin
cuestionar si correspondía o no exigirla.
Si se presenta una prueba de bombeo revisar el caudal de bombeo, los tiempos y las curvas de
descenso y recuperación de la fuente, observar cualquier anomalía o manipulación de datos.""",
    },
    "diseno_hidraulico": {
        "nombre": "Diseño y cálculos hidráulicos",
        "tipo_docs": ["diseno_hidraulico", "diseno_agronomico"],
        "checklist": """Verifica que la memoria incluya, como mínimo lo exigido por ITT-03:
Diseño agronómico — cultivo, ETo, Kc en periodo de máxima demanda, demandas neta y bruta, tipo de
riego y emisores por sector, marco de plantación, marco/espaciamiento de emisores, caudal del
emisor, precipitación del equipo, N° de laterales por hilera, N° de sectores/bloques, tiempos de
riego por sector y total, superficies y caudales por sector — idealmente en un Cuadro Resumen.
Cálculos hidráulicos — sectorización, características de la red por tramo (nodos, longitud,
diámetro, Presión Nominal PN y material), cálculo de pérdidas de carga, presión requerida vs.
disponible y caudal, potencia del equipo de bombeo y Cuadro de Carga Dinámica Total (CDT) — estos
dos últimos NO se recalculan automáticamente en la app, verifica que estén presentes y sean
coherentes con el diseño.
Si el caudal de diseño de un sector supera el caudal continuo disponible, confirma que se declare
un acumulador (excepción: aguas superficiales con diferencia <20%). Si se incluyen equipos de
capacidad mayor a la necesidad hídrica, exige declaración jurada del solicitante aceptando los
costos operacionales. En aducciones californianas, exige el detalle de sus componentes (red,
válvulas, cámaras reguladoras, campanas) y los cálculos que lo fundamenten. En aspersión
móvil/semimóvil no automatizada, verifica que el tiempo de riego diario considere la capacidad
operativa para los cambios de postura.""",
    },
    "diseno_fotovoltaico": {
        "nombre": "Diseño Fotovoltaico",
        "tipo_docs": ["diseno_fotovoltaico", "reporte_explorador_solar"],
        "checklist": """Verifica que el proyecto ERNC incluya, como mínimo (ITT-03 4.5.1.1): diseño del sistema y su
memoria de cálculo, plano de la estructura de soporte, plano del proyecto eléctrico, elementos de
protección, e inversor (salvo bomba de corriente continua). El diseño debe demostrar que la
generación cubre el 100% de la energía requerida en la temporada de riego, o la fracción
complementaria declarada — coherente con el consumo de la bomba del diseño hidráulico
(dimensionamiento básico ya verificado por la app: N° de paneles, kWp, sección de cable DC). La
capacidad de generación debe basarse en el Explorador Solar del Ministerio de Energía — exige el
reporte y que los kWh/año declarados sean consistentes con él.
El proyecto eléctrico debe estar firmado por profesional acreditado SEC y detallar
cubicación/precios de sus componentes (postes, cable de conducción, subestación, elementos de
protección y medida, costos de tramitación SEC). Verifica certificación/tramitación SEC según
corresponda (on-grid/off-grid). Ítems del presupuesto completos: paneles, inversor, cableado
DC/AC, estructura, protecciones, puesta a tierra. Un sistema ERNC no puede reemplazar una fuente
convencional existente sin ampliar la operación (no genera superficie de nuevo riego).""",
    },
    "estudios_complementarios": {
        "nombre": "Estudios y diseños complementarios",
        "tipo_docs": ["estudios_complementarios"],
        "checklist": """Verifica que cada estudio complementario presentado (geotécnico, hidrogeológico, de suelos,
estructural de obras anexas como invernaderos, ambiental, etc.) sea pertinente al tipo de obra
proyectada, esté firmado por el profesional competente, y que sus conclusiones/parámetros
(capacidad de suelo, nivel freático, sobrecarga de diseño, etc.) sean consistentes con los
supuestos usados en el diseño hidráulico, agronómico o estructural del resto del expediente. La
ausencia de un estudio que la obra proyectada claramente requiere (ej. fundaciones sin estudio de
suelo, pozo sin estudio hidrogeológico) es observable.""",
    },
    "especificaciones_tecnicas": {
        "nombre": "Especificaciones técnicas de construcción e instalación",
        "tipo_docs": ["especificaciones_tecnicas"],
        "checklist": """Verifica que las especificaciones sean consistentes con el diseño/cálculos hidráulicos y con
las partidas del presupuesto detallado (mismos diámetros, materiales, PN, marcas/modelos). Exige
catálogos legibles con modelo específico (no genérico) al menos para bombas, filtros, emisores y
máquinas de riego. Si hay fertirriego, verifica los 4 componentes mínimos: caudalímetro,
dispositivo de inyección de fertilizantes, estanque, fitting de conexión. Para filtros, la
presión de entrada especificada debe estar dentro del rango recomendado por el fabricante. Los
equipos deben cumplir la norma chilena vigente aplicable a equipos y elementos de riego mecánico
— su ausencia en equipos mecánicos/eléctricos ES observable.
En goteo: exige cabezal de control (filtraje/regulación/dosificación) y tablero de programación
con sectorización y válvulas si corresponde según diseño; tuberías (principal/secundaria/lateral)
con diámetro y clase; distancia y fijación de goteros. En aspersión: exige la presión necesaria
en tuberías para el caudal/presión de riego del cultivo, disposición de aspersores, y capacidad
del equipo de bombeo. En ambos casos, goteo o aspersión, si no están acá esos datos, deben estar
en Diseño y cálculo hidráulico. Si el proyecto incluye invernadero, la memoria de cálculo
estructural debe estar respaldada aquí o en Estudios complementarios — no debe faltar.""",
    },
    "cronograma": {
        "nombre": "Cronograma",
        "tipo_docs": ["cronograma"],
        "checklist": """Verifica que el cronograma desglose el plazo por ítem del presupuesto (no solo etapas
genéricas) y que la secuencia constructiva sea lógica y ejecutable (obras civiles →
tecnificación/red hidráulica → energización/FV → puesta en marcha, sin traslapes imposibles). El
plazo total no debe exceder el máximo reglamentario según el costo del proyecto: 12 meses si es
≤15.000 UF (prorrogable a 24) o 36 meses si es >15.000 UF (prorrogable a 72), contado desde la
fecha de emisión del CBRD — o el plazo específico que fijen las bases del concurso si es más
restrictivo. Si el proyecto contempla sistema fotovoltaico, el cronograma debe incluir
explícitamente su instalación y las gestiones de conexión/certificación SEC.""",
    },
    "presupuesto": {
        "nombre": "Presupuesto detallado de obras",
        "tipo_docs": ["presupuesto"],
        "checklist": """Partidas corresponden a las obras cubicadas y descritas técnicamente (material, diámetro,
marca/modelo cuando aplique — no descripciones genéricas), agrupadas en Sistema de Riego
(materiales) y Obras Civiles según el formato FT-01 de la CNR. Precios unitarios deben ser de
mercado: verifica que el costo directo (materiales + mano de obra + equipos) sea razonable
considerando la distancia al centro de abastecimiento, el tipo de acceso y la altura (s.n.m.) del
predio, según la metodología DT-18 — sobreprecios injustificados o valores anormalmente bajos
frente a esos factores son observables. El costo unitario por hectárea (Total presupuesto obras /
superficie) es un indicador útil de proporcionalidad frente a proyectos comparables. Los gastos
generales/utilidades del proyecto deben ser razonables frente al costo directo total (la CNR
aplica un porcentaje decreciente a mayor monto de obra, no un % fijo parejo).
Verifica además el cumplimiento de estas reglas específicas — señala cualquier ítem que incumpla
o esté cerca del límite, con el monto y la regla infringida:
a. Cotizaciones/facturas con menos de 6 meses de antigüedad; precios de obras civiles según DT-18.
b. Gastos Generales: deben detallarse si superan el 5% del costo total o UF 150. No corresponde
   GG en ítems subcontratados.
c. Imprevistos deben ir separados en el presupuesto general.
d. La utilidad solo corresponde en partidas con análisis de precio unitario (APU), no en
   subcontratos.
e. Costo de instalación ≤ $1.000.000 (hasta 5 ha) o + $200.000/ha adicional, para sistemas de
   goteo/microaspersión/cinta.
f. Costo de estudio ≤ los topes por tipo de estudio/superficie; honorarios del consultor ≤
   $4.000.000.
g. La inspección técnica de obras debe ser un profesional externo, inscrito en el Registro de
   Consultores CNR.
h. Límite del 15%: (Gastos Generales + Imprevistos + Estudio + ITO) / Costo Total del proyecto ≤
   15%.
i. El IVA va excluido del presupuesto, salvo excepción INDAP justificada.
j. No debe incluir costos prohibidos: pólizas, cercos, caminos interiores, obras a nivel de
   potrero, camellones, instalación de faenas, estudios ya bonificados en otra postulación.
k. Invernaderos: costo máximo por m² de $70.000 si la estructura es de metalcón con cubierta de
   policarbonato, o de $50.000 si la cubierta es de polietileno.""",
    },
    "presupuesto_electrico": {
        "nombre": "Presupuesto detallado electrificación",
        "tipo_docs": ["presupuesto_electrico"],
        "checklist": """Corresponde a los equipos del diseño eléctrico/fotovoltaico definidos en ese ítem (paneles,
inversor, estructura de montaje, tablero eléctrico, protecciones, cierre perimetral, cableado
DC/AC, bomba si aplica) con cantidades y especificaciones (marca, modelo, potencia) consistentes
con el dimensionamiento declarado. A diferencia de obras civiles, la CNR no tiene una tabla DT-18
de precios unitarios para equipos eléctricos/FV — la verificación de precio razonable depende de
las cotizaciones/facturas de respaldo y de la tabla de precios referenciales de la app; observa
solo si el precio se aparta claramente de esas referencias, no por ausencia de un DT-18
aplicable.""",
    },
    "cotizaciones_facturas": {
        "nombre": "Cotizaciones y Facturas",
        "tipo_docs": ["cotizaciones_facturas", "cotizaciones"],
        "checklist": """Verifica que las cotizaciones/facturas estén a nombre del postulante (o su
representante/organización, según el tipo de beneficiario) y que su detalle de bienes/servicios
(marca, modelo, cantidad, especificación técnica) coincida con lo señalado en el presupuesto del
proyecto — no debe haber ítems del presupuesto sin respaldo ni compensación entre partidas. Las
boletas de honorarios por elaboración del proyecto deben corresponder al consultor responsable;
si hay boleta de inspección técnica de obras, el profesional debe ser distinto del que ejecuta la
obra, sin relación de dependencia laboral ni vínculo societario con el contratista. Verifica
vigencia razonable de las cotizaciones respecto a la fecha de postulación.""",
    },
    "declaracion_iva": {
        "nombre": "Declaración No Contribuyente IVA",
        "tipo_docs": ["declaracion_iva"],
        "checklist": """Verifica que la declaración de no contribuyente de IVA corresponda al mismo postulante/RUT
identificado en el proyecto y sea coherente con el tratamiento del IVA en el presupuesto. Para
postulantes usuarios de INDAP, la CNR incluye el IVA en la bonificación, pero deben tener inicio
de actividades. Si NO son usuarios de INDAP, el IVA debe ser pagado por el postulante aunque se
incluya en el presupuesto — observa si el tratamiento del IVA en el presupuesto no corresponde al
tipo de beneficiario declarado.""",
    },
    "planos_tecnificacion": {
        "nombre": "Planos Proyecto tecnificación",
        "tipo_docs": ["planos_tecnificacion"],
        "checklist": """Analiza el plano visualmente, en detalle:
- Trazado de la red (matriz, secundarias, laterales): diámetros y longitudes ROTULADOS por tramo
  — deben coincidir con los tramos del diseño hidráulico (mismos diámetros, largos y
  materiales/PN).
- Cambios de diámetro marcados; nodos, válvulas, filtros y equipo de bombeo ubicados e
  identificados en la simbología.
- Sectores de riego delimitados: número de sectores coherente con el diseño (tiempo de riego ×
  horas disponibles).
- Marco de plantación/espaciamiento de emisores o aspersores anotado y coherente con el diseño
  agronómico.
- Viñeta/rótulo: escala, norte, fecha, profesional; superficie total coincidente con la memoria
  de superficies.
- Debe incluir el Cuadro 1 Resumen (diseño hidráulico y agronómico) en el mismo plano.
- Escala acorde a la superficie: 1-3 ha → 1:500 · 3-20 ha → 1:1000 · 20-40 ha → 1:2000 · >40 ha →
  1:2500 (o una escala legible si el predio es muy irregular/alargado/con ladera).
- Curvas de nivel acotadas, equidistancia máxima 1 m (0,5 m si la pendiente es muy baja);
  topografía y diseño en el mismo plano.
- Al menos un lateral por sector dibujado con su orientación, y orientación de la plantación
  señalada.
- Ubicación del cabezal de control.
- Simbología utilizada declarada.
Lee SOLO lo rotulado/acotado — si un dato clave (diámetro o longitud de un tramo principal) no
está rotulado en el plano, esa ausencia ES una observación (el plano debe bastarse para
construir).""",
    },
    "planos_obras_civiles": {
        "nombre": "Planos Obras Civiles proy. de tecnificación",
        "tipo_docs": ["planos_obras_civiles"],
        "checklist": """Analiza el plano visualmente, en detalle:
- Caseta de bombeo, estanque/embalse, cámaras y obras de arte: dimensiones ACOTADAS (planta,
  elevación y cortes) y materiales especificados. El plano de detalle debe traer un cuadro de
  especificaciones técnicas (tipo de hormigón, calidad del acero, recubrimientos, traslapos) y,
  si hay armadura, un cuadro de cubicación de la enfierradura — su ausencia es observable.
- Si el proyecto incluye tranques/embalse con muro (tierra u hormigón): debe mostrarse un corte
  transversal tipo con nivel de aguas máximas, ancho de coronamiento, taludes, revancha (borde
  libre) y, si es de tierra, grado de compactación del relleno. Observar si la revancha graficada
  es menor a 30 cm sin cálculo que la respalde, o si el ancho de coronamiento no guarda relación
  con la altura del muro. Verificar además que el diseño contemple cerco perimetral y salida(s)
  de emergencia/escalera de seguridad — exigencia explícita para toda obra de acumulación.
- Diseño estructural en hormigón armado (caseta/estanque/cámaras): la memoria/plano debe dejar
  constancia de las combinaciones de carga consideradas y, si corresponde, del análisis sísmico —
  observar si una obra de cierta envergadura se presenta sin ningún respaldo de cálculo
  estructural.
- Las dimensiones acotadas deben cuadrar con las cubicaciones y el presupuesto (volúmenes de
  excavación/hormigón, m² de caseta, kg de acero si hay cuadro de enfierradura).
- Electrificación/FV: ubicación de paneles, inversor y tableros si corresponde.
- Viñeta/rótulo con escala, profesional responsable y firma — debe identificar claramente quién
  proyecta y quién revisa.
Lee SOLO lo rotulado/acotado — si una obra del presupuesto no aparece dibujada/acotada, o las
cotas no permiten verificar la cubicación, genera observación.""",
    },
    "memoria_superficies": {
        "nombre": "Memoria de cálculo de superficies",
        "tipo_docs": ["memoria_superficies"],
        "checklist": """Verificar el método y los números del balance hídrico según ITT-02:
(1) Superficie = Q85% / Demanda(ETo/eficiencia), calculado por separado para situación actual
(SRA) y futura (SRF);
(2) SNR = SRF − SRA y SENR = superficie por caudal excedentario (SRQex) — no deben invertirse ni
sumarse mal;
(3) la eficiencia de aplicación usada debe corresponder a la Tabla N°1 del ITT-02 según método de
riego (goteo 90%, microaspersión/microjet 85%, aspersión 75%, surco 45-50%, tendido 30-35%,
etc.); si hay más de un método, la eficiencia ponderada debe calcularse según la pauta DT-04;
(4) la superficie de postulación (SNR+SENR) no puede superar la superficie regable máxima del
predio ni la superficie física del proyecto;
(5) si hay asimilación de suelos, la superficie asimilada debe coincidir con el Informe de
Asimilación;
(6) los resultados deben cuadrar exactamente con los usados en Identificación del área de riego y
ser consistentes con el monto bonificable/presupuesto.""",
    },
    "estudio_suelos": {
        "nombre": "Estudio de suelo - Informe de asimilación",
        "tipo_docs": ["estudio_suelos"],
        "checklist": """Verificar que el Informe de Asimilación cumpla los requisitos técnicos DT-19:
(1) plano topográfico con el mismo formato/escala/gráfica que el proyecto de riego, con viñeta de
achurados, delimitando el área Clase VI o VII (y VIII si corresponde) que se incorpora al riego
según clasificación CIREN, indicando la fuente de agua;
(2) en laderas/pendientes pronunciadas, trazado de la zanja superior de drenaje que delimita el
huerto y obras de control de erosión en quebradas/cauces/caminos;
(3) descripción de perfil de suelos por calicata o barreno, mínimo 1 punto cada 4 ha, con
profundidad, horizontes, estructura, textura, pendiente y capacidad de retención de agua
aproximada (Manual SAG);
(4) obras de drenaje de aguas lluvias y revegetación cuando corresponda;
(5) si hay camellones, verificar largo, orientación respecto a la pendiente y talud de la pared
aguas abajo.
La clasificación de Capacidad de Uso citada (Clase I-VIII, subclases s/w/e/cl) debe ajustarse a
los criterios técnicos de la Pauta SAG 2011 (DT-17) — profundidad, pendiente, pedregosidad,
drenaje, textura, erosión, salinidad/sodicidad con sus tablas de símbolos —, más detallada que la
pauta antigua DT-03/AT-07. La superficie de riego declarada no debe exceder la capacidad de uso
del suelo ni la superficie asimilada aprobada.""",
    },
    "coherencia": {
        "nombre": "Coherencia Global",
        "tipo_docs": [],   # usa TODOS los documentos del proyecto
        "checklist": """COHERENCIA GLOBAL — cierre transversal de todo el expediente.
Este grupo NO revisa un documento puntual ni repite el detalle que ya reviso ítem por ítem.
La pregunta que responde es de otro nivel: ¿la IDEA del proyecto como un todo —su forma de
operar, su lógica de diseño y de construcción— es coherente y viable? Es decir, si se construye
tal como está proyectado en el conjunto de documentos, ¿funciona como un sistema de riego real,
ejecutable en terreno, sin piezas que se contradigan entre sí?
Ejemplos de la relación entre documentos que hay que verificar (no es una lista cerrada):
- Superficie ↔ demanda hídrica ↔ caudal disponible ↔ caudal de diseño ↔ presupuesto.
- La superficie de la memoria coincide con la de los planos y la identificación de riego.
- El caudal de diseño no excede el derecho de agua ni el caudal disponible al 85%.
- La potencia del sistema FV cubre la bomba del diseño hidráulico.
- El presupuesto corresponde a las obras dibujadas y cubicadas.
- El monto solicitado de bonificación es proporcional a la superficie de nuevo riego.
- La secuencia constructiva (cronograma, obras civiles, tecnificación, energización) tiene un
  orden lógico y ejecutable, sin depender de una obra que aparece después de la que la necesita.
- El plazo total del cronograma es compatible con el plazo reglamentario según el monto del
  proyecto en UF (12 o 36 meses).
- La estructura de partidas del presupuesto (Sistema de riego / Obras civiles) refleja lo
  mostrado en planos y cubicaciones, sin ítems de un componente apareciendo solo en el otro
  documento.
Marca cualquier CONTRADICCIÓN entre documentos o quiebre en la lógica global del proyecto. Este
es el cierre que atrapa los errores que se escapan al revisar documento por documento — NO es una
segunda pasada que repite lo que cada ítem individual ya detectó por su cuenta.""",
    },
}

# Orden de presentación de los ítems SEP (tal como se ingresan en el sistema). "coherencia" va
# al final: cierre transversal después de haber revisado todos los ítems individuales.
ITEMS_ORDEN = ["plano_ubicacion", "identificacion_riego", "hidrologico", "pruebas_bombeo",
               "diseno_hidraulico", "diseno_fotovoltaico", "estudios_complementarios",
               "especificaciones_tecnicas", "cronograma", "presupuesto", "presupuesto_electrico",
               "cotizaciones_facturas", "declaracion_iva", "planos_tecnificacion",
               "planos_obras_civiles", "memoria_superficies", "estudio_suelos", "coherencia"]


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
        {"key": "superficie_predial",   "label": "Superficie Cert. Avalúo", "tipo": "text"},
        {"key": "rol",                  "label": "Rol",                    "tipo": "text"},
        {"key": "clase",                "label": "Clase declarada en SEP", "tipo": "text",
         "linea_con": "superficie_clase_sep"},
        {"key": "superficie_clase_sep", "label": "Superficie (SEP)",       "tipo": "text"},
        {"key": "predio_bonificado",    "label": "Predio bonificado",      "tipo": "text"},
        {"key": "tenencia",             "label": "Tenencia",               "tipo": "text"},
    ]},
    {"titulo": "4. Derechos de agua (DAA)", "campos": [
        {"key": "daa", "label": "Derechos de aprovechamiento de aguas", "tipo": "textarea"},
    ]},
    {"titulo": "5. Uso actual del suelo", "campos": [
        {"key": "uso_actual_suelo", "label": "Uso Actual Suelo (SEP)", "tipo": "textarea"},
    ]},
    {"titulo": "6. Obras", "campos": [
        {"key": "obras", "label": "Obras del proyecto", "tipo": "textarea"},
    ]},
    {"titulo": "7. Cultivo y superficie", "campos": [
        {"key": "cultivo_superficie", "label": "Cultivo y superficie", "tipo": "textarea"},
    ]},
    {"titulo": "Características de obras", "campos": [
        {"key": "caracteristicas_obras_resumen", "label": "Características obras", "tipo": "textarea",
         "maxlen": 300, "resumen_ia": "resumen breve, en prosa, explicando de qué se trata el "
         "proyecto — qué construye/instala y para qué (no una lista de datos sueltos)"},
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


# Documentos que alimentan cada verificación numérica determinística (independiente del ítem
# SEP que se esté revisando) — usado por analizar_item() y por las rutas de extracción de la
# página "Chequeo de Cálculos" en main.py.
# "hidraulico" y "agronomico" se solapan a propósito en diseno_hidraulico/diseno_agronomico:
# en la práctica el consultor a veces mete datos agronómicos dentro del documento clasificado
# como diseño hidráulico (o viceversa), o entrega un solo documento combinado con ambos
# cálculos — si cada extracción solo mirara su propio tipo_doc, se perdería esa información
# según cómo haya quedado clasificado el archivo. Cada extracción igual solo saca del texto los
# datos que le corresponden (Haiku recibe instrucciones específicas por tipo de cálculo), así
# que darles el mismo pool de documentos no mezcla resultados, solo evita el falso negativo.
DOCS_VERIFICACION = {
    "hidraulico": ["diseno_hidraulico", "diseno_agronomico", "planos_tecnificacion",
                   "especificaciones_tecnicas", "pruebas_bombeo"],
    "agronomico": ["diseno_agronomico", "diseno_hidraulico", "estudio_suelos",
                   "memoria_superficies"],
    "energetico": ["diseno_fotovoltaico", "reporte_explorador_solar", "presupuesto_electrico",
                   "diseno_hidraulico"],
}


def _documentos_para_verificacion(grupo_key: str, documentos: list) -> list:
    """Retorna los documentos que alimentan la verificación numérica determinística
    (hidraulico/agronomico/energetico) de la página "Chequeo de Cálculos"."""
    tipos = set(DOCS_VERIFICACION.get(grupo_key, []))
    return [d for d in documentos if d.get("tipo_doc") in tipos]


MAX_IMG_EJE = 14   # tope de imágenes (páginas) por revisión de grupo, para controlar costo

# Tipos de documento que son PLANOS: van a visión SIEMPRE que el archivo exista (aunque el PDF
# tenga capa de texto — un plano exportado de AutoCAD suele traer las cotas/textos extraíbles,
# pero la geometría del trazado solo se ve en imagen), y se renderizan en ALTA RESOLUCIÓN con
# cuadrantes ampliados (render_plano_tiles) en vez del renderizado básico de página completa —
# pensado para dibujos grandes donde el texto/cotas se pierden a escala normal.
# "identificacion_riego" se agregó jul-2026: ese documento delimita el área de riego sobre un
# plano/mapa del predio con las superficies anotadas gráficamente (polígonos, rótulos de
# hectáreas) — el texto extraído del PDF no captura esas anotaciones, así que sin visión la IA
# no las "ve" y puede observar por error que la superficie no está declarada.
TIPOS_PLANO_VISION = {"planos_tecnificacion", "planos_obras_civiles", "plano_ubicacion",
                       "identificacion_riego"}

# Tipos que van a visión SIEMPRE que el archivo exista, igual que TIPOS_PLANO_VISION, pero SIN
# el renderizado en cuadrantes (no son dibujos grandes — usan el renderizado básico de página
# completa). "pruebas_bombeo" se agregó jul-2026: el informe suele traer una tabla de datos
# (caudal, tiempos, niveles) y la curva de descenso/recuperación como GRÁFICO — ninguno de los
# dos se captura en el texto extraído del PDF, así que sin visión la IA solo "conocía" la mitad
# del documento (la parte narrativa), sin poder leer la tabla ni ver la forma de la curva.
TIPOS_SIEMPRE_VISION = TIPOS_PLANO_VISION | {"pruebas_bombeo"}


# ── Verificación numérica determinística (hidráulica y agronómica) ─────────────
# En vez de que la IA haga la matemática de memoria a partir de texto libre, se extraen los
# datos numéricos declarados por el consultor (Haiku, extracción barata) y se recalculan con
# las mismas fórmulas del Diseñador de Riego (calculos_riego.py) — Hazen-Williams y la cadena
# agronómica ETo→ETc→AD→Dn→Fr→Db. El resultado se inyecta como bloque de alta confianza en el
# prompt de _analizar_grupo, distinto de "criterios de énfasis" (eso es criterio; esto es cálculo).

MAX_TOKENS_EXTRACCION = 1500


def _texto_grupo_para_extraccion(docs_grupo: list, max_chars: int = 60000) -> str:
    """Texto combinado del grupo para una extracción numérica (Haiku). El presupuesto se
    reparte de forma ADAPTATIVA entre los documentos (`_repartir_presupuesto`, water-filling) —
    antes se asignaba por orden de llegada y un primer archivo largo dejaba a los demás
    completamente fuera; luego se pasó a una cuota FIJA por documento, que desperdiciaba margen
    en manuales/folletos cortos en vez de dárselo a los documentos densos que sí lo necesitan.
    Cada documento se trunca conservando inicio + final (los resultados declarados por el
    consultor suelen estar en las conclusiones, al final del documento)."""
    docs_utiles = [d for d in docs_grupo
                   if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]
    if not docs_utiles:
        return ""
    tamanos = [len(d.get("texto_extraido", "").strip()) for d in docs_utiles]
    presupuestos = _repartir_presupuesto(tamanos, max_chars, minimo=4000)
    partes = []
    for d, budget in zip(docs_utiles, presupuestos):
        t = _truncar_inteligente(d.get("texto_extraido", "").strip(), budget)
        label = d.get("tipo_doc_label") or d.get("tipo_doc", "")
        partes.append(f"--- {label} ({d.get('nombre_original','')}) ---\n{t}")
    return "\n\n".join(partes)


def _extraer_json_simple(content: str) -> dict:
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except json.JSONDecodeError:
        pass
    return {}


async def _extraer_datos_hidraulicos(docs_grupo: list, n_sistemas: int = 1) -> dict:
    """Extrae los tramos de tubería (caudal, diámetro, longitud, material) declarados en el
    diseño hidráulico. Nunca inventa: usa null si un dato no aparece en el texto.

    `n_sistemas`: 1 o 2 — mismo N° de sistemas de riego GLOBAL del proyecto que usa el Chequeo
    Agronómico (un proyecto con 2 sistemas de riego tiene 2 diseños hidráulicos distintos, uno
    por sistema — no puede declarar 2 en Agronómico y 1 en Hidráulico). Si es 2, se le pide a la
    IA identificar los tramos de CADA sistema por separado (normalmente en bloques con su propio
    encabezado, igual que en el cálculo agronómico).
    Retorna siempre {"sistemas": [ {"tramos": [...]}, ... ]} — un objeto por sistema."""
    texto = _texto_grupo_para_extraccion(docs_grupo)
    if not texto.strip():
        return {}
    n = 2 if n_sistemas == 2 else 1
    if n == 2:
        instr_sistemas = (
            "\n\nEste proyecto declara 2 SISTEMAS DE RIEGO DISTINTOS (ej. un sector con goteo y "
            "otro con aspersión), cada uno con su propio diseño hidráulico. Los consultores "
            "habitualmente presentan los tramos de cada sistema en un bloque separado, con su "
            "propio encabezado o título. Identifica cada bloque y extrae sus tramos POR "
            "SEPARADO — NO mezcles tramos de un sistema con otro. Responde el array \"sistemas\" "
            "con EXACTAMENTE 2 objetos, en el mismo orden en que aparecen los encabezados en el "
            "expediente (el que aparece primero en el texto va primero en el array).")
    else:
        instr_sistemas = "\n\nEste proyecto declara un solo sistema de riego. Responde el array \"sistemas\" con exactamente 1 objeto."
    prompt = f"""Extrae del siguiente expediente los TRAMOS de tubería del diseño hidráulico
(matriz, terciaria, lateral, succión, etc.) con sus datos numéricos declarados.
{instr_sistemas}

NO inventes ni calcules nada — si un dato no aparece explícitamente, usa null.
Responde SOLO este JSON, sin texto adicional:
{{"sistemas": [
{{"tramos": [{{"nombre": "ej: Matriz / Lateral crítico", "caudal_ls": number|null,
"diametro_mm": number|null, "longitud_m": number|null,
"material": "pvc"|"pe"|"aluminio"|null, "velocidad_declarada_ms": number|null}}]}}
]}}

EXPEDIENTE:
{texto}"""
    try:
        client = _get_client()
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODELO_HAIKU, max_tokens=MAX_TOKENS_EXTRACCION * n,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extraer_json_simple(_texto_respuesta(response))
        sistemas = data.get("sistemas")
        if not isinstance(sistemas, list) or not sistemas:
            return {}
        return {"sistemas": sistemas[:n]}
    except Exception as e:
        print(f"⚠️ _extraer_datos_hidraulicos: {e}")
        return {}


# DT-05: rango de valores de Kc aceptados por CNR (Ley 18.450) para elaborar diseños de riego.
# Clave normalizada (minúsculas, sin tildes) → (Kc mínimo, Kc máximo). Fuente:
# normativa/DT-05_Rangos_Kc_Cultivos.txt — mantener sincronizado si ese archivo cambia.
KC_RANGOS_DT05 = {
    "alfalfa": (0.85, 1.00), "almendro": (0.95, 1.05), "arandano": (0.60, 1.00),
    "arroz": (1.05, 1.15), "avellano europeo": (0.70, 0.80), "cerezo": (1.00, 1.25),
    "ciruelo": (0.90, 1.15), "damasco": (0.80, 1.15),
    "duraznero y nectarino": (1.00, 1.15), "esparragos": (1.00, 1.10),
    "frambuesa": (0.70, 0.80), "granado": (0.80, 0.95), "kiwi": (1.10, 1.20),
    "limonero": (0.60, 0.80), "maiz": (1.00, 1.10), "manzano": (1.05, 1.25),
    "naranjo": (0.65, 0.90), "nogal": (0.90, 1.10), "olivo para mesa": (0.50, 0.80),
    "olivo para aceite": (0.40, 0.80), "palto": (0.75, 0.85), "papas": (1.00, 1.10),
    "peral": (1.00, 1.15), "pistacho": (1.10, 1.30), "pradera": (0.90, 1.05),
    "remolacha": (1.00, 1.10), "tabaco": (0.95, 1.10), "tomate": (1.00, 1.10),
    "tuna": (0.25, 0.35), "vides viniferas": (0.50, 0.60), "vid de mesa": (1.00, 1.30),
}

# Nombres/variantes comunes en Chile que no calzan literal con la columna "Cultivo" de DT-05
# (singular/plural, sinónimo, nombre de la fruta en vez del árbol) → clave canónica de arriba.
_KC_ALIAS_DT05 = {
    "palta": "palto", "paltas": "palto", "aguacate": "palto",
    "uva de mesa": "vid de mesa", "uvas de mesa": "vid de mesa",
    "uva vinifera": "vides viniferas", "uvas viniferas": "vides viniferas",
    "vid": "vid de mesa", "vides": "vides viniferas",
    "durazno": "duraznero y nectarino", "duraznos": "duraznero y nectarino",
    "nectarin": "duraznero y nectarino", "nectarina": "duraznero y nectarino",
    "nectarinas": "duraznero y nectarino",
    "cereza": "cerezo", "cerezas": "cerezo", "manzana": "manzano", "manzanas": "manzano",
    "pera": "peral", "peras": "peral", "naranja": "naranjo", "naranjas": "naranjo",
    "limon": "limonero", "limones": "limonero", "nuez": "nogal", "nueces": "nogal",
    "almendra": "almendro", "almendras": "almendro",
    "avellana": "avellano europeo", "avellanas": "avellano europeo",
    "avellano": "avellano europeo", "damascos": "damasco",
    "granada": "granado", "granadas": "granado", "kiwis": "kiwi",
    "arandanos": "arandano", "frambuesas": "frambuesa", "esparrago": "esparragos",
    "tomates": "tomate", "papa": "papas", "patata": "papas", "patatas": "papas",
    "maices": "maiz", "praderas": "pradera", "pasto": "pradera", "pastizal": "pradera",
    "tunas": "tuna", "pistachos": "pistacho", "ciruela": "ciruelo", "ciruelas": "ciruelo",
}


def _normalizar_cultivo(texto: str) -> str:
    import unicodedata
    s = (texto or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def _buscar_rango_kc(cultivo: str):
    """Busca el rango Kc DT-05 para un cultivo declarado en texto libre (nombre exacto, alias
    común, o substring — ej. "Vid de mesa cv. Thompson Seedless"). Retorna (clave_canonica,
    kc_min, kc_max), o None si el cultivo no está cubierto por DT-05 o el nombre es ambiguo
    (ej. "olivo" solo, sin especificar mesa/aceite — mejor no adivinar)."""
    if not cultivo:
        return None
    s = _normalizar_cultivo(cultivo)
    if s in KC_RANGOS_DT05:
        return (s,) + KC_RANGOS_DT05[s]
    if s in _KC_ALIAS_DT05:
        clave = _KC_ALIAS_DT05[s]
        return (clave,) + KC_RANGOS_DT05[clave]
    candidatos = {k for k in KC_RANGOS_DT05 if k in s or s in k}
    for alias, clave in _KC_ALIAS_DT05.items():
        if alias in s or s in alias:
            candidatos.add(clave)
    if len(candidatos) == 1:
        clave = next(iter(candidatos))
        return (clave,) + KC_RANGOS_DT05[clave]
    return None


async def _extraer_datos_agronomicos(docs_grupo: list, n_sistemas: int = 1) -> dict:
    """Extrae los datos de la cadena de demanda agronómica declarados en el diseño, más los
    datos base del diseño de riego (superficie, caudal disponible, precipitación del sistema,
    horas disponibles) y lo que el consultor declara como caudal de diseño/tiempo de riego/N°
    de sectores. Nunca inventa: usa null si un dato no aparece en el texto.

    `n_sistemas`: 1 o 2 — cuántos sistemas de riego distintos declara el proyecto (fijado por
    el revisor en la página "Chequeo de Cálculos", ANTES de extraer). Si es 2, el expediente
    normalmente trae el cálculo de cada sistema en un bloque separado con su propio encabezado
    (ej. "Cálculo agronómico — Sector Goteo" / "Cálculo agronómico — Sector Aspersión") — se le
    pide a la IA identificar cada bloque y extraerlo por separado en vez de mezclar datos de
    ambos sistemas en un mismo campo (bug real detectado en producción: con un único bloque, la
    extracción tomaba en silencio los datos de un solo sistema sin avisar cuál).
    Retorna siempre {"sistemas": [ {...}, ... ]} — un objeto por sistema, en el mismo orden en
    que aparecen en el expediente."""
    texto = _texto_grupo_para_extraccion(docs_grupo)
    if not texto.strip():
        return {}
    n = 2 if n_sistemas == 2 else 1
    if n == 2:
        instr_sistemas = (
            "\n\nEste proyecto declara 2 SISTEMAS DE RIEGO DISTINTOS (ej. un sector con goteo y "
            "otro con aspersión). Los consultores habitualmente presentan el cálculo de cada "
            "sistema en un bloque separado dentro del expediente, con su propio encabezado o "
            "título que lo identifica (ej. \"Sector Goteo\" / \"Sector Aspersión\"). Identifica "
            "cada bloque y extrae sus datos POR SEPARADO — NO mezcles datos de un sistema con "
            "otro en un mismo objeto. Responde el array \"sistemas\" con EXACTAMENTE 2 objetos, "
            "en el mismo orden en que aparecen los encabezados en el expediente (el que aparece "
            "primero en el texto va primero en el array).")
    else:
        instr_sistemas = "\n\nEste proyecto declara un solo sistema de riego. Responde el array \"sistemas\" con exactamente 1 objeto."
    prompt = f"""Extrae del siguiente expediente los datos del cálculo de demanda agronómica
(cultivo/especie principal del proyecto, capacidad de campo, punto de marchitez, densidad
aparente, profundidad radicular, Kc, evapotranspiración del mes crítico, factor de agotamiento
— también llamado "criterio de riego" o "% de agua aprovechable" en algunos documentos, es el
mismo dato —, eficiencia del sistema, y los resultados finales que el consultor declara: lámina
neta, frecuencia de riego, demanda bruta),
además de los datos base del diseño de riego: superficie de riego del proyecto, caudal
disponible (fuente/derecho de agua), precipitación (tasa de aplicación) del sistema de riego,
horas disponibles de riego al día, volumen de un ACUMULADOR/estanque/tranque regulador si el
proyecto declara uno (para aumentar el caudal instantáneo disponible respecto al de la fuente),
y lo que el consultor declara como resultado: caudal de diseño del sistema, tiempo de riego por
sector y número de sectores de riego.
También extrae el SISTEMA DE RIEGO (Goteo, Microaspersión, Aspersión, o Carrete) y el
espaciamiento del sistema: si es Goteo/Microaspersión, distancia entre hileras, distancia entre
plantas o sobre hilera, N° de líneas de emisor y espaciamiento entre emisores (marco de
plantación del cultivo); si es Aspersión/Carrete, espaciamiento entre aspersores y entre
laterales (NO el marco de plantación — en aspersión no aplica). Si el sistema es Aspersión,
extrae además la VIB (Velocidad de Infiltración Básica del suelo, mm/hr) — para verificar que
no la supere la precipitación/tasa de aplicación del sistema (riesgo de escorrentía).
{instr_sistemas}

NO inventes ni calcules nada — si un dato no aparece explícitamente, usa null.
Responde SOLO este JSON, sin texto adicional, donde cada objeto de "sistemas" tiene esta forma:
{{"sistemas": [
{{"cultivo": string|null, "sistema_riego": "Goteo"|"Microaspersión"|"Aspersión"|"Carrete"|null,
"distancia_hileras_m": number|null, "distancia_plantas_m": number|null,
"n_lineas_emisor": number|null, "espaciamiento_emisores_m": number|null,
"espaciamiento_aspersores_m": number|null, "espaciamiento_laterales_m": number|null,
"cc_pct": number|null, "pmp_pct": number|null, "da": number|null,
"prof_radicular_cm": number|null, "kc": number|null, "eto_dia_mm": number|null,
"factor_agotamiento_pct": number|null, "eficiencia_pct": number|null,
"superficie_riego_ha": number|null, "caudal_disponible_ls": number|null,
"precipitacion_sistema_mmhr": number|null, "horas_disponibles_dia": number|null,
"volumen_acumulador_m3": number|null, "vib_mmhr": number|null,
"declarado": {{"dn_mm": number|null, "fr_dias": number|null, "db_mm": number|null,
"caudal_diseno_ls": number|null, "tiempo_riego_hr": number|null, "n_sectores": number|null}}}}
]}}

EXPEDIENTE:
{texto}"""
    try:
        client = _get_client()
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODELO_HAIKU, max_tokens=MAX_TOKENS_EXTRACCION * n,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extraer_json_simple(_texto_respuesta(response))
        sistemas = data.get("sistemas")
        if not isinstance(sistemas, list) or not sistemas:
            return {}
        return {"sistemas": sistemas[:n]}
    except Exception as e:
        print(f"⚠️ _extraer_datos_agronomicos: {e}")
        return {}


def _diferencia_relevante(calculado: float, declarado: float, tolerancia_pct: float = 10) -> bool:
    if not calculado or declarado is None:
        return False
    return abs(calculado - declarado) / calculado * 100 > tolerancia_pct


def _bloque_verificacion_hidraulica(datos: dict) -> str:
    """Punto de entrada: recibe {"sistemas": [ {"tramos": [...]}, ... ]} (1 o 2 sistemas de
    riego, mismo N° global que el Chequeo Agronómico) y arma el bloque de verificación
    hidráulica para inyectar en el prompt del ítem. Con 1 sistema es un solo bloque (igual que
    antes); con 2, cada sistema se recalcula por separado y se etiqueta explícitamente."""
    sistemas = (datos or {}).get("sistemas") or []
    if not sistemas:
        return ""
    if len(sistemas) == 1:
        return _bloque_verificacion_hidraulica_sistema(sistemas[0])
    bloques = []
    for i, s in enumerate(sistemas, start=1):
        cuerpo = _bloque_verificacion_hidraulica_sistema(s)
        if cuerpo:
            bloques.append(f"\n\n=== SISTEMA DE RIEGO {i} — DISEÑO HIDRÁULICO ===" + cuerpo)
    if not bloques:
        return ""
    return ("\n\nEste proyecto declara 2 sistemas de riego distintos — a continuación la "
            "verificación hidráulica de CADA sistema por separado. Trátalos de forma "
            "independiente: NO compares ni mezcles tramos/velocidades de un sistema con el "
            "otro — cada uno tiene su propio diseño y puede tener valores distintos y "
            "correctos.") + "".join(bloques)


def _bloque_verificacion_hidraulica_sistema(datos: dict) -> str:
    """Recalcula velocidad/pérdida de carga por tramo (Hazen-Williams) para UN sistema de
    riego y arma el bloque. Solo compara lo que efectivamente se pudo extraer."""
    tramos = (datos or {}).get("tramos") or []
    lineas = []
    for t in tramos:
        q = t.get("caudal_ls")
        d = t.get("diametro_mm")
        if not q or not d:
            continue
        c = calculos_riego.C_HAZEN_WILLIAMS.get((t.get("material") or "").lower())
        r = calculos_riego.evaluar_tramo(q, d, t.get("longitud_m"), c)
        nombre = t.get("nombre") or "Tramo"
        linea = (f"- {nombre}: Q={q} l/s, Ø={d} mm → V recalculada = {r['velocidad_ms']} m/s "
                 f"(Ø sugerido para V≤1,5 m/s: {r['diametro_sugerido_mm']} mm)")
        if r["hf_mca"] is not None:
            linea += f", Hf = {r['hf_mca']} mca (Hazen-Williams, C={c})"
        if r["alerta"]:
            linea += f" ⚠️ {r['alerta']}"
        vel_decl = t.get("velocidad_declarada_ms")
        if vel_decl is not None and _diferencia_relevante(r["velocidad_ms"], vel_decl, 15):
            linea += (f" — el expediente declara V={vel_decl} m/s, no coincide con el "
                      f"cálculo (revisar el dato base o la fórmula usada por el consultor).")
        lineas.append(linea)
    if not lineas:
        return ""
    return ("\n\nVERIFICACIÓN HIDRÁULICA (cálculo determinístico con Hazen-Williams, misma "
            "fórmula normativa del Diseñador de Riego — no es una estimación de la IA, es un "
            "recálculo exacto a partir del caudal y diámetro que declara el expediente):\n"
            + "\n".join(lineas) +
            "\n\nSi hay una alerta de velocidad fuera de rango (0,5–2,0 m/s) o una diferencia "
            "relevante con lo declarado, genera una observación citando los números exactos "
            "de este cálculo. Si todo está dentro de rango, NO lo menciones como observación.")


def _bloque_verificacion_agronomica(datos: dict) -> str:
    """Punto de entrada: recibe {"sistemas": [ {...}, ... ]} (1 o 2 sistemas de riego) y arma el
    bloque de verificación agronómica para inyectar en el prompt del ítem. Con 1 sistema es un
    solo bloque (igual que antes); con 2, cada sistema se recalcula por separado y se etiqueta
    explícitamente, para que la IA no cruce parámetros (Kc/eficiencia/etc.) entre sistemas."""
    sistemas = (datos or {}).get("sistemas") or []
    if not sistemas:
        return ""
    if len(sistemas) == 1:
        return _bloque_verificacion_agronomica_sistema(sistemas[0])
    bloques = []
    for i, s in enumerate(sistemas, start=1):
        nombre_sis = s.get("sistema_riego") or f"Sistema {i}"
        cuerpo = _bloque_verificacion_agronomica_sistema(s)
        if cuerpo:
            bloques.append(f"\n\n=== SISTEMA DE RIEGO {i} ({nombre_sis}) ==="+ cuerpo)
    if not bloques:
        return ""
    return ("\n\nEste proyecto declara 2 sistemas de riego distintos — a continuación la "
            "verificación agronómica de CADA sistema por separado (bloques \"SISTEMA DE RIEGO "
            "1\"/\"SISTEMA DE RIEGO 2\"). Trátalos de forma independiente: NO compares ni "
            "mezcles parámetros (Kc, eficiencia, factor de agotamiento, etc.) de un sistema con "
            "el otro — cada uno puede tener valores distintos y correctos.") + "".join(bloques)


def _bloque_verificacion_agronomica_sistema(datos: dict) -> str:
    """Recalcula la cadena ETo→ETc→AD→Dn→Fr→Db para UN sistema de riego y arma el bloque.
    Además valida el Kc declarado contra los rangos oficiales DT-05 — este chequeo es
    INDEPENDIENTE del resto (solo necesita cultivo+Kc, no la cadena completa)."""
    if not datos:
        return ""

    texto = ""
    if datos.get("sistema_riego") == "Mixto":
        texto += ("\n\nAVISO: el proyecto declara MÁS DE UN sistema de riego (ej. goteo en un "
                  "sector y aspersión en otro). Los datos agronómicos que siguen (Kc, "
                  "eficiencia, factor de agotamiento, etc.) corresponden solo al sistema "
                  "principal/de mayor superficie — no asumas que aplican a todo el proyecto. Si "
                  "detectas que el otro sistema tiene parámetros claramente distintos declarados "
                  "en el expediente (ej. otra eficiencia u otro Kc) que no se están verificando "
                  "acá, adviértelo en una observación informativa.")
    cultivo, kc = datos.get("cultivo"), datos.get("kc")
    if cultivo and kc is not None:
        match = _buscar_rango_kc(cultivo)
        if match:
            clave, kc_min, kc_max = match
            texto += (f"\n\nVERIFICACIÓN Kc vs. DT-05 (cálculo determinístico — rango oficial "
                      f"CNR para \"{clave}\": {kc_min}–{kc_max}): el expediente declara Kc={kc} "
                      f"para el cultivo \"{cultivo}\".")
            if not (kc_min <= kc <= kc_max):
                texto += (f" Kc FUERA del rango DT-05 — según DT-05, un Kc fuera de rango debe "
                          f"respaldarse con publicaciones de instituciones reconocidas; si el "
                          f"expediente no lo respalda, genera una observación citando el rango "
                          f"oficial ({kc_min}–{kc_max}) y el valor declarado ({kc}).")
            else:
                texto += " Dentro del rango — no lo menciones como observación."

    # VIB vs. Precipitación del sistema — solo Aspersión, independiente del resto de la cadena.
    vib = datos.get("vib_mmhr")
    precip = datos.get("precipitacion_sistema_mmhr")
    if datos.get("sistema_riego") == "Aspersión" and vib is not None and precip is not None:
        vib_check = calculos_riego.verificacion_vib(vib, precip)
        if vib_check:
            texto += (f"\n\nVERIFICACIÓN VIB vs. PRECIPITACIÓN DEL SISTEMA (cálculo determinístico "
                      f"— la Velocidad de Infiltración Básica del suelo debe superar la "
                      f"precipitación/tasa de aplicación del sistema, si no hay riesgo de "
                      f"escorrentía; mismo criterio del Diseñador de Riego): VIB={vib} mm/hr, "
                      f"Precipitación del sistema={precip} mm/hr.")
            if not vib_check["vib_ok"]:
                texto += (f" La precipitación SUPERA la VIB del suelo — genera una observación "
                          f"citando estos números exactos (riesgo de escorrentía; se sugiere "
                          f"reducir el caudal del aspersor o aumentar el espaciamiento).")
            else:
                texto += " VIB > Precipitación — dentro de rango, no lo menciones como observación."

    # Goteo: riego de alta frecuencia, Db directo de ETc sin factor de agotamiento (modelo
    # calcGA del Diseñador). No requiere ni usa el criterio de riego.
    alta_frec = datos.get("sistema_riego") == "Goteo"
    base = ["cc_pct", "pmp_pct", "da", "prof_radicular_cm", "kc", "eto_dia_mm", "eficiencia_pct"]
    if not alta_frec:
        base.append("factor_agotamiento_pct")
    if any(datos.get(k) is None for k in base):
        return texto
    r = calculos_riego.cadena_agronomica(
        datos["cc_pct"], datos["pmp_pct"], datos["da"], datos["prof_radicular_cm"],
        datos["kc"], datos["eto_dia_mm"], datos.get("factor_agotamiento_pct"),
        datos["eficiencia_pct"], alta_frecuencia=alta_frec)
    declarado = datos.get("declarado") or {}
    if alta_frec:
        lineas = [
            f"ETc = ETo × Kc = {datos['eto_dia_mm']} × {datos['kc']} = {r['etc_mm_dia']} mm/día",
            f"Db (demanda bruta) recalculada = ETc / Ef = {r['db_mm']} mm/día (goteo: riego diario, "
            f"la demanda sale directo de la ETc — sin factor de agotamiento)",
        ]
    else:
        lineas = [
            f"ETc = ETo × Kc = {datos['eto_dia_mm']} × {datos['kc']} = {r['etc_mm_dia']} mm/día",
            f"AD (agua disponible) = {r['ad_mm']} mm",
            f"Dn (lámina neta) recalculada = {r['dn_mm']} mm",
            f"Fr (frecuencia de riego) recalculada = {r['fr_adj_dias']} días",
            f"Db (demanda bruta) recalculada = {r['db_mm']} mm/día",
        ]
    comparaciones = []
    if not alta_frec and declarado.get("dn_mm") is not None and _diferencia_relevante(r["dn_adj_mm"], declarado["dn_mm"]):
        comparaciones.append(f"Dn declarada = {declarado['dn_mm']} mm — no coincide con el recálculo ({r['dn_adj_mm']} mm).")
    if not alta_frec and declarado.get("fr_dias") is not None and declarado["fr_dias"] != r["fr_adj_dias"]:
        comparaciones.append(f"Fr declarada = {declarado['fr_dias']} días — no coincide con el recálculo ({r['fr_adj_dias']} días).")
    if declarado.get("db_mm") is not None and _diferencia_relevante(r["db_mm"], declarado["db_mm"]):
        comparaciones.append(f"Db declarada = {declarado['db_mm']} mm — no coincide con el recálculo ({r['db_mm']} mm).")
    texto += ("\n\nVERIFICACIÓN AGRONÓMICA (cálculo determinístico, misma fórmula normativa del "
            "Diseñador de Riego — no es una estimación de la IA, es un recálculo exacto a partir "
            f"de los datos base que declara el expediente):\n" + "\n".join(f"- {l}" for l in lineas))
    if comparaciones:
        texto += ("\n\nDISCREPANCIAS con lo declarado en el expediente:\n"
                  + "\n".join(f"- {c}" for c in comparaciones) +
                  "\nGenera una observación citando estos números exactos.")
    else:
        texto += "\n\nSin datos declarados para comparar, o coinciden con el recálculo — no lo menciones como observación."

    volumen_acum = datos.get("volumen_acumulador_m3")
    diseno = calculos_riego.verificacion_diseno_riego(
        db_mm_dia=r["db_mm"],
        superficie_ha=datos.get("superficie_riego_ha"),
        caudal_disponible_ls=datos.get("caudal_disponible_ls"),
        precipitacion_mmhr=datos.get("precipitacion_sistema_mmhr"),
        horas_disponibles_dia=datos.get("horas_disponibles_dia"),
        volumen_acumulador_m3=volumen_acum,
    )
    if diseno:
        lineas_diseno = [f"Demanda = Db / 8,64 = {diseno['demanda_ls_ha']} l/s/ha"]
        superficie_decl = datos.get("superficie_riego_ha")
        caudal_para_diseno = datos.get("caudal_disponible_ls")
        if "caudal_acumulador_ls" in diseno:
            lineas_diseno.append(
                f"El proyecto declara un acumulador de {volumen_acum} m³ — caudal equivalente = "
                f"Vol×1000/(horas disponibles×3600) = {volumen_acum}×1000/"
                f"({datos.get('horas_disponibles_dia')}×3600) = {diseno['caudal_acumulador_ls']} "
                f"l/s (misma fórmula que usa el Diseñador de Riego). Este caudal REEMPLAZA al "
                f"caudal de la fuente para la superficie de riego segura y el chequeo ITT-03 de "
                f"abajo — la fuente solo necesita alcanzar para recargar el acumulador entre "
                f"riegos, no para regar directo.")
            caudal_para_diseno = diseno["caudal_acumulador_ls"]
        if "superficie_segura_ha" in diseno:
            etiqueta_caudal = "del acumulador" if "caudal_acumulador_ls" in diseno else "disponible declarado"
            linea = (f"Superficie de riego segura (con el caudal {etiqueta_caudal} de "
                      f"{caudal_para_diseno} l/s) = {diseno['superficie_segura_ha']} ha")
            if superficie_decl is not None and diseno["superficie_segura_ha"] < superficie_decl:
                linea += (f" — MENOR a la superficie de riego del proyecto declarada "
                          f"({superficie_decl} ha): el caudal {etiqueta_caudal} no alcanza para "
                          f"regar toda la superficie con esta demanda.")
            lineas_diseno.append(linea)
        declarado_qdiseno = declarado.get("caudal_diseno_ls")
        if declarado_qdiseno is not None and caudal_para_diseno and \
                calculos_riego.requiere_acumulador(declarado_qdiseno, caudal_para_diseno):
            if "caudal_acumulador_ls" in diseno:
                lineas_diseno.append(
                    f"Caudal de diseño declarado ({declarado_qdiseno} l/s) supera el caudal "
                    f"equivalente del acumulador ({caudal_para_diseno} l/s) × 1,2 — el volumen "
                    f"de acumulador declarado ({volumen_acum} m³) no alcanza para este caudal de "
                    f"diseño; debe justificar o aumentar el volumen del acumulador.")
            else:
                lineas_diseno.append(
                    f"Caudal de diseño declarado ({declarado_qdiseno} l/s) supera el caudal "
                    f"disponible ({caudal_para_diseno} l/s) × 1,2 — según ITT-03, se "
                    f"requiere acumulador (estanque) y el expediente debe contemplarlo.")
        if "tiempo_riego_hr" in diseno:
            linea = (f"Tiempo de riego = Db / Precipitación del sistema declarada "
                      f"({datos.get('precipitacion_sistema_mmhr')} mm/hr) = {diseno['tiempo_riego_hr']} hr/día")
            declarado_triego = declarado.get("tiempo_riego_hr")
            if declarado_triego is not None and _diferencia_relevante(diseno["tiempo_riego_hr"], declarado_triego, 15):
                linea += f" — declarado = {declarado_triego} hr/día, no coincide con el recálculo."
            lineas_diseno.append(linea)
        if "n_sectores" in diseno:
            linea = f"N° de sectores = ⌊horas disponibles / tiempo de riego⌋ = {diseno['n_sectores']}"
            declarado_nsec = declarado.get("n_sectores")
            if declarado_nsec is not None and declarado_nsec != diseno["n_sectores"]:
                linea += f" — declarado = {declarado_nsec}, no coincide con el recálculo."
            lineas_diseno.append(linea)
        texto += ("\n\nVERIFICACIÓN DE DISEÑO BASE (relación demanda↔caudal↔tiempo↔sectores, "
                  "cálculo determinístico — nota: esta relación es la que usan los sistemas "
                  "localizados goteo/microaspersión del Diseñador de Riego; en aspersión/carrete "
                  "el diseño real usa un modelo de posturas más elaborado, así que trata esta "
                  "verificación como una referencia general, no como el diseño exacto si el "
                  "sistema es de aspersión o carrete):\n"
                  + "\n".join(f"- {l}" for l in lineas_diseno) +
                  "\n\nSi hay una discrepancia relevante o falta el acumulador exigido por "
                  "ITT-03, genera una observación citando los números exactos. Si todo cuadra, "
                  "no lo menciones como observación.")
    return texto


async def _extraer_datos_fv(docs_grupo: list) -> dict:
    """Extrae los datos de dimensionamiento fotovoltaico declarados (diseño FV, reporte
    Explorador Solar, presupuesto eléctrico). Nunca inventa: usa null si no aparece."""
    texto = _texto_grupo_para_extraccion(docs_grupo)
    if not texto.strip():
        return {}
    prompt = f"""Extrae del siguiente expediente los datos del dimensionamiento del sistema
fotovoltaico (bomba a alimentar, panel solar, sitio, inversor) y los resultados que declara
el consultor. NO inventes ni calcules nada — si un dato no aparece explícitamente, usa null.
Responde SOLO este JSON, sin texto adicional:
{{"pkw": number|null, "hbom": number|null, "hsp": number|null, "fp": number|null,
"wp": number|null, "vmp": number|null, "imp": number|null, "ct": number|null,
"temp": number|null, "einv": number|null, "vsis": number|null,
"declarado": {{"n_paneles": number|null, "kwp_total": number|null, "seccion_cable_mm2": number|null}}}}

Notas: pkw = potencia de la bomba en kW (si el documento da HP, conviértelo: kW = HP × 0,7457).
hbom = horas de bombeo al día. hsp = horas sol pico del sitio (del Explorador Solar CNR).
fp = factor de pérdidas del sistema (decimal 0-1, ej 0,80). wp/vmp/imp = ficha técnica del
panel (potencia nominal, voltaje y corriente en punto de máxima potencia). ct = coeficiente
de temperatura del panel (%/°C). temp = temperatura máxima del sitio. einv = eficiencia del
inversor (decimal 0-1). vsis = voltaje nominal del sistema/inversor.

EXPEDIENTE:
{texto}"""
    try:
        client = _get_client()
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODELO_HAIKU, max_tokens=MAX_TOKENS_EXTRACCION,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extraer_json_simple(_texto_respuesta(response))
    except Exception as e:
        print(f"⚠️ _extraer_datos_fv: {e}")
        return {}


def _bloque_verificacion_fv(datos: dict) -> str:
    """Recalcula el dimensionamiento fotovoltaico y arma el bloque para inyectar en el
    prompt. Solo calcula si los datos base imprescindibles están presentes."""
    if not datos:
        return ""
    base = ["pkw", "hbom", "hsp", "wp", "vmp", "imp"]
    if any(datos.get(k) is None for k in base):
        return ""
    r = calculos_riego.dimensionamiento_fv(
        pkw=datos["pkw"], hbom=datos["hbom"], hsp=datos["hsp"], fp=datos.get("fp"),
        wp=datos["wp"], vmp=datos["vmp"], imp=datos["imp"], ct=datos.get("ct"),
        temp=datos.get("temp"), einv=datos.get("einv"), vsis=datos.get("vsis"),
    )
    if not r:
        return ""
    declarado = datos.get("declarado") or {}
    lineas = [
        f"E_día requerida = P_bomba × H_bombeo = {datos['pkw']} kW × {datos['hbom']} hr = {r['e_dia_kwh']} kWh/día",
        f"N° paneles mínimo recalculado = {r['n_paneles_minimo']} (config. real: "
        f"{r['paneles_serie']} serie × {r['strings_paralelo']} paralelo = {r['n_paneles_real']} paneles)",
        f"kWp total recalculado = {r['kwp_total']} kWp",
        f"Cable DC recalculado = {r['seccion_cable_mm2']} mm² "
        f"(V campo={r['v_campo_v']} V, I campo={r['i_campo_a']} A, caída máx. 2%)",
    ]
    comparaciones = []
    if declarado.get("n_paneles") is not None and declarado["n_paneles"] < r["n_paneles_real"]:
        comparaciones.append(
            f"El expediente declara {declarado['n_paneles']} paneles — el recálculo indica "
            f"que se necesitan al menos {r['n_paneles_real']} para cubrir la energía requerida.")
    if declarado.get("kwp_total") is not None and _diferencia_relevante(r["kwp_total"], declarado["kwp_total"], 15):
        comparaciones.append(f"kWp declarado = {declarado['kwp_total']} — no coincide con el recálculo ({r['kwp_total']} kWp).")
    if declarado.get("seccion_cable_mm2") is not None and declarado["seccion_cable_mm2"] < r["seccion_cable_mm2"]:
        comparaciones.append(
            f"Sección de cable DC declarada = {declarado['seccion_cable_mm2']} mm² — el "
            f"recálculo sugiere al menos {r['seccion_cable_mm2']} mm² para no exceder la caída de tensión del 2%.")
    texto = ("\n\nVERIFICACIÓN FOTOVOLTAICA (cálculo determinístico con la cadena de "
            "dimensionamiento del Diseñador de Riego — no es una estimación de la IA, es un "
            "recálculo exacto a partir de los datos base que declara el expediente):\n"
            + "\n".join(f"- {l}" for l in lineas))
    if comparaciones:
        texto += ("\n\nDISCREPANCIAS con lo declarado en el expediente:\n"
                  + "\n".join(f"- {c}" for c in comparaciones) +
                  "\nGenera una observación citando estos números exactos.")
    else:
        texto += "\n\nSin datos declarados para comparar, o coinciden con el recálculo — no lo menciones como observación."
    return texto


# ── Verificación de precios contra la tabla de precios referenciales promedio ──────
# A diferencia de las verificaciones anteriores (fórmulas exactas), esto compara texto libre
# (la partida del presupuesto) contra un catálogo de referencia — es inherentemente aproximado
# (match por similitud de palabras, no por código de producto). NO es una copia oficial de la
# CNR: es una tabla de precios promedio que el revisor arma y sube en /admin/precios (Excel:
# categoria/item/unidad/precio); si no ha subido nada, este bloque queda vacío y el análisis
# del presupuesto sigue igual que siempre (puramente aditivo).

TOLERANCIA_PRECIO_PCT = 30   # variación normal de mercado; fuera de este rango se observa
_STOPWORDS_PRECIO = {"de", "del", "la", "el", "los", "las", "para", "con", "y", "en", "a",
                      "un", "una", "por", "su"}


def _tokens_precio(texto: str) -> set:
    texto = re.sub(r"[^\w\s]", " ", (texto or "").lower())
    return {t for t in texto.split() if t and t not in _STOPWORDS_PRECIO}


def _similitud_item_precio(a: str, b: str) -> float:
    """Similitud por solapamiento de palabras (Jaccard) — más robusto que comparar caracteres
    ante reordenamientos ("Tubería PVC 110mm C-10" vs "Tubería PVC clase 10 diámetro 110mm")."""
    ta, tb = _tokens_precio(a), _tokens_precio(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _mejor_match_precio(item_texto: str, tabla_precios: list):
    mejor, mejor_score = None, 0.0
    for ref in tabla_precios:
        score = _similitud_item_precio(item_texto, f"{ref.get('categoria','')} {ref.get('item','')}")
        if score > mejor_score:
            mejor, mejor_score = ref, score
    return mejor if mejor_score >= 0.35 else None


async def _extraer_partidas_presupuesto(docs_grupo: list) -> dict:
    """Extrae las partidas (ítem, unidad, cantidad, precio unitario) declaradas en el
    presupuesto. Nunca inventa: usa null si un dato no aparece en el texto."""
    texto = _texto_grupo_para_extraccion(docs_grupo)
    if not texto.strip():
        return {}
    prompt = f"""Extrae del siguiente presupuesto TODAS las partidas de materiales/equipos con
sus datos declarados. NO inventes ni calcules nada — si un dato no aparece explícitamente, usa null.
Responde SOLO este JSON, sin texto adicional:
{{"partidas": [{{"item": "descripción de la partida tal como aparece", "unidad": "un"|"m"|"m2"|"m3"|"kg"|null,
"cantidad": number|null, "precio_unitario": number|null}}]}}

⚠️ NOTACIÓN CHILENA: coma (,) = decimal · punto (.) = miles. Ej: "1.234,56" = 1234.56. Convierte
todos los precios a número plano sin separador de miles.

PRESUPUESTO:
{texto}"""
    try:
        client = _get_client()
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODELO_HAIKU, max_tokens=4000,   # presupuestos pueden tener muchas partidas
            messages=[{"role": "user", "content": prompt}],
        )
        return _extraer_json_tolerante(_texto_respuesta(response))
    except Exception as e:
        print(f"⚠️ _extraer_partidas_presupuesto: {e}")
        return {}


def _extraer_json_tolerante(content: str) -> dict:
    """Como _extraer_json_simple, pero si el JSON quedó cortado a mitad (lista larga de
    partidas y el thinking se comió el cupo), reintenta cerrando llaves/corchetes abiertos."""
    data = _extraer_json_simple(content)
    if data:
        return data
    try:
        start = content.find("{")
        if start < 0:
            return {}
        frag = content[start:]
        frag += "]" * (frag.count("[") - frag.count("]"))
        frag += "}" * (frag.count("{") - frag.count("}"))
        return json.loads(frag)
    except Exception:
        return {}


def _bloque_verificacion_precios(partidas: list, tabla_precios: list) -> str:
    """Compara cada partida declarada contra su mejor match en la tabla de precios
    referenciales PROMEDIO (no oficial de la CNR). Solo reporta las que exceden
    TOLERANCIA_PRECIO_PCT — evita ruido en partidas que calzan razonablemente con el precio
    de referencia."""
    if not partidas or not tabla_precios:
        return ""
    lineas = []
    for p in partidas:
        item_texto = (p.get("item") or "").strip()
        precio_decl = p.get("precio_unitario")
        if not item_texto or precio_decl is None:
            continue
        match = _mejor_match_precio(item_texto, tabla_precios)
        if not match or not match.get("precio"):
            continue
        precio_ref = match["precio"]
        diff_pct = (precio_decl - precio_ref) / precio_ref * 100
        if abs(diff_pct) < TOLERANCIA_PRECIO_PCT:
            continue
        signo = "sobreprecio" if diff_pct > 0 else "posible subvaluación"
        unidad = f"/{p['unidad']}" if p.get("unidad") else ""
        lineas.append(
            f'- "{item_texto}" declarado a ${precio_decl:,.0f}{unidad} vs referencia CNR '
            f'"{match["item"]}" (categoría {match.get("categoria","")}) = ${precio_ref:,.0f} '
            f'→ {signo} de {abs(diff_pct):.0f}%'
        )
    if not lineas:
        return ""
    return ("\n\nVERIFICACIÓN DE PRECIOS (comparación contra una tabla de precios referenciales "
            "PROMEDIO que subió el revisor — NO es una tabla oficial certificada por la CNR, es "
            "una referencia aproximada; el match entre la partida y el catálogo también es "
            "aproximado por similitud de texto, NO por código de producto exacto. Verifica tú "
            "mismo que el match corresponda al mismo producto antes de observar, ignora los que "
            "no calcen, y no cites esto como \"precio oficial CNR\" en la observación — di "
            "\"precio referencial promedio\"):\n"
            + "\n".join(lineas) +
            f"\n\nSi la diferencia es real y el match es correcto (>±{TOLERANCIA_PRECIO_PCT}% de "
            "diferencia), genera una observación citando los montos exactos. Si el match no "
            "corresponde al mismo producto, ignóralo por completo — no lo menciones.")


async def _analizar_grupo(nombre: str, checklist: str, docs_grupo: list, documentos: list, *,
                          modo: str = "EJE TEMÁTICO", es_coherencia: bool = False,
                          observaciones_previas: list = None,
                          bases_texto: str = "", concurso_id: str = "",
                          feedback_concurso: list = None, feedback_key: str = "",
                          criterios_aprendidos: str = "", criterios_enfasis: str = "",
                          bloque_verificacion: str = "",
                          consultor: dict = None, resumen: dict = None,
                          max_chars_total: int = MAX_CHARS_EJE_TOTAL,
                          tipo_revision: str = "tecnica", ruta_uploads: str = None) -> dict:
    """
    Núcleo de análisis de un grupo de documentos (eje temático o ítem del SEP).
    Cruza los documentos del grupo en UNA llamada; usa texto extraído + VISIÓN para
    documentos escaneados/planos (si el archivo físico existe y no es coherencia global).
    Retorna dict: {observaciones: [...], docs_incluidos: [...], sin_documentos: bool}.
    """
    import os as _os

    # Separar documentos con texto de documentos-imagen (escaneados / planos / pruebas de bombeo).
    # Los tipos en TIPOS_SIEMPRE_VISION van a visión aunque tengan texto extraíble (texto E
    # imagen a la vez): la capa de texto trae cotas/rótulos/narrativa, pero el trazado, o una
    # tabla/gráfico incrustado como imagen, solo se ve en la imagen.
    docs_texto  = []
    docs_imagen = []   # (doc, filepath)
    for d in docs_grupo:
        t = d.get("texto_extraido", "").strip()
        es_imagen = (t == "__PDF_ESCANEADO__" or len(t) < MIN_CHARS_TEXTO)
        es_siempre_vision = d.get("tipo_doc") in TIPOS_SIEMPRE_VISION
        fp = _os.path.join(ruta_uploads, d.get("filename", "")) if ruta_uploads else ""
        pdf_disponible = (fp and d.get("filename", "").lower().endswith(".pdf")
                          and _os.path.exists(fp))
        if not es_coherencia and pdf_disponible and (es_imagen or es_siempre_vision):
            docs_imagen.append((d, fp))
            if es_imagen:
                continue
        if t not in ("", "__PDF_ESCANEADO__"):
            docs_texto.append(d)

    # Documentos del grupo que NO entraron ni como texto ni como imagen — caso: escaneado
    # ("__PDF_ESCANEADO__", cero texto extraíble) Y sin archivo físico disponible para visión
    # (se perdió tras un redeploy y no se pudo restaurar desde Postgres, o nunca se guardó ahí).
    # Antes desaparecían del análisis SIN NINGÚN AVISO — ni en el prompt, ni en "archivos
    # usados", ni en Railway — así que un documento crítico (ej. cálculo estructural de un
    # invernadero) podía faltar del todo sin que el revisor se enterara. Ahora se detecta y se
    # avisa por DOS vías: (1) nota informativa determinística (no depende de que la IA lo
    # mencione) y (2) aparece en "archivos usados" marcado como no leído, para que el revisor
    # sepa que tiene que resubirlo. Calculado ANTES del return temprano de abajo para que
    # también avise si TODOS los documentos del grupo quedaron excluidos (antes ahí no había
    # ningún aviso — solo el banner genérico "sin documentos disponibles").
    ids_incluidos = ({d.get("id") for d in docs_texto}
                      | {d.get("id") for d, _ in docs_imagen})
    docs_excluidos = [d for d in docs_grupo if d.get("id") not in ids_incluidos]
    observaciones_excluidos = []
    docs_incluidos_excluidos = []
    for d in docs_excluidos:
        label_doc = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        nombre_doc = d.get("nombre_original", "")
        print(f"⚠️ Grupo '{nombre}': documento excluido del análisis (sin texto extraíble y "
              f"sin archivo disponible para visión) — {label_doc} ({nombre_doc}), "
              f"id={d.get('id')}")
        observaciones_excluidos.append({
            "texto": (f'El documento "{nombre_doc}" ({label_doc}) no pudo leerse — no tiene '
                      f"texto extraíble (parece escaneado) y su archivo físico no está "
                      f"disponible (probablemente se perdió tras un redeploy). Debe resubirse "
                      f"para poder evaluarlo."),
            "categoria": "administrativa", "severidad": "informativa", "referencia_normativa": "",
        })
        docs_incluidos_excluidos.append({"id": d.get("id"), "nombre": nombre_doc,
                                         "label": label_doc + " (NO SE PUDO LEER)"})

    if not docs_texto and not docs_imagen:
        if observaciones_excluidos:
            return {"observaciones": observaciones_excluidos,
                    "docs_incluidos": docs_incluidos_excluidos, "sin_documentos": False}
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}

    client = _get_client()

    # Bloque de texto de los documentos con texto (presupuesto repartido de forma ADAPTATIVA:
    # un manual/folleto corto recibe solo lo que necesita, y el margen sobrante se le pasa a
    # los documentos que sí lo requieren — ver _repartir_presupuesto).
    tamanos = [len(d.get("texto_extraido", "")) for d in docs_texto]
    presupuestos = _repartir_presupuesto(tamanos, max_chars_total, minimo=3000)
    bloque_docs = ""
    docs_incluidos = []
    for d, budget_doc in zip(docs_texto, presupuestos):
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        texto = _truncar_inteligente(d.get("texto_extraido", ""), budget_doc)
        bloque_docs += f"\n\n{'─'*55}\nDOCUMENTO: {label}  ({d.get('nombre_original','')})\n{'─'*55}\n{texto}"
        docs_incluidos.append({"id": d.get("id"), "nombre": d.get("nombre_original"),
                               "label": label})

    # Renderizar imágenes de los documentos escaneados/planos (con tope global). Los planos
    # usan render_plano_tiles (vista completa + 4 cuadrantes ampliados por página, 5 imágenes
    # por página); el resto, el renderizado básico de página completa.
    from extractor import render_pdf_as_images, render_plano_tiles
    imagenes_por_doc = []   # (label, nombre_original, [(etiqueta_imagen, b64), ...])
    ids_imagen_lograda = set()
    ids_con_tiles = set()   # docs renderizados con render_plano_tiles (vista + 4 cuadrantes)
    motivo_fallo_imagen = {}   # doc_id -> "tope" | "cuota" | "error: <detalle>"
    # Cuota FIJA por documento (no water-filling): reserva de entrada un cupo parejo para cada
    # documento que necesita visión, para que el primero de la lista no consuma TODO el tope
    # MAX_IMG_EJE y deje a los demás sin nada — antes era estrictamente por orden de llegada.
    n_docs_imagen = len(docs_imagen)
    cuota_por_doc = max(1, MAX_IMG_EJE // n_docs_imagen) if n_docs_imagen else 0
    restante = MAX_IMG_EJE
    for d, fp in docs_imagen:
        doc_id = d.get("id")
        if restante <= 0:
            motivo_fallo_imagen[doc_id] = "tope"
            continue
        cuota_doc = min(cuota_por_doc, restante)
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        es_plano = d.get("tipo_doc") in TIPOS_PLANO_VISION
        imgs = []
        try:
            if es_plano and cuota_doc >= 5:
                pags = min(2, cuota_doc // 5)
                imgs = await asyncio.to_thread(render_plano_tiles, fp, max_pages=pags)
                if imgs:
                    ids_con_tiles.add(doc_id)
            else:
                # Sin cuota suficiente para el renderizado en alta resolución de planos
                # (render_plano_tiles pide mínimo 5 imágenes por página) — degrada a la
                # página completa básica en vez de dejar el documento sin nada. Con muchos
                # planos compitiendo por el mismo cupo, es mejor verlos todos en resolución
                # normal que perder algunos por completo.
                pags = min(cuota_doc, MAX_PAGINAS_POR_TIPO.get(d.get("tipo_doc"), 4))
                crudas = await asyncio.to_thread(render_pdf_as_images, fp, max_pages=pags)
                imgs = [(f"página {i+1}", b64) for i, b64 in enumerate(crudas)]
        except Exception as e:
            print(f"⚠️ Grupo '{nombre}': error renderizando imagen de "
                  f"'{d.get('nombre_original','')}': {e}")
            motivo_fallo_imagen[doc_id] = f"error: {e}"
        if imgs:
            imagenes_por_doc.append((label, d.get("nombre_original", ""), imgs))
            restante -= len(imgs)
            ids_imagen_lograda.add(doc_id)
            # Si el documento ya entró como texto (plano con capa de texto), no duplicar la
            # entrada — solo marcar que también se analiza como imagen.
            ya = next((di for di in docs_incluidos if di["id"] == doc_id), None)
            if ya:
                ya["label"] += " (texto + imagen)"
            else:
                docs_incluidos.append({"id": doc_id, "nombre": d.get("nombre_original"),
                                       "label": label + " (imagen)"})
        elif doc_id not in motivo_fallo_imagen:
            motivo_fallo_imagen[doc_id] = "error: el render no devolvió imágenes"

    # Documentos que estaban en cola para VISIÓN (sin texto, así que dependían por completo de
    # la imagen) pero cuyo render falló, quedaron sin cuota o quedaron fuera por el tope
    # MAX_IMG_EJE — mismo problema que docs_excluidos de más arriba: sin este aviso,
    # desaparecían del análisis sin dejar rastro pese a tener el archivo físico disponible
    # (ej. un documento recién resubido, cuyo archivo SÍ existe en disco pero no se pudo
    # renderizar como imagen). Se les da el mismo tratamiento: nota determinística + marca en
    # "archivos usados", salvo que el documento ya tenga cobertura por texto (plano con capa de
    # texto que sí se incluyó, solo falló el canal de imagen — cobertura parcial, no total).
    for d, fp in docs_imagen:
        doc_id = d.get("id")
        if doc_id in ids_imagen_lograda:
            continue
        ya_tiene_texto = any(di["id"] == doc_id for di in docs_incluidos)
        label_doc = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        nombre_doc = d.get("nombre_original", "")
        motivo = motivo_fallo_imagen.get(doc_id, "error: motivo no determinado")
        print(f"⚠️ Grupo '{nombre}': documento en cola de visión SIN renderizar — {label_doc} "
              f"({nombre_doc}), id={doc_id}, motivo={motivo}, ya_tiene_texto={ya_tiene_texto}")
        if ya_tiene_texto:
            continue
        if motivo == "tope":
            razon = ("se alcanzó el máximo de imágenes permitidas en una sola revisión "
                     "(este grupo tiene varios documentos que requieren visión y el cupo ya "
                     "se agotó con los anteriores)")
        elif motivo == "cuota":
            razon = ("el cupo de imágenes se reparte entre todos los documentos de este grupo "
                     "que necesitan visión, y a este no le alcanzó espacio suficiente")
        elif motivo.startswith("error:"):
            razon = f"hubo un error al procesar el PDF ({motivo[7:]})"
        else:
            razon = "no se pudo determinar la causa exacta"
        observaciones_excluidos.append({
            "texto": (f'El documento "{nombre_doc}" ({label_doc}) no pudo incluirse en el '
                      f"análisis visual: {razon}. Debe revisarse manualmente o resubirse si "
                      f"el problema persiste."),
            "categoria": "administrativa", "severidad": "informativa", "referencia_normativa": "",
        })
        docs_incluidos_excluidos.append({"id": doc_id, "nombre": nombre_doc,
                                         "label": label_doc + " (NO SE PUDO RENDERIZAR)"})

    if not bloque_docs and not imagenes_por_doc:
        if observaciones_excluidos:
            return {"observaciones": observaciones_excluidos,
                    "docs_incluidos": docs_incluidos_excluidos, "sin_documentos": False}
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}

    bloque_bases    = _construir_bloque_bases(bases_texto, concurso_id)
    bloque_resumen  = _construir_bloque_resumen(resumen)
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
                         f"(planos, mapas de delimitación de áreas, pruebas de bombeo o "
                         f"escaneados) — analízalos visualmente: {nombres_img}."
                         f"\nLee SOLO lo efectivamente anotado/rotulado en la imagen: diámetros, "
                         f"longitudes, SUPERFICIES/hectáreas rotuladas, números de la simbología "
                         f"y las cotas anotadas, valores de TABLAS, y la forma de CURVAS o "
                         f"gráficos (ej. descenso/recuperación de una prueba de bombeo) — nunca "
                         f"midas a escala ni estimes a ojo.")
        if ids_con_tiles:
            nota_imagenes += (f"\nOJO con los PLANOS/MAPAS: cada página viene como una vista "
                              f"completa MÁS 4 cuadrantes AMPLIADOS de esa MISMA página (para "
                              f"leer cotas, diámetros y textos chicos) — los cuadrantes NO son "
                              f"páginas ni láminas distintas, no dupliques conteos ni "
                              f"superficies.")

    bloque_enfasis = ""
    if criterios_enfasis and criterios_enfasis.strip():
        bloque_enfasis = (f"\n\n{'═'*60}\nCRITERIOS DE ÉNFASIS DEFINIDOS POR EL REVISOR PARA "
                          f"ESTE GRUPO EN ESTE CONCURSO — verifícalos SIEMPRE, tienen prioridad "
                          f"sobre el resto de la guía:\n{'═'*60}\n{criterios_enfasis.strip()}\n")

    # Coherencia Global revisa el expediente COMPLETO, así que sin este bloque tiende a
    # re-encontrar y repetir hallazgos puntuales que ya quedaron registrados al revisar cada
    # ítem por separado (ej. superficie inconsistente ya observada en Memoria de superficies).
    # Se le pasa lo YA observado en los demás ítems para que no lo repita y se concentre en lo
    # que solo se ve mirando el conjunto: la lógica global del proyecto, su viabilidad como
    # sistema, contradicciones entre documentos que ningún ítem individual detecta solo.
    bloque_obs_previas = ""
    if es_coherencia and observaciones_previas:
        lineas = [f"• [{o.get('item_nombre', '')}] {(o.get('texto', '') or '')[:400]}"
                  for o in observaciones_previas[:200]]
        bloque_obs_previas = (
            f"\n\n{'═'*60}\nOBSERVACIONES YA REGISTRADAS AL REVISAR CADA ÍTEM POR SEPARADO "
            f"(NO LAS REPITAS — ya están cubiertas y se gestionan en su propio ítem)\n{'═'*60}\n"
            + "\n".join(lineas) +
            f"\n\nTu tarea acá es EXCLUSIVAMENTE detectar lo que SOLO se ve mirando el expediente "
            f"COMPLETO: si la idea del proyecto, su forma de operar y su lógica de diseño y "
            f"construcción son coherentes y viables en conjunto. NO vuelvas a señalar algo de la "
            f"lista de arriba aunque lo veas de nuevo en los documentos, aunque lo redactes "
            f"distinto. Si no encuentras una incoherencia genuinamente NUEVA (no cubierta arriba), "
            f"no fuerces una observación — la ausencia de hallazgos nuevos es un resultado válido.")

    prompt = f"""{bloque_bases}{bloque_resumen}{bloque_feedback}{bloque_consultor}Realiza una REVISIÓN POR {modo} del expediente CNR.

GRUPO A REVISAR: {nombre}
Tipo de revisión: Revisión {revision_nombre}

{checklist}{bloque_enfasis}{bloque_obs_previas}{bloque_verificacion}

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
        for etiqueta, b64 in imgs:
            content_blocks.append({"type": "text", "text": f"[{etiqueta}]"})
            content_blocks.append({"type": "image",
                                   "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": b64}})

    def _stream_final(max_tokens):
        # Streaming (no create()) para peticiones con mucho input y max_tokens alto — el ítem
        # Presupuesto reparte hasta 120.000 caracteres y pide hasta 20.000 tokens de salida: una
        # llamada create() sin streaming choca contra el timeout HTTP del SDK y la app queda
        # "colgada" varios minutos sin respuesta. get_final_message() devuelve el Message completo
        # (mismo objeto que create()), así que .stop_reason y _texto_respuesta() siguen igual.
        with client.messages.stream(
            model=MODELO_SONNET,
            max_tokens=max_tokens,
            system=system_con_cache,
            messages=[{"role": "user", "content": content_blocks}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        ) as stream:
            return stream.get_final_message()

    async def _llamar(max_tokens):
        return await asyncio.to_thread(_stream_final, max_tokens)

    response = await _llamar(MAX_TOKENS_SONNET)
    content = _texto_respuesta(response)

    # El "thinking" de Sonnet 5 a veces se come todo el cupo antes de escribir el JSON,
    # sobre todo en grupos con imágenes (más que razonar). Si la respuesta llega vacía y
    # cortada por límite de tokens, reintenta una vez con más cupo antes de rendirse.
    if not content.strip() and response.stop_reason == "max_tokens":
        print(f"⚠️ Grupo '{nombre}': respuesta vacía por max_tokens ({MAX_TOKENS_SONNET}) — "
              f"reintentando con más cupo…")
        response = await _llamar(MAX_TOKENS_SONNET + 8000)
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

    if not observaciones and not observaciones_excluidos:
        print(f"⚠️ Grupo '{nombre}': 0 observaciones — stop_reason={response.stop_reason}, "
              f"content_len={len(content)}, preview={content[:200]!r}")

    # Se agregan al final las notas deterministas de documentos que no se pudieron leer (ver
    # más arriba) — así el revisor las ve igual que cualquier otra observación del ítem.
    return {"observaciones": observaciones + observaciones_excluidos,
            "docs_incluidos": docs_incluidos + docs_incluidos_excluidos,
            "sin_documentos": False}


# ─── Invalidación cruzada: auto-descartar observaciones que otro ítem resuelve ────────────────
# Equivalente al que existía en el método viejo de análisis documento-por-documento (eliminado
# jul-2026 junto con ese método), portado a la unidad de trabajo actual (ítem, no documento).

async def revisar_invalidacion_cruzada(item_nombre_nuevo: str, texto_resumen_nuevo: str,
                                       observaciones_pendientes_otras: list) -> list:
    """Tras revisar un ítem, determina si su contenido resuelve observaciones PENDIENTES de
    OTROS ítems ya revisados (ej.: "Especificaciones técnicas" aclara un dato que "Diseño
    hidráulico" había marcado como ambiguo). Retorna la lista de IDs a auto-descartar.

    Llamada barata con Haiku (lectura + comparación, no razonamiento técnico — regla de costo
    de siempre) y con un resumen corto del ítem (no el presupuesto completo de caracteres del
    análisis principal) — se ejecuta en paralelo a `_analizar_grupo`, no agrega latencia.

    Deliberadamente CONSERVADORA: ante la duda, no invalida (mismo criterio de la app para
    generar observaciones). Un falso positivo acá esconde un hallazgo real sin que el revisor
    lo note; un falso negativo solo deja una observación ya resuelta visible de más, que el
    revisor descarta a mano igual que siempre — el costo de equivocarse no es simétrico."""
    if not observaciones_pendientes_otras or not texto_resumen_nuevo.strip():
        return []

    client = _get_client()
    lista_obs = "\n".join(
        f'- ID: {o.get("id","")} | Ítem: {o.get("item_nombre","")} | '
        f'Observación: {(o.get("texto","") or "")[:250]}'
        for o in observaciones_pendientes_otras[:150]
    )

    prompt = f"""Se acaba de revisar el ítem "{item_nombre_nuevo}" de un expediente CNR (Ley 18.450).

CONTENIDO REVISADO EN ESTE ÍTEM:
{texto_resumen_nuevo}

OBSERVACIONES PENDIENTES DE OTROS ÍTEMS (generadas antes, sobre otros documentos del mismo
expediente):
{lista_obs}

TAREA: Determina cuáles de esas observaciones pendientes quedan RESUELTAS por el contenido de
arriba — la información que faltaba o la ambigüedad que señalaban queda aclarada o corregida
por lo que dice este ítem.

SÉ CONSERVADOR: ante la duda, NO la marques como resuelta. Solo marca una observación si el
contenido de arriba la resuelve de forma DIRECTA y explícita, no por relación tangencial o
parecido superficial.

Responde SOLO en JSON, sin texto adicional:
{{"resueltas": ["id_obs_1", "id_obs_2"], "justificaciones": {{"id_obs_1": "razón breve"}}}}

Si ninguna se resuelve, responde: {{"resueltas": [], "justificaciones": {{}}}}"""

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODELO_HAIKU, max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extraer_json_simple(_texto_respuesta(response))
        ids = data.get("resueltas", [])
        return ids if isinstance(ids, list) else []
    except Exception as e:
        print(f"⚠️ revisar_invalidacion_cruzada falló, se omite: {e}")
        return []


async def analizar_item(item_key: str, documentos: list, bases_texto: str = "",
                        concurso_id: str = "", feedback_concurso: list = None,
                        criterios_aprendidos: str = "", criterios_enfasis: str = "",
                        consultor: dict = None, resumen: dict = None,
                        datos_verificacion_hidraulica: dict = None,
                        datos_verificacion_agronomica: dict = None,
                        n_sistemas: int = 1,
                        datos_verificacion_fv: dict = None,
                        tabla_precios: list = None,
                        observaciones_previas: list = None,
                        observaciones_pendientes_otros: list = None,
                        tipo_revision: str = "tecnica", ruta_uploads: str = None) -> dict:
    """Analiza un ÍTEM DEL SEP (revisa el/los documento(s) de ese ítem). Envoltorio de _analizar_grupo.

    `resumen`: lo que el revisor ya completó en la página Resumen del proyecto
    (`proyecto["resumen"]`) — se inyecta como contexto YA VALIDADO en TODO ítem (ver
    `_construir_bloque_resumen`), para que la IA no genere una observación asumiendo que falta
    un dato que el revisor ya declaró (ej. derechos de agua no inscritos, servidumbres, etc.).

    `datos_verificacion_*`: si se entregan (datos que el revisor ya revisó/corrigió a mano en la
    página "Chequeo de Cálculos"), se usan directamente en vez de volver a extraerlos con
    Haiku — evita depender de una extracción automática que puede fallar en algunos casos.

    `tabla_precios`: tabla de precios referenciales PROMEDIO subida por el revisor en
    /admin/precios ([{categoria, item, unidad, precio}, ...]) — no es data oficial de la CNR,
    es una referencia aproximada. Si es None/vacía (nunca se ha subido nada), la verificación
    de precios del ítem Presupuesto simplemente no corre.

    `observaciones_previas`: solo se usa para `item_key == "coherencia"` — las observaciones ya
    generadas en los OTROS ítems del mismo proyecto ([{item_nombre, texto}, ...]), para que el
    cierre transversal no repita hallazgos puntuales ya cubiertos y se concentre en lo que solo
    se ve mirando el expediente completo (ver `_analizar_grupo`).

    `observaciones_pendientes_otros`: observaciones PENDIENTES de OTROS ítems ya revisados
    ([{id, item_nombre, texto}, ...]) — si el contenido de ESTE ítem las resuelve, se devuelven
    sus IDs en el resultado (`invalidadas`) para que el llamador las auto-descarte (ver
    `revisar_invalidacion_cruzada`). Corre en paralelo al análisis principal, sin agregar
    latencia."""
    item = ITEMS_SEP.get(item_key)
    if not item:
        return {"observaciones": [], "docs_incluidos": [], "sin_documentos": True}
    if item_key == "coherencia":
        # Usa TODOS los documentos con texto, sin filtrar por tipo, y sin visión (cierre
        # transversal, no analiza planos/escaneados por costo).
        docs_grupo = [d for d in documentos
                      if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]
    else:
        tipos = set(item["tipo_docs"])
        docs_grupo = [d for d in documentos if d.get("tipo_doc") in tipos]

    # Verificación numérica determinística (Hazen-Williams / cadena agronómica / dimensionamiento
    # FV): solo en los ítems donde hay fórmula normativa aplicable. Si la extracción no
    # encuentra datos, el bloque queda vacío y no afecta el resto del análisis.
    bloque_verificacion = ""
    try:
        if item_key == "diseno_hidraulico":
            # n_sistemas es GLOBAL al proyecto (mismo selector para Agronómico e Hidráulico —
            # un proyecto con 2 sistemas de riego tiene 2 diseños hidráulicos Y 2 cadenas
            # agronómicas, no puede ser 2 en uno y 1 en el otro).
            docs_hid = _documentos_para_verificacion("hidraulico", documentos)
            datos_hid = datos_verificacion_hidraulica if datos_verificacion_hidraulica is not None \
                else await _extraer_datos_hidraulicos(docs_hid, n_sistemas=n_sistemas)
            bloque_verificacion += _bloque_verificacion_hidraulica(datos_hid)

            docs_agro = _documentos_para_verificacion("agronomico", documentos)
            datos_agro = datos_verificacion_agronomica if datos_verificacion_agronomica is not None \
                else await _extraer_datos_agronomicos(docs_agro, n_sistemas=n_sistemas)
            bloque_verificacion += _bloque_verificacion_agronomica(datos_agro)
        elif item_key == "diseno_fotovoltaico":
            docs_fv = _documentos_para_verificacion("energetico", documentos)
            datos_fv = datos_verificacion_fv if datos_verificacion_fv is not None \
                else await _extraer_datos_fv(docs_fv)
            bloque_verificacion = _bloque_verificacion_fv(datos_fv)
        elif item_key in ("presupuesto", "presupuesto_electrico") and tabla_precios:
            partidas_data = await _extraer_partidas_presupuesto(docs_grupo)
            bloque_verificacion = _bloque_verificacion_precios(
                partidas_data.get("partidas", []), tabla_precios)
    except Exception as e:
        print(f"⚠️ Verificación numérica '{item_key}' falló, se omite: {e}")

    analisis_task = _analizar_grupo(
        item["nombre"], item["checklist"], docs_grupo, documentos,
        modo="ÍTEM DEL SEP", es_coherencia=(item_key == "coherencia"),
        observaciones_previas=observaciones_previas if item_key == "coherencia" else None,
        bases_texto=bases_texto, concurso_id=concurso_id,
        feedback_concurso=feedback_concurso, feedback_key="item_" + item_key,
        criterios_aprendidos=criterios_aprendidos, criterios_enfasis=criterios_enfasis,
        bloque_verificacion=bloque_verificacion,
        consultor=consultor, resumen=resumen,
        max_chars_total=MAX_CHARS_POR_ITEM.get(item_key, MAX_CHARS_EJE_TOTAL),
        tipo_revision=tipo_revision, ruta_uploads=ruta_uploads)

    # Invalidación cruzada: corre en PARALELO al análisis principal (asyncio.gather) — no agrega
    # latencia — y solo si hay observaciones pendientes de otros ítems para revisar.
    if observaciones_pendientes_otros:
        texto_resumen = _texto_grupo_para_extraccion(docs_grupo, max_chars=8000)
        resultado, invalidadas = await asyncio.gather(
            analisis_task,
            revisar_invalidacion_cruzada(item["nombre"], texto_resumen, observaciones_pendientes_otros)
        )
    else:
        resultado = await analisis_task
        invalidadas = []

    resultado["invalidadas"] = invalidadas
    return resultado


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

    response = await asyncio.to_thread(
        client.messages.create,
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
    budget = max(2000, 80000 // max(1, len(docs_texto)))
    bloque = ""
    for d in docs_texto:
        label = d.get("tipo_doc_label") or TIPOS_DOC.get(d.get("tipo_doc"), d.get("tipo_doc", ""))
        bloque += f"\n\n--- {label} ---\n{_truncar_inteligente(d.get('texto_extraido', ''), budget)}"

    campos_lista = "\n".join(
        f'- {c["key"]}: {c["label"]}'
        + (" (responde \"Sí\" o \"No\")" if c["tipo"] == "sino" else "")
        + (f' (máx {c["maxlen"]} caracteres — {c["resumen_ia"]})' if c.get("maxlen") else "")
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

    # Extracción de datos a JSON — Haiku es suficiente (tarea de lectura/estructuración, no de
    # razonamiento técnico). Antes usaba Sonnet 5 pese a que CLAUDE.md ya lo listaba como tarea
    # de Haiku — se corrige acá para bajar costo sin perder calidad.
    response = await asyncio.to_thread(
        client.messages.create,
        model=MODELO_HAIKU,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
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


def _repartir_presupuesto(tamanos: list, total_chars: int, minimo: int = 3000) -> list:
    """Reparte `total_chars` entre documentos según su tamaño REAL (algoritmo "water-filling"),
    en vez de una cuota fija por documento (`total // n`). Antes, un manual de equipo de 2
    páginas (poco texto) recibía la MISMA cuota que un documento denso de 20 páginas — el
    margen que el manual no necesitaba se perdía, en vez de pasarle ese espacio al documento que
    sí lo necesitaba (caso real: 8 documentos donde 5 eran manuales/folletos cortos y 3 eran
    memorias técnicas densas).

    Ordena ascendente por tamaño; a cada documento que cabe completo dentro de la cuota
    equitativa del momento se le da su tamaño exacto (nada de margen desperdiciado) y se saca
    del reparto; el resto del presupuesto se recalcula entre los documentos que quedan. Cuando
    un documento excede la cuota, él y todos los que siguen (son ≥ en tamaño, por el orden
    ascendente) se reparten en partes iguales lo que queda. `minimo`: piso por documento para
    que ninguno quede en 0 si hay muchísimos documentos.

    Devuelve una lista de presupuestos (mismo orden y largo que `tamanos`)."""
    n = len(tamanos)
    if n == 0:
        return []
    orden = sorted(range(n), key=lambda i: tamanos[i])
    presupuestos = [0] * n
    restante = total_chars
    pendientes = n
    for pos, idx in enumerate(orden):
        cuota = max(minimo, restante // pendientes)
        if tamanos[idx] <= cuota:
            presupuestos[idx] = tamanos[idx]
            restante -= tamanos[idx]
            pendientes -= 1
        else:
            cuota_final = max(minimo, restante // pendientes)
            for idx2 in orden[pos:]:
                presupuestos[idx2] = cuota_final
            break
    return presupuestos


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
        bloque += (f"\n[... texto de bases truncado por longitud — se muestran los primeros "
                   f"{MAX_CHARS_BASES:,} caracteres]\n".replace(",", "."))
    bloque += "\n"
    return bloque


MAX_CHARS_CAMPO_RESUMEN = 500   # tope por campo del Resumen (textareas pueden ser largos)

def _construir_bloque_resumen(resumen: dict) -> str:
    """Construye el bloque de contexto con lo que el REVISOR ya completó/confirmó en la página
    Resumen del proyecto (RESUMEN_SECCIONES) — ej. si declara derechos de agua no inscritos,
    servidumbres, INDAP, etc. Se inyecta en TODO análisis de ítem para que la IA cruce contra
    esos datos en vez de asumir un incumplimiento solo porque el ítem que está revisando no
    incluye ese dato por su cuenta (evita falsos positivos por falta de contexto entre ítems)."""
    if not resumen:
        return ""
    lineas = []
    for sec in RESUMEN_SECCIONES:
        for campo in sec["campos"]:
            valor = resumen.get(campo["key"])
            if not valor or not str(valor).strip():
                continue
            v = str(valor).strip()
            if len(v) > MAX_CHARS_CAMPO_RESUMEN:
                v = v[:MAX_CHARS_CAMPO_RESUMEN] + "…"
            lineas.append(f"• {campo['label']}: {v}")
    if not lineas:
        return ""
    return (f"\n{'═'*60}\nDATOS YA DECLARADOS POR EL REVISOR EN EL RESUMEN DEL PROYECTO\n"
            f"{'═'*60}\nEstos datos ya fueron completados/confirmados por el revisor humano —"
            f" trátalos como contexto YA VALIDADO. NO generes una observación asumiendo que "
            f"falta un dato que ya está declarado aquí (ej. si aquí consta que el derecho de "
            f"agua NO está inscrito, no observes la ausencia de su inscripción). Si un "
            f"documento del expediente CONTRADICE explícitamente algo de esta lista, sí "
            f"obsérvalo — esto es contexto de apoyo, no reemplaza verificar los documentos.\n"
            + "\n".join(lineas) + "\n")


# ── Documentos obligatorios de admisibilidad (según las bases del concurso) ─────
# Las bases de cada concurso señalan qué documentos son obligatorios — su no presentación deja
# el proyecto como NO ADMITIDO — pero no siempre están en el mismo lugar del texto, hay que
# buscarlos. Esta extracción corre UNA VEZ POR CONCURSO (no por proyecto, las bases son las
# mismas para todos), y el resultado SIEMPRE requiere revisión y guardado explícito del revisor
# humano antes de usarse — nunca dispara advertencias en un proyecto por sí sola. Ver
# `main.py`: rutas `/admin/concursos/{id}/documentos-obligatorios/{extraer,guardar}` y el campo
# `concurso["documentos_obligatorios_revisado"]`.

async def extraer_documentos_obligatorios(bases_texto: str, catalogo_tipo_doc: dict) -> dict:
    """Lee las bases del concurso y determina qué tipos de documento son OBLIGATORIOS para la
    admisibilidad — bases que indican EXPLÍCITAMENTE que su no presentación deja el proyecto
    NO ADMITIDO (o expresiones equivalentes: "causal de inadmisibilidad", "se declarará
    inadmisible", "quedará fuera de bases", etc.). NO inventa: si las bases solo listan
    documentos a presentar sin mencionar esa consecuencia, no los marca — mejor una lista corta
    y certera que una larga y especulativa. También identifica el punto/numeral exacto de las
    bases donde encontró esa lista, para que el revisor pueda verificarlo directamente ahí.
    Devuelve {"obligatorios": [...], "referencia": "..."} — la lista se filtra siempre contra
    catalogo_tipo_doc, sin confiar ciegamente en lo que devuelva la IA."""
    if not bases_texto or not bases_texto.strip():
        return {"obligatorios": [], "referencia": ""}
    texto = _truncar_inteligente(bases_texto.strip(), MAX_CHARS_BASES)
    catalogo_txt = "\n".join(f"- {k}: {v}" for k, v in catalogo_tipo_doc.items())
    prompt = f"""Lee las bases del concurso CNR (Ley 18.450) y determina cuáles de los
siguientes tipos de documento son OBLIGATORIOS para la admisibilidad — es decir, las bases
indican EXPLÍCITAMENTE que si el documento no se presenta, el proyecto queda NO ADMITIDO (o
expresiones equivalentes de esa misma consecuencia).

NO inventes ni asumas — solo marca un documento como obligatorio si las bases lo dicen de forma
explícita con esa consecuencia. Si las bases no distinguen niveles de exigencia y simplemente
listan documentos a presentar sin mencionar inadmisibilidad, NO los marques.

Además, identifica el punto/numeral/artículo EXACTO de las bases donde está esa lista (ej:
"6.3" o "Numeral 6.3 — Antecedentes obligatorios"), para que el revisor pueda verificarlo
directamente ahí. Si no logras identificar un punto específico, deja "referencia" vacío — no
inventes un número.

CATÁLOGO DE TIPOS DE DOCUMENTO (usa exactamente estas claves, no inventes otras):
{catalogo_txt}

Responde SOLO este JSON, sin texto adicional:
{{"obligatorios": ["clave1", "clave2", ...], "referencia": "punto exacto de las bases o vacío"}}

BASES DEL CONCURSO:
{texto}"""
    try:
        client = _get_client()
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODELO_HAIKU, max_tokens=MAX_TOKENS_EXTRACCION,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extraer_json_tolerante(_texto_respuesta(response))
        obligatorios = data.get("obligatorios", [])
        if not isinstance(obligatorios, list):
            obligatorios = []
        referencia = data.get("referencia") or ""
        return {
            "obligatorios": [k for k in obligatorios if k in catalogo_tipo_doc],
            "referencia": referencia.strip() if isinstance(referencia, str) else "",
        }
    except Exception as e:
        print(f"⚠️ extraer_documentos_obligatorios: {e}")
        return {"obligatorios": [], "referencia": ""}


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

    response = await asyncio.to_thread(
        client.messages.create,
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

    response = await asyncio.to_thread(
        client.messages.create,
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

    # Construir contexto con texto de todos los documentos analizados. Reparto equitativo del
    # presupuesto entre los documentos con texto + truncado inteligente (inicio + final), en
    # vez de tomar solo el inicio de cada uno (perdía las conclusiones/resultados finales).
    docs_texto = [d for d in documentos
                  if d.get("texto_extraido", "").strip() not in ("", "__PDF_ESCANEADO__")]
    budget = max(3000, 90000 // max(1, len(docs_texto)))
    contexto_docs = ""
    for doc in docs_texto:
        label = doc.get("tipo_doc_label") or doc.get("tipo_doc", "Documento")
        texto = _truncar_inteligente(doc.get("texto_extraido", "").strip(), budget)
        contexto_docs += f"\n\n--- {label} ({doc.get('nombre_original','')}) ---\n{texto}"

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

    response = await asyncio.to_thread(
        client.messages.create,
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
        texto = ("La IA no devolvió respuesta (posible corte). Intenta reformular la "
                 "consulta de forma más breve o vuelve a intentar.")
    return texto


# ── Evaluación IA de la respuesta del consultor a una observación (subsanación) ──────────────
# Parte del PROCESO de revisión, que solo termina al aprobar/rechazar el proyecto: la IA ayuda al
# revisor a juzgar si la respuesta del consultor RESUELVE la observación, cruzándola con TODOS los
# antecedentes actuales del proyecto (que ya incluyen cualquier documento nuevo o corregido que el
# consultor haya presentado y el revisor haya vuelto a subir). Es un APOYO: la decisión final
# (marcar resuelta / reiterar) la toma siempre el revisor.

async def evaluar_respuesta_subsanacion(observacion_texto: str, referencia: str,
                                        respuesta_consultor: str, item_key: str,
                                        documentos: list, resumen: dict = None,
                                        bases_texto: str = "", concurso_id: str = "",
                                        doc_ids_extra: list = None) -> dict:
    """Devuelve {"recomendacion": "resuelta"|"no_resuelta"|"", "fundamento": "..."}.

    `doc_ids_extra`: IDs de documentos que el consultor adjuntó junto a ESTA respuesta (ej. una
    nueva prueba de bombeo). Se incluyen SIEMPRE en el contexto, aunque su tipo_doc no pertenezca
    al ítem observado — si no, un respaldo clasificado bajo otro tipo quedaría invisible para la
    evaluación."""
    if not (respuesta_consultor or "").strip():
        return {"recomendacion": "", "fundamento": "No hay respuesta del consultor para evaluar."}

    client = _get_client()

    # Antecedentes del ítem observado (para 'coherencia' o ítem desconocido, todos los que tengan
    # texto). Mismo criterio de selección que el análisis; reparto adaptativo, solo texto.
    item = ITEMS_SEP.get(item_key)
    if item and item_key != "coherencia" and item.get("tipo_docs"):
        tipos = set(item["tipo_docs"])
        docs_grupo = [d for d in documentos if d.get("tipo_doc") in tipos]
    else:
        docs_grupo = list(documentos)
    # Sumar los adjuntos de esta respuesta que no hayan quedado ya incluidos por su tipo_doc.
    ids_extra = set(doc_ids_extra or [])
    if ids_extra:
        ya = {d.get("id") for d in docs_grupo}
        docs_grupo = docs_grupo + [d for d in documentos
                                   if d.get("id") in ids_extra and d.get("id") not in ya]
    contexto_docs = _texto_grupo_para_extraccion(docs_grupo, max_chars=80000)
    if not contexto_docs.strip():
        contexto_docs = "(No hay antecedentes con texto extraíble para este ítem.)"

    bloque_resumen = _construir_bloque_resumen(resumen)
    system_con_cache = [{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    bloque_bases = _construir_bloque_bases(bases_texto, concurso_id)
    if bloque_bases.strip():
        system_con_cache.append({"type": "text", "text": bloque_bases,
                                 "cache_control": {"type": "ephemeral", "ttl": "1h"}})

    nombre_item = item["nombre"] if item else item_key
    prompt = f"""{bloque_resumen}
Estás revisando la RESPUESTA del consultor a una observación de un proyecto CNR (Ley 18.450).
Determina si la respuesta, CONSIDERANDO LOS ANTECEDENTES ACTUALES del expediente (que ya
incluyen cualquier documento nuevo o corregido que el consultor haya presentado), RESUELVE la
observación.

OBSERVACIÓN ORIGINAL (ítem: {nombre_item}):
{observacion_texto}
{f'Referencia citada: {referencia}' if referencia else ''}

RESPUESTA DEL CONSULTOR (transcrita por el revisor):
{respuesta_consultor.strip()}

ANTECEDENTES ACTUALES DEL ÍTEM:
{contexto_docs}

CRITERIOS:
- "resuelta": la respuesta aporta lo que faltaba, corrige lo observado o aclara satisfactoriamente
  el punto, de forma verificable en los antecedentes.
- "no_resuelta": no resuelve, resuelve solo parcialmente, o no aporta evidencia suficiente. Si
  resuelve a medias, es "no_resuelta" y explica qué falta.
Aplica el criterio de ingeniero (ante la duda razonable, no exijas de más), pero exige respaldo
REAL: no des por resuelto un punto solo porque el consultor afirme haberlo hecho, si eso no se
refleja en los antecedentes.

Responde SOLO este JSON, sin texto adicional:
{{"recomendacion": "resuelta"|"no_resuelta", "fundamento": "2-4 líneas explicando por qué, citando la norma/base si aplica"}}"""

    def _stream_final(max_tokens):
        with client.messages.stream(
            model=MODELO_SONNET, max_tokens=max_tokens, system=system_con_cache,
            messages=[{"role": "user", "content": prompt}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        ) as stream:
            return stream.get_final_message()

    try:
        response = await asyncio.to_thread(_stream_final, 2500)
    except Exception as e:
        print(f"⚠️ evaluar_respuesta_subsanacion: {e}")
        return {"recomendacion": "", "fundamento": f"No se pudo evaluar con IA: {e}"}

    content = _texto_respuesta(response)
    data = _extraer_json_tolerante(content)
    rec = data.get("recomendacion", "")
    if rec not in ("resuelta", "no_resuelta"):
        rec = ""
    fund = (data.get("fundamento", "") or "").strip()
    if not rec and not fund:
        print(f"⚠️ evaluar_respuesta_subsanacion: respuesta vacía — stop_reason={response.stop_reason}")
        fund = "La IA no devolvió una evaluación clara. Revísalo manualmente."
    return {"recomendacion": rec, "fundamento": fund}
