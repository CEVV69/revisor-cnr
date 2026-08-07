"""
Revisor CNR - Aplicación de revisión de proyectos de riego Ley 18.450
"""
import os
import re
import json
import uuid
import asyncio
import unicodedata
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from dotenv import load_dotenv

from auth import create_token, verify_token, verify_password
from extractor import extract_text, extract_zip, parse_tabla_precios, truncar_texto_guardado
from analyzer import (consultar_expediente, analizar_item, chatear_item, resumir_proyecto,
                      extraer_metodologia_consultor, extraer_metodologia_fv,
                      CONCEPTOS_METODOLOGIA, CONCEPTOS_METODOLOGIA_FV,
                      consolidar_aprendizaje, consolidar_perfil_consultor, ITEMS_SEP,
                      ITEMS_ORDEN, RESUMEN_SECCIONES, RESUMEN_KEYS, _documentos_para_verificacion,
                      MIN_CHARS_TEXTO, _extraer_datos_hidraulicos, _extraer_datos_agronomicos,
                      _extraer_datos_fv, extraer_documentos_obligatorios, _buscar_rango_kc,
                      _rango_eficiencia_oficial,
                      TIPOS_SIEMPRE_VISION, evaluar_respuesta_subsanacion, iniciar_costo)
import calculos_riego
import geo
import exportar_disenador

# Dashboard público de la CNR con precios referenciales de materiales y equipos — el revisor
# lo consulta manualmente desde un botón en los ítems de Presupuesto (ver proyecto.html). La
# app NO puede leer este link en vivo (Power BI no expone datos ni API pública) — para la
# verificación automática, el revisor sube su propia tabla de precios PROMEDIO (no una copia
# oficial de este dashboard) en Excel desde /admin/precios.
URL_PRECIOS_CNR = ("https://app.powerbi.com/view?r=eyJrIjoiZDJhMjgwM2QtNGUyYy00YzEyLWEyZjctND"
                   "hjN2E0NjFlOTBiIiwidCI6IjBmOWNhOGViLWI4MjctNGEyMS1iNmNkLTAxNmRlODNkYmRlNyIs"
                   "ImMiOjR9")

# Visor CIREN/Minagri (IDE Minagri) para consultar roles y uso de suelo del predio — el revisor
# lo consulta manualmente desde un botón en los ítems de Estudio de suelos y Memoria de
# superficies (ver proyecto.html). Igual que con los precios CNR, es solo un link externo de
# apoyo — la app no lee estos datos en vivo.
URL_IDEMINAGRI = "https://esri.ciren.cl/portal/apps/experiencebuilder/experience/?id=77b51b8c89c3461ab7aea120be55c4b4"
from database import db


def _parse_coord_numero(valor):
    """Parsea un número simple (UTM o grados decimales) en texto libre extraído de un
    documento — no es un dato que el revisor tipee en un formulario con convención fija, así
    que el punto puede ser separador de miles (notación chilena, ej. "349.876") O decimal
    (notación GPS/GIS/CAD, ej. "349876.32", habitual si el consultor copió de un software
    topográfico). Regla de desambiguación: si hay coma, es notación chilena completa
    (punto=miles, coma=decimal); si no hay coma pero el o los puntos dividen el número en
    grupos de EXACTAMENTE 3 dígitos después del primero (ej. "349.876" o "6.294.127"), es
    agrupación de miles y se eliminan; cualquier otro patrón de un solo punto se trata como
    decimal."""
    if not valor:
        return None
    s = re.sub(r"[^\d,.\-]", "", str(valor).strip())
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        partes = s.split(".")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            s = "".join(partes)
    try:
        return float(s)
    except ValueError:
        return None


_RE_DMS_ESPACIOS = re.compile(
    r"-?\d+(?:[.,]\d+)?(?:\s+\d+(?:[.,]\d+)?){1,2}\s*[NnSsEeOoWw]?$")


def _parse_coord_dms(valor):
    """Parsea grados/minutos/segundos (DMS) a grados decimales — ej. 33°26'43"S, 33 26 43 S,
    -33 26 43. Solo se activa con símbolos de grado (° ' ") o con 2-3 números separados
    ESPECÍFICAMENTE por espacios (no por puntos, para no confundirse con una coordenada UTM en
    notación chilena de miles como "6.294.127", que también tiene varios grupos de dígitos
    pero separados por puntos). Retorna None si no calza, para que el llamador use el otro
    parser."""
    if not valor:
        return None
    s = str(valor).strip()
    tiene_simbolo_gms = bool(re.search(r"[°'\"]", s))
    if not tiene_simbolo_gms and not _RE_DMS_ESPACIOS.match(s):
        return None
    numeros = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", s)]
    if not numeros:
        return None
    grados = numeros[0]
    if len(numeros) >= 2:
        grados += numeros[1] / 60
    if len(numeros) >= 3:
        grados += numeros[2] / 3600
    negativo = s.startswith("-") or bool(re.search(r"[SsWwOo]\s*$", s))
    return -grados if negativo else grados


def _parse_coord(valor):
    """Parsea una coordenada (UTM, grados decimales o DMS) en texto libre — el formato varía
    mucho según cómo lo haya escrito el consultor en el documento original. Retorna un número
    simple; quien llama decide si es una coordenada UTM o un grado decimal según su magnitud."""
    dms = _parse_coord_dms(valor)
    if dms is not None:
        return dms
    numero = _parse_coord_numero(valor)
    if numero is None:
        return None
    # Grado decimal simple con letra de hemisferio pero sin patrón DMS completo (ej.
    # "70.6158 O") — _parse_coord_numero ya descartó la letra, aplicamos el signo acá.
    if re.search(r"[SsWwOo]\s*$", str(valor).strip()):
        return -abs(numero)
    return numero


def _mapa_url_resumen(resumen: dict, codigo_sep: str) -> str:
    """Arma el link de Google Maps al punto declarado en el Resumen del proyecto (Coordenada E,
    Coordenada N, Huso), con el código del proyecto como etiqueta del pin. Acepta UTM (con
    Huso), grados decimales o grados/minutos/segundos (coord_e=longitud, coord_n=latitud en
    estos dos últimos casos) — se distinguen por la magnitud del número ya parseado: una
    longitud/latitud siempre cae en ±180/±90, mientras que una coordenada UTM siempre es mucho
    mayor. None si falta algún dato o no se puede interpretar."""
    este = _parse_coord(resumen.get("coord_e"))
    norte = _parse_coord(resumen.get("coord_n"))
    if este is None or norte is None:
        return None
    if abs(este) <= 180 and abs(norte) <= 90:
        lon, lat = este, norte
    else:
        huso_match = re.search(r"\d{1,2}", str(resumen.get("coord_h") or ""))
        # Rango plausible de una coordenada UTM real — evita convertir un número mal
        # interpretado y mostrar un pin en un lugar disparatado.
        if not huso_match or not (100000 <= este <= 900000 and 1000000 <= norte <= 10000000):
            return None
        huso = int(huso_match.group())
        if not (1 <= huso <= 60):
            return None
        try:
            lat, lon = geo.utm_a_latlon(este, norte, huso)
        except (ValueError, ZeroDivisionError):
            return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    etiqueta = quote(codigo_sep or "Proyecto")
    return f"https://maps.google.com/maps?q={lat:.6f},{lon:.6f}({etiqueta})"

BASE_DIR = Path(__file__).parent
os.chdir(BASE_DIR)
load_dotenv(BASE_DIR / ".env")


def _extraer_concurso_id(codigo_sep: str) -> str:
    """
    Extrae el ID del concurso desde el código SEP.
    Ej: '204-2026-16-003' → '204-2026'
         '16-2026-8-001'  → '16-2026'
    """
    partes = codigo_sep.strip().split("-")
    if len(partes) >= 2:
        return f"{partes[0]}-{partes[1]}"
    return codigo_sep


def _consultor_key(nombre: str) -> str:
    """Normaliza el nombre del consultor a una clave estable (minúsculas, sin acentos ni
    espacios extra), para agrupar sus proyectos aunque varíe la escritura."""
    import unicodedata
    n = (nombre or "").strip().lower()
    n = "".join(c for c in unicodedata.normalize("NFD", n)
                if unicodedata.category(c) != "Mn")   # quita acentos
    n = " ".join(n.split())                            # colapsa espacios
    return n


def _consultor_de_proyecto(proyecto: dict) -> tuple:
    """Devuelve (key, nombre_mostrado) del consultor del proyecto, tomado del resumen."""
    nombre = (proyecto.get("resumen", {}) or {}).get("consultor", "").strip()
    return (_consultor_key(nombre), nombre) if nombre else ("", "")


def _criterios_enfasis_combinados(item_key: str, concurso: dict) -> str:
    """Combina los criterios de énfasis PERMANENTES (globales, cruzan todos los concursos —
    ver db.get_criterios_item(), editados en /admin/aprendizaje) con los PUNTUALES de este
    concurso en particular (excepciones específicas de sus bases — ej. "no se acepta agua NO
    inscrita" — que el revisor sigue pudiendo agregar por ítem en /admin/concursos/{id}, ver
    concurso["criterios_enfasis"]). Se inyectan juntos en el prompt del ítem, con secciones
    separadas para que la IA distinga cuál es la regla general y cuál la excepción de este
    concurso."""
    clave = "item_" + item_key
    generales = (db.get_criterios_item().get("criterios", {}) or {}).get(clave, "")
    puntuales = (concurso.get("criterios_enfasis", {}).get(clave, "") if concurso else "")
    partes = []
    if generales.strip():
        partes.append("GENERALES (todos los concursos):\n" + generales.strip())
    if puntuales.strip():
        partes.append("PUNTUALES DE ESTE CONCURSO:\n" + puntuales.strip())
    return "\n\n".join(partes)


def _texto_len(texto: str) -> int:
    """Longitud "útil" de un texto extraído — 0 si está vacío o es el sentinel de PDF
    escaneado (`__PDF_ESCANEADO__`). Se guarda en el documento LIVIANO (`doc["texto_len"]`)
    para poder decidir si un documento tiene texto usable sin cargar el texto completo desde
    su clave aparte (ver la nota grande en `_con_texto()` más abajo)."""
    return len(texto) if texto and texto != "__PDF_ESCANEADO__" else 0


def _doc_disponible_analisis(d: dict, permite_vision: bool = True) -> bool:
    """Un documento está disponible para el análisis si tiene texto usable, o si es un PDF
    escaneado/plano cuyo archivo físico existe (disco o base) y el grupo admite visión (todos
    menos Coherencia global). Debe reflejar exactamente lo que usa `_analizar_grupo()` en
    analyzer.py, para que el contador de documentos de cada eje/ítem no subestime lo que
    realmente se analiza."""
    if d.get("texto_len", 0) > 0:
        return True
    if not permite_vision:
        return False
    return bool(d.get("archivo_presente")) and d.get("filename", "").lower().endswith(".pdf")


def _restaurar_archivos_necesarios(proyecto_id: str, documentos: list):
    """Si el archivo físico de un documento que necesita visión se perdió tras un redeploy de
    Railway, lo recupera desde PostgreSQL antes de analizar — así no hay que resubirlo a mano
    mientras siga guardado en la base.

    "Necesita visión" son dos casos (mismo criterio que `_analizar_grupo` en analyzer.py):
    escaneado/con poco texto, O un tipo de `TIPOS_SIEMPRE_VISION` (planos + pruebas de bombeo —
    van a visión SIEMPRE que el archivo exista, aunque tengan texto). Antes este helper solo
    cubría el primer caso, así que un plano con harto texto (ej. exportado de AutoCAD con cotas
    como texto) que perdía su archivo físico en un redeploy quedaba sin restaurar — la visión
    nunca se disparaba pese a que el código la esperaba siempre para ese tipo, y el revisor no
    tenía forma de notarlo sin revisar manualmente el indicador de la página Documentos."""
    carpeta = UPLOAD_DIR / proyecto_id
    for d in documentos:
        necesita_vision = (d.get("texto_len", 0) < MIN_CHARS_TEXTO
                            or d.get("tipo_doc") in TIPOS_SIEMPRE_VISION)
        if not necesita_vision:
            continue
        filepath = carpeta / d.get("filename", "")
        if filepath.exists():
            continue
        contenido = db.obtener_archivo(proyecto_id, d["id"])
        if contenido:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(contenido)


async def _con_texto(proyecto_id: str, documentos: list) -> list:
    """Devuelve una COPIA de `documentos` con `texto_extraido` restaurado desde su clave
    aparte en la base (`textos:{proyecto_id}`) — usar SOLO en el momento en que el texto
    realmente hace falta (análisis de un ítem, chat, autocompletar Resumen, consulta libre,
    Chequeo de Cálculos, evaluación de respuestas de subsanación). El proyecto guardado
    (`proyecto["documentos"]`) NUNCA lleva el texto embebido — no tocar/reasignar esa lista
    con el resultado de esta función, o el próximo `db.save_proyecto()` volvería a guardar el
    texto completo dentro del blob liviano del proyecto, perdiendo el sentido de separarlo."""
    textos = await asyncio.to_thread(db.get_textos_proyecto, proyecto_id)
    return [dict(d, texto_extraido=textos.get(d["id"], "")) for d in documentos]


def _volver_a(request: Request, proyecto_id: str, defecto: str = "resumen") -> str:
    """URL de la página del proyecto desde la que se envió el formulario (según Referer),
    para volver a ella tras acciones del encabezado (estado). Si no se puede, usa `defecto`."""
    ref = request.headers.get("referer", "") or ""
    base = f"/proyecto/{proyecto_id}/"
    for pag in ("resumen", "documentos", "items", "calculos", "respuestas"):
        if base + pag in ref:
            return base + pag
    return base + defecto


def _registrar_feedback_obs(proyecto: dict, obs: dict, accion: str, user: dict):
    """Registra en el concurso y en el consultor la decisión tomada sobre una observación
    (aprobada/descartada), para alimentar el aprendizaje por eje/ítem/consultor."""
    concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
    if obs.get("eje"):
        tipo_doc_obs = obs["eje"]
    elif obs.get("item"):
        tipo_doc_obs = "item_" + obs["item"]
    else:
        doc_de_obs = next(
            (d for d in proyecto.get("documentos", []) if d["id"] == obs.get("doc_id")), None
        )
        tipo_doc_obs = doc_de_obs["tipo_doc"] if doc_de_obs else "otro"
    entrada_fb = {
        "id":        obs["id"],
        "fecha":     _ahora().isoformat(),
        "tipo_doc":  tipo_doc_obs,
        "texto_obs": obs["texto"][:300],
        "accion":    accion,
        "revisor":   user["username"],
    }
    db.add_feedback_concurso(concurso_id, entrada_fb)
    ckey, cnombre = _consultor_de_proyecto(proyecto)
    if ckey:
        db.add_feedback_consultor(ckey, cnombre, entrada_fb)


def _aplicar_accion_chat(proyecto: dict, accion: dict, user: dict) -> bool:
    """Aplica sobre la observación real el cambio que la IA decidió en el chat (descartar,
    reclasificar a nota, o editar el texto). Devuelve True si se modificó algo, para que el
    llamador sepa que debe refrescar la vista de observaciones."""
    obs = next((o for o in proyecto.get("observaciones", [])
               if o.get("id") == accion.get("id")), None)
    if not obs:
        return False
    tipo = accion.get("accion")
    texto_nuevo = (accion.get("texto_nuevo") or "").strip()
    if tipo == "descartar":
        obs["estado"] = "descartada"
        obs["revisado_por"] = user["nombre"]
        _registrar_feedback_obs(proyecto, obs, "descartada", user)
    elif tipo == "reclasificar_nota":
        obs["severidad"] = "informativa"
        if texto_nuevo:
            obs["texto"] = texto_nuevo
        obs["revisado_por"] = user["nombre"]
        _registrar_feedback_obs(proyecto, obs, "descartada", user)
    elif tipo == "editar":
        if texto_nuevo:
            obs["texto"] = texto_nuevo
        obs["revisado_por"] = user["nombre"]
    elif tipo == "eliminar":
        # Igual señal de aprendizaje que "descartar" (no es válida), pero no reversible:
        # se borra el registro por completo en vez de solo marcarla como descartada.
        _registrar_feedback_obs(proyecto, obs, "descartada", user)
        proyecto["observaciones"] = [o for o in proyecto.get("observaciones", [])
                                     if o.get("id") != obs["id"]]
    else:
        return False
    return True


app = FastAPI(title="Revisor CNR")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Railway corre los contenedores en UTC, no en hora de Chile — usar datetime.now() a secas
# desataba timestamps ~3-4 h adelantados (ej: 13:07 en vez de las 09-10 am reales). Todo el
# código de la app debe usar _ahora() en vez de datetime.now() directo.
TZ_CHILE = ZoneInfo("America/Santiago")


def _ahora() -> datetime:
    return datetime.now(TZ_CHILE)


# Análisis de ítems en segundo plano (ver `revisar_item`/`_analizar_item_fondo`) — se guarda una
# referencia a cada tarea para que Python no la recolija como basura a mitad de camino (gotcha
# conocido de asyncio: una tarea sin referencias vivas puede destruirse "pending"). Se limpia sola
# al terminar via el callback en `_lanzar_analisis_fondo`.
_tareas_fondo: set = set()


def _fmt_fecha(iso_str: str, con_hora: bool = False) -> str:
    """Formatea un datetime ISO a notación chilena dd/mm/aaaa (o dd/mm/aaaa HH:MM si
    con_hora=True). Los registros de antes de este fix son naive (sin huso horario) y quedan
    tal cual estaban guardados — solo los timestamps nuevos usan hora de Chile correctamente."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    return dt.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")


def _fmt_usd(valor, decimales: int = 2) -> str:
    """Monto en dólares con notación chilena (coma decimal), para el contador de costo."""
    try:
        return f"{float(valor):.{decimales}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "0,00"


templates.env.filters["fecha"] = _fmt_fecha
templates.env.filters["fecha_hora"] = lambda s: _fmt_fecha(s, con_hora=True)
templates.env.filters["usd"] = _fmt_usd


# ── Contador de costo de la API por proyecto ────────────────────────────────────
# El costo real de cada llamada ya se calculaba (`analyzer._log_uso`), pero solo se imprimía en
# el log de Railway — que el revisor no mira. Sin esto, la única forma de saber cuánto costó un
# proyecto era comparar el saldo de la consola de Anthropic antes y después de revisarlo, que es
# lo que el usuario venía haciendo a mano. Ahora cada operación que llama a la IA abre un
# acumulador (`analyzer.iniciar_costo()`), y al terminar suma el resultado acá, en el propio
# proyecto, desglosado por paso — así el número queda a la vista en la app.
#
# NO se incluyen las llamadas que no son de un proyecto puntual (documentos obligatorios de un
# concurso, consolidar aprendizaje, perfil de consultor): son de administración, corren a demanda
# unas pocas veces y cargarlas a un proyecto cualquiera falsearía su costo.
PASOS_COSTO = {
    "revision":    "Revisión de ítems",
    "chequeo":     "Chequeo de cálculos",
    "resumen":     "Resumen del proyecto",
    "chat":        "Debatir con la IA",
    "consulta":    "Consulta al expediente",
    "subsanacion": "Respuestas del consultor",
}


def _registrar_costo(proyecto: dict, paso: str, acc: dict, detalle: str = None) -> None:
    """Suma al proyecto lo que costó una operación de IA. `acc` es el dict devuelto por
    `analyzer.iniciar_costo()`, ya poblado. `detalle` (opcional) es el item_key, para poder
    mostrar qué ítem salió más caro.

    Muta `proyecto` en memoria — NO guarda; el llamador ya hace `db.save_proyecto()` con el
    resto del resultado, así que sumarse a ese guardado evita un round-trip extra a Postgres.
    Si la operación no registró ninguna llamada (datos reusados del Chequeo, error antes de
    llamar a la IA), no escribe nada: un paso con 0 llamadas no debe ensuciar el desglose."""
    if not acc or not acc.get("llamadas"):
        return
    usd = round(acc.get("usd", 0.0), 6)
    costo = proyecto.setdefault("costo_api", {})
    costo["total_usd"] = round(costo.get("total_usd", 0.0) + usd, 6)
    costo["llamadas"]  = costo.get("llamadas", 0) + acc["llamadas"]
    p = costo.setdefault("pasos", {}).setdefault(paso, {"usd": 0.0, "llamadas": 0})
    p["usd"]      = round(p["usd"] + usd, 6)
    p["llamadas"] = p["llamadas"] + acc["llamadas"]
    if detalle:
        items = costo.setdefault("items", {})
        items[detalle] = round(items.get(detalle, 0.0) + usd, 6)
    costo["actualizado"] = _ahora().isoformat()


def _costo_para_vista(proyecto: dict) -> dict:
    """Arma el desglose que consumen las plantillas: total, y las líneas por paso ordenadas de
    mayor a menor (el ítem más caro primero dentro de Revisión). `None` si el proyecto todavía
    no gastó nada — así la plantilla puede no mostrar nada en vez de un '0,00' sin sentido."""
    costo = proyecto.get("costo_api") or {}
    if not costo.get("llamadas"):
        return None
    pasos = [{"nombre": PASOS_COSTO.get(k, k), "usd": v.get("usd", 0.0),
              "llamadas": v.get("llamadas", 0)}
             for k, v in (costo.get("pasos") or {}).items()]
    pasos.sort(key=lambda x: x["usd"], reverse=True)
    por_item = [{"nombre": ITEMS_SEP.get(k, {}).get("nombre", k), "usd": v}
                for k, v in (costo.get("items") or {}).items()]
    por_item.sort(key=lambda x: x["usd"], reverse=True)
    # OJO: la clave NO puede llamarse "items" — en Jinja `costo_api.items` resolvería al método
    # `dict.items()` en vez de a la lista, y el render revienta en runtime (mismo bug ya sufrido
    # con `grupo.items` en las observaciones, ver CLAUDE.md).
    return {
        "total_usd": costo.get("total_usd", 0.0),
        "llamadas": costo.get("llamadas", 0),
        "actualizado": costo.get("actualizado", ""),
        "pasos": pasos,
        "por_item": por_item,
    }


# ── Estados del proyecto ────────────────────────────────────────────────────────
# Única fuente de verdad para las 6 clasificaciones válidas — usada para validar el cambio de
# estado, armar el selector del encabezado del proyecto y colorear el badge en el dashboard
# (mismo color en los dos lugares). Reutiliza las clases `badge-*` ya existentes en base.html
# (mismo criterio de color que ya usaban obs./items: azul=neutro, amarillo=alerta liviana,
# morado=legal/en trámite, verde=aprobado, rojo=rechazo) en vez de definir CSS nuevo — salvo
# "Pendiente" (jul-2026), que sí necesitó una clase nueva (`badge-pendiente`, rosa/magenta) porque
# los 5 colores existentes ya estaban todos tomados y el usuario pidió explícitamente un color
# DISTINTO y bien visible, para que un proyecto que quedó a medio revisar (empezó, pero se dejó de
# lado por otro más urgente) no pase desapercibido en el dashboard.
ESTADOS_PROYECTO = ["En revisión", "Pendiente", "Observado", "Con respuesta Observaciones",
                    "Aprobado Técnicamente", "Rechazado"]
ESTADOS_PROYECTO_BADGE = {
    "En revisión":                 "badge-estado",     # celeste
    "Pendiente":                   "badge-pendiente",   # rosa/magenta
    "Observado":                   "badge-menor",       # amarillo
    "Con respuesta Observaciones": "badge-legal",       # morado claro
    "Aprobado Técnicamente":       "badge-tecnica",     # verde
    "Rechazado":                   "badge-mayor",       # rojo
}
ESTADOS_PROYECTO_COLOR_SOLIDO = {
    "En revisión":                 "#2b6cb0",
    "Pendiente":                   "#c2185b",
    "Observado":                   "#c05621",
    "Con respuesta Observaciones": "#5e35b1",
    "Aprobado Técnicamente":       "#276749",
    "Rechazado":                   "#c41230",
}
templates.env.filters["estado_badge"] = lambda e: ESTADOS_PROYECTO_BADGE.get(e, "badge-estado")


@app.on_event("startup")
async def startup_event():
    from database import DATABASE_URL, db
    if DATABASE_URL:
        print(f"🐘 Modo: PostgreSQL (persistencia garantizada)")
        try:
            from database import _get_pg
            _get_pg()
            print("✅ Conexión PostgreSQL OK")
            db.migrar_proyectos()
        except Exception as e:
            print(f"❌ Error PostgreSQL: {e}")
    else:
        print(f"📁 Modo: JSON local (DATA_DIR = {os.getenv('DATA_DIR', 'data')})")

    try:
        db.migrar_textos_documentos()
    except Exception as e:
        print(f"❌ Error migrando textos de documentos: {e}")

    try:
        db.migrar_criterios_enfasis()
    except Exception as e:
        print(f"❌ Error migrando criterios de énfasis: {e}")

    if not db.get_user("admin"):
        db.create_user("admin", "admin123", "Administrador CNR", "admin")
        print("✅ Usuario admin creado: admin / admin123")
    else:
        print("✅ Usuario admin existe — datos persistidos correctamente")

    try:
        _limpiar_analisis_huerfanos()
    except Exception as e:
        print(f"❌ Error limpiando análisis huérfanos: {e}")


def _limpiar_analisis_huerfanos():
    """Análisis de ítems que quedaron marcados "analizando" de un proceso ANTERIOR (Railway
    redespliega seguido en este proyecto) — la tarea asyncio que lo iba a terminar murió junto
    con ese proceso, así que el ítem quedaría "analizando" para siempre sin esta limpieza. Correr
    al arrancar es seguro y suficiente: cualquier entrada de `items_en_progreso` que exista en
    este momento es, por definición, huérfana (ningún proceso vivo la está trabajando todavía —
    recién estamos arrancando)."""
    ligeros = db.get_proyectos_ligero(["id", "items_en_progreso", "revision_lote"])
    afectados = [p for p in ligeros
                 if p.get("items_en_progreso") or (p.get("revision_lote") or {}).get("activo")]
    if not afectados:
        return
    for p_ligero in afectados:
        proyecto = db.get_proyecto(p_ligero["id"])
        if not proyecto:
            continue
        proyecto.setdefault("items_error", {})
        for item_key in list((proyecto.get("items_en_progreso") or {}).keys()):
            proyecto["items_error"][item_key] = {
                "mensaje": "El análisis se interrumpió (reinicio del servidor) — puedes volver a intentarlo.",
                "fecha": _ahora().isoformat(),
            }
        proyecto["items_en_progreso"] = {}
        # Una revisión en tanda del proceso anterior tampoco puede continuar: la tarea que la
        # encadenaba murió con ese proceso. Se cierra para que el botón vuelva a estar disponible
        # (los ítems que alcanzó a terminar quedan revisados; los que faltan se relanzan con otro
        # clic, que los tomará como pendientes por no estar en `items_revisados`).
        if (proyecto.get("revision_lote") or {}).get("activo"):
            proyecto["revision_lote"]["activo"] = False
            proyecto["revision_lote"]["actual"] = None
            proyecto["revision_lote"]["interrumpido"] = True
        db.save_proyecto(proyecto)
    print(f"🧹 Limpiados {len(afectados)} proyecto(s) con análisis huérfanos tras el reinicio")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session")
    if not token:
        return None
    return verify_token(token)


# ─── Rutas de autenticación ───────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = db.get_user(username)
    # bcrypt es deliberadamente lento (~100-300ms) — sin to_thread bloquea el event loop
    # entero (toda la app) durante ese rato en cada login.
    if not user or not await asyncio.to_thread(verify_password, password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Usuario o contraseña incorrectos"
        })
    token = create_token({"username": username, "nombre": user["nombre"], "rol": user["rol"]})
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=28800)  # 8 horas
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


# ─── Dashboard principal ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    # Listado liviano: dashboard.html solo necesita estos campos — evita traer el texto
    # extraído de todos los documentos de todos los proyectos en cada carga del dashboard.
    # "resumen" se pide completo (es chico, ~25 campos cortos) solo para sacar el consultor.
    proyectos = db.get_proyectos_ligero(
        ["id", "codigo_sep", "nombre", "postulante", "estado", "fecha_creacion", "revisor",
         "resumen"],
        username=user["username"])
    for p in proyectos:
        p["consultor"] = ((p.get("resumen") or {}).get("consultor") or "").strip()
    # Numeración por antigüedad (el más antiguo = 1) — la tabla sigue mostrando los más
    # recientes primero (orden de siempre, sin cambios), solo se le agrega este número como
    # referencia estable de cuándo se creó cada proyecto relativo a los demás.
    orden_antiguedad = sorted(proyectos, key=lambda p: p.get("fecha_creacion") or "")
    numero_por_id = {p["id"]: i + 1 for i, p in enumerate(orden_antiguedad)}
    for p in proyectos:
        p["numero"] = numero_por_id.get(p["id"])
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "proyectos": proyectos
    })


# ─── Proyectos ────────────────────────────────────────────────────────────────

@app.get("/proyecto/nuevo", response_class=HTMLResponse)
async def nuevo_proyecto_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("nuevo_proyecto.html", {"request": request, "user": user})


@app.post("/proyecto/nuevo")
async def crear_proyecto(
    request: Request,
    codigo_sep: str = Form(...),
    nombre_proyecto: str = Form(...),
    postulante: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    proyecto_id = str(uuid.uuid4())[:8]
    proyecto = {
        "id": proyecto_id,
        "codigo_sep": codigo_sep,
        "nombre": nombre_proyecto,
        "postulante": postulante,
        "tipo_revision": "tecnica",   # única modalidad — la app solo hace revisión técnica
        "revisor": user["username"],
        "revisor_nombre": user["nombre"],
        "estado": "En revisión",
        "fecha_creacion": _ahora().isoformat(),
        "documentos": [],
        "observaciones": []
    }
    db.save_proyecto(proyecto)

    # Crear carpeta para documentos del proyecto
    (UPLOAD_DIR / proyecto_id).mkdir(exist_ok=True)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}", status_code=302)


async def _render_proyecto(request: Request, proyecto_id: str, pagina: str):
    """Renderiza una de las páginas del proyecto (resumen/documentos/items).
    Todas comparten el mismo encabezado y barra de navegación; `pagina` decide qué se muestra."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
    concurso = db.get_concurso(concurso_id)
    # Ordenar documentos por número de anexo SEP
    proyecto["documentos"] = sorted(
        proyecto.get("documentos", []),
        key=lambda d: TIPO_DOC_ORDEN.get(d.get("tipo_doc", "otro"), 50)
    )
    # Documentos obligatorios de admisibilidad (según las bases) que faltan en este proyecto.
    # Solo advierte si el revisor ya confirmó la lista en /admin/concursos/{id} — una extracción
    # de la IA sin revisar nunca dispara esta advertencia (ver documentos_obligatorios_revisado).
    # `obligatorios_excepciones` (por proyecto, NO por concurso) cubre el caso puntual de un
    # documento que las bases exigen en general pero que no aplica a ESTE proyecto en particular
    # (ej. Prueba de bombeo cuando la fuente es superficial/canal o acumulación de aguas lluvias
    # tipo SCALL/tranque — no corresponde exigirla si no hay pozo/bomba) — desactivarlo en el
    # concurso afectaría a TODOS sus proyectos, la mayoría de los cuales sí la necesitan.
    faltan_obligatorios = []
    obligatorios_exceptuados = []
    if concurso and concurso.get("documentos_obligatorios_revisado") and concurso.get("documentos_obligatorios"):
        tipos_presentes = {d.get("tipo_doc") for d in proyecto["documentos"]}
        excepciones = proyecto.get("obligatorios_excepciones", {})
        for k in concurso["documentos_obligatorios"]:
            if k in tipos_presentes:
                continue
            if k in excepciones:
                obligatorios_exceptuados.append({"key": k, "label": TIPO_DOC_LABELS.get(k, k),
                                                 **excepciones[k]})
            else:
                faltan_obligatorios.append({"key": k, "label": TIPO_DOC_LABELS.get(k, k)})
    # Estado del archivo físico (se pierde tras cada re-despliegue de Railway).
    # Solo importa re-subir los que necesitan visión: escaneados/con poco texto, O un tipo de
    # `TIPOS_SIEMPRE_VISION` (planos + pruebas de bombeo — van a visión SIEMPRE aunque tenga
    # texto, ver _restaurar_archivos_necesarios); el resto ya tiene su texto extraído guardado y
    # no requiere el archivo físico.
    carpeta_proyecto = UPLOAD_DIR / proyecto_id
    ids_guardados_db = db.ids_con_archivo(proyecto_id)
    for doc in proyecto["documentos"]:
        doc["necesita_archivo"] = (doc.get("texto_len", 0) < MIN_CHARS_TEXTO
                                    or doc.get("tipo_doc") in TIPOS_SIEMPRE_VISION)
        doc["archivo_presente"] = ((carpeta_proyecto / doc.get("filename", "")).exists()
                                    or doc["id"] in ids_guardados_db)
    n_faltan_resubir = len([d for d in proyecto["documentos"]
                            if d["necesita_archivo"] and not d["archivo_presente"]])
    # Construir info de ítems SEP: cuántos documentos tiene disponible cada ítem y si ya se revisó
    items_revisados = proyecto.get("items_revisados", {})
    items_en_progreso = proyecto.get("items_en_progreso", {})
    items_error = proyecto.get("items_error", {})
    item_chats = proyecto.get("item_chats", {})
    items_info = []
    for item_key in ITEMS_ORDEN:
        item = ITEMS_SEP[item_key]
        if item_key == "coherencia":
            # Usa TODOS los documentos con texto, igual que el eje homónimo (sin visión).
            n_docs = len([d for d in proyecto["documentos"]
                          if _doc_disponible_analisis(d, permite_vision=False)])
        else:
            tipos = set(item["tipo_docs"])
            n_docs = len([d for d in proyecto["documentos"]
                          if d.get("tipo_doc") in tipos and _doc_disponible_analisis(d)])
        items_info.append({
            "key": item_key,
            "nombre": item["nombre"],
            "n_docs": n_docs,
            "revisado": items_revisados.get(item_key),
            "chat": item_chats.get(item_key, []),
            # Análisis en segundo plano (ver revisar_item()/estado_item()) — la tarjeta del ítem
            # muestra "Analizando…" (con polling) o el error guardado en vez del botón normal.
            "en_progreso": item_key in items_en_progreso,
            "error_analisis": items_error.get(item_key),
        })

    # Agrupar observaciones bajo un solo título por ítem, en su orden lógico.
    orden_item = {ITEMS_SEP[k]["nombre"]: i for i, k in enumerate(ITEMS_ORDEN)}

    def _agrupar(observaciones, campo_nombre, campo_key, orden):
        grupos = {}
        for o in observaciones:
            nombre = o.get(campo_nombre) or "Otras observaciones"
            grupos.setdefault(nombre, {"key": o.get(campo_key, ""), "obs": []})
            grupos[nombre]["obs"].append(o)
        return [{"nombre": n, "key": g["key"], "obs": g["obs"]}
                for n, g in sorted(grupos.items(), key=lambda kv: orden.get(kv[0], 999))]

    todas_obs    = proyecto.get("observaciones", [])
    # Observaciones del método por ÍTEMS SEP (único método vigente; las tageadas con "eje" son
    # historial de proyectos revisados antes de eliminar el método por Ejes — la ficha las
    # sigue mostrando, agrupadas por su propio eje_nombre, aunque ya no se puedan generar más).
    obs_item     = [o for o in todas_obs if o.get("item")]
    prin_item    = [o for o in obs_item if o.get("severidad") != "informativa"]
    notas_item   = [o for o in obs_item if o.get("severidad") == "informativa"]

    def _contadores(principales):
        return {
            "n": len(principales),
            "pend": len([o for o in principales if o.get("estado") == "pendiente"]),
            "aprob": len([o for o in principales if o.get("estado") == "aprobada"]),
            "desc": len([o for o in principales
                         if o.get("estado") not in ("pendiente", "aprobada")]),
        }

    # Grupo revisado más recientemente (por fecha), para abrirlo desplegado por defecto y
    # dejar los demás contraídos — así la lista no obliga a bajar tanto en cada revisión nueva.
    def _mas_reciente(revisados: dict) -> str:
        if not revisados:
            return ""
        return max(revisados.items(), key=lambda kv: kv[1].get("fecha", ""))[0]

    item_reciente = _mas_reciente(items_revisados)

    # Ítems revisados SIN observaciones ni notas: cumplen con la normativa — mostrar un
    # mensaje positivo en vez de dejar la sección vacía y ambigua.
    items_cumplen = [{"key": k, "nombre": ITEMS_SEP[k]["nombre"]}
                     for k in ITEMS_ORDEN
                     if items_revisados.get(k) and items_revisados[k].get("n_obs", 0) == 0
                     and items_revisados[k].get("n_notas", 0) == 0]

    # Resumen del proyecto (formulario): valores guardados + auto-relleno de campos vacíos
    # desde los datos que el proyecto ya tiene (código, postulante, nombre).
    resumen = dict(proyecto.get("resumen", {}))
    for sec in RESUMEN_SECCIONES:
        for campo in sec["campos"]:
            k = campo["key"]
            if not resumen.get(k) and campo.get("auto"):
                resumen[k] = proyecto.get(campo["auto"], "") or ""

    return templates.TemplateResponse("proyecto.html", {
        "request": request,
        "user": user,
        "proyecto": proyecto,
        "concurso": concurso,
        "concurso_id": concurso_id,
        "items_info": items_info,
        # Revisión en tanda: `lote` solo si está corriendo ahora; `lote_pendientes` es cuántos
        # ítems tomaría el botón si se apretara (con documentos y todavía sin revisar) — sirve
        # para decidir si mostrarlo y para avisar el N° antes de gastar.
        "lote": (proyecto.get("revision_lote") or {}) if (proyecto.get("revision_lote") or {}).get("activo") else None,
        "lote_pendientes": len([k for k in _items_con_documentos(proyecto)
                                if k not in items_revisados and k not in items_en_progreso]),
        "n_faltan_resubir": n_faltan_resubir,
        "faltan_obligatorios": faltan_obligatorios,
        "obligatorios_exceptuados": obligatorios_exceptuados,
        # Método por ítems SEP
        "grupos_obs_item": _agrupar(prin_item, "item_nombre", "item", orden_item),
        "grupos_notas_item": _agrupar(notas_item, "item_nombre", "item", orden_item),
        "cont_item": _contadores(prin_item),
        "item_reciente": item_reciente,
        "items_cumplen": items_cumplen,
        # Resumen del proyecto (formulario)
        "resumen_secciones": RESUMEN_SECCIONES,
        "resumen": resumen,
        "mapa_url": _mapa_url_resumen(resumen, proyecto.get("codigo_sep", "")),
        # Página activa (resumen / documentos / items)
        "pagina": pagina,
        "url_precios_cnr": URL_PRECIOS_CNR,
        "url_ideminagri": URL_IDEMINAGRI,
        # Selector de estado del encabezado — (nombre, color sólido para el botón/opciones)
        "estados_proyecto_opciones": [(e, ESTADOS_PROYECTO_COLOR_SOLIDO[e]) for e in ESTADOS_PROYECTO],
        "costo_api": _costo_para_vista(proyecto),
    })


@app.get("/proyecto/{proyecto_id}", response_class=HTMLResponse)
async def ver_proyecto(request: Request, proyecto_id: str):
    # Al abrir un proyecto se entra al Resumen
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/resumen")


@app.get("/proyecto/{proyecto_id}/resumen", response_class=HTMLResponse)
async def pagina_resumen(request: Request, proyecto_id: str):
    return await _render_proyecto(request, proyecto_id, "resumen")


@app.get("/proyecto/{proyecto_id}/documentos", response_class=HTMLResponse)
async def pagina_documentos(request: Request, proyecto_id: str):
    return await _render_proyecto(request, proyecto_id, "documentos")


@app.get("/proyecto/{proyecto_id}/items", response_class=HTMLResponse)
async def pagina_items(request: Request, proyecto_id: str):
    return await _render_proyecto(request, proyecto_id, "items")


# ─── Cambiar estado del proyecto ─────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/estado")
async def cambiar_estado_proyecto(
    request: Request,
    proyecto_id: str,
    estado: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    if estado in ESTADOS_PROYECTO:
        proyecto["estado"] = estado
        proyecto["fecha_estado"] = _ahora().isoformat()
        proyecto["estado_por"] = user["nombre"]
        db.save_proyecto(proyecto)
    return RedirectResponse(url=_volver_a(request, proyecto_id), status_code=302)


# ─── Excepciones a documentos obligatorios (por proyecto, no por concurso) ────────────────────

@app.post("/proyecto/{proyecto_id}/obligatorio/no-aplica")
async def marcar_obligatorio_no_aplica(
    request: Request, proyecto_id: str,
    tipo_doc: str = Form(...), motivo: str = Form(...)
):
    """Marca un documento obligatorio (según las bases del concurso) como NO aplicable a ESTE
    proyecto en particular — ej. Prueba de bombeo cuando la fuente es superficial/canal o
    acumulación de aguas lluvias (SCALL/tranque), caso en que no corresponde exigirla. A
    diferencia de desmarcarlo en /admin/concursos/{id} (que afectaría a TODOS los proyectos del
    concurso), esta excepción es puntual y queda registrada con motivo/autor/fecha para
    auditoría — no desaparece en silencio."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    motivo = motivo.strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Debe indicar un motivo")
    proyecto.setdefault("obligatorios_excepciones", {})[tipo_doc] = {
        "motivo": motivo, "por": user["nombre"], "fecha": _ahora().isoformat(),
    }
    db.save_proyecto(proyecto)
    return RedirectResponse(url=_volver_a(request, proyecto_id), status_code=302)


@app.post("/proyecto/{proyecto_id}/obligatorio/no-aplica/quitar")
async def quitar_obligatorio_no_aplica(request: Request, proyecto_id: str, tipo_doc: str = Form(...)):
    """Revierte una excepción — el documento vuelve a advertirse como faltante si sigue sin
    estar en el expediente."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    proyecto.setdefault("obligatorios_excepciones", {}).pop(tipo_doc, None)
    db.save_proyecto(proyecto)
    return RedirectResponse(url=_volver_a(request, proyecto_id), status_code=302)


# ─── Documentos ───────────────────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/subir")
async def subir_documento(
    request: Request,
    proyecto_id: str,
    archivo: UploadFile = File(...),
    tipo_doc: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    # Guardar archivo
    ext = Path(archivo.filename).suffix.lower()
    doc_id = str(uuid.uuid4())[:8]
    filename = f"{doc_id}{ext}"
    filepath = UPLOAD_DIR / proyecto_id / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)

    content = await archivo.read()
    with open(filepath, "wb") as f:
        f.write(content)
    db.guardar_archivo(proyecto_id, doc_id, filename, content)

    # Extraer texto (en un thread aparte — PyMuPDF/openpyxl bloquean y un PDF grande
    # congelaría el resto de la app mientras se procesa)
    texto = await asyncio.to_thread(extract_text, str(filepath), ext)
    texto_guardado = truncar_texto_guardado(texto)

    doc = {
        "id": doc_id,
        "nombre_original": archivo.filename,
        "filename": filename,
        "tipo_doc": tipo_doc,
        "tipo_doc_label": TIPO_DOC_LABELS.get(tipo_doc, tipo_doc),
        "fecha_subida": _ahora().isoformat(),
        "texto_len": _texto_len(texto_guardado),
        "analizado": False
    }

    proyecto["documentos"].append(doc)
    db.save_proyecto(proyecto)
    await asyncio.to_thread(db.set_texto_documento, proyecto_id, doc_id, texto_guardado)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}/documentos", status_code=302)


# ─── Revisión por eje temático ────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/revisar-item/{item_key}")
async def revisar_item(request: Request, proyecto_id: str, item_key: str):
    """Lanza el análisis del ítem en SEGUNDO PLANO y responde de inmediato — el navegador nunca
    vuelve a sostener una conexión HTTP larga esperando a la IA (ver `_analizar_item_fondo` y
    CLAUDE.md: esa espera era la causa de las pantallas en blanco con Presupuesto/Planos, cuando
    el proxy externo cortaba la conexión aunque el análisis terminara bien en el servidor). La
    página de Ítems SEP hace *polling* a `GET .../item/{item_key}/estado` hasta que termina."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if item_key not in ITEMS_SEP:
        raise HTTPException(status_code=404, detail="Ítem no válido")

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    # Ya está analizando este ítem (doble clic, u otra pestaña) — no relanzar, la tarea en curso
    # sigue su curso sola.
    if item_key in proyecto.get("items_en_progreso", {}):
        return RedirectResponse(url=f"/proyecto/{proyecto_id}/items#item-{item_key}", status_code=302)

    proyecto.setdefault("items_en_progreso", {})[item_key] = {"inicio": _ahora().isoformat()}
    proyecto.setdefault("items_error", {}).pop(item_key, None)
    db.save_proyecto(proyecto)

    tarea = asyncio.create_task(_analizar_item_fondo(proyecto_id, item_key))
    _tareas_fondo.add(tarea)
    tarea.add_done_callback(_tareas_fondo.discard)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items#item-{item_key}", status_code=302)


def _finalizar_analisis_fondo(proyecto_id: str, item_key: str, mensaje_error: str,
                              sin_docs: bool = False, proyecto_ya_cargado: dict = None):
    """Cierra un análisis en segundo plano que terminó en error (o "sin documentos", tratado
    igual — ver `estado_item()`): saca el ítem de `items_en_progreso` y deja el motivo en
    `items_error` para que el próximo *poll* del navegador lo muestre."""
    proyecto = proyecto_ya_cargado or db.get_proyecto(proyecto_id)
    if not proyecto:
        return
    proyecto.setdefault("items_en_progreso", {}).pop(item_key, None)
    proyecto.setdefault("items_error", {})[item_key] = {
        "mensaje": mensaje_error, "fecha": _ahora().isoformat(), "sin_docs": sin_docs,
    }
    db.save_proyecto(proyecto)


async def _analizar_item_fondo(proyecto_id: str, item_key: str):
    """Cuerpo real del análisis de un ítem SEP — antes vivía dentro de `revisar_item()` y el
    navegador esperaba esta misma corrutina completa; ahora corre desatada como tarea asyncio
    (ver `revisar_item()`), así que nunca hay una conexión HTTP larga que un proxy externo pueda
    cortar. La lógica de negocio (qué se le pasa a `analizar_item()`, cómo se guardan las
    observaciones, la invalidación cruzada) es EXACTAMENTE la misma de siempre — no cambia el
    análisis, solo cuándo/cómo le llega el resultado al navegador."""
    acc_costo = iniciar_costo()
    try:
        proyecto = db.get_proyecto(proyecto_id)
        if not proyecto:
            return

        concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
        concurso = db.get_concurso(concurso_id)
        bases_texto       = concurso.get("bases_texto", "") if concurso else ""
        feedback_concurso = concurso.get("feedback", [])   if concurso else []
        criterios = (concurso.get("criterios_aprendidos", {}).get("item_" + item_key, "")
                     if concurso else "")
        enfasis = _criterios_enfasis_combinados(item_key, concurso)
        ckey, _ = _consultor_de_proyecto(proyecto)
        consultor = db.get_consultor(ckey) if ckey else None

        verif_calc = proyecto.get("verificacion_calculos", {})

        # Si el Chequeo de Cálculos YA tiene datos guardados para este grupo, se reusan tal cual
        # en vez de volver a extraerlos con Haiku — SIN exigir que estén marcados "validado"
        # (ago-2026, corrección del usuario sobre cómo usa realmente la app; ver
        # "Reuso de la extracción del Chequeo de Cálculos" en CLAUDE.md). El tilde "Ya revisé
        # estos datos" sigue existiendo y mostrándose con fecha/autor, pero ya no decide esto.
        def _datos_guardados(valor):
            return valor if _tiene_datos(valor) else None

        n_sistemas = _n_sistemas_proyecto(verif_calc)
        verif_hid_norm = _normalizar_verif_multisistema(verif_calc.get("hidraulico"), n_sistemas, "tramos")
        datos_verificacion_hidraulica = (
            _datos_guardados({"sistemas": verif_hid_norm["sistemas"]})
            if item_key == "diseno_hidraulico" else None
        )
        verif_agro_norm = _normalizar_verif_multisistema(verif_calc.get("agronomico"), n_sistemas)
        datos_verificacion_agronomica = (
            _datos_guardados({"sistemas": verif_agro_norm["sistemas"]})
            if item_key == "diseno_hidraulico" else None
        )
        datos_verificacion_fv = (
            _datos_guardados(verif_calc.get("energetico"))
            if item_key == "diseno_fotovoltaico" else None
        )

        tabla_precios = None
        if item_key in ("presupuesto", "presupuesto_electrico"):
            precios_data = db.get_precios()
            tabla_precios = precios_data.get("items") if precios_data else None

        # Lo ya observado en los OTROS ítems, para que este no lo repita (ver `_analizar_grupo`).
        # Antes solo se le pasaba a Coherencia Global; desde ago-2026 lo recibe todo ítem, porque
        # la repetición también se daba entre ítems normales (ej. el espesor no declarado de un
        # material observado en Especificaciones Técnicas y otra vez en Presupuesto). Se excluyen
        # las descartadas: si el revisor ya las descartó, no deben condicionar nada.
        observaciones_previas = [
            {"item_nombre": o.get("item_nombre", ""), "texto": o.get("texto", "")}
            for o in proyecto.get("observaciones", [])
            if o.get("item") and o.get("item") != item_key and o.get("estado") != "descartada"
        ]

        observaciones_pendientes_otros = [
            {"id": o.get("id"), "item_nombre": o.get("item_nombre", ""), "texto": o.get("texto", "")}
            for o in proyecto.get("observaciones", [])
            if o.get("item") and o.get("item") != item_key and o.get("estado") == "pendiente"
        ]

        # En `to_thread` (no directo): esta función es SINCRÓNICA y puede hacer varias lecturas
        # de `bytea` de varios MB desde Postgres MÁS la escritura de esos PDF al disco. Llamada
        # directo desde este `async def` bloqueaba el event loop entero mientras tanto — es decir,
        # congelaba TODAS las páginas para TODOS los usuarios, no solo este análisis. Mismo patrón
        # de bug ya corregido antes para las llamadas a la API de Anthropic, PyMuPDF y bcrypt
        # (ver "Auditoría de rendimiento" en CLAUDE.md); este punto se había quedado afuera.
        # Se nota sobre todo tras un redeploy de Railway (frecuentes en este proyecto), que es
        # justo cuando esta restauración tiene trabajo real que hacer.
        await asyncio.to_thread(_restaurar_archivos_necesarios, proyecto_id,
                                proyecto.get("documentos", []))
        documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))

        resultado = await analizar_item(
            item_key=item_key,
            documentos=documentos_con_texto,
            bases_texto=bases_texto,
            concurso_id=concurso_id,
            feedback_concurso=feedback_concurso,
            criterios_aprendidos=criterios,
            criterios_enfasis=enfasis,
            consultor=consultor,
            resumen=proyecto.get("resumen", {}),
            datos_verificacion_hidraulica=datos_verificacion_hidraulica,
            datos_verificacion_agronomica=datos_verificacion_agronomica,
            n_sistemas=n_sistemas,
            datos_verificacion_fv=datos_verificacion_fv,
            tabla_precios=tabla_precios,
            observaciones_previas=observaciones_previas,
            observaciones_pendientes_otros=observaciones_pendientes_otros,
            tipo_revision=proyecto.get("tipo_revision", "tecnica"),
            ruta_uploads=str(UPLOAD_DIR / proyecto_id),
        )
    except Exception as e:
        import traceback
        print(f"❌ ERROR en _analizar_item_fondo {item_key}: {e}")
        print(traceback.format_exc())
        _finalizar_analisis_fondo(proyecto_id, item_key, f"Error al revisar ítem: {str(e)}")
        return

    # Se relee el proyecto FRESCO justo antes de guardar — el análisis puede tardar minutos, y en
    # ese tiempo el revisor pudo haber hecho otros cambios (aprobar una observación, editar el
    # Resumen, etc.) desde otra pestaña. Aplicar el resultado sobre la copia más reciente posible
    # acota esa ventana — mismo riesgo que ya existía en el flujo síncrono de siempre mientras
    # esperaba a la IA (la app no usa transacciones, ver database.py), no uno nuevo de este cambio.
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        return

    if resultado.get("sin_documentos"):
        _finalizar_analisis_fondo(
            proyecto_id, item_key,
            "Ese ítem no tiene documentos con texto disponibles en este expediente. Sube o clasifica los documentos correspondientes.",
            sin_docs=True, proyecto_ya_cargado=proyecto)
        return

    # Reemplazar observaciones previas de este ítem — las AGREGADAS A MANO por el revisor
    # (obs["manual"]) se conservan: no son un resultado del análisis, así que re-analizar no
    # debe borrarlas.
    proyecto["observaciones"] = [
        o for o in proyecto.get("observaciones", [])
        if o.get("item") != item_key or o.get("manual")
    ]

    nombre_item  = ITEMS_SEP[item_key]["nombre"]
    docs_incluidos = resultado.get("docs_incluidos", [])
    resumen_docs = ", ".join(d["label"] for d in docs_incluidos)
    for obs in resultado.get("observaciones", []):
        obs["id"] = str(uuid.uuid4())[:8]
        obs["item"] = item_key
        obs["item_nombre"] = nombre_item
        obs["doc_id"] = ""
        obs["doc_nombre"] = f"Ítem SEP: {nombre_item} ({resumen_docs})"
        obs["fecha"] = _ahora().isoformat()
        obs["estado"] = "pendiente"
        proyecto["observaciones"].append(obs)

    # Registrar qué ítems se han revisado
    obs_generadas = resultado.get("observaciones", [])
    n_notas = len([o for o in obs_generadas if o.get("severidad") == "informativa"])
    n_obs   = len(obs_generadas) - n_notas

    # Invalidación cruzada: auto-descartar observaciones PENDIENTES de OTROS ítems que el
    # contenido de este ítem resolvió (ver analyzer.revisar_invalidacion_cruzada). Solo toca
    # "pendiente" — si el revisor ya la aprobó o ya la había descartado, no se toca. Se guarda la
    # justificación que dio la IA (cita textual del contenido que la resolvió) junto con el
    # descarte, para que el revisor pueda juzgar de un vistazo si el criterio fue razonable —
    # bug real detectado (jul-2026): sin esta justificación visible, un descarte incorrecto (ej.
    # el Presupuesto marcado como si resolviera una observación de superficies del Diseño
    # hidráulico, cosa que no tiene sentido) pasaba desapercibido para el revisor.
    invalidadas = resultado.get("invalidadas") or []
    mapa_invalidadas = {i.get("id"): i.get("justificacion", "") for i in invalidadas if i.get("id")}
    n_invalidadas = 0
    if mapa_invalidadas:
        for o in proyecto["observaciones"]:
            if o.get("id") in mapa_invalidadas and o.get("estado") == "pendiente":
                justificacion = mapa_invalidadas[o["id"]]
                sufijo = f' — {justificacion}' if justificacion else ""
                o["estado"] = "descartada"
                o["texto"] = o["texto"] + f'\n\n[Auto-descartada: resuelta al revisar "{nombre_item}"{sufijo}]'
                n_invalidadas += 1

    proyecto.setdefault("items_revisados", {})
    proyecto["items_revisados"][item_key] = {
        "fecha": _ahora().isoformat(),
        "n_obs": n_obs,
        "n_notas": n_notas,
        "docs": docs_incluidos,   # [{id, nombre (archivo real), label (tipo)}] — para mostrar cuáles se usaron
        "ultima_invalidadas": n_invalidadas,  # para que GET .../estado se lo pueda avisar al navegador
    }
    proyecto.setdefault("items_en_progreso", {}).pop(item_key, None)
    proyecto.setdefault("items_error", {}).pop(item_key, None)
    _registrar_costo(proyecto, "revision", acc_costo, detalle=item_key)
    db.save_proyecto(proyecto)


@app.get("/proyecto/{proyecto_id}/item/{item_key}/estado")
async def estado_item(request: Request, proyecto_id: str, item_key: str):
    """*Polling* liviano — la página de Ítems SEP pregunta cada pocos segundos si un análisis en
    segundo plano ya terminó, en vez de que el navegador sostenga una conexión larga. Nunca lee
    documentos ni llama a la IA, solo el estado guardado en el proyecto."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    # Proyección liviana: solo los 3 campos de estado. Este endpoint se consulta cada 4 segundos
    # mientras dura un análisis, y con el proyecto completo traía y deserializaba TODAS las
    # observaciones en cada vuelta solo para leer si el ítem ya terminó.
    proyecto = db.get_proyecto_campos(
        proyecto_id, ["items_en_progreso", "items_error", "items_revisados"])
    if not proyecto:
        raise HTTPException(status_code=404)

    if item_key in (proyecto.get("items_en_progreso") or {}):
        return JSONResponse({"estado": "analizando"})

    # OJO con el `or {}`: la proyección de Postgres devuelve el campo en null (no ausente) cuando
    # el proyecto todavía no lo tiene, así que `.get(campo, {})` devolvería None, no {}.
    error = (proyecto.get("items_error") or {}).get(item_key)
    if error:
        return JSONResponse({"estado": "error", "mensaje": error.get("mensaje", ""),
                             "sin_documentos": bool(error.get("sin_docs"))})

    revisado = (proyecto.get("items_revisados") or {}).get(item_key)
    n_invalidadas = revisado.get("ultima_invalidadas", 0) if revisado else 0
    return JSONResponse({"estado": "listo", "item_invalidadas": n_invalidadas})


# ─── Revisión de todos los ítems en tanda (opcional, adicional a los botones por ítem) ──────

def _items_con_documentos(proyecto: dict) -> list:
    """Ítems que tienen al menos un documento disponible para analizar, en el orden del SEP.
    Misma cuenta que muestra cada tarjeta en la página ("N documentos disponibles")."""
    docs = proyecto.get("documentos", [])
    pendientes = []
    for item_key in ITEMS_ORDEN:
        if item_key == "coherencia":
            n_docs = len([d for d in docs if _doc_disponible_analisis(d, permite_vision=False)])
        else:
            tipos = set(ITEMS_SEP[item_key]["tipo_docs"])
            n_docs = len([d for d in docs
                          if d.get("tipo_doc") in tipos and _doc_disponible_analisis(d)])
        if n_docs:
            pendientes.append(item_key)
    return pendientes


async def _revisar_lote_fondo(proyecto_id: str):
    """Recorre los ítems del lote UNO DESPUÉS DEL OTRO (nunca en paralelo) y corre para cada uno
    exactamente el mismo análisis que el botón individual.

    El orden secuencial no es un detalle de implementación: la **invalidación cruzada** compara
    el ítem recién revisado contra las observaciones PENDIENTES de los otros ítems, así que solo
    funciona si los anteriores ya terminaron y dejaron sus observaciones guardadas. En paralelo,
    cada ítem no vería nada de los demás y el auto-descarte quedaría muerto.

    Vive en el servidor (no en el navegador) a propósito: un lote completo puede tardar bastante,
    y así el revisor puede cerrar la pestaña o irse sin cortarlo."""
    try:
        while True:
            proyecto = db.get_proyecto(proyecto_id)
            lote = (proyecto or {}).get("revision_lote") or {}
            pendientes = lote.get("pendientes") or []
            if not proyecto or not lote.get("activo") or not pendientes:
                break

            item_key = pendientes[0]
            lote["pendientes"] = pendientes[1:]
            lote["actual"] = item_key
            proyecto["revision_lote"] = lote
            proyecto.setdefault("items_en_progreso", {})[item_key] = {"inicio": _ahora().isoformat()}
            proyecto.setdefault("items_error", {}).pop(item_key, None)
            db.save_proyecto(proyecto)

            # `_analizar_item_fondo` ya trae su propio try/except y cierra el ítem con su error
            # en `items_error`; un ítem que falle no debe cortar el resto del lote.
            await _analizar_item_fondo(proyecto_id, item_key)

            proyecto = db.get_proyecto(proyecto_id)
            if not proyecto:
                break
            lote = proyecto.get("revision_lote") or {}
            lote.setdefault("completados", []).append(item_key)
            lote["actual"] = None
            proyecto["revision_lote"] = lote
            db.save_proyecto(proyecto)
    except Exception as e:
        import traceback
        print(f"❌ ERROR en _revisar_lote_fondo {proyecto_id}: {e}")
        print(traceback.format_exc())
    finally:
        # Cierre del lote pase lo que pase — si no, el botón quedaría deshabilitado para siempre.
        proyecto = db.get_proyecto(proyecto_id)
        if proyecto and proyecto.get("revision_lote"):
            proyecto["revision_lote"]["activo"] = False
            proyecto["revision_lote"]["actual"] = None
            proyecto["revision_lote"]["fin"] = _ahora().isoformat()
            db.save_proyecto(proyecto)


@app.post("/proyecto/{proyecto_id}/revisar-todos")
async def revisar_todos_items(request: Request, proyecto_id: str):
    """Revisa en tanda todos los ítems que tengan documentos y NO estén revisados todavía.

    Deja fuera los ya revisados a propósito: `revisar_item()` borra las observaciones de la IA del
    ítem antes de insertar las nuevas, así que re-analizar en masa borraría observaciones que el
    revisor quizá ya aprobó o editó. Para rehacer un ítem puntual está su botón individual, y para
    rehacer todo está "Limpiar revisión"."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    if (proyecto.get("revision_lote") or {}).get("activo"):
        return RedirectResponse(url=f"/proyecto/{proyecto_id}/items", status_code=302)

    revisados = proyecto.get("items_revisados", {})
    en_progreso = proyecto.get("items_en_progreso", {})
    pendientes = [k for k in _items_con_documentos(proyecto)
                  if k not in revisados and k not in en_progreso]
    if not pendientes:
        return RedirectResponse(url=f"/proyecto/{proyecto_id}/items?lote_vacio=1", status_code=302)

    proyecto["revision_lote"] = {
        "activo": True, "pendientes": pendientes, "actual": None, "completados": [],
        "total": len(pendientes), "inicio": _ahora().isoformat(), "por": user["nombre"],
    }
    db.save_proyecto(proyecto)

    tarea = asyncio.create_task(_revisar_lote_fondo(proyecto_id))
    _tareas_fondo.add(tarea)
    tarea.add_done_callback(_tareas_fondo.discard)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items", status_code=302)


@app.post("/proyecto/{proyecto_id}/revisar-todos/detener")
async def detener_lote(request: Request, proyecto_id: str):
    """Corta el lote: el ítem que esté analizándose en este momento igual termina y se guarda
    (no se pierde lo pagado), pero no se empieza ninguno más."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    if proyecto.get("revision_lote"):
        proyecto["revision_lote"]["pendientes"] = []
        proyecto["revision_lote"]["detenido_por"] = user["nombre"]
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items", status_code=302)


@app.get("/proyecto/{proyecto_id}/lote/estado")
async def estado_lote(request: Request, proyecto_id: str):
    """*Polling* del lote — mismo patrón liviano que `estado_item()`: solo lee el estado guardado.
    Mientras el lote corre, la página consulta esto en vez de que cada tarjeta haga su propio
    poll (que navegaría al terminar cada ítem e interrumpiría la tanda)."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    proyecto = db.get_proyecto_campos(proyecto_id, ["revision_lote"])
    if not proyecto:
        raise HTTPException(status_code=404)
    lote = proyecto.get("revision_lote") or {}
    if not lote.get("activo"):
        return JSONResponse({"activo": False})
    actual = lote.get("actual")
    return JSONResponse({
        "activo": True,
        "actual": ITEMS_SEP[actual]["nombre"] if actual in ITEMS_SEP else None,
        "actual_key": actual,
        "completados_keys": lote.get("completados") or [],
        "hechos": len(lote.get("completados") or []),
        "total": lote.get("total", 0),
    })


@app.post("/proyecto/{proyecto_id}/item/{item_key}/observacion/agregar-manual")
async def agregar_observacion_manual(
    request: Request, proyecto_id: str, item_key: str,
    texto: str = Form(...), categoria: str = Form(...), severidad: str = Form(...),
    referencia_normativa: str = Form("")
):
    """El revisor agrega una observación a mano en un ítem (ej. algo que ya sabe sin necesidad
    de re-analizar, o que la IA no captó). Queda marcada `manual=True` para que revisar_item()
    NUNCA la borre al re-analizar el ítem — a diferencia de las observaciones de la IA, no es
    un resultado del análisis, es juicio directo del revisor.

    A partir de acá se trata EXACTAMENTE igual que cualquier observación (mismos campos: item,
    estado, categoria, severidad) — por eso, sin código extra en ningún otro lado, ya queda
    cubierta por todo lo que ya trata "toda observación del proyecto" igual sin mirar su origen:
    Coherencia Global la ve para no repetirla, la invalidación cruzada puede auto-descartarla si
    otro ítem la resuelve, al aprobarla/descartarla alimenta el aprendizaje del ítem/consultor
    igual que una de la IA, aparece en la ficha de revisión, y si se aprueba entra al flujo de
    Respuestas/subsanación como cualquier otra."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if item_key not in ITEMS_SEP:
        raise HTTPException(status_code=404, detail="Ítem no válido")
    if categoria not in ("tecnica", "legal", "presupuesto", "administrativa"):
        raise HTTPException(status_code=400, detail="Categoría no válida")
    if severidad not in ("mayor", "menor", "informativa"):
        raise HTTPException(status_code=400, detail="Severidad no válida")
    texto = texto.strip()
    if not texto:
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    nombre_item = ITEMS_SEP[item_key]["nombre"]
    obs_item = [o for o in proyecto.get("observaciones", []) if o.get("item") == item_key]
    numero = max([o.get("numero", 0) for o in obs_item], default=0) + 1

    proyecto.setdefault("observaciones", []).append({
        "id": str(uuid.uuid4())[:8],
        "numero": numero,
        "categoria": categoria,
        "severidad": severidad,
        "texto": texto,
        "referencia_normativa": referencia_normativa.strip(),
        "item": item_key,
        "item_nombre": nombre_item,
        "doc_id": "",
        "doc_nombre": f"Ítem SEP: {nombre_item} (agregada manualmente)",
        "fecha": _ahora().isoformat(),
        "estado": "pendiente",
        "manual": True,
        "agregada_por": user["nombre"],
    })

    # El contador de la tarjeta del ítem (badge "N obs") es un conteo acumulado desde el último
    # análisis — se incrementa igual al sumar una manual, para que se refleje sin re-analizar.
    proyecto.setdefault("items_revisados", {})
    rev = proyecto["items_revisados"].setdefault(
        item_key, {"fecha": _ahora().isoformat(), "n_obs": 0, "n_notas": 0, "docs": []})
    if severidad == "informativa":
        rev["n_notas"] = rev.get("n_notas", 0) + 1
    else:
        rev["n_obs"] = rev.get("n_obs", 0) + 1

    db.save_proyecto(proyecto)
    return RedirectResponse(
        url=f"/proyecto/{proyecto_id}/items?item_ok={item_key}#item-{item_key}", status_code=302)


async def _manejar_chat(request: Request, proyecto_id: str, tipo: str, key: str, mensaje: str):
    """Lógica del chat de refinamiento por ítem SEP. Si la IA decide aplicar un cambio a la
    observación (descartar/reclasificar/editar), lo aplica y avisa al frontend con
    "modificado": true para que refresque la página."""
    es_ajax = request.headers.get("x-requested-with") == "fetch"
    user = get_current_user(request)
    if not user:
        if es_ajax:
            return JSONResponse({"ok": False, "error": "sesion"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)

    pagina = "items"

    # A partir de aquí, TODO queda envuelto en un solo try/except: si una petición AJAX
    # entra aquí, SIEMPRE debe salir como JSON (nunca como HTMLException/texto plano que el
    # frontend no pueda interpretar — eso es lo que producía el mensaje genérico sin motivo).
    try:
        if key not in ITEMS_SEP:
            raise ValueError(f"'{key}' no es un {tipo} válido")
        proyecto = db.get_proyecto(proyecto_id)
        if not proyecto:
            raise ValueError("proyecto no encontrado")

        mensaje = (mensaje or "").strip()
        if not mensaje:
            if es_ajax:
                return JSONResponse({"ok": False, "error": "vacio"}, status_code=400)
            return RedirectResponse(url=f"/proyecto/{proyecto_id}/{pagina}#chat-{tipo}-{key}",
                                    status_code=302)

        concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
        concurso = db.get_concurso(concurso_id)
        bases_texto = concurso.get("bases_texto", "") if concurso else ""

        observaciones_grupo = [o for o in proyecto.get("observaciones", []) if o.get("item") == key]
        proyecto.setdefault("item_chats", {})
        historial = proyecto["item_chats"].get(key, [])
        documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))

        acc_costo = iniciar_costo()
        resultado = await chatear_item(
            item_key=key, documentos=documentos_con_texto,
            observaciones_item=observaciones_grupo, historial=historial,
            mensaje=mensaje, bases_texto=bases_texto, concurso_id=concurso_id,
        )

        respuesta = resultado.get("texto", "")
        if not respuesta.strip():
            respuesta = ("La IA no devolvió una respuesta (posible corte por respuesta muy larga). "
                         "Intenta reformular la pregunta de forma más breve o vuelve a enviarla.")

        # Si la IA decidió aplicar un cambio concreto a la observación, aplicarlo de verdad.
        modificado = False
        accion = resultado.get("accion")
        if accion:
            modificado = _aplicar_accion_chat(proyecto, accion, user)

        historial.append({"rol": "revisor", "texto": mensaje, "fecha": _ahora().isoformat()})
        historial.append({"rol": "ia", "texto": respuesta, "fecha": _ahora().isoformat()})
        proyecto["item_chats"][key] = historial[-40:]   # conservar últimos 40 turnos
        _registrar_costo(proyecto, "chat", acc_costo)
        db.save_proyecto(proyecto)
    except Exception as e:
        import traceback
        print(f"❌ ERROR en chat {tipo} {key}: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        mensaje_error = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        if es_ajax:
            return JSONResponse({"ok": False, "error": mensaje_error}, status_code=500)
        raise HTTPException(status_code=500, detail=f"Error en el chat: {mensaje_error}")

    if es_ajax:
        return JSONResponse({"ok": True, "mensaje": mensaje, "respuesta": respuesta,
                            "modificado": modificado})
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/{pagina}#chat-{tipo}-{key}", status_code=302)


@app.post("/proyecto/{proyecto_id}/item/{item_key}/chat")
async def chat_item(request: Request, proyecto_id: str, item_key: str,
                    mensaje: str = Form(...)):
    return await _manejar_chat(request, proyecto_id, "item", item_key, mensaje)


# ─── Chequeo de Cálculos (verificación numérica hidráulica y agronómica) ──────
# Página aparte donde el revisor puede ver/corregir los datos que la IA extrajo de los
# documentos, y "validarlos" — desde ahí en adelante esos datos (no la extracción automática)
# se usan para la comparación en el análisis del eje. Cubre solo Hidráulico (Hazen-Williams,
# tramos de tubería) y Agronómico (cadena ETo→ETc→AD→Dn→Fr→Db) por ahora — fotovoltaico,
# carrete y microaspersión quedan pendientes para una siguiente iteración.

N_TRAMOS_HIDRAULICOS = 6


def _num_form(form, campo: str):
    v = (form.get(campo) or "").strip()
    if not v:
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def _tramos_con_calculo(tramos: list) -> list:
    """Adjunta a cada tramo su resultado recalculado (Hazen-Williams), para mostrarlo en la UI."""
    out = []
    for t in tramos:
        t = dict(t)
        q, d = t.get("caudal_ls"), t.get("diametro_mm")
        if q and d:
            c = calculos_riego.C_HAZEN_WILLIAMS.get((t.get("material") or "").lower())
            t["calculo"] = calculos_riego.evaluar_tramo(q, d, t.get("longitud_m"), c)
        else:
            t["calculo"] = None
        out.append(t)
    return out


def _kc_dt05_calculo(cultivo, kc):
    """Rango Kc DT-05 para el cultivo declarado, si hay match — independiente del resto de la
    cadena agronómica (usado tanto en el preview de Chequeo de Cálculos como para completar
    agro_calc aunque falten los otros 7 campos base)."""
    if not cultivo or kc in (None, ""):
        return None
    match = _buscar_rango_kc(cultivo)
    if not match:
        return None
    clave, kc_min, kc_max = match
    return {"cultivo_match": clave, "kc_min": kc_min, "kc_max": kc_max,
            "kc_fuera_rango": not (kc_min <= float(kc) <= kc_max)}


def _eficiencia_oficial_calculo(sistema_riego, eficiencia_pct):
    """Contraste de la eficiencia de aplicación declarada contra los valores oficiales CNR
    (Tabla 4 de la Guía Metodológica DT-24 cruzada con DT-04) — independiente del resto de la
    cadena agronómica, igual que `_kc_dt05_calculo`. None si el sistema no tiene valor oficial
    (Carrete, Mixto o sin declarar) o si no hay eficiencia declarada."""
    rango = _rango_eficiencia_oficial(sistema_riego)
    if not rango or eficiencia_pct in (None, ""):
        return None
    ef_min, ef_max = rango
    ef = float(eficiencia_pct)
    return {"ef_min": ef_min, "ef_max": ef_max,
            "sobre_oficial": ef > ef_max,     # el caso que infla la superficie regable
            "bajo_oficial":  ef < ef_min}


_CLAVES_META_VERIF = ("validado", "fecha_validado", "validado_por", "n_sistemas")


def _tiene_datos(valor) -> bool:
    """True si hay AL MENOS UN dato real en cualquier nivel de la estructura (ignorando la
    metadata de validación, que existe siempre). Sirve para distinguir "el revisor ya cargó o
    extrajo datos en el Chequeo de Cálculos" de "la clave existe pero está vacía" — un
    formulario guardado en blanco deja `{"sistemas": [{"tramos": [], "amt_declarada_m": None,
    ...}]}`, que NO debe impedir que el análisis extraiga por su cuenta."""
    if isinstance(valor, dict):
        return any(_tiene_datos(v) for k, v in valor.items() if k not in _CLAVES_META_VERIF)
    if isinstance(valor, (list, tuple)):
        return any(_tiene_datos(v) for v in valor)
    if isinstance(valor, str):
        return bool(valor.strip())
    return valor is not None


def _n_sistemas_proyecto(verif: dict) -> int:
    """N° de sistemas de riego GLOBAL del proyecto (1 o 2) — selector ÚNICO, compartido entre
    el Chequeo Agronómico y el Hidráulico: un proyecto con 2 sistemas de riego tiene 2 diseños
    hidráulicos Y 2 cadenas agronómicas, nunca 2 en uno y 1 en el otro.
    Fuente de verdad: verificacion_calculos["n_sistemas"]. Si no existe (proyectos guardados
    antes de unificar el selector, jul-2026 — cuando el selector vivía solo en la tarjeta
    Agronómico), cae al valor que haya quedado ahí."""
    verif = verif or {}
    if verif.get("n_sistemas") in (1, 2):
        return verif["n_sistemas"]
    legacy = (verif.get("agronomico") or {}).get("n_sistemas")
    return legacy if legacy in (1, 2) else 1


def _normalizar_verif_multisistema(datos: dict, n_sistemas: int, campo_legacy: str = None) -> dict:
    """Normaliza un bloque de verificación (agronomico o hidraulico) a la forma
    {"sistemas": [...], "validado", "fecha_validado", "validado_por"}, ajustado al N° de
    sistemas GLOBAL del proyecto (`n_sistemas`, ver `_n_sistemas_proyecto`).

    Datos guardados ANTES de jul-2026 (multi-sistema) son un dict plano de un solo sistema, sin
    clave "sistemas": en Agronómico son campos sueltos (cc_pct, kc, ...); en Hidráulico están
    bajo una clave propia (`campo_legacy="tramos"`). Ambos se envuelven en una lista de 1 para
    no perder proyectos ya cargados."""
    datos = datos or {}
    if isinstance(datos.get("sistemas"), list) and datos["sistemas"]:
        sistemas = list(datos["sistemas"])
    elif campo_legacy and campo_legacy in datos:
        sistemas = [{campo_legacy: datos[campo_legacy]}]
    elif datos:
        sistemas = [{k: v for k, v in datos.items()
                      if k not in ("validado", "fecha_validado", "validado_por", "n_sistemas", "sistemas")}]
    else:
        sistemas = [{}]
    while len(sistemas) < n_sistemas:
        sistemas.append({})
    sistemas = sistemas[:n_sistemas]
    return {"sistemas": sistemas, "validado": datos.get("validado"),
            "fecha_validado": datos.get("fecha_validado"), "validado_por": datos.get("validado_por")}


def _es_goteo(datos: dict) -> bool:
    """True si el sistema de riego declarado es Goteo — usa el modelo de alta frecuencia (Db
    directo de la ETc, sin criterio de riego). Microaspersión/Aspersión/Carrete usan la cadena
    con agotamiento, igual que el Diseñador de Riego (calcGA vs. calcMA/calcAA)."""
    return (datos or {}).get("sistema_riego") == "Goteo"


def _agronomico_calculo(datos: dict):
    alta_frec = _es_goteo(datos)
    # En goteo (alta frecuencia) Db sale directo de ETc/Ef (Fr=1) — CC/PMP/Da/Prof. radicular
    # NO entran en esa cuenta, solo se usan para el dato informativo AD (que en goteo ni
    # siquiera se muestra). Exigirlos ahí bloqueaba el cálculo sin necesidad — el revisor tenía
    # que rellenarlos con un valor cualquiera (ej. "1") solo para que el resto se calculara.
    campos = ["kc", "eto_dia_mm", "eficiencia_pct"]
    if not alta_frec:
        campos = ["cc_pct", "pmp_pct", "da", "prof_radicular_cm", "kc", "eto_dia_mm",
                  "factor_agotamiento_pct", "eficiencia_pct"]
    kc_dt05 = _kc_dt05_calculo(datos.get("cultivo") if datos else None,
                               datos.get("kc") if datos else None)
    # Eficiencia declarada vs. valores oficiales — independiente del resto de la cadena.
    eficiencia_check = _eficiencia_oficial_calculo(
        datos.get("sistema_riego") if datos else None,
        datos.get("eficiencia_pct") if datos else None)
    # VIB vs. Precipitación — independiente del resto, solo Aspersión.
    vib_check = None
    if datos and datos.get("sistema_riego") == "Aspersión":
        vib_check = calculos_riego.verificacion_vib(
            datos.get("vib_mmhr"), datos.get("precipitacion_sistema_mmhr")) or None
    # Postura de Aspersión (VA, superficie/caudal/N° por postura) — independiente del resto,
    # solo Aspersión. Tiempo por postura/posturas por día se agregan más abajo si la cadena
    # completa está disponible (necesitan Db).
    postura_check = None
    if datos and datos.get("sistema_riego") == "Aspersión":
        postura_check = calculos_riego.postura_aspersion(
            caudal_aspersor_m3h=datos.get("caudal_aspersor_m3h"),
            espaciamiento_aspersores_m=datos.get("espaciamiento_aspersores_m"),
            espaciamiento_laterales_m=datos.get("espaciamiento_laterales_m"),
            n_aspersores=datos.get("n_aspersores_postura"),
            superficie_ha=datos.get("superficie_riego_ha"),
            vib_mmhr=datos.get("vib_mmhr"),
        ) or None
    # Operación del carrete (INIA-Carillanca) — independiente del resto, solo Carrete.
    carrete_check = None
    if datos and datos.get("sistema_riego") == "Carrete":
        carrete_check = calculos_riego.diseno_carrete(
            caudal_catalogo_m3h=datos.get("caudal_canon_m3h"),
            margen_sobredim_pct=datos.get("margen_sobredimensionamiento_pct"),
            radio_alcance_m=datos.get("radio_alcance_m"),
            velocidad_viento_ms=datos.get("velocidad_viento_ms"),
            longitud_franja_m=datos.get("longitud_franja_m"),
            velocidad_avance_mh=datos.get("velocidad_avance_mh"),
            superficie_ha=datos.get("superficie_riego_ha"),
            vib_mmhr=datos.get("vib_mmhr"),
        ) or None
    if not (datos and all(datos.get(k) not in (None, "") for k in campos)):
        r = {}
        if kc_dt05:
            r["kc_dt05"] = kc_dt05
        if eficiencia_check:
            r["eficiencia_check"] = eficiencia_check
        if vib_check:
            r["vib_check"] = vib_check
        if postura_check:
            r["postura_check"] = postura_check
        if carrete_check:
            r["carrete_check"] = carrete_check
        return r or None
    # cc_pct/pmp_pct/da/prof_radicular_cm van con .get() (no datos[...]): en goteo ya no están
    # garantizados por `campos` — cadena_agronomica los admite en None (AD queda None, dato
    # puramente informativo que en goteo ni se usa ni se muestra).
    r = calculos_riego.cadena_agronomica(
        datos.get("cc_pct"), datos.get("pmp_pct"), datos.get("da"), datos.get("prof_radicular_cm"),
        datos["kc"], datos["eto_dia_mm"], datos.get("factor_agotamiento_pct"),
        datos["eficiencia_pct"], alta_frecuencia=alta_frec)
    # Aspersión/Carrete: el N° de posturas real reemplaza al N° de sectores por caudal en Caudal
    # de operación/Tiempo total/Balance/Volumen del estanque (ver docstring de
    # verificacion_diseno_riego).
    n_posturas_ext = None
    if datos.get("sistema_riego") == "Aspersión" and postura_check:
        n_posturas_ext = postura_check.get("n_posturas")
    elif datos.get("sistema_riego") == "Carrete" and carrete_check:
        n_posturas_ext = carrete_check.get("n_posturas")
    r.update(calculos_riego.verificacion_diseno_riego(
        db_mm_dia=r["db_mm"],
        db_diario_mm_dia=r.get("db_diario_mm"),
        superficie_ha=datos.get("superficie_riego_ha"),
        caudal_disponible_ls=datos.get("caudal_disponible_ls"),
        precipitacion_mmhr=datos.get("precipitacion_sistema_mmhr"),
        horas_disponibles_dia=datos.get("horas_disponibles_dia"),
        volumen_acumulador_m3=datos.get("volumen_acumulador_m3"),
        n_posturas_ext=n_posturas_ext,
    ))
    if kc_dt05:
        r["kc_dt05"] = kc_dt05
    if eficiencia_check:
        r["eficiencia_check"] = eficiencia_check
    if vib_check:
        r["vib_check"] = vib_check
    if postura_check:
        if postura_check.get("va_mmhr"):
            postura_check = calculos_riego.postura_aspersion(
                caudal_aspersor_m3h=datos.get("caudal_aspersor_m3h"),
                espaciamiento_aspersores_m=datos.get("espaciamiento_aspersores_m"),
                espaciamiento_laterales_m=datos.get("espaciamiento_laterales_m"),
                n_aspersores=datos.get("n_aspersores_postura"),
                superficie_ha=datos.get("superficie_riego_ha"),
                vib_mmhr=datos.get("vib_mmhr"),
                db_mm=r["db_mm"], horas_disponibles_dia=datos.get("horas_disponibles_dia"),
            ) or postura_check
        r["postura_check"] = postura_check
    if carrete_check:
        r["carrete_check"] = carrete_check
    return r


def _fv_calculo(datos: dict):
    campos = ["pkw", "hbom", "hsp", "wp", "vmp", "imp"]
    if datos and all(datos.get(k) not in (None, "") for k in campos):
        return calculos_riego.dimensionamiento_fv(
            pkw=datos["pkw"], hbom=datos["hbom"], hsp=datos["hsp"], fp=datos.get("fp"),
            wp=datos["wp"], vmp=datos["vmp"], imp=datos["imp"], ct=datos.get("ct"),
            temp=datos.get("temp"), einv=datos.get("einv"), vsis=datos.get("vsis"),
        ) or None
    return None


@app.get("/proyecto/{proyecto_id}/calculos", response_class=HTMLResponse)
async def pagina_calculos(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    verif = proyecto.get("verificacion_calculos", {})
    n_sistemas = _n_sistemas_proyecto(verif)

    agro_norm = _normalizar_verif_multisistema(verif.get("agronomico"), n_sistemas)
    agro_sistemas = [
        {"idx": i, "datos": s, "calc": _agronomico_calculo(s)}
        for i, s in enumerate(agro_norm["sistemas"])
    ]

    # El nombre del sistema de riego (Goteo/Aspersión/...) solo se extrae en Agronómico — se
    # reutiliza acá para el título de cada tarjeta Hidráulico (mismo orden/índice: sistema i de
    # Hidráulico es el mismo sistema físico que sistema i de Agronómico).
    hid_norm = _normalizar_verif_multisistema(verif.get("hidraulico"), n_sistemas, "tramos")
    hid_sistemas = []
    for i, s in enumerate(hid_norm["sistemas"]):
        tramos = list((s or {}).get("tramos") or [])[:N_TRAMOS_HIDRAULICOS]
        while len(tramos) < N_TRAMOS_HIDRAULICOS:
            tramos.append({})
        sistema_riego = agro_norm["sistemas"][i].get("sistema_riego") if i < len(agro_norm["sistemas"]) else None
        hid_sistemas.append({
            "idx": i, "tramos": _tramos_con_calculo(tramos), "sistema_riego": sistema_riego,
            "amt_declarada_m": (s or {}).get("amt_declarada_m"),
            "caudal_bombeo_ls": (s or {}).get("caudal_bombeo_ls"),
        })
    fv = verif.get("energetico", {})

    return templates.TemplateResponse("calculos.html", {
        "request": request, "user": user, "proyecto": proyecto,
        "costo_api": _costo_para_vista(proyecto),
        "n_sistemas": n_sistemas,
        "hid_sistemas": hid_sistemas,
        "hid_validado": hid_norm.get("validado"), "hid_fecha": hid_norm.get("fecha_validado"),
        "hid_por": hid_norm.get("validado_por"),
        "agro_sistemas": agro_sistemas,
        "agro_validado": agro_norm.get("validado"), "agro_fecha": agro_norm.get("fecha_validado"),
        "agro_por": agro_norm.get("validado_por"),
        "fv": fv, "fv_calc": _fv_calculo(fv),
        "fv_validado": fv.get("validado"), "fv_fecha": fv.get("fecha_validado"),
        "fv_por": fv.get("validado_por"),
    })


@app.post("/proyecto/{proyecto_id}/calculos/n-sistemas")
async def calculos_guardar_n_sistemas(request: Request, proyecto_id: str):
    """Selector ÚNICO de N° de sistemas de riego (1 o 2), compartido entre el Chequeo
    Agronómico y el Hidráulico — se guarda aparte, a nivel de verificacion_calculos, para que
    ambas tarjetas lean siempre el mismo valor y nunca queden desincronizadas."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    form = await request.form()
    n_sistemas = 2 if form.get("n_sistemas") == "2" else 1
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["n_sistemas"] = n_sistemas
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/hidraulico/extraer")
async def calculos_extraer_hidraulico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    n_sistemas = _n_sistemas_proyecto(proyecto.get("verificacion_calculos", {}))
    documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))
    docs_grupo = _documentos_para_verificacion("hidraulico", documentos_con_texto)
    acc_costo = iniciar_costo()
    datos = await _extraer_datos_hidraulicos(docs_grupo, n_sistemas=n_sistemas)
    sistemas = datos.get("sistemas") or [{} for _ in range(n_sistemas)]
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["hidraulico"] = {
        "sistemas": sistemas, "validado": False,
    }
    _registrar_costo(proyecto, "chequeo", acc_costo)
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/hidraulico/guardar")
async def calculos_guardar_hidraulico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    n_sistemas = _n_sistemas_proyecto(proyecto.get("verificacion_calculos", {}))
    form = await request.form()
    sistemas = []
    for si in range(n_sistemas):
        sp = f"s{si}_"
        tramos = []
        for i in range(N_TRAMOS_HIDRAULICOS):
            nombre = (form.get(f"{sp}t{i}_nombre") or "").strip()
            q = _num_form(form, f"{sp}t{i}_caudal")
            d = _num_form(form, f"{sp}t{i}_diametro")
            if not nombre and not q and not d:
                continue
            tramos.append({
                "nombre": nombre or f"Tramo {i+1}",
                "caudal_ls": q, "diametro_mm": d,
                "longitud_m": _num_form(form, f"{sp}t{i}_longitud"),
                "material": (form.get(f"{sp}t{i}_material") or "").strip() or None,
                "velocidad_declarada_ms": _num_form(form, f"{sp}t{i}_vel_declarada"),
                "hf_declarada_mca": _num_form(form, f"{sp}t{i}_hf_declarada"),
            })
        sistemas.append({
            "tramos": tramos,
            "amt_declarada_m": _num_form(form, f"{sp}amt_declarada"),
            "caudal_bombeo_ls": _num_form(form, f"{sp}caudal_bombeo"),
        })

    validado = form.get("validar") == "on"
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["hidraulico"] = {
        "sistemas": sistemas, "validado": validado,
        "fecha_validado": _ahora().isoformat() if validado else None,
        "validado_por": user["nombre"] if validado else None,
    }
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


def _fecha_disenador() -> str:
    """Fecha/hora actual en el formato del Diseñador de Riego: 'dd-mm-aaaa, h:mm:ss a.m./p.m.'."""
    now = _ahora()
    ampm = "a.m." if now.hour < 12 else "p.m."
    h12 = now.hour % 12 or 12
    return f"{now.day:02d}-{now.month:02d}-{now.year}, {h12}:{now.minute:02d}:{now.second:02d} {ampm}"


@app.get("/proyecto/{proyecto_id}/calculos/informe")
async def informe_calculo_completo(request: Request, proyecto_id: str):
    """Memoria de cálculo completa del proyecto: todos los sistemas de riego + FV en un solo informe."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    verif = proyecto.get("verificacion_calculos", {})
    n_sistemas = _n_sistemas_proyecto(verif)
    agro_norm = _normalizar_verif_multisistema(verif.get("agronomico"), n_sistemas)
    hid_norm  = _normalizar_verif_multisistema(verif.get("hidraulico"),  n_sistemas, "tramos")

    sistemas = []
    for i in range(n_sistemas):
        agro = dict(agro_norm["sistemas"][i])
        hid_s = hid_norm["sistemas"][i] if i < len(hid_norm["sistemas"]) else {}
        tramos_raw = list((hid_s or {}).get("tramos") or [])[:N_TRAMOS_HIDRAULICOS]

        def _rellenar_none(d, claves):
            for k in claves:
                d.setdefault(k, None)
            return d

        _rellenar_none(agro, (
            "cultivo","cc_pct","pmp_pct","da","prof_radicular_cm","factor_agotamiento_pct",
            "kc","eto_dia_mm","eficiencia_pct","superficie_riego_ha","caudal_disponible_ls",
            "precipitacion_sistema_mmhr","horas_disponibles_dia","volumen_acumulador_m3",
            "vib_mmhr","caudal_canon_m3h","margen_sobredimensionamiento_pct","radio_alcance_m",
            "velocidad_viento_ms","longitud_franja_m","velocidad_avance_mh",
        ))
        if isinstance(agro.get("declarado"), dict):
            _rellenar_none(agro["declarado"], (
                "dn_mm","fr_dias","db_mm","caudal_diseno_ls","tiempo_riego_hr",
                "n_sectores","pluviometria_mmhr",
            ))
        calc  = _agronomico_calculo(agro) or {}
        _rellenar_none(calc, (
            "etc_mm_dia","ad_mm","dn_mm","fr_dias","fr_adj_dias","dn_adj_mm","db_mm",
            "db_diario_mm","demanda_ls_ha","superficie_segura_ha","tiempo_riego_hr",
            "n_sectores","tiempo_total_dia_hr","caudal_operacion_ls","v_requerido_dia_l",
            "v_fuente_dia_l","volumen_minimo_estanque_l","acumulador_ok","delta_q_estanque_ls",
            "autonomia_estanque_hr","tiempo_llenado_estanque_hr","caudal_estanque_ls",
            "q_requerido_total_ls",
        ))
        if calc.get("postura_check"):
            _rellenar_none(calc["postura_check"], ("tiempo_postura_hr","posturas_dia"))
        tramos = _tramos_con_calculo(tramos_raw)
        for t in tramos:
            _rellenar_none(t, ("nombre","caudal_ls","diametro_mm","longitud_m","material",
                               "velocidad_declarada_ms","hf_declarada_mca"))
        sistemas.append({
            "idx": i,
            "sistema_riego": agro.get("sistema_riego"),
            "agro": agro, "calc": calc, "tramos": tramos,
            "amt_declarada_m": (hid_s or {}).get("amt_declarada_m"),
            "caudal_bombeo_ls": (hid_s or {}).get("caudal_bombeo_ls"),
        })

    fv = verif.get("energetico") or {}
    fv_calc = _fv_calculo(fv) or {}

    # Metodología del consultor para el informe completo
    mc_completo = (verif.get("metodologia_consultor") or {}).get("completo") or {}
    mc_sistemas = mc_completo.get("sistemas") or []
    mc_fv_raw   = mc_completo.get("fv") or {}
    # Preparar mc por sistema (normalizado igual que en informe individual)
    mc_por_sistema = []
    for i in range(n_sistemas):
        mc_raw = mc_sistemas[i] if i < len(mc_sistemas) else None
        mc = None
        if mc_raw and mc_raw.get("conceptos"):
            mc = {k: {"formula": (mc_raw["conceptos"].get(k) or {}).get("formula"),
                       "resultado": (mc_raw["conceptos"].get(k) or {}).get("resultado")}
                  for k, _ in CONCEPTOS_METODOLOGIA}
        mc_por_sistema.append(mc)
    mc_fv = None
    if mc_fv_raw.get("conceptos"):
        mc_fv = {k: {"formula": (mc_fv_raw["conceptos"].get(k) or {}).get("formula"),
                      "resultado": (mc_fv_raw["conceptos"].get(k) or {}).get("resultado")}
                 for k, _ in CONCEPTOS_METODOLOGIA_FV}

    return templates.TemplateResponse("informe_calculo_completo.html", {
        "request": request, "proyecto": proyecto,
        "n_sistemas": n_sistemas, "sistemas": sistemas,
        "fv": fv, "fv_calc": fv_calc,
        "mc_por_sistema": mc_por_sistema,
        "mc_fv": mc_fv,
        "mc_fecha": mc_completo.get("fecha", "")[:10] if mc_completo else None,
        "CONCEPTOS_METODOLOGIA": CONCEPTOS_METODOLOGIA,
        "CONCEPTOS_METODOLOGIA_FV": CONCEPTOS_METODOLOGIA_FV,
        "fecha_informe": _ahora().strftime("%d/%m/%Y"),
    })


@app.get("/proyecto/{proyecto_id}/calculos/informe/{idx}")
async def informe_calculo(request: Request, proyecto_id: str, idx: int):
    """Memoria de cálculo explicada, paso a paso, del sistema de riego `idx` — página aparte
    (pestaña nueva, mismo patrón que "Exportar para el Diseñador"), pensada para auditar de un
    vistazo lo que YA calculó/verificó el Chequeo de Cálculos, con la fórmula y una explicación
    breve en cada paso. No hace ninguna extracción ni cálculo nuevo — reutiliza exactamente los
    mismos datos guardados y las mismas funciones (`_agronomico_calculo`, `_tramos_con_calculo`)
    que ya alimentan la tabla de `calculos.html`, así nunca puede mostrar un número distinto al
    que efectivamente usó el análisis."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    verif = proyecto.get("verificacion_calculos", {})
    n_sistemas = _n_sistemas_proyecto(verif)
    agro_norm = _normalizar_verif_multisistema(verif.get("agronomico"), n_sistemas)
    if idx < 0 or idx >= len(agro_norm["sistemas"]):
        raise HTTPException(status_code=404, detail="Sistema no válido")

    agro = dict(agro_norm["sistemas"][idx])
    hid_norm = _normalizar_verif_multisistema(verif.get("hidraulico"), n_sistemas, "tramos")
    tramos_raw = list((hid_norm["sistemas"][idx] if idx < len(hid_norm["sistemas"]) else {}).get("tramos") or [])[:N_TRAMOS_HIDRAULICOS]
    hid_sistema = hid_norm["sistemas"][idx] if idx < len(hid_norm["sistemas"]) else {}

    # Varios de estos dicts son ADITIVOS por diseño (`calculos_riego.py`, y los datos "en bruto"
    # recién extraídos por la IA, aún sin pasar por "Guardar"): una clave que no se pudo calcular
    # o extraer queda AUSENTE del dict, no en None — correcto para el resto de la app (que solo
    # lee con `.get()` en Python o la ignora en JS), pero en Jinja `dict.clave_ausente` devuelve
    # `Undefined`, y `Undefined is not none` da `True` (mismo bug ya documentado para
    # `fila-acumulador` en calculos.html) — rompería cada `{% if x is not none %}` de este
    # informe, que SÍ lee estos campos directo en el servidor (a diferencia de calculos.html, que
    # los deja en "—" y los rellena por JS). Se normaliza acá, una sola vez por dict, en vez de
    # repetir la trampa en cada condicional del template.
    def _rellenar_none(d: dict, claves) -> dict:
        for k in claves:
            d.setdefault(k, None)
        return d

    _rellenar_none(agro, (
        "cultivo", "cc_pct", "pmp_pct", "da", "prof_radicular_cm", "factor_agotamiento_pct",
        "kc", "eto_dia_mm", "eficiencia_pct", "superficie_riego_ha", "caudal_disponible_ls",
        "precipitacion_sistema_mmhr", "horas_disponibles_dia", "volumen_acumulador_m3",
        "vib_mmhr", "caudal_canon_m3h", "margen_sobredimensionamiento_pct", "radio_alcance_m",
        "velocidad_viento_ms", "longitud_franja_m", "velocidad_avance_mh",
    ))
    if isinstance(agro.get("declarado"), dict):
        _rellenar_none(agro["declarado"], (
            "dn_mm", "fr_dias", "db_mm", "caudal_diseno_ls", "tiempo_riego_hr", "n_sectores",
            "pluviometria_mmhr",
        ))

    calc = _agronomico_calculo(agro) or {}
    # `cabe_en_horas_disponibles` y `balance_diario_ok` NO se incluyen acá a propósito — a
    # diferencia del resto, el template los distingue con `is defined` (¿se pudo verificar o no,
    # por faltar horas_disponibles_dia/caudal_disponible_ls?), no con `is not none`. Si se
    # rellenaran a None, "no se pudo verificar" pasaría a mostrarse igual que "no cumple" (None
    # es falsy) — un resultado incorrecto (falso positivo de incumplimiento sin datos reales).
    _rellenar_none(calc, (
        "etc_mm_dia", "ad_mm", "dn_mm", "fr_dias", "fr_adj_dias", "dn_adj_mm", "db_mm",
        "db_diario_mm", "demanda_ls_ha", "superficie_segura_ha", "tiempo_riego_hr", "n_sectores",
        "tiempo_total_dia_hr", "caudal_operacion_ls",
        "v_requerido_dia_l", "v_fuente_dia_l", "volumen_minimo_estanque_l",
        "acumulador_ok", "delta_q_estanque_ls", "autonomia_estanque_hr",
        "tiempo_llenado_estanque_hr", "caudal_estanque_ls", "q_requerido_total_ls",
    ))
    if calc.get("postura_check"):
        _rellenar_none(calc["postura_check"], ("tiempo_postura_hr", "posturas_dia"))
    # `vib_supera_pp`/`vib_cumple_minimo_inia` de carrete_check NO se normalizan a propósito: el
    # template los distingue con `is defined` (¿se declaró VIB o no?), no con `is not none` — si
    # se rellenaran a None acá, "no se declaró VIB" pasaría a verse igual que "VIB no cumple"
    # (None es falsy), un resultado incorrecto y distinto del real.

    tramos = _tramos_con_calculo(tramos_raw)
    for t in tramos:
        _rellenar_none(t, ("nombre", "caudal_ls", "diametro_mm", "longitud_m", "material",
                           "velocidad_declarada_ms", "hf_declarada_mca"))

    # Metodología del consultor (ver "Comparar con la metodología del consultor", más abajo) —
    # guardada aparte de `verificacion_calculos.agronomico`/`hidraulico` porque es un dato de otra
    # naturaleza (texto libre citado del expediente, no un número recalculable) y porque se genera
    # bajo demanda, no en cada revisión. `mc_sistema` es None si el revisor todavía no lo pidió.
    mc_sistemas = (verif.get("metodologia_consultor") or {}).get("sistemas") or []
    mc_guardado = mc_sistemas[idx] if idx < len(mc_sistemas) else None
    mc = None
    if mc_guardado and mc_guardado.get("conceptos"):
        mc = dict(mc_guardado["conceptos"])
        for k, _ in CONCEPTOS_METODOLOGIA:
            c = mc.get(k) or {}
            mc[k] = {"formula": c.get("formula"), "resultado": c.get("resultado")}

    fv = verif.get("energetico") or {}
    fv_calc = _fv_calculo(fv) or {}

    return templates.TemplateResponse("informe_calculo.html", {
        "request": request, "proyecto": proyecto,
        "idx": idx, "n_sistemas": n_sistemas,
        "sistema_riego": agro.get("sistema_riego"),
        "agro": agro, "calc": calc,
        "tramos": tramos,
        "amt_declarada_m": hid_sistema.get("amt_declarada_m"),
        "caudal_bombeo_ls": hid_sistema.get("caudal_bombeo_ls"),
        "fv": fv, "fv_calc": fv_calc,
        "fecha_informe": _ahora().strftime("%d/%m/%Y"),
        "mc": mc, "mc_fecha": (mc_guardado or {}).get("fecha"),
    })


@app.post("/proyecto/{proyecto_id}/calculos/informe/{idx}/metodologia-consultor")
async def extraer_metodologia_consultor_route(request: Request, proyecto_id: str, idx: int):
    """Botón "Comparar con la metodología del consultor" de la Memoria de cálculo explicada —
    a diferencia del resto del informe (Python puro, gratis), ESTA acción sí llama a la IA
    (Sonnet 5, sin caché — es una acción puntual, no repetida 19 veces como el resto del
    análisis) para leer el expediente y ver si el consultor MUESTRA su propio cálculo (fórmula,
    no solo el resultado) para cada concepto. Por eso es un botón explícito, nunca automática, y
    el resultado se GUARDA (no se vuelve a pagar en cada recarga de la página — el revisor puede
    volver a pedirlo a mano si sube documentos nuevos)."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    verif = proyecto.get("verificacion_calculos", {})
    n_sistemas = _n_sistemas_proyecto(verif)
    agro_norm = _normalizar_verif_multisistema(verif.get("agronomico"), n_sistemas)
    if idx < 0 or idx >= len(agro_norm["sistemas"]):
        raise HTTPException(status_code=404, detail="Sistema no válido")
    sistema_riego = agro_norm["sistemas"][idx].get("sistema_riego")

    documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))
    docs_grupo = _documentos_para_verificacion("hidraulico", documentos_con_texto)
    acc_costo = iniciar_costo()
    conceptos = await extraer_metodologia_consultor(docs_grupo, sistema_riego)

    proyecto.setdefault("verificacion_calculos", {})
    mc_bloque = proyecto["verificacion_calculos"].setdefault("metodologia_consultor", {})
    sistemas_mc = list(mc_bloque.get("sistemas") or [])
    while len(sistemas_mc) <= idx:
        sistemas_mc.append(None)
    sistemas_mc[idx] = {"conceptos": conceptos, "fecha": _ahora().isoformat()}
    mc_bloque["sistemas"] = sistemas_mc
    _registrar_costo(proyecto, "chequeo", acc_costo)
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos/informe/{idx}", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/informe/metodologia-completa")
async def extraer_metodologia_completa_route(request: Request, proyecto_id: str):
    """Extrae la metodología del consultor para TODOS los sistemas + FV en una sola operación,
    para el informe completo. Guarda en metodologia_consultor.completo."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    verif = proyecto.get("verificacion_calculos", {})
    n_sistemas = _n_sistemas_proyecto(verif)
    agro_norm = _normalizar_verif_multisistema(verif.get("agronomico"), n_sistemas)
    documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))
    docs_hidraulicos = _documentos_para_verificacion("hidraulico", documentos_con_texto)
    docs_fv = _documentos_para_verificacion("diseno_fotovoltaico", documentos_con_texto)

    acc_costo = iniciar_costo()

    # Extraer por sistema (agronómico + hidráulico) en paralelo + FV
    import asyncio as _asyncio
    tareas_sis = [
        extraer_metodologia_consultor(
            docs_hidraulicos,
            agro_norm["sistemas"][i].get("sistema_riego") if i < len(agro_norm["sistemas"]) else None
        )
        for i in range(n_sistemas)
    ]
    tarea_fv = extraer_metodologia_fv(docs_fv)
    resultados = await _asyncio.gather(*tareas_sis, tarea_fv)

    sistemas_mc = [{"conceptos": r, "fecha": _ahora().isoformat()} for r in resultados[:-1]]
    fv_mc = {"conceptos": resultados[-1], "fecha": _ahora().isoformat()}

    proyecto.setdefault("verificacion_calculos", {})
    mc = proyecto["verificacion_calculos"].setdefault("metodologia_consultor", {})
    mc["completo"] = {"sistemas": sistemas_mc, "fv": fv_mc, "fecha": _ahora().isoformat()}
    _registrar_costo(proyecto, "chequeo", acc_costo)
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos/informe", status_code=302)


@app.get("/proyecto/{proyecto_id}/calculos/exportar-disenador/{idx}")
async def exportar_para_disenador(request: Request, proyecto_id: str, idx: int):
    """Descarga un .json con el formato del Diseñador de Riego, armado con los datos GUARDADOS del
    Chequeo de Cálculos del sistema `idx`. Solo exporta lo que Revisor tiene (no inventa). Si el
    sistema no está declarado como uno de los cuatro exportables, vuelve al Chequeo con un aviso."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    verif = proyecto.get("verificacion_calculos", {})
    n_sistemas = _n_sistemas_proyecto(verif)
    agro_norm = _normalizar_verif_multisistema(verif.get("agronomico"), n_sistemas)
    hid_norm = _normalizar_verif_multisistema(verif.get("hidraulico"), n_sistemas, "tramos")
    if idx < 0 or idx >= len(agro_norm["sistemas"]):
        raise HTTPException(status_code=404, detail="Sistema no válido")

    sistema_agro = agro_norm["sistemas"][idx]
    nombre_sistema = (sistema_agro or {}).get("sistema_riego")
    tramos_hid = (hid_norm["sistemas"][idx] if idx < len(hid_norm["sistemas"]) else {}).get("tramos", [])
    fv = verif.get("energetico", {})
    # La UTM del Resumen puede venir en notación chilena de miles ("5.946.762"); el input
    # type="number" del Diseñador solo acepta un número plano, así que se normaliza aquí.
    resumen = dict(proyecto.get("resumen", {}))
    for k in ("coord_n", "coord_e"):
        num = _parse_coord_numero(resumen.get(k))
        if num is not None:
            resumen[k] = int(num) if float(num).is_integer() else num

    data = exportar_disenador.construir(
        sistema_agro, tramos_hid, fv, resumen, proyecto, nombre_sistema, _fecha_disenador())
    if not data:
        return RedirectResponse(
            url=f"/proyecto/{proyecto_id}/calculos?export_sin_sistema=1", status_code=302)

    contenido = json.dumps(data, ensure_ascii=False, indent=2)
    codigo = (proyecto.get("codigo_sep", "") or "").replace("/", "-").replace(" ", "")
    # Nombre de archivo sin tildes/ñ ni espacios (el header Content-Disposition es ASCII-safe;
    # el __name interno del JSON sí conserva la tilde, es contenido, no header).
    sis_ascii = (unicodedata.normalize("NFKD", nombre_sistema)
                 .encode("ascii", "ignore").decode("ascii"))
    filename = f"DR_{sis_ascii}_{codigo}.json".replace(" ", "_")
    return Response(content=contenido, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/proyecto/{proyecto_id}/calculos/agronomico/extraer")
async def calculos_extraer_agronomico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    n_sistemas = _n_sistemas_proyecto(proyecto.get("verificacion_calculos", {}))
    documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))
    docs_grupo = _documentos_para_verificacion("agronomico", documentos_con_texto)
    acc_costo = iniciar_costo()
    datos = await _extraer_datos_agronomicos(docs_grupo, n_sistemas=n_sistemas)
    sistemas = datos.get("sistemas") or [{} for _ in range(n_sistemas)]
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["agronomico"] = {
        "sistemas": sistemas, "validado": False,
    }
    _registrar_costo(proyecto, "chequeo", acc_costo)
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/agronomico/guardar")
async def calculos_guardar_agronomico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    n_sistemas = _n_sistemas_proyecto(proyecto.get("verificacion_calculos", {}))
    form = await request.form()
    campos = ["cc_pct", "pmp_pct", "da", "prof_radicular_cm", "kc", "eto_dia_mm",
              "factor_agotamiento_pct", "eficiencia_pct", "vib_mmhr",
              "superficie_riego_ha", "caudal_disponible_ls",
              "precipitacion_sistema_mmhr", "horas_disponibles_dia", "volumen_acumulador_m3",
              "distancia_hileras_m", "distancia_plantas_m", "n_lineas_emisor",
              "espaciamiento_emisores_m", "espaciamiento_aspersores_m",
              "espaciamiento_laterales_m", "n_aspersores_postura", "caudal_aspersor_m3h",
              "caudal_canon_m3h", "margen_sobredimensionamiento_pct", "radio_alcance_m",
              "velocidad_viento_ms", "longitud_franja_m", "velocidad_avance_mh"]
    sistemas = []
    for i in range(n_sistemas):
        p = f"s{i}_"
        datos = {c: _num_form(form, p + c) for c in campos}
        datos["cultivo"] = (form.get(p + "cultivo") or "").strip() or None
        datos["sistema_riego"] = (form.get(p + "sistema_riego") or "").strip() or None
        datos["declarado"] = {
            "dn_mm": _num_form(form, p + "decl_dn"),
            "fr_dias": _num_form(form, p + "decl_fr"),
            "db_mm": _num_form(form, p + "decl_db"),
            "caudal_diseno_ls": _num_form(form, p + "decl_qdiseno"),
            "tiempo_riego_hr": _num_form(form, p + "decl_triego"),
            "n_sectores": _num_form(form, p + "decl_nsec"),
            "pluviometria_mmhr": _num_form(form, p + "decl_pp"),
        }
        sistemas.append(datos)

    validado = form.get("validar") == "on"
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["agronomico"] = {
        "sistemas": sistemas,
        "validado": validado,
        "fecha_validado": _ahora().isoformat() if validado else None,
        "validado_por": user["nombre"] if validado else None,
    }
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/energetico/extraer")
async def calculos_extraer_fv(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))
    docs_grupo = _documentos_para_verificacion("energetico", documentos_con_texto)
    acc_costo = iniciar_costo()
    datos = await _extraer_datos_fv(docs_grupo)
    datos["validado"] = False
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["energetico"] = datos
    _registrar_costo(proyecto, "chequeo", acc_costo)
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/energetico/guardar")
async def calculos_guardar_fv(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    form = await request.form()
    campos = ["pkw", "hbom", "hsp", "fp", "wp", "vmp", "imp", "ct", "temp", "einv", "vsis"]
    datos = {c: _num_form(form, c) for c in campos}
    datos["declarado"] = {
        "n_paneles": _num_form(form, "decl_npaneles"),
        "kwp_total": _num_form(form, "decl_kwp"),
        "seccion_cable_mm2": _num_form(form, "decl_seccion"),
    }
    validado = form.get("validar") == "on"
    datos["validado"] = validado
    datos["fecha_validado"] = _ahora().isoformat() if validado else None
    datos["validado_por"] = user["nombre"] if validado else None
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["energetico"] = datos
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


# ─── Subida ZIP ───────────────────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/subir-zip")
async def subir_zip(
    request: Request,
    proyecto_id: str,
    archivo: UploadFile = File(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    # Guardar ZIP temporalmente
    zip_id = str(uuid.uuid4())[:8]
    zip_path = UPLOAD_DIR / proyecto_id / f"{zip_id}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    content = await archivo.read()
    with open(zip_path, "wb") as f:
        f.write(content)

    # Extraer y clasificar archivos (thread aparte: puede haber muchos PDF que procesar)
    dest_dir = str(UPLOAD_DIR / proyecto_id)
    archivos = await asyncio.to_thread(extract_zip, str(zip_path), dest_dir)

    # Registrar cada archivo como documento del proyecto
    textos_nuevos = {}
    for arch in archivos:
        doc_id = str(uuid.uuid4())[:8]
        doc = {
            "id": doc_id,
            "nombre_original": arch["nombre_original"],
            "filename": arch["filename"],
            "tipo_doc": arch["tipo_doc"],
            "tipo_doc_label": arch["label"],
            "fecha_subida": _ahora().isoformat(),
            "texto_len": _texto_len(arch["texto_extraido"]),
            "analizado": False,
            "origen": "zip"
        }
        proyecto["documentos"].append(doc)
        textos_nuevos[doc_id] = arch["texto_extraido"]
        archivo_extraido = UPLOAD_DIR / proyecto_id / arch["filename"]
        if archivo_extraido.exists():
            db.guardar_archivo(proyecto_id, doc_id, arch["filename"], archivo_extraido.read_bytes())

    # Eliminar ZIP temporal
    zip_path.unlink(missing_ok=True)

    db.save_proyecto(proyecto)
    if textos_nuevos:
        await asyncio.to_thread(db.set_textos_documentos, proyecto_id, textos_nuevos)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/documentos?zip_ok={len(archivos)}", status_code=302)


# ─── Subida múltiple (archivos sueltos o carpeta) ─────────────────────────────

@app.post("/proyecto/{proyecto_id}/subir-multiple")
async def subir_multiple(
    request: Request,
    proyecto_id: str,
    archivos: List[UploadFile] = File(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    from extractor import detectar_anexo
    FORMATOS_SOPORTADOS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
    registrados = 0
    textos_nuevos = {}

    for archivo in archivos:
        ext = Path(archivo.filename).suffix.lower()
        nombre = Path(archivo.filename).name
        if ext not in FORMATOS_SOPORTADOS:
            continue

        doc_id = str(uuid.uuid4())[:8]
        filename = f"{doc_id}{ext}"
        filepath = UPLOAD_DIR / proyecto_id / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        content = await archivo.read()
        with open(filepath, "wb") as f:
            f.write(content)
        db.guardar_archivo(proyecto_id, doc_id, filename, content)

        tipo_doc, label = detectar_anexo(nombre)
        texto = await asyncio.to_thread(extract_text, str(filepath), ext)
        texto_guardado = truncar_texto_guardado(texto)

        doc = {
            "id": doc_id,
            "nombre_original": nombre,
            "filename": filename,
            "tipo_doc": tipo_doc,
            "tipo_doc_label": label,
            "fecha_subida": _ahora().isoformat(),
            "texto_len": _texto_len(texto_guardado),
            "analizado": False,
            "origen": "multiple"
        }
        proyecto["documentos"].append(doc)
        textos_nuevos[doc_id] = texto_guardado
        registrados += 1

    db.save_proyecto(proyecto)
    if textos_nuevos:
        await asyncio.to_thread(db.set_textos_documentos, proyecto_id, textos_nuevos)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/documentos?multi_ok={registrados}", status_code=302)


# ─── Eliminar documento ───────────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/documento/{doc_id}/eliminar")
async def eliminar_documento(request: Request, proyecto_id: str, doc_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    # Eliminar archivo físico y sus observaciones
    doc = next((d for d in proyecto["documentos"] if d["id"] == doc_id), None)
    if doc:
        filepath = UPLOAD_DIR / proyecto_id / doc["filename"]
        if filepath.exists():
            filepath.unlink()
        db.eliminar_archivo(proyecto_id, doc_id)
        db.eliminar_texto_documento(proyecto_id, doc_id)
        proyecto["documentos"] = [d for d in proyecto["documentos"] if d["id"] != doc_id]
        proyecto["observaciones"] = [o for o in proyecto["observaciones"] if o.get("doc_id") != doc_id]
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/documentos", status_code=302)


@app.post("/proyecto/{proyecto_id}/documentos/eliminar-todos")
async def eliminar_todos_documentos(request: Request, proyecto_id: str):
    """Elimina TODOS los documentos del expediente de una sola vez — pensado para el caso de
    subida duplicada por error (ej. los mismos 40 archivos subidos dos veces), donde borrar uno
    por uno con la confirmación individual de `eliminar_documento()` es tedioso. Mismo efecto
    neto que borrar cada documento uno por uno, pero en lote: borra la carpeta física del
    proyecto entera de una vez (en vez de archivo por archivo) y usa las versiones EN LOTE de
    `eliminar_archivos_proyectos()`/`eliminar_textos_proyecto()` en vez de iterar doc por doc.
    NO toca `items_revisados` ni las observaciones de ítem (no están ligadas a un `doc_id`,
    llevan `item`/`item_nombre`) — mismo alcance que el borrado individual, que tampoco las
    toca; solo se limpian observaciones legacy del método por documento (`doc_id` real)."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    doc_ids = {d["id"] for d in proyecto.get("documentos", [])}
    if doc_ids:
        carpeta = UPLOAD_DIR / proyecto_id
        if carpeta.exists():
            shutil.rmtree(carpeta)
        db.eliminar_archivos_proyectos([proyecto_id])
        db.eliminar_textos_proyecto(proyecto_id)
        proyecto["documentos"] = []
        proyecto["observaciones"] = [o for o in proyecto["observaciones"] if o.get("doc_id") not in doc_ids]
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/documentos", status_code=302)


# ─── Cambiar tipo de documento ───────────────────────────────────────────────

# Orden de visualización por número de anexo SEP
TIPO_DOC_ORDEN = {
    "plano_ubicacion":          1,
    "identificacion_riego":     2,
    "estudio_hidrologico":      3,
    "pruebas_bombeo":           4,
    "diseno_hidraulico":        5,
    "diseno_agronomico":        6,
    "diseno_fotovoltaico":      7,
    "reporte_explorador_solar": 8,
    "estudios_complementarios": 9,
    "especificaciones_tecnicas":10,
    "cronograma":               11,
    "cubicaciones":             12,
    "presupuesto":              13,
    "presupuesto_electrico":    14,
    "cotizaciones_facturas":    15,
    "cotizaciones":             16,
    "declaracion_iva":          17,
    "planos_tecnificacion":     18,
    "planos_obras_civiles":     19,
    "memoria_superficies":      20,
    "estudio_suelos":           21,
    "evaluacion_social":        22,
    "antecedentes_legales":     23,
    "lista_beneficiarios":      24,
    "otro":                     99,
}

# Mapa completo tipo_doc → label (coincide con las opciones del select en proyecto.html)
TIPO_DOC_LABELS = {
    "plano_ubicacion":          "Anexo 9.1 — Plano de ubicación",
    "identificacion_riego":     "Anexo 9.2 — Identificación área de riego",
    "estudio_hidrologico":      "Anexo 9.4 — Análisis Hidrológico",
    "pruebas_bombeo":           "Anexo 9.4.2 — Prueba de bombeo",
    "diseno_hidraulico":        "Anexo 9.5 — Diseño y cálculos hidráulicos",
    "diseno_agronomico":        "Anexo 9.5 — Diseño agronómico",
    "diseno_fotovoltaico":      "Anexo 9.5 — Diseño fotovoltaico",
    "reporte_explorador_solar": "Anexo 9.5 — Reporte Explorador Solar",
    "estudios_complementarios": "Anexo 9.6 — Estudios complementarios",
    "especificaciones_tecnicas":"Anexo 9.8 — Especificaciones técnicas",
    "cronograma":               "Anexo 9.8.1 — Cronograma",
    "cubicaciones":             "Anexo 9.9 — Cubicaciones",
    "presupuesto":              "Anexo 9.10.1 — Presupuesto obras",
    "presupuesto_electrico":    "Anexo 9.10.2 — Presupuesto electrificación",
    "cotizaciones_facturas":    "Anexo 9.10.3 — Cotizaciones y Facturas",
    "cotizaciones":             "Anexo 9.10.4 — Cotizaciones",
    "declaracion_iva":          "Anexo 9.10.5 — Declaración No Contribuyente IVA",
    "planos_tecnificacion":     "Anexo 9.12.1.1 — Planos tecnificación",
    "planos_obras_civiles":     "Anexo 9.12.1.2 — Planos obras civiles",
    "memoria_superficies":      "Anexo 9.13.1 — Memoria cálculo superficies",
    "estudio_suelos":           "Anexo 9.13.2 — Estudio de suelos",
    "evaluacion_social":        "Anexo 9.14 — Evaluación Social MIDESO",
    "antecedentes_legales":     "Antecedentes legales",
    "lista_beneficiarios":      "Lista de beneficiarios",
    "otro":                     "Otro documento",
}

# Catálogo para "Documentos obligatorios de admisibilidad" (checklist + extracción IA):
# excluye "diseno_agronomico" — no es un anexo propio del SEP (mismo Anexo 9.5 que
# diseno_hidraulico, ver CLAUDE.md), así que no debe poder marcarse como obligatorio aparte.
# Se mantiene en TIPO_DOC_LABELS solo para no romper el display de documentos ya
# clasificados así en proyectos antiguos.
TIPO_DOC_LABELS_OBLIGATORIOS = {k: v for k, v in TIPO_DOC_LABELS.items() if k != "diseno_agronomico"}


@app.post("/proyecto/{proyecto_id}/documento/{doc_id}/tipo")
async def actualizar_tipo_documento(
    request: Request, proyecto_id: str, doc_id: str,
    tipo_doc: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return {"error": "no autorizado"}
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        return {"error": "proyecto no encontrado"}
    doc = next((d for d in proyecto["documentos"] if d["id"] == doc_id), None)
    if not doc or doc.get("analizado"):
        return {"error": "documento no modificable"}
    label = TIPO_DOC_LABELS.get(tipo_doc, tipo_doc.replace("_", " ").title())
    doc["tipo_doc"] = tipo_doc
    doc["tipo_doc_label"] = label
    db.save_proyecto(proyecto)
    return {"ok": True, "label": label}


# ─── Ver / previsualizar documento ───────────────────────────────────────────

@app.get("/proyecto/{proyecto_id}/documento/{doc_id}/ver")
async def ver_documento(request: Request, proyecto_id: str, doc_id: str):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    doc = next((d for d in proyecto["documentos"] if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404)
    filepath = UPLOAD_DIR / proyecto_id / doc["filename"]
    ext = Path(doc["filename"]).suffix.lower()
    media_types = {
        ".pdf":  "application/pdf",
        ".doc":  "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls":  "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    # PDFs se abren inline en el navegador; el resto se descarga
    disposition = "inline" if ext == ".pdf" else "attachment"

    if not filepath.exists():
        # No está en disco (se pierde entre deploys en Railway) — probar la copia guardada
        # en PostgreSQL antes de resignarse a mostrar solo el texto extraído.
        contenido = db.obtener_archivo(proyecto_id, doc_id)
        if contenido:
            return Response(
                content=contenido,
                media_type=media_type,
                headers={"Content-Disposition": f'{disposition}; filename="{doc["nombre_original"]}"'}
            )
        textos = await asyncio.to_thread(db.get_textos_proyecto, proyecto_id)
        texto = textos.get(doc_id, "")
        if texto == "__PDF_ESCANEADO__":
            texto = "(Documento escaneado — sin texto extraíble)"
        html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>{doc['nombre_original']}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1d1d1f}}
.aviso{{background:#fff8e6;border:1px solid #f6d860;border-radius:8px;padding:1rem 1.2rem;margin-bottom:1.5rem;font-size:0.9rem}}
h1{{font-size:1.1rem;margin-bottom:0.3rem}}pre{{white-space:pre-wrap;font-size:0.85rem;line-height:1.6;background:#f5f5f7;padding:1rem;border-radius:8px}}</style>
</head><body>
<h1>{doc['nombre_original']}</h1>
<div class="aviso">El archivo original no está disponible en el servidor.
Se muestra el texto extraído que sí está guardado en la base de datos.
Para ver el archivo original, vuelve a subirlo al proyecto.</div>
<pre>{texto[:50000] if texto else '(Sin texto extraído)'}</pre>
</body></html>"""
        return HTMLResponse(content=html, status_code=200)

    return FileResponse(
        path=str(filepath),
        media_type=media_type,
        filename=doc["nombre_original"],
        headers={"Content-Disposition": f'{disposition}; filename="{doc["nombre_original"]}"'}
    )


# ─── Ficha de revisión (imprimible) ──────────────────────────────────────────

@app.get("/proyecto/{proyecto_id}/ficha", response_class=HTMLResponse)
async def ficha_revision(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    try:
        obs_aprobadas = [o for o in proyecto.get("observaciones", [])
                         if o.get("estado") == "aprobada" and o.get("severidad") != "informativa"]
        # Agrupar por ítem en su orden lógico, para la ficha oficial (ingreso al SEP). Las
        # observaciones con eje_nombre son historial de proyectos revisados antes de eliminar
        # el método por Ejes — se siguen mostrando, ordenadas al final (no están en `orden`).
        orden = {ITEMS_SEP[k]["nombre"]: i for i, k in enumerate(ITEMS_ORDEN)}
        grupos = {}
        for o in obs_aprobadas:
            nombre = o.get("item_nombre") or o.get("eje_nombre") or "Otras observaciones"
            grupos.setdefault(nombre, []).append(o)
        grupos_ficha = [{"nombre": n, "obs": items}
                        for n, items in sorted(grupos.items(),
                                               key=lambda kv: orden.get(kv[0], 999))]
        return templates.TemplateResponse("ficha.html", {
            "request": request,
            "proyecto": proyecto,
            "user": user,
            "obs_aprobadas": obs_aprobadas,
            "grupos_ficha": grupos_ficha,
            "fecha_ficha": _ahora().strftime("%d/%m/%Y")
        })
    except Exception as e:
        import traceback
        print(f"❌ ERROR en ficha {proyecto_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al generar ficha: {str(e)}")


def _sistemas_riego_proyecto(proyecto: dict) -> str:
    """Sistema(s) de riego declarado(s) del proyecto (para el encabezado del informe) — lee
    verificacion_calculos["agronomico"], mismo dato que muestra el Chequeo de Cálculos. Con 2
    sistemas los une con " + " (ej. "Goteo + Aspersión"); si no hay ninguno declarado aún,
    "No especificado"."""
    verif = proyecto.get("verificacion_calculos", {})
    n_sistemas = _n_sistemas_proyecto(verif)
    agro_norm = _normalizar_verif_multisistema(verif.get("agronomico"), n_sistemas)
    vistos = []
    for s in agro_norm["sistemas"]:
        nombre = (s or {}).get("sistema_riego")
        if nombre and nombre not in vistos:
            vistos.append(nombre)
    return " + ".join(vistos) if vistos else "No especificado"


@app.get("/proyecto/{proyecto_id}/resumen/informe", response_class=HTMLResponse)
async def informe_resumen(request: Request, proyecto_id: str):
    """Informe imprimible del Resumen del proyecto (solo lectura) — botón "Imprimir informe" en
    la página Resumen. Mismo patrón que ficha.html: template standalone (no extiende base.html),
    botones Imprimir/Descargar PDF, y una sección "Notas" que solo aparece en la versión impresa
    (@media print), para anotar a mano sobre el papel — nunca se guarda ni se envía al backend."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    resumen = dict(proyecto.get("resumen", {}))
    for sec in RESUMEN_SECCIONES:
        for campo in sec["campos"]:
            k = campo["key"]
            if not resumen.get(k) and campo.get("auto"):
                resumen[k] = proyecto.get(campo["auto"], "") or ""

    return templates.TemplateResponse("informe_resumen.html", {
        "request": request,
        "proyecto": proyecto,
        "resumen": resumen,
        "resumen_secciones": RESUMEN_SECCIONES,
        "sistemas_riego_str": _sistemas_riego_proyecto(proyecto),
        "fecha_informe": _ahora().strftime("%d/%m/%Y"),
    })


# ─── Resumen del proyecto (formulario) ────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/resumen")
async def guardar_resumen(request: Request, proyecto_id: str):
    """Guarda los campos del formulario de resumen editados por el revisor."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    form = await request.form()
    resumen = dict(proyecto.get("resumen", {}))
    for k in RESUMEN_KEYS:
        resumen[k] = (form.get(k) or "").strip()
    proyecto["resumen"] = resumen
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/resumen?resumen_ok=1",
                            status_code=302)


@app.post("/proyecto/{proyecto_id}/resumen/autocompletar")
async def autocompletar_resumen(request: Request, proyecto_id: str):
    """Autocompleta con la IA los campos vacíos del resumen a partir de los documentos."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
    concurso = db.get_concurso(concurso_id)
    bases_texto = concurso.get("bases_texto", "") if concurso else ""

    acc_costo = iniciar_costo()
    try:
        documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))
        datos = await resumir_proyecto(
            documentos=documentos_con_texto,
            bases_texto=bases_texto,
            concurso_id=concurso_id,
        )
    except Exception as e:
        import traceback
        print(f"❌ ERROR en autocompletar_resumen {proyecto_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al autocompletar: {str(e)}")

    # Rellenar SOLO los campos que estén vacíos (no pisar lo que el revisor ya escribió)
    resumen = dict(proyecto.get("resumen", {}))
    completados = 0
    for k in RESUMEN_KEYS:
        if not resumen.get(k) and datos.get(k):
            resumen[k] = datos[k]
            completados += 1
    proyecto["resumen"] = resumen
    _registrar_costo(proyecto, "resumen", acc_costo)
    db.save_proyecto(proyecto)
    return RedirectResponse(
        url=f"/proyecto/{proyecto_id}/resumen?auto_ok={completados}",
        status_code=302)


# ─── Consultas al expediente ─────────────────────────────────────────────────

@app.get("/proyecto/{proyecto_id}/consultar", response_class=HTMLResponse)
async def consultar_page(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("consultar.html", {
        "request": request, "user": user, "proyecto": proyecto
    })


@app.post("/proyecto/{proyecto_id}/consultar", response_class=HTMLResponse)
async def consultar_post(request: Request, proyecto_id: str, pregunta: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))
    acc_costo = iniciar_costo()
    respuesta = await consultar_expediente(pregunta, documentos_con_texto)

    consulta = {
        "id": str(uuid.uuid4())[:8],
        "pregunta": pregunta,
        "respuesta": respuesta,
        "fecha": _ahora().isoformat(),
        "revisor": user["nombre"]
    }
    if "consultas" not in proyecto:
        proyecto["consultas"] = []
    proyecto["consultas"].insert(0, consulta)   # más reciente primero
    _registrar_costo(proyecto, "consulta", acc_costo)
    db.save_proyecto(proyecto)

    return templates.TemplateResponse("consultar.html", {
        "request": request, "user": user, "proyecto": proyecto,
        "ultima_consulta": consulta
    })


# ─── Eliminar proyecto ────────────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/limpiar-items")
async def limpiar_items(request: Request, proyecto_id: str):
    """Limpia SOLO la revisión por ítems SEP. No toca los ejes."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if proyecto:
        # Conservar las observaciones de ejes; borrar solo las de ítems
        proyecto["observaciones"] = [o for o in proyecto.get("observaciones", []) if not o.get("item")]
        proyecto["items_revisados"] = {}
        proyecto["item_chats"] = {}
        # No se toca items_en_progreso — si hay un análisis realmente corriendo en segundo plano,
        # se lo deja seguir su curso (interrumpirlo a mitad de camino no aporta nada, y su propio
        # `_finalizar_analisis_fondo`/actualización de `items_revisados` no rompe nada si corre
        # después de esta limpieza). Sí se limpian los errores viejos, para no dejar un banner de
        # error de un análisis anterior después de que el revisor pidió partir de cero.
        proyecto["items_error"] = {}
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items", status_code=302)


@app.post("/proyecto/{proyecto_id}/eliminar")
async def eliminar_proyecto(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if proyecto:
        import shutil
        carpeta = UPLOAD_DIR / proyecto_id
        if carpeta.exists():
            shutil.rmtree(carpeta)
        db.eliminar_archivos_proyectos([proyecto_id])
        db.delete_proyecto(proyecto_id)
    return RedirectResponse(url="/", status_code=302)


# ─── Observaciones ────────────────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/estado")
async def actualizar_observacion(
    request: Request,
    proyecto_id: str,
    obs_id: str,
    estado: str = Form(...),
    texto_editado: str = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    obs_actualizada = None
    for obs in proyecto.get("observaciones", []):
        if obs["id"] == obs_id:
            obs["estado"] = estado
            if texto_editado:
                obs["texto"] = texto_editado
            obs["revisado_por"] = user["nombre"]
            obs_actualizada = obs
            break

    db.save_proyecto(proyecto)

    # ── Guardar feedback en el concurso/consultor para aprendizaje futuro ────
    if obs_actualizada and estado in ("aprobada", "descartada"):
        _registrar_feedback_obs(proyecto, obs_actualizada, estado, user)

    # Volver al MISMO ítem que ya estaba abierto (no saltar al más recientemente analizado) —
    # mismo patrón que revisar_item(): item_ok controla qué <details> queda expandido.
    item_key = obs_actualizada.get("item") if obs_actualizada else None
    extra = f"?item_ok={item_key}#item-{item_key}" if item_key else ""
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items{extra}", status_code=302)


@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/eliminar")
async def eliminar_observacion(request: Request, proyecto_id: str, obs_id: str):
    """Elimina una observación por completo (no reversible), a diferencia de Descartar que
    solo la marca como descartada conservando el registro."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    obs = next((o for o in proyecto.get("observaciones", []) if o["id"] == obs_id), None)
    item_key = None
    if obs:
        item_key = obs.get("item")
        # Misma señal de aprendizaje que descartar (no era válida) antes de borrarla.
        _registrar_feedback_obs(proyecto, obs, "descartada", user)
        proyecto["observaciones"] = [o for o in proyecto["observaciones"] if o["id"] != obs_id]
        db.save_proyecto(proyecto)

    # Mismo criterio que actualizar_observacion(): no saltar al ítem más recientemente analizado.
    extra = f"?item_ok={item_key}#item-{item_key}" if item_key else ""
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items{extra}", status_code=302)


@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/derivar-item")
async def derivar_observacion_item(
    request: Request, proyecto_id: str, obs_id: str, item_key: str = Form(...)
):
    """"Coherencia Global" no existe como ítem en el SEP real — es un cierre transversal interno
    de la app. Cuando una observación de ese grupo (incluida la falta de un documento completo,
    de un ítem que ni siquiera se pudo evaluar) debe copiarse al SEP, el revisor la deriva acá al
    ítem real que corresponde, para poder trasladarla directo. El ítem destino no necesita haber
    sido revisado (puede no tener documentos) — derivar es solo una reclasificación de a quién
    pertenece la observación, no depende de que exista un análisis previo de ese ítem."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if item_key not in ITEMS_SEP or item_key == "coherencia":
        raise HTTPException(status_code=400, detail="Ítem destino no válido")

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    obs = next((o for o in proyecto.get("observaciones", []) if o["id"] == obs_id), None)
    if not obs:
        raise HTTPException(status_code=404, detail="Observación no encontrada")

    origen_key = obs.get("item")
    origen_nombre = obs.get("item_nombre")
    # Solo se guarda la primera vez — si ya se había derivado antes, conserva el origen real.
    if origen_key == "coherencia" and not obs.get("derivada_de"):
        obs["derivada_de"] = origen_nombre

    obs["item"] = item_key
    obs["item_nombre"] = ITEMS_SEP[item_key]["nombre"]
    obs_destino = [o for o in proyecto.get("observaciones", [])
                   if o.get("item") == item_key and o["id"] != obs_id]
    obs["numero"] = max([o.get("numero", 0) for o in obs_destino], default=0) + 1
    obs["revisado_por"] = user["nombre"]

    db.save_proyecto(proyecto)
    return RedirectResponse(
        url=f"/proyecto/{proyecto_id}/items?item_ok={item_key}#item-{item_key}", status_code=302)


# ─── Subsanación: revisión de las respuestas del consultor a las observaciones ────────────────
# Tras enviar las observaciones APROBADAS al consultor (fuera de la app, vía SEP), este tiene 10
# días hábiles para responder. El revisor transcribe cada respuesta acá y la evalúa: la resuelve
# (cierra el punto) o no la resuelve (reitera). Hasta 2 rondas por observación. El proyecto pasa
# a "Aprobado Técnicamente" solo cuando TODAS las observaciones enviadas quedan resueltas.

MAX_RONDAS_SUBSANACION = 2

def _estado_subsanacion(obs: dict) -> dict:
    """Estado derivado del hilo de respuestas de UNA observación aprobada:
      estado: "esperando" (falta la respuesta de la ronda actual) | "resuelta" | "no_resuelta"
      ronda_actual: N° de la próxima ronda a responder (1 o 2), solo si estado=="esperando"
      puede_responder: si el revisor todavía puede registrar una respuesta
      rondas: rondas ya registradas."""
    rondas = (obs.get("subsanacion") or {}).get("rondas", [])
    if not rondas:
        return {"estado": "esperando", "ronda_actual": 1, "puede_responder": True, "rondas": []}
    ultima = rondas[-1]
    if ultima.get("evaluacion") == "resuelta":
        return {"estado": "resuelta", "ronda_actual": None, "puede_responder": False, "rondas": rondas}
    # La última respuesta fue "reiterada": si aún quedan rondas, se espera la siguiente.
    if len(rondas) >= MAX_RONDAS_SUBSANACION:
        return {"estado": "no_resuelta", "ronda_actual": None, "puede_responder": False, "rondas": rondas}
    return {"estado": "esperando", "ronda_actual": len(rondas) + 1, "puede_responder": True, "rondas": rondas}


@app.get("/proyecto/{proyecto_id}/respuestas", response_class=HTMLResponse)
async def pagina_respuestas(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    # Solo entran al flujo las observaciones APROBADAS (las que se enviaron al consultor).
    aprobadas = [o for o in proyecto.get("observaciones", []) if o.get("estado") == "aprobada"]
    orden_item = {ITEMS_SEP[k]["nombre"]: i for i, k in enumerate(ITEMS_ORDEN)}
    grupos = {}
    for o in aprobadas:
        nombre = o.get("item_nombre") or "Otras observaciones"
        grupos.setdefault(nombre, {"key": o.get("item", ""), "obs": []})
        # Opciones de tipo_doc para clasificar un respaldo del consultor: las del ítem observado
        # (todas si es "coherencia" o el ítem no está mapeado), para que el respaldo caiga en su
        # grupo y la IA lo vea al re-analizar.
        # Opciones = catálogo COMPLETO de tipos de documento (el revisor puede clasificar el
        # respaldo en cualquiera), pero preseleccionando el tipo del ítem observado — casi
        # siempre el respaldo corresponde a ese mismo ítem.
        opciones_td = [{"key": k, "label": v} for k, v in TIPO_DOC_LABELS.items()]
        item_o = ITEMS_SEP.get(o.get("item"))
        item_tds = item_o.get("tipo_docs", []) if item_o else []
        if o.get("item") in TIPO_DOC_LABELS:
            preselect = o.get("item")            # el ítem coincide con un tipo_doc (caso usual)
        elif item_tds:
            preselect = item_tds[0]              # ítem con varios tipos → el principal
        else:
            preselect = ""                       # ej. "coherencia": sin preselección
        pendientes = (o.get("subsanacion") or {}).get("adjuntos_pendientes", [])
        grupos[nombre]["obs"].append({"obs": o, "sub": _estado_subsanacion(o),
                                      "tipo_docs": opciones_td, "preselect": preselect,
                                      "adjuntos_pendientes": pendientes})
    grupos_lista = [{"nombre": n, "key": g["key"], "obs": g["obs"]}
                    for n, g in sorted(grupos.items(), key=lambda kv: orden_item.get(kv[0], 999))]

    estados = [_estado_subsanacion(o)["estado"] for o in aprobadas]
    total = len(aprobadas)
    n_resueltas = estados.count("resuelta")
    n_no_resueltas = estados.count("no_resuelta")
    n_esperando = estados.count("esperando")
    todas_resueltas = total > 0 and n_resueltas == total

    return templates.TemplateResponse("respuestas.html", {
        "request": request, "user": user, "proyecto": proyecto,
        "costo_api": _costo_para_vista(proyecto),
        "grupos": grupos_lista, "total": total, "n_resueltas": n_resueltas,
        "n_no_resueltas": n_no_resueltas, "n_esperando": n_esperando,
        "todas_resueltas": todas_resueltas,
    })


@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/responder")
async def registrar_respuesta_subsanacion(
    request: Request, proyecto_id: str, obs_id: str,
    respuesta: str = Form(...), evaluacion: str = Form(...), comentario: str = Form(""),
    ia_recomendacion: str = Form(""), ia_fundamento: str = Form("")
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    obs = next((o for o in proyecto.get("observaciones", []) if o["id"] == obs_id), None)
    if not obs or obs.get("estado") != "aprobada":
        raise HTTPException(status_code=404, detail="Observación no válida para subsanación")
    if evaluacion not in ("resuelta", "reiterada"):
        raise HTTPException(status_code=400, detail="Evaluación no válida")

    sub = _estado_subsanacion(obs)
    if sub["puede_responder"] and respuesta.strip():
        obs.setdefault("subsanacion", {}).setdefault("rondas", [])
        ronda = {
            "ronda": sub["ronda_actual"],
            "respuesta": respuesta.strip(),
            "evaluacion": evaluacion,
            "comentario": comentario.strip(),
            "fecha": _ahora().isoformat(),
            "por": user["nombre"],
        }
        # Si el revisor consultó a la IA antes de decidir, se guarda su recomendación como
        # registro (queda visible en el hilo, junto al veredicto humano).
        if ia_recomendacion in ("resuelta", "no_resuelta"):
            ronda["ia_recomendacion"] = ia_recomendacion
            ronda["ia_fundamento"] = (ia_fundamento or "").strip()
        # Documentos de respaldo que el consultor entregó junto a esta respuesta (subidos antes
        # vía adjuntar-respaldo) — pasan de "pendientes" a formar parte de esta ronda.
        pendientes = obs["subsanacion"].get("adjuntos_pendientes", [])
        if pendientes:
            ronda["adjuntos"] = pendientes
            obs["subsanacion"]["adjuntos_pendientes"] = []
        obs["subsanacion"]["rondas"].append(ronda)
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/respuestas#obs-{obs_id}", status_code=302)


@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/evaluar-respuesta")
async def evaluar_respuesta_ia(request: Request, proyecto_id: str, obs_id: str):
    """AJAX: la IA evalúa si la respuesta del consultor (aún sin guardar) resuelve la
    observación, usando todos los antecedentes del proyecto. Devuelve JSON con recomendación +
    fundamento — es un apoyo, la decisión final la toma el revisor."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "sesion"}, status_code=401)
    try:
        proyecto = db.get_proyecto(proyecto_id)
        if not proyecto:
            return JSONResponse({"ok": False, "error": "proyecto no encontrado"}, status_code=404)
        obs = next((o for o in proyecto.get("observaciones", []) if o["id"] == obs_id), None)
        if not obs:
            return JSONResponse({"ok": False, "error": "observación no encontrada"}, status_code=404)
        form = await request.form()
        respuesta = (form.get("respuesta") or "").strip()
        if not respuesta:
            return JSONResponse({"ok": False, "error": "vacio"}, status_code=400)

        concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
        concurso = db.get_concurso(concurso_id)
        bases_texto = concurso.get("bases_texto", "") if concurso else ""

        # Incluir siempre los adjuntos que el consultor entregó con esta respuesta, aunque su
        # tipo_doc no sea del ítem observado.
        pendientes = (obs.get("subsanacion") or {}).get("adjuntos_pendientes", [])
        doc_ids_extra = [a.get("id") for a in pendientes]

        documentos_con_texto = await _con_texto(proyecto_id, proyecto.get("documentos", []))

        # Cuántas observaciones aprobadas tiene ESTE ítem: los antecedentes que se le mandan a la
        # IA son los mismos para todas ellas, así que con varias conviene cachearlos en vez de
        # pagarlos frescos una vez por observación (ver `evaluar_respuesta_subsanacion`).
        item_obs = obs.get("item", "")
        n_obs_item = sum(1 for o in proyecto.get("observaciones", [])
                         if o.get("estado") == "aprobada" and o.get("item", "") == item_obs)

        acc_costo = iniciar_costo()
        resultado = await evaluar_respuesta_subsanacion(
            observacion_texto=obs.get("texto", ""),
            referencia=obs.get("referencia_normativa", ""),
            respuesta_consultor=respuesta, item_key=item_obs,
            documentos=documentos_con_texto, resumen=proyecto.get("resumen", {}),
            bases_texto=bases_texto, concurso_id=concurso_id, doc_ids_extra=doc_ids_extra,
            n_obs_item=n_obs_item,
        )

        # Esta ruta no modifica el proyecto (solo devuelve la recomendación por AJAX), pero el
        # costo sí hay que persistirlo. Se relee FRESCO antes de guardar porque la evaluación
        # tarda decenas de segundos y en ese lapso un análisis en segundo plano pudo haber
        # escrito sus observaciones — guardar la copia vieja las borraría.
        proyecto_fresco = db.get_proyecto(proyecto_id)
        if proyecto_fresco:
            _registrar_costo(proyecto_fresco, "subsanacion", acc_costo)
            db.save_proyecto(proyecto_fresco)

        return JSONResponse({"ok": True, "recomendacion": resultado.get("recomendacion", ""),
                             "fundamento": resultado.get("fundamento", "")})
    except Exception as e:
        import traceback
        print(f"❌ ERROR en evaluar-respuesta {obs_id}: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/adjuntar-respaldo")
async def adjuntar_respaldo_subsanacion(
    request: Request, proyecto_id: str, obs_id: str,
    archivo: UploadFile = File(...), tipo_doc: str = Form(...)
):
    """AJAX: sube un documento de respaldo que el consultor entregó con su respuesta. El archivo
    se agrega como documento del proyecto (canónico, con extracción + respaldo en Postgres, igual
    que la página Documentos) y se enlaza a la observación como adjunto PENDIENTE de la respuesta
    en curso — así la IA lo ve al evaluar y queda registrado en la ronda al decidir."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "sesion"}, status_code=401)
    try:
        proyecto = db.get_proyecto(proyecto_id)
        if not proyecto:
            return JSONResponse({"ok": False, "error": "proyecto no encontrado"}, status_code=404)
        obs = next((o for o in proyecto.get("observaciones", []) if o["id"] == obs_id), None)
        if not obs:
            return JSONResponse({"ok": False, "error": "observación no encontrada"}, status_code=404)
        if not archivo.filename:
            return JSONResponse({"ok": False, "error": "sin archivo"}, status_code=400)

        ext = Path(archivo.filename).suffix.lower()
        doc_id = str(uuid.uuid4())[:8]
        filename = f"{doc_id}{ext}"
        filepath = UPLOAD_DIR / proyecto_id / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        content = await archivo.read()
        with open(filepath, "wb") as f:
            f.write(content)
        db.guardar_archivo(proyecto_id, doc_id, filename, content)
        texto = await asyncio.to_thread(extract_text, str(filepath), ext)
        texto_guardado = truncar_texto_guardado(texto)
        label = TIPO_DOC_LABELS.get(tipo_doc, tipo_doc)
        doc = {
            "id": doc_id, "nombre_original": archivo.filename, "filename": filename,
            "tipo_doc": tipo_doc, "tipo_doc_label": label,
            "fecha_subida": _ahora().isoformat(),
            "texto_len": _texto_len(texto_guardado),
            "analizado": False, "origen_subsanacion": obs_id,
        }
        proyecto.setdefault("documentos", []).append(doc)
        obs.setdefault("subsanacion", {}).setdefault("adjuntos_pendientes", []).append(
            {"id": doc_id, "nombre": archivo.filename, "tipo_label": label})
        db.save_proyecto(proyecto)
        await asyncio.to_thread(db.set_texto_documento, proyecto_id, doc_id, texto_guardado)
        return JSONResponse({"ok": True, "doc": {"id": doc_id, "nombre": archivo.filename,
                                                 "tipo_label": label}})
    except Exception as e:
        import traceback
        print(f"❌ ERROR en adjuntar-respaldo {obs_id}: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/subsanacion/deshacer")
async def deshacer_respuesta_subsanacion(request: Request, proyecto_id: str, obs_id: str):
    """Borra la ÚLTIMA ronda registrada (por si el revisor se equivocó al evaluar). Solo quita
    el último registro, conserva los anteriores."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    obs = next((o for o in proyecto.get("observaciones", []) if o["id"] == obs_id), None)
    if obs and (obs.get("subsanacion") or {}).get("rondas"):
        obs["subsanacion"]["rondas"].pop()
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/respuestas#obs-{obs_id}", status_code=302)


@app.post("/proyecto/{proyecto_id}/aprobar-tecnicamente")
async def aprobar_tecnicamente(request: Request, proyecto_id: str):
    """Marca el proyecto 'Aprobado Técnicamente' — solo si TODAS las observaciones aprobadas
    (enviadas al consultor) quedaron resueltas. Si falta alguna, no hace nada."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    aprobadas = [o for o in proyecto.get("observaciones", []) if o.get("estado") == "aprobada"]
    todas_resueltas = bool(aprobadas) and all(
        _estado_subsanacion(o)["estado"] == "resuelta" for o in aprobadas)
    if todas_resueltas:
        proyecto["estado"] = "Aprobado Técnicamente"
        proyecto["fecha_estado"] = _ahora().isoformat()
        proyecto["estado_por"] = user["nombre"]
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/respuestas", status_code=302)


# ─── Administración de concursos ─────────────────────────────────────────────

@app.get("/admin/concursos", response_class=HTMLResponse)
async def admin_concursos(request: Request):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concursos = db.get_all_concursos()
    msg_ok  = request.query_params.get("ok")
    msg_err = request.query_params.get("error")
    return templates.TemplateResponse("admin_concursos.html", {
        "request": request, "user": user, "concursos": concursos,
        "msg_ok": msg_ok, "msg_err": msg_err
    })


@app.post("/admin/concursos/crear")
async def admin_crear_concurso(
    request: Request,
    concurso_id: str = Form(...),
    nombre: str = Form(...)
):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso_id = concurso_id.strip()
    if db.get_concurso(concurso_id):
        return RedirectResponse(url="/admin/concursos?error=existe", status_code=302)
    db.save_concurso({
        "id": concurso_id,
        "nombre": nombre.strip(),
        "bases_texto": "",
        "fecha_creacion": _ahora().isoformat(),
        "feedback": []
    })
    return RedirectResponse(url=f"/admin/concursos/{concurso_id}?ok=creado", status_code=302)


@app.get("/admin/concursos/{concurso_id}", response_class=HTMLResponse)
async def admin_concurso_detalle(request: Request, concurso_id: str):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    # Si llega desde el banner con ?crear=1 y el concurso no existe, lo creamos
    if not concurso and request.query_params.get("crear") == "1":
        concurso = {
            "id": concurso_id,
            "nombre": f"Concurso {concurso_id}",
            "bases_texto": "",
            "fecha_creacion": _ahora().isoformat(),
            "feedback": []
        }
        db.save_concurso(concurso)
        msg_ok = "creado"
    elif not concurso:
        raise HTTPException(status_code=404, detail="Concurso no encontrado")
    else:
        msg_ok = request.query_params.get("ok")
    # Resumen de criterios aprendidos (para mostrarlos y saber qué se puede consolidar)
    criterios = concurso.get("criterios_aprendidos", {})
    criterios_lista = []
    for item_key in ITEMS_ORDEN:
        if criterios.get("item_" + item_key):
            criterios_lista.append({"nombre": "Ítem SEP: " + ITEMS_SEP[item_key]["nombre"],
                                    "texto": criterios["item_" + item_key]})
    # Archivos guardados en la base para los proyectos de este concurso (para poder
    # "dar por terminado" el concurso y liberar ese espacio sin perder el análisis ya hecho).
    proyectos_concurso = [p for p in db.get_proyectos_ligero(["id", "codigo_sep"])
                          if _extraer_concurso_id(p.get("codigo_sep", "")) == concurso_id]
    resumen_archivos = db.resumen_archivos([p["id"] for p in proyectos_concurso])
    # Criterios PUNTUALES de este concurso (jul-2026): a diferencia de los criterios de énfasis
    # GENERALES (ahora permanentes, cruzan todos los concursos — se editan en /admin/aprendizaje),
    # este campo quedó para excepciones específicas de las bases de ESTE concurso en particular
    # (ej. "no se acepta agua NO inscrita") — no aplica a todo concurso ni a todo ítem, ver
    # CLAUDE.md. Ambos se combinan al analizar (_criterios_enfasis_combinados()).
    enfasis_guardados = concurso.get("criterios_enfasis", {})
    grupos_enfasis = []
    for item_key in ITEMS_ORDEN:
        grupos_enfasis.append({
            "key": "item_" + item_key, "tipo": "Ítem SEP",
            "nombre": ITEMS_SEP[item_key]["nombre"],
            "texto": enfasis_guardados.get("item_" + item_key, ""),
        })
    # Documentos obligatorios de admisibilidad: checklist de TODOS los tipos de documento
    # (orden del SEP), marcados según lo último guardado (extracción IA sin revisar, o ya
    # confirmado por el revisor — ver documentos_obligatorios_revisado).
    obligatorios_actuales = set(concurso.get("documentos_obligatorios", []))
    checklist_doc_obligatorios = [
        {"key": k, "label": TIPO_DOC_LABELS_OBLIGATORIOS[k], "checked": k in obligatorios_actuales}
        for k in sorted(TIPO_DOC_LABELS_OBLIGATORIOS, key=lambda k: TIPO_DOC_ORDEN.get(k, 999))
    ]
    return templates.TemplateResponse("admin_concurso_detalle.html", {
        "request": request, "user": user, "concurso": concurso, "msg_ok": msg_ok,
        "n_feedback": len(concurso.get("feedback", [])),
        "criterios_lista": criterios_lista,
        "criterios_fecha": concurso.get("criterios_fecha", ""),
        "n_proyectos_concurso": len(proyectos_concurso),
        "resumen_archivos": resumen_archivos,
        "grupos_enfasis": grupos_enfasis,
        "checklist_doc_obligatorios": checklist_doc_obligatorios,
    })


@app.post("/admin/concursos/{concurso_id}/criterios-enfasis")
async def guardar_criterios_enfasis(request: Request, concurso_id: str):
    """Guarda los criterios PUNTUALES de este concurso en particular — excepciones puntuales
    a las bases de ESTE concurso (ej. "no se acepta agua NO inscrita"), no la regla general
    (que ahora es permanente/global, ver db.get_criterios_item() y /admin/aprendizaje). Nunca
    se sobrescribe automáticamente — es supervisión directa del revisor."""
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    if not concurso:
        raise HTTPException(status_code=404)

    form = await request.form()
    criterios_enfasis = dict(concurso.get("criterios_enfasis", {}))
    for campo, valor in form.items():
        if not campo.startswith("enfasis__"):
            continue
        grupo_key = campo[len("enfasis__"):]
        texto = (valor or "").strip()
        if texto:
            criterios_enfasis[grupo_key] = texto
        else:
            criterios_enfasis.pop(grupo_key, None)
    concurso["criterios_enfasis"] = criterios_enfasis
    db.save_concurso(concurso)
    return RedirectResponse(url=f"/admin/concursos/{concurso_id}?ok=enfasis_guardado", status_code=302)


# ─── Documentos obligatorios (admisibilidad según las bases) ─────────────────
# Las bases señalan qué documentos son obligatorios — su no presentación deja el proyecto como
# NO ADMITIDO — pero no siempre están en el mismo lugar del texto. La IA los extrae UNA VEZ POR
# CONCURSO (no por proyecto), pero el resultado solo se usa para advertir en los proyectos
# después de que el revisor lo revisa y guarda explícitamente ("documentos_obligatorios_revisado").

@app.post("/admin/concursos/{concurso_id}/documentos-obligatorios/extraer")
async def extraer_doc_obligatorios(request: Request, concurso_id: str):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    if not concurso:
        raise HTTPException(status_code=404)
    if not concurso.get("bases_texto", "").strip():
        return RedirectResponse(url=f"/admin/concursos/{concurso_id}?error=sin_bases", status_code=302)

    resultado = await extraer_documentos_obligatorios(concurso["bases_texto"], TIPO_DOC_LABELS_OBLIGATORIOS)
    concurso["documentos_obligatorios"] = resultado["obligatorios"]
    concurso["documentos_obligatorios_referencia"] = resultado["referencia"]
    concurso["documentos_obligatorios_revisado"] = False   # requiere VB explícito antes de advertir
    db.save_concurso(concurso)
    return RedirectResponse(
        url=f"/admin/concursos/{concurso_id}?ok=doc_obl_extraidos_{len(resultado['obligatorios'])}#doc-obligatorios",
        status_code=302)


@app.post("/admin/concursos/{concurso_id}/documentos-obligatorios/guardar")
async def guardar_doc_obligatorios(request: Request, concurso_id: str):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    if not concurso:
        raise HTTPException(status_code=404)

    form = await request.form()
    seleccionados = [k for k in TIPO_DOC_LABELS_OBLIGATORIOS if form.get(f"doc__{k}") == "on"]
    concurso["documentos_obligatorios"] = seleccionados
    concurso["documentos_obligatorios_referencia"] = (form.get("referencia") or "").strip()
    concurso["documentos_obligatorios_revisado"] = True
    concurso["documentos_obligatorios_fecha"] = _ahora().isoformat()
    concurso["documentos_obligatorios_por"] = user["nombre"]
    db.save_concurso(concurso)
    return RedirectResponse(
        url=f"/admin/concursos/{concurso_id}?ok=doc_obl_guardado#doc-obligatorios", status_code=302)


@app.post("/admin/concursos/{concurso_id}/consolidar")
async def consolidar_concurso(request: Request, concurso_id: str):
    """Destila el feedback acumulado en criterios aprendidos por ítem — solo de ESTE concurso
    (a diferencia de los perfiles de consultor, que cruzan concursos y se consolidan aparte
    desde /admin/aprendizaje, ver consolidar_consultores())."""
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    if not concurso:
        raise HTTPException(status_code=404)

    feedback = concurso.get("feedback", [])
    criterios = dict(concurso.get("criterios_aprendidos", {}))
    n = 0
    try:
        for item_key in ITEMS_ORDEN:
            texto = await consolidar_aprendizaje(feedback, "item_" + item_key, ITEMS_SEP[item_key]["nombre"])
            if texto:
                criterios["item_" + item_key] = texto
                n += 1
    except Exception as e:
        import traceback
        print(f"❌ ERROR en consolidar_concurso {concurso_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al consolidar aprendizaje: {str(e)}")

    concurso["criterios_aprendidos"] = criterios
    concurso["criterios_fecha"] = _ahora().isoformat()
    db.save_concurso(concurso)
    return RedirectResponse(url=f"/admin/concursos/{concurso_id}?ok=consolidado_{n}", status_code=302)


@app.post("/admin/concursos/{concurso_id}/bases")
async def admin_guardar_bases(
    request: Request,
    concurso_id: str,
    bases_texto: str = Form(""),
    nombre: str = Form("")
):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    if not concurso:
        raise HTTPException(status_code=404)
    if nombre.strip():
        concurso["nombre"] = nombre.strip()
    concurso["bases_texto"] = bases_texto.strip()
    concurso["fecha_actualizacion"] = _ahora().isoformat()
    db.save_concurso(concurso)
    return RedirectResponse(url=f"/admin/concursos/{concurso_id}?ok=guardado", status_code=302)


@app.post("/admin/concursos/{concurso_id}/bases-pdf")
async def admin_subir_bases_pdf(
    request: Request,
    concurso_id: str,
    archivo: UploadFile = File(...),
    nombre: str = Form("")
):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    if not concurso:
        raise HTTPException(status_code=404)

    ext = Path(archivo.filename).suffix.lower()
    if ext not in (".pdf", ".doc", ".docx"):
        return RedirectResponse(url=f"/admin/concursos/{concurso_id}?error=formato", status_code=302)

    # Guardar temporalmente
    tmp_path = UPLOAD_DIR / f"_bases_{concurso_id}{ext}"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    content = await archivo.read()
    with open(tmp_path, "wb") as f:
        f.write(content)

    # Extraer texto (thread aparte — las bases suelen ser un PDF largo)
    texto = await asyncio.to_thread(extract_text, str(tmp_path), ext)
    tmp_path.unlink(missing_ok=True)

    if texto.strip() == "__PDF_ESCANEADO__":
        return RedirectResponse(url=f"/admin/concursos/{concurso_id}?error=escaneado", status_code=302)

    if nombre.strip():
        concurso["nombre"] = nombre.strip()
    concurso["bases_texto"] = texto.strip()
    concurso["fecha_actualizacion"] = _ahora().isoformat()
    db.save_concurso(concurso)
    return RedirectResponse(url=f"/admin/concursos/{concurso_id}?ok=pdf_cargado", status_code=302)


@app.post("/admin/concursos/{concurso_id}/liberar-archivos")
async def liberar_archivos_concurso(request: Request, concurso_id: str):
    """Dar por terminado un concurso: borra los archivos físicos guardados (disco + base de
    datos) de todos sus proyectos, para liberar espacio. NO toca texto_extraido, observaciones
    ni el resto del análisis ya hecho — solo el archivo original, igual que si se hubiera
    perdido tras un redeploy (ya manejado en el resto de la app: se puede resubir si hiciera
    falta reanalizar con visión)."""
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    concurso = db.get_concurso(concurso_id)
    if not concurso:
        raise HTTPException(status_code=404)

    proyecto_ids = [p["id"] for p in db.get_proyectos_ligero(["id", "codigo_sep"])
                    if _extraer_concurso_id(p.get("codigo_sep", "")) == concurso_id]
    db.eliminar_archivos_proyectos(proyecto_ids)
    import shutil
    for pid in proyecto_ids:
        carpeta = UPLOAD_DIR / pid
        if carpeta.exists():
            shutil.rmtree(carpeta, ignore_errors=True)

    concurso["archivos_liberados"] = True
    concurso["fecha_archivos_liberados"] = _ahora().isoformat()
    db.save_concurso(concurso)
    return RedirectResponse(url=f"/admin/concursos/{concurso_id}?ok=archivos_liberados", status_code=302)


@app.post("/admin/concursos/{concurso_id}/eliminar")
async def admin_eliminar_concurso(request: Request, concurso_id: str):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    db.delete_concurso(concurso_id)
    return RedirectResponse(url="/admin/concursos?ok=eliminado", status_code=302)


# ─── Precios referenciales PROMEDIO (tabla global, para verificar sobreprecios/subvaluación) ──
# NO es una tabla oficial certificada por la CNR — la CNR publica sus propios precios de
# referencia en un dashboard de Power BI que no expone datos ni API pública (solo
# visualización). El revisor arma y sube acá su propia tabla de precios PROMEDIO en Excel
# (columnas categoria/item/unidad/precio) y esa tabla se usa para comparar contra las partidas
# del presupuesto de cada proyecto (ver analyzer.py: _bloque_verificacion_precios). Reemplaza
# la tabla completa en cada subida — no es un feed en vivo, se actualiza a mano cuando cambien
# los precios de referencia.

@app.get("/admin/precios", response_class=HTMLResponse)
async def admin_precios(request: Request):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    precios = db.get_precios()
    items = precios.get("items", []) if precios else []
    categorias = {}
    for it in items:
        categorias.setdefault(it.get("categoria", ""), []).append(it)
    grupos = [{"nombre": nombre, "productos": sorted(lista, key=lambda x: x.get("item", ""))}
              for nombre, lista in sorted(categorias.items())]
    msg_ok  = request.query_params.get("ok")
    msg_err = request.query_params.get("error")
    return templates.TemplateResponse("admin_precios.html", {
        "request": request, "user": user, "precios": precios, "grupos": grupos,
        "n_items": len(items), "url_precios_cnr": URL_PRECIOS_CNR,
        "msg_ok": msg_ok, "msg_err": msg_err,
    })


@app.post("/admin/precios/subir")
async def admin_subir_precios(request: Request, archivo: UploadFile = File(...)):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")

    ext = Path(archivo.filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        return RedirectResponse(url="/admin/precios?error=formato", status_code=302)

    tmp_path = UPLOAD_DIR / "_precios_referenciales_tmp.xlsx"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    content = await archivo.read()
    with open(tmp_path, "wb") as f:
        f.write(content)

    try:
        items = parse_tabla_precios(str(tmp_path))
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        from urllib.parse import quote
        return RedirectResponse(url=f"/admin/precios?error={quote(str(e))}", status_code=302)
    tmp_path.unlink(missing_ok=True)

    if not items:
        return RedirectResponse(url="/admin/precios?error=vacio", status_code=302)

    db.save_precios({
        "items": items,
        "fecha_actualizado": _ahora().isoformat(),
        "actualizado_por": user["nombre"],
        "nombre_archivo": archivo.filename,
    })
    return RedirectResponse(url=f"/admin/precios?ok=cargado_{len(items)}", status_code=302)


@app.post("/admin/precios/eliminar")
async def admin_eliminar_precios(request: Request):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    db.save_precios({})
    return RedirectResponse(url="/admin/precios?ok=eliminado", status_code=302)


# ─── Aprendizaje (página global, jul-2026) ────────────────────────────────────
# Reúne los dos mecanismos de aprendizaje que CRUZAN concursos (antes vivían dentro de la
# página de un concurso específico, lo que confundía — ver CLAUDE.md):
# 1. Criterios de énfasis por ítem — PERMANENTES, los escribe el revisor a mano, se inyectan
#    siempre en el prompt de ese ítem sin importar el concurso. Las excepciones puntuales de
#    un concurso en particular (ej. "no se acepta agua NO inscrita" en las bases de UN
#    concurso) se siguen agregando desde la página de ESE concurso — ver
#    guardar_criterios_enfasis() más arriba, ahora reetiquetado como "puntuales".
# 2. Aprendizaje por consultor — destilado del feedback (aprobar/descartar), cruza proyectos
#    y concursos por diseño desde que existe (ver database.py: consultores, keyed por nombre).

@app.get("/admin/aprendizaje", response_class=HTMLResponse)
async def admin_aprendizaje(request: Request):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    criterios_guardados = db.get_criterios_item().get("criterios", {})
    grupos_enfasis = [
        {"key": "item_" + item_key, "nombre": ITEMS_SEP[item_key]["nombre"],
         "texto": criterios_guardados.get("item_" + item_key, "")}
        for item_key in ITEMS_ORDEN
    ]
    consultores_info = []
    for c in db.get_all_consultores():
        n_fb = len(c.get("feedback", []))
        if n_fb > 0:
            consultores_info.append({
                "nombre": c.get("nombre", ""), "n_feedback": n_fb,
                "perfil": c.get("perfil", ""), "perfil_fecha": c.get("perfil_fecha", ""),
            })
    consultores_info.sort(key=lambda c: c["nombre"])
    msg_ok = request.query_params.get("ok")
    return templates.TemplateResponse("admin_aprendizaje.html", {
        "request": request, "user": user, "grupos_enfasis": grupos_enfasis,
        "criterios_fecha": db.get_criterios_item().get("fecha_actualizado", ""),
        "consultores_info": consultores_info, "msg_ok": msg_ok,
    })


@app.post("/admin/aprendizaje/criterios-item")
async def guardar_criterios_item(request: Request):
    """Guarda los criterios de énfasis PERMANENTES por ítem (globales, cruzan todos los
    concursos) — mismo mecanismo que antes vivía por concurso, ver
    db.migrar_criterios_enfasis() para la migración de lo que ya existía."""
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    form = await request.form()
    guardado = db.get_criterios_item()
    criterios = dict(guardado.get("criterios", {}))
    for campo, valor in form.items():
        if not campo.startswith("enfasis__"):
            continue
        grupo_key = campo[len("enfasis__"):]
        texto = (valor or "").strip()
        if texto:
            criterios[grupo_key] = texto
        else:
            criterios.pop(grupo_key, None)
    db.save_criterios_item({
        "criterios": criterios,
        "fecha_actualizado": _ahora().isoformat(),
        "actualizado_por": user["nombre"],
    })
    return RedirectResponse(url="/admin/aprendizaje?ok=enfasis_guardado", status_code=302)


@app.post("/admin/aprendizaje/consolidar-consultores")
async def consolidar_consultores(request: Request):
    """Destila el perfil de TODOS los consultores con historial (cruza proyectos/concursos por
    diseño) — separado de "Consolidar aprendizaje" de cada concurso, que ahora solo destila
    los criterios aprendidos por ítem DE ESE concurso."""
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    n = 0
    try:
        for c in db.get_all_consultores():
            perfil = await consolidar_perfil_consultor(c.get("feedback", []), c.get("nombre", ""))
            if perfil:
                c["perfil"] = perfil
                c["perfil_fecha"] = _ahora().isoformat()
                db.save_consultor(c)
                n += 1
    except Exception as e:
        import traceback
        print(f"❌ ERROR en consolidar_consultores: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al consolidar aprendizaje: {str(e)}")
    return RedirectResponse(url=f"/admin/aprendizaje?ok=consolidado_{n}", status_code=302)


# ─── Administración de usuarios ──────────────────────────────────────────────

@app.get("/admin/usuarios", response_class=HTMLResponse)
async def admin_usuarios(request: Request):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    usuarios = db.get_all_users()
    msg_ok  = request.query_params.get("ok")
    msg_err = request.query_params.get("error")
    return templates.TemplateResponse("admin_usuarios.html", {
        "request": request, "user": user, "usuarios": usuarios,
        "msg_ok": msg_ok, "msg_err": msg_err
    })


@app.post("/admin/usuarios/crear")
async def admin_crear_usuario(
    request: Request,
    username: str = Form(...),
    nombre: str = Form(...),
    password: str = Form(...),
    rol: str = Form(...)
):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    if db.get_user(username):
        return RedirectResponse(url="/admin/usuarios?error=existe", status_code=302)
    db.create_user(username, password, nombre, rol)
    return RedirectResponse(url="/admin/usuarios?ok=creado", status_code=302)


@app.post("/admin/usuarios/{username}/eliminar")
async def admin_eliminar_usuario(request: Request, username: str):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    if username == user["username"]:
        return RedirectResponse(url="/admin/usuarios?error=self", status_code=302)
    db.delete_user(username)
    return RedirectResponse(url="/admin/usuarios?ok=eliminado", status_code=302)


# ─── Mi cuenta (cambio de contraseña) ────────────────────────────────────────

@app.get("/mi-cuenta", response_class=HTMLResponse)
async def mi_cuenta_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("mi_cuenta.html", {"request": request, "user": user})


@app.post("/mi-cuenta", response_class=HTMLResponse)
async def cambiar_password(
    request: Request,
    password_actual: str = Form(...),
    password_nuevo: str = Form(...),
    password_confirmar: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    db_user = db.get_user(user["username"])

    def _render(error=None, ok=False):
        return templates.TemplateResponse("mi_cuenta.html", {
            "request": request, "user": user, "error_pass": error, "ok_pass": ok
        })

    if not await asyncio.to_thread(verify_password, password_actual, db_user["password_hash"]):
        return _render("Contraseña actual incorrecta.")
    if password_nuevo != password_confirmar:
        return _render("Las contraseñas nuevas no coinciden.")
    if len(password_nuevo) < 6:
        return _render("La contraseña debe tener al menos 6 caracteres.")
    db.update_password(user["username"], password_nuevo)
    return _render(ok=True)


@app.post("/mi-cuenta/nombre", response_class=HTMLResponse)
async def cambiar_nombre(request: Request, nombre_nuevo: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    nombre_nuevo = nombre_nuevo.strip()

    def _render(error=None, ok=False, user_actual=None):
        return templates.TemplateResponse("mi_cuenta.html", {
            "request": request, "user": user_actual or user, "error_nombre": error, "ok_nombre": ok
        })

    if not nombre_nuevo:
        return _render("El nombre no puede quedar vacío.")
    db.update_nombre(user["username"], nombre_nuevo)
    # El nombre viaja en el JWT de la sesión (fijado al hacer login) — sin reemitir la cookie,
    # el cambio no se vería reflejado en la app (nav, "Mi cuenta", registros nuevos como
    # "validado_por"/"agregada_por") hasta el próximo login. Se reemite con el mismo patrón que
    # usa login() (mismo max_age de 8 h, no reinicia el conteo de la sesión desde cero salvo por
    # la duración total).
    user_actualizado = {**user, "nombre": nombre_nuevo}
    token = create_token({"username": user["username"], "nombre": nombre_nuevo, "rol": user["rol"]})
    response = _render(ok=True, user_actual=user_actualizado)
    response.set_cookie("session", token, httponly=True, max_age=28800)
    return response


# ─── Inicio ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Crear usuario admin por defecto si no existe
    if not db.get_user("admin"):
        db.create_user("admin", "admin123", "Administrador CNR", "admin")
        print("✅ Usuario creado: admin / admin123")
        print("   ⚠️  Cambia la contraseña después del primer ingreso")

    print("\n🌊 Revisor CNR iniciado")
    print("   Abre tu navegador en: http://localhost:8000")
    print("   Presiona Ctrl+C para detener\n")
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0" if os.getenv("RAILWAY_ENVIRONMENT") else "127.0.0.1"
    uvicorn.run(app, host=host, port=port)
