"""Análisis de documentos con Claude API según normativa CNR Ley 18.450"""
import os
import json
from pathlib import Path
import anthropic

def _get_client():
    # El SDK lee ANTHROPIC_API_KEY del entorno automáticamente.
    # En local también carga el .env vía load_dotenv en main.py.
    return anthropic.Anthropic()

BASE_DIR = Path(__file__).parent
NORMATIVA_DIR = BASE_DIR / "normativa"

# ─── Modelo y configuración de costos ─────────────────────────────────────────
# Modelos disponibles en esta cuenta (confirmado)
MODELO_SONNET = "claude-sonnet-4-5"   # Análisis complejos (~5× más barato que Opus)
MODELO_HAIKU  = "claude-haiku-4-5"    # Documentos simples (~18× más barato que Opus)

# Tipos de documento que requieren mayor capacidad analítica
DOCS_COMPLEJOS = {
    "diseno_hidraulico",       # Cálculos hidráulicos
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
    if es_escaneado or tipo_doc in DOCS_COMPLEJOS:
        return MODELO_SONNET
    return MODELO_HAIKU
MAX_TOKENS_HAIKU  = 1500   # Documentos simples
MAX_TOKENS_SONNET = 2500   # Documentos complejos — margen amplio para observaciones detalladas
MAX_CHARS_DOCUMENTO = 3000    # Primeros 3.000 chars del documento (reduce costo ~50%)
MAX_PAGINAS_ESCANEADO = 3     # Páginas a procesar en PDFs escaneados

# ─── Carga de normativa real desde archivos ────────────────────────────────────

def cargar_normativa() -> str:
    """Carga todos los documentos normativos disponibles en /normativa"""
    textos = []
    if not NORMATIVA_DIR.exists():
        return ""
    for archivo in sorted(NORMATIVA_DIR.glob("*.txt")):
        contenido = archivo.read_text(encoding="utf-8")
        textos.append(f"\n{'='*60}\n{archivo.stem}\n{'='*60}\n{contenido}")
    return "\n".join(textos)

NORMATIVA_CNR = cargar_normativa()

# ─── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""Eres un revisor experto de la Comisión Nacional de Riego (CNR) de Chile,
especializado en la evaluación de proyectos de riego y drenaje bajo la Ley N° 18.450.

Tienes acceso a la normativa técnica y legal oficial de la CNR:

{NORMATIVA_CNR}

Tu función es revisar documentos técnicos y administrativos presentados por postulantes
e identificar observaciones concretas que deben ser subsanadas, basándote SIEMPRE en la
normativa anterior.

REGLA CRÍTICA — NOTACIÓN NUMÉRICA CHILENA:
Los documentos siguen la norma chilena donde:
- La COMA (,) es separador decimal → "34,56" significa treinta y cuatro con cincuenta y seis centésimas
- El PUNTO (.) es separador de miles → "1.234.567" significa un millón doscientos treinta y cuatro mil quinientos sesenta y siete
Ejemplos: "0,4 l/s" = 0.4 litros/segundo; "34.560 m³" = treinta y cuatro mil quinientos sesenta metros cúbicos; "34,560 m³" = treinta y cuatro con cincuenta y seis metros cúbicos.
Antes de marcar cualquier error de cálculo o unidades, interpreta los números con esta convención.
Si el formato es ambiguo o inconsistente dentro del mismo documento, aplica criterio de contexto
(orden de magnitud esperable para la magnitud física en cuestión) antes de generar observación.
NUNCA marques como error un número correctamente escrito en notación chilena.

Al revisar debes verificar según el tipo de documento:

REVISIÓN TÉCNICA:
- Estudio hidrológico: caudales al 85% de seguridad, fuente (DT-01/DT-02), metodología
- Demanda hídrica: ETP correcta, Kc dentro del rango permitido (DT-05), eficiencia ponderada (DT-04)
- Diseño hidráulico: cumplimiento especificaciones técnicas (DT-06)
- Estudio de suelos: capacidad de uso (DT-03), categoría riego, aptitud frutal si corresponde
- Presupuesto: coherencia con obras, análisis de precios unitarios (DT-18)
- Planos: escala, viñeta, curvas de nivel, obras señaladas

REVISIÓN LEGAL:
- Documentos de postulación: lista completa según IL-01
- Estrato del postulante: correctamente declarado y respaldado (IL-10)
- F22: verificación códigos SII (18, 36, 158, 305, 611)
- Derechos de agua: vigencia, caudal suficiente, inscripción DGA
- Títulos de dominio: vigentes y concordantes con el proyecto
- OUA: acta asamblea, poder representante, listado beneficiarios (FL-07)
- Consultor: habilitado en Registro MOP

Responde SIEMPRE en formato JSON exacto:
{{
  "observaciones": [
    {{
      "numero": 1,
      "categoria": "técnica|legal|presupuesto|administrativa",
      "severidad": "mayor|menor|informativa",
      "texto": "Descripción clara de qué falta o qué está incorrecto",
      "referencia_normativa": "IL-01, DT-04, Art. X Ley 18.450, etc."
    }}
  ],
  "resumen": "Evaluación general del documento en 2-3 oraciones"
}}

Severidades:
- mayor: impide la admisión del proyecto, debe subsanarse obligatoriamente
- menor: debe corregirse pero no impide la admisión
- informativa: recomendación o advertencia sin impacto en admisión

Si el documento está correcto, devuelve lista vacía en observaciones."""


TIPOS_DOC = {
    "memoria_explicativa": "Memoria explicativa del proyecto",
    "estudio_hidrologico": "Estudio hidrológico",
    "diseno_hidraulico": "Diseño hidráulico de obras",
    "estudio_suelos": "Estudio de suelos y capacidad de uso",
    "presupuesto": "Presupuesto y análisis de precios unitarios",
    "planos": "Planos y especificaciones técnicas",
    "evaluacion_social": "Evaluación socioeconómica",
    "antecedentes_legales": "Antecedentes legales (derechos de agua, títulos)",
    "lista_beneficiarios": "Lista de beneficiarios",
    "otro": "Documento complementario"
}


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


async def analyze_document(texto: str, tipo_doc: str, tipo_revision: str, nombre_doc: str,
                           filepath: str = None, doc_id: str = "",
                           todos_documentos: list = None) -> list:
    tipo_nombre = TIPOS_DOC.get(tipo_doc, tipo_doc)
    revision_nombre = "técnica" if tipo_revision == "tecnica" else "legal"
    client = _get_client()

    es_escaneado = texto.strip() == "__PDF_ESCANEADO__"
    modelo = seleccionar_modelo(tipo_doc, es_escaneado)
    max_tokens = MAX_TOKENS_SONNET if modelo == MODELO_SONNET else MAX_TOKENS_HAIKU

    contexto_expediente = _construir_contexto_expediente(todos_documentos or [], doc_id)

    system_con_cache = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }
    ]

    # ── PDF escaneado: usar visión de Claude ──────────────────────────────────
    if es_escaneado and filepath and filepath.endswith(".pdf"):
        from extractor import render_pdf_as_images
        imagenes = render_pdf_as_images(filepath, max_pages=MAX_PAGINAS_ESCANEADO)

        if not imagenes:
            return [{
                "numero": 1, "categoria": "administrativa", "severidad": "informativa",
                "texto": "No fue posible leer el contenido del PDF. El archivo puede estar dañado o protegido.",
                "referencia_normativa": ""
            }]

        prompt_texto = f"""Revisa el siguiente documento escaneado presentado en el concurso CNR.

Tipo de documento: {tipo_nombre}
Nombre del archivo: {nombre_doc}
Tipo de revisión: Revisión {revision_nombre}
{contexto_expediente}
Lee el contenido completo de las imágenes y genera las observaciones que correspondan.
Identifica todos los aspectos que el postulante debe subsanar según la normativa CNR."""

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
        prompt = f"""Revisa el siguiente documento presentado en el concurso CNR.

Tipo de documento: {tipo_nombre}
Nombre del archivo: {nombre_doc}
Tipo de revisión asignada: Revisión {revision_nombre}
{contexto_expediente}
CONTENIDO DEL DOCUMENTO:
{texto[:MAX_CHARS_DOCUMENTO]}

Identifica todas las observaciones que el postulante debe subsanar basándote
en la normativa CNR que tienes disponible. Sé específico y cita la norma aplicable."""

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
