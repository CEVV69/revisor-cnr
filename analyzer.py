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
Eres un revisor con criterio técnico profesional, NO un auditor burocrático.
Tu trabajo es identificar lo que REALMENTE importa para la admisión y buen
funcionamiento del proyecto, no buscar defectos menores o de forma.

GENERA observación solo cuando:
• El problema impide técnicamente el funcionamiento del sistema de riego
• Hay incumplimiento explícito de normativa CNR o de las bases del concurso
• El presupuesto tiene inconsistencias que afectan la viabilidad económica
• Faltan antecedentes legales sin los cuales el proyecto no puede aprobarse
• Los datos técnicos (caudales, superficies, eficiencias) están fuera de rango normativo
• La información es contradictoria entre secciones del mismo documento

NO GENERES observación cuando:
• Es un asunto de formato, presentación o estética sin impacto técnico
• La información puede deducirse razonablemente del contexto del mismo documento
• Es una diferencia menor de nomenclatura cuando el contenido es correcto
• El aspecto está cubierto en otros documentos del expediente (ver lista de documentos)
• Se trata de una buena práctica recomendable pero sin base normativa obligatoria
• Falta un detalle que no afecta ni la admisibilidad ni la ejecución del proyecto
• La observación sería de tipo "informativa" sobre algo que el revisor no va a exigir corregir

PRIORIDAD: Una observación "mayor" real vale más que diez "informativas" irrelevantes.
Genera pocas observaciones de alta certeza, no muchas de baja certeza.

REGLA DE ORO: Genera observaciones sobre todo lo que un revisor técnico experimentado
esperaría que el postulante corrigiera o aclarara. No omitas incumplimientos normativos
ni de bases por considerarlos "menores" — si algo no cumple, márcalo. Tampoco inventes
observaciones de formato sin impacto técnico real. El objetivo es detectar todos los
problemas reales, sin agregar ruido burocrático.

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
REVISIÓN TÉCNICA (solo lo esencial):
- Estudio hidrológico: caudales al 85% de seguridad, fuente (DT-01/DT-02), metodología
- Demanda hídrica: ETP correcta, Kc en rango (DT-05), eficiencia ponderada (DT-04)
- Diseño hidráulico: cumplimiento especificaciones técnicas (DT-06)
- Estudio de suelos: capacidad de uso (DT-03), categoría riego
- Presupuesto: coherencia con obras, APU (DT-18) — enfócate en ítems mayores
- Planos: información mínima para ejecutar la obra

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
