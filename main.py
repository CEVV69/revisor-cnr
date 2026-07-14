"""
Revisor CNR - Aplicación de revisión de proyectos de riego Ley 18.450
"""
import os
import re
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
import uvicorn
from dotenv import load_dotenv

from auth import create_token, verify_token, hash_password, verify_password
from extractor import extract_text, extract_zip, parse_tabla_precios, truncar_texto_guardado
from analyzer import (consultar_expediente, analizar_item, chatear_item, resumir_proyecto,
                      consolidar_aprendizaje, consolidar_perfil_consultor, ITEMS_SEP,
                      ITEMS_ORDEN, RESUMEN_SECCIONES, RESUMEN_KEYS, _documentos_para_verificacion,
                      MIN_CHARS_TEXTO, _extraer_datos_hidraulicos, _extraer_datos_agronomicos,
                      _extraer_datos_fv, extraer_documentos_obligatorios)
import calculos_riego
import geo

# Dashboard público de la CNR con precios referenciales de materiales y equipos — el revisor
# lo consulta manualmente desde un botón en los ítems de Presupuesto (ver proyecto.html). La
# app NO puede leer este link en vivo (Power BI no expone datos ni API pública) — para la
# verificación automática, el revisor sube su propia tabla de precios PROMEDIO (no una copia
# oficial de este dashboard) en Excel desde /admin/precios.
URL_PRECIOS_CNR = ("https://app.powerbi.com/view?r=eyJrIjoiZDJhMjgwM2QtNGUyYy00YzEyLWEyZjctND"
                   "hjN2E0NjFlOTBiIiwidCI6IjBmOWNhOGViLWI4MjctNGEyMS1iNmNkLTAxNmRlODNkYmRlNyIs"
                   "ImMiOjR9")
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


def _doc_disponible_analisis(d: dict, permite_vision: bool = True) -> bool:
    """Un documento está disponible para el análisis si tiene texto usable, o si es un PDF
    escaneado/plano cuyo archivo físico existe (disco o base) y el grupo admite visión (todos
    menos Coherencia global). Debe reflejar exactamente lo que usa `_analizar_grupo()` en
    analyzer.py, para que el contador de documentos de cada eje/ítem no subestime lo que
    realmente se analiza."""
    texto = d.get("texto_extraido", "").strip()
    if texto not in ("", "__PDF_ESCANEADO__"):
        return True
    if not permite_vision:
        return False
    return bool(d.get("archivo_presente")) and d.get("filename", "").lower().endswith(".pdf")


def _restaurar_archivos_necesarios(proyecto_id: str, documentos: list):
    """Si el archivo físico de un documento que necesita visión (escaneado/con poco texto) se
    perdió tras un redeploy de Railway, lo recupera desde PostgreSQL antes de analizar — así
    no hay que resubirlo a mano mientras siga guardado en la base."""
    carpeta = UPLOAD_DIR / proyecto_id
    for d in documentos:
        texto = d.get("texto_extraido", "").strip()
        necesita_vision = (texto == "__PDF_ESCANEADO__" or len(texto) < MIN_CHARS_TEXTO)
        if not necesita_vision:
            continue
        filepath = carpeta / d.get("filename", "")
        if filepath.exists():
            continue
        contenido = db.obtener_archivo(proyecto_id, d["id"])
        if contenido:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(contenido)


def _volver_a(request: Request, proyecto_id: str, defecto: str = "resumen") -> str:
    """URL de la página del proyecto desde la que se envió el formulario (según Referer),
    para volver a ella tras acciones del encabezado (estado). Si no se puede, usa `defecto`."""
    ref = request.headers.get("referer", "") or ""
    base = f"/proyecto/{proyecto_id}/"
    for pag in ("resumen", "documentos", "items", "calculos"):
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


templates.env.filters["fecha"] = _fmt_fecha
templates.env.filters["fecha_hora"] = lambda s: _fmt_fecha(s, con_hora=True)


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

    if not db.get_user("admin"):
        db.create_user("admin", "admin123", "Administrador CNR", "admin")
        print("✅ Usuario admin creado: admin / admin123")
    else:
        print("✅ Usuario admin existe — datos persistidos correctamente")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session")
    if not token:
        return None
    return verify_token(token)


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


# ─── Debug temporal ──────────────────────────────────────────────────────────

def _leer_env_proc1() -> dict:
    """Lee variables del proceso init del contenedor (workaround Railway V2)."""
    try:
        with open("/proc/1/environ", "rb") as f:
            data = f.read()
        return dict(
            item.split(b"=", 1)
            for item in data.split(b"\x00")
            if b"=" in item
        )
    except Exception:
        return {}


@app.get("/debug-env")
async def debug_env(request: Request):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return {"error": "forbidden"}
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    proc1 = _leer_env_proc1()
    key_proc1 = proc1.get(b"ANTHROPIC_API_KEY", b"").decode("utf-8", errors="replace")
    return {
        "os_environ_tiene_key": bool(key),
        "proc1_tiene_key": bool(key_proc1),
        "proc1_primeros_chars": key_proc1[:10] if key_proc1 else "(vacio)",
        "proc1_vars": sorted(k.decode("utf-8", errors="replace") for k in proc1.keys()),
    }


# ─── Rutas de autenticación ───────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = db.get_user(username)
    if not user or not verify_password(password, user["password_hash"]):
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
        return RedirectResponse(url="/login")
    proyectos = db.get_proyectos(user["username"])
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
        return RedirectResponse(url="/login")
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
        return RedirectResponse(url="/login")

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
        return RedirectResponse(url="/login")
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
    faltan_obligatorios = []
    if concurso and concurso.get("documentos_obligatorios_revisado") and concurso.get("documentos_obligatorios"):
        tipos_presentes = {d.get("tipo_doc") for d in proyecto["documentos"]}
        faltan_obligatorios = [
            {"key": k, "label": TIPO_DOC_LABELS.get(k, k)}
            for k in concurso["documentos_obligatorios"] if k not in tipos_presentes
        ]
    # Estado del archivo físico (se pierde tras cada re-despliegue de Railway).
    # Solo importa re-subir los que necesitan visión (escaneados/planos con poco texto);
    # el resto ya tiene su texto extraído guardado y no requiere el archivo físico.
    carpeta_proyecto = UPLOAD_DIR / proyecto_id
    ids_guardados_db = db.ids_con_archivo(proyecto_id)
    for doc in proyecto["documentos"]:
        texto = doc.get("texto_extraido", "").strip()
        doc["necesita_archivo"] = (texto == "__PDF_ESCANEADO__" or len(texto) < MIN_CHARS_TEXTO)
        doc["archivo_presente"] = ((carpeta_proyecto / doc.get("filename", "")).exists()
                                    or doc["id"] in ids_guardados_db)
    n_faltan_resubir = len([d for d in proyecto["documentos"]
                            if d["necesita_archivo"] and not d["archivo_presente"]])
    # Construir info de ítems SEP: cuántos documentos tiene disponible cada ítem y si ya se revisó
    items_revisados = proyecto.get("items_revisados", {})
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
        "n_faltan_resubir": n_faltan_resubir,
        "faltan_obligatorios": faltan_obligatorios,
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
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    estados_validos = {"En revisión", "Revisado", "Observado", "Rechazado"}
    if estado in estados_validos:
        proyecto["estado"] = estado
        proyecto["fecha_estado"] = _ahora().isoformat()
        proyecto["estado_por"] = user["nombre"]
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
        return RedirectResponse(url="/login")

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

    doc = {
        "id": doc_id,
        "nombre_original": archivo.filename,
        "filename": filename,
        "tipo_doc": tipo_doc,
        "tipo_doc_label": TIPO_DOC_LABELS.get(tipo_doc, tipo_doc),
        "fecha_subida": _ahora().isoformat(),
        "texto_extraido": truncar_texto_guardado(texto),
        "analizado": False
    }

    proyecto["documentos"].append(doc)
    db.save_proyecto(proyecto)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}/documentos", status_code=302)


# ─── Revisión por eje temático ────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/revisar-item/{item_key}")
async def revisar_item(request: Request, proyecto_id: str, item_key: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    if item_key not in ITEMS_SEP:
        raise HTTPException(status_code=404, detail="Ítem no válido")

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
    concurso = db.get_concurso(concurso_id)
    bases_texto       = concurso.get("bases_texto", "") if concurso else ""
    feedback_concurso = concurso.get("feedback", [])   if concurso else []
    criterios = (concurso.get("criterios_aprendidos", {}).get("item_" + item_key, "")
                 if concurso else "")
    enfasis = (concurso.get("criterios_enfasis", {}).get("item_" + item_key, "")
               if concurso else "")
    ckey, _ = _consultor_de_proyecto(proyecto)
    consultor = db.get_consultor(ckey) if ckey else None

    # Si el revisor ya validó/corrigió los datos en "Chequeo de Cálculos", se usan tal cual en
    # vez de volver a extraerlos automáticamente — la extracción puede fallar en algunos casos.
    verif_calc = proyecto.get("verificacion_calculos", {})

    def _validado(clave):
        v = verif_calc.get(clave)
        return v if v and v.get("validado") else None

    datos_verificacion_hidraulica = _validado("hidraulico") if item_key == "diseno_hidraulico" else None
    datos_verificacion_agronomica = _validado("agronomico") if item_key == "diseno_hidraulico" else None
    datos_verificacion_fv         = _validado("energetico") if item_key == "diseno_fotovoltaico" else None

    # Tabla de precios referenciales promedio (subida en /admin/precios, no oficial de la CNR).
    # Si nunca se ha subido nada, queda None y analizar_item() no corre la verificación de precios.
    tabla_precios = None
    if item_key in ("presupuesto", "presupuesto_electrico"):
        precios_data = db.get_precios()
        tabla_precios = precios_data.get("items") if precios_data else None

    _restaurar_archivos_necesarios(proyecto_id, proyecto.get("documentos", []))

    try:
        resultado = await analizar_item(
            item_key=item_key,
            documentos=proyecto.get("documentos", []),
            bases_texto=bases_texto,
            concurso_id=concurso_id,
            feedback_concurso=feedback_concurso,
            criterios_aprendidos=criterios,
            criterios_enfasis=enfasis,
            consultor=consultor,
            datos_verificacion_hidraulica=datos_verificacion_hidraulica,
            datos_verificacion_agronomica=datos_verificacion_agronomica,
            datos_verificacion_fv=datos_verificacion_fv,
            tabla_precios=tabla_precios,
            tipo_revision=proyecto.get("tipo_revision", "tecnica"),
            ruta_uploads=str(UPLOAD_DIR / proyecto_id),
        )
    except Exception as e:
        import traceback
        print(f"❌ ERROR en revisar_item {item_key}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al revisar ítem: {str(e)}")

    if resultado.get("sin_documentos"):
        return RedirectResponse(
            url=f"/proyecto/{proyecto_id}/items?item_sin_docs={item_key}", status_code=302)

    # Reemplazar observaciones previas de este ítem
    proyecto["observaciones"] = [
        o for o in proyecto.get("observaciones", []) if o.get("item") != item_key
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
    proyecto.setdefault("items_revisados", {})
    proyecto["items_revisados"][item_key] = {
        "fecha": _ahora().isoformat(),
        "n_obs": n_obs,
        "n_notas": n_notas,
        "docs": docs_incluidos,   # [{id, nombre (archivo real), label (tipo)}] — para mostrar cuáles se usaron
    }

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
        return RedirectResponse(url="/login")

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

        resultado = await chatear_item(
            item_key=key, documentos=proyecto.get("documentos", []),
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


def _agronomico_calculo(datos: dict):
    campos = ["cc_pct", "pmp_pct", "da", "prof_radicular_cm", "kc", "eto_dia_mm",
              "factor_agotamiento_pct", "eficiencia_pct"]
    if not (datos and all(datos.get(k) not in (None, "") for k in campos)):
        return None
    r = calculos_riego.cadena_agronomica(*[datos[k] for k in campos])
    r.update(calculos_riego.verificacion_diseno_riego(
        db_mm_dia=r["db_mm"],
        superficie_ha=datos.get("superficie_riego_ha"),
        caudal_disponible_ls=datos.get("caudal_disponible_ls"),
        precipitacion_mmhr=datos.get("precipitacion_sistema_mmhr"),
        horas_disponibles_dia=datos.get("horas_disponibles_dia"),
    ))
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
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    verif = proyecto.get("verificacion_calculos", {})
    hid = verif.get("hidraulico", {})
    tramos = list(hid.get("tramos") or [])[:N_TRAMOS_HIDRAULICOS]
    while len(tramos) < N_TRAMOS_HIDRAULICOS:
        tramos.append({})
    agro = verif.get("agronomico", {})
    fv = verif.get("energetico", {})

    return templates.TemplateResponse("calculos.html", {
        "request": request, "user": user, "proyecto": proyecto,
        "tramos": _tramos_con_calculo(tramos),
        "hid_validado": hid.get("validado"), "hid_fecha": hid.get("fecha_validado"),
        "hid_por": hid.get("validado_por"),
        "agro": agro, "agro_calc": _agronomico_calculo(agro),
        "agro_validado": agro.get("validado"), "agro_fecha": agro.get("fecha_validado"),
        "agro_por": agro.get("validado_por"),
        "fv": fv, "fv_calc": _fv_calculo(fv),
        "fv_validado": fv.get("validado"), "fv_fecha": fv.get("fecha_validado"),
        "fv_por": fv.get("validado_por"),
    })


@app.post("/proyecto/{proyecto_id}/calculos/hidraulico/extraer")
async def calculos_extraer_hidraulico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    docs_grupo = _documentos_para_verificacion("hidraulico", proyecto.get("documentos", []))
    datos = await _extraer_datos_hidraulicos(docs_grupo)
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["hidraulico"] = {
        "tramos": datos.get("tramos", []), "validado": False,
    }
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/hidraulico/guardar")
async def calculos_guardar_hidraulico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    form = await request.form()
    tramos = []
    for i in range(N_TRAMOS_HIDRAULICOS):
        nombre = (form.get(f"t{i}_nombre") or "").strip()
        q = _num_form(form, f"t{i}_caudal")
        d = _num_form(form, f"t{i}_diametro")
        if not nombre and not q and not d:
            continue
        tramos.append({
            "nombre": nombre or f"Tramo {i+1}",
            "caudal_ls": q, "diametro_mm": d,
            "longitud_m": _num_form(form, f"t{i}_longitud"),
            "material": (form.get(f"t{i}_material") or "").strip() or None,
            "velocidad_declarada_ms": _num_form(form, f"t{i}_vel_declarada"),
        })

    validado = form.get("validar") == "on"
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["hidraulico"] = {
        "tramos": tramos, "validado": validado,
        "fecha_validado": _ahora().isoformat() if validado else None,
        "validado_por": user["nombre"] if validado else None,
    }
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/agronomico/extraer")
async def calculos_extraer_agronomico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    docs_grupo = _documentos_para_verificacion("agronomico", proyecto.get("documentos", []))
    datos = await _extraer_datos_agronomicos(docs_grupo)
    datos["validado"] = False
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["agronomico"] = datos
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/agronomico/guardar")
async def calculos_guardar_agronomico(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    form = await request.form()
    campos = ["cc_pct", "pmp_pct", "da", "prof_radicular_cm", "kc", "eto_dia_mm",
              "factor_agotamiento_pct", "eficiencia_pct",
              "superficie_riego_ha", "caudal_disponible_ls",
              "precipitacion_sistema_mmhr", "horas_disponibles_dia"]
    datos = {c: _num_form(form, c) for c in campos}
    datos["declarado"] = {
        "dn_mm": _num_form(form, "decl_dn"),
        "fr_dias": _num_form(form, "decl_fr"),
        "db_mm": _num_form(form, "decl_db"),
        "caudal_diseno_ls": _num_form(form, "decl_qdiseno"),
        "tiempo_riego_hr": _num_form(form, "decl_triego"),
        "n_sectores": _num_form(form, "decl_nsec"),
    }
    validado = form.get("validar") == "on"
    datos["validado"] = validado
    datos["fecha_validado"] = _ahora().isoformat() if validado else None
    datos["validado_por"] = user["nombre"] if validado else None
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["agronomico"] = datos
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/energetico/extraer")
async def calculos_extraer_fv(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)
    docs_grupo = _documentos_para_verificacion("energetico", proyecto.get("documentos", []))
    datos = await _extraer_datos_fv(docs_grupo)
    datos["validado"] = False
    proyecto.setdefault("verificacion_calculos", {})
    proyecto["verificacion_calculos"]["energetico"] = datos
    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/calculos", status_code=302)


@app.post("/proyecto/{proyecto_id}/calculos/energetico/guardar")
async def calculos_guardar_fv(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
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
        return RedirectResponse(url="/login")

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
    for arch in archivos:
        doc_id = str(uuid.uuid4())[:8]
        doc = {
            "id": doc_id,
            "nombre_original": arch["nombre_original"],
            "filename": arch["filename"],
            "tipo_doc": arch["tipo_doc"],
            "tipo_doc_label": arch["label"],
            "fecha_subida": _ahora().isoformat(),
            "texto_extraido": arch["texto_extraido"],
            "analizado": False,
            "origen": "zip"
        }
        proyecto["documentos"].append(doc)
        archivo_extraido = UPLOAD_DIR / proyecto_id / arch["filename"]
        if archivo_extraido.exists():
            db.guardar_archivo(proyecto_id, doc_id, arch["filename"], archivo_extraido.read_bytes())

    # Eliminar ZIP temporal
    zip_path.unlink(missing_ok=True)

    db.save_proyecto(proyecto)
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
        return RedirectResponse(url="/login")

    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    from extractor import detectar_anexo
    FORMATOS_SOPORTADOS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
    registrados = 0

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

        doc = {
            "id": doc_id,
            "nombre_original": nombre,
            "filename": filename,
            "tipo_doc": tipo_doc,
            "tipo_doc_label": label,
            "fecha_subida": _ahora().isoformat(),
            "texto_extraido": truncar_texto_guardado(texto),
            "analizado": False,
            "origen": "multiple"
        }
        proyecto["documentos"].append(doc)
        registrados += 1

    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/documentos?multi_ok={registrados}", status_code=302)


# ─── Eliminar documento ───────────────────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/documento/{doc_id}/eliminar")
async def eliminar_documento(request: Request, proyecto_id: str, doc_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
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
        proyecto["documentos"] = [d for d in proyecto["documentos"] if d["id"] != doc_id]
        proyecto["observaciones"] = [o for o in proyecto["observaciones"] if o.get("doc_id") != doc_id]
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
        texto = doc.get("texto_extraido", "")
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


# ─── Resumen del proyecto (formulario) ────────────────────────────────────────

@app.post("/proyecto/{proyecto_id}/resumen")
async def guardar_resumen(request: Request, proyecto_id: str):
    """Guarda los campos del formulario de resumen editados por el revisor."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
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
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
    concurso = db.get_concurso(concurso_id)
    bases_texto = concurso.get("bases_texto", "") if concurso else ""

    try:
        datos = await resumir_proyecto(
            documentos=proyecto.get("documentos", []),
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
    db.save_proyecto(proyecto)
    return RedirectResponse(
        url=f"/proyecto/{proyecto_id}/resumen?auto_ok={completados}",
        status_code=302)


# ─── Consultas al expediente ─────────────────────────────────────────────────

@app.get("/proyecto/{proyecto_id}/consultar", response_class=HTMLResponse)
async def consultar_page(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
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
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    respuesta = await consultar_expediente(pregunta, proyecto.get("documentos", []))

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
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if proyecto:
        # Conservar las observaciones de ejes; borrar solo las de ítems
        proyecto["observaciones"] = [o for o in proyecto.get("observaciones", []) if not o.get("item")]
        proyecto["items_revisados"] = {}
        proyecto["item_chats"] = {}
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items", status_code=302)


@app.post("/proyecto/{proyecto_id}/eliminar")
async def eliminar_proyecto(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
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
        return RedirectResponse(url="/login")

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

    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items", status_code=302)


@app.post("/proyecto/{proyecto_id}/observacion/{obs_id}/eliminar")
async def eliminar_observacion(request: Request, proyecto_id: str, obs_id: str):
    """Elimina una observación por completo (no reversible), a diferencia de Descartar que
    solo la marca como descartada conservando el registro."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404)

    obs = next((o for o in proyecto.get("observaciones", []) if o["id"] == obs_id), None)
    if obs:
        # Misma señal de aprendizaje que descartar (no era válida) antes de borrarla.
        _registrar_feedback_obs(proyecto, obs, "descartada", user)
        proyecto["observaciones"] = [o for o in proyecto["observaciones"] if o["id"] != obs_id]
        db.save_proyecto(proyecto)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}/items", status_code=302)


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
    # Consultores con historia/perfil aprendido (cruza concursos)
    consultores_info = []
    for c in db.get_all_consultores():
        n_fb = len(c.get("feedback", []))
        if n_fb > 0:
            consultores_info.append({
                "nombre": c.get("nombre", ""),
                "n_feedback": n_fb,
                "perfil": c.get("perfil", ""),
            })
    # Archivos guardados en la base para los proyectos de este concurso (para poder
    # "dar por terminado" el concurso y liberar ese espacio sin perder el análisis ya hecho).
    proyectos_concurso = [p for p in db.get_proyectos()
                          if _extraer_concurso_id(p.get("codigo_sep", "")) == concurso_id]
    resumen_archivos = db.resumen_archivos([p["id"] for p in proyectos_concurso])
    # Criterios de énfasis: a diferencia de criterios_aprendidos (se destila solo del
    # feedback aprobada/descartada), esto lo escribe y edita el revisor directamente — su
    # supervisión explícita sobre qué debe verificar la IA en cada ítem de ESTE concurso.
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
        {"key": k, "label": TIPO_DOC_LABELS[k], "checked": k in obligatorios_actuales}
        for k in sorted(TIPO_DOC_LABELS, key=lambda k: TIPO_DOC_ORDEN.get(k, 999))
    ]
    return templates.TemplateResponse("admin_concurso_detalle.html", {
        "request": request, "user": user, "concurso": concurso, "msg_ok": msg_ok,
        "n_feedback": len(concurso.get("feedback", [])),
        "criterios_lista": criterios_lista,
        "criterios_fecha": concurso.get("criterios_fecha", ""),
        "consultores_info": consultores_info,
        "n_proyectos_concurso": len(proyectos_concurso),
        "resumen_archivos": resumen_archivos,
        "grupos_enfasis": grupos_enfasis,
        "checklist_doc_obligatorios": checklist_doc_obligatorios,
    })


@app.post("/admin/concursos/{concurso_id}/criterios-enfasis")
async def guardar_criterios_enfasis(request: Request, concurso_id: str):
    """Guarda los criterios de énfasis por ítem escritos a mano por el revisor — a
    diferencia de criterios_aprendidos (se destila solo de aprobar/descartar observaciones),
    esto es supervisión directa del revisor y nunca se sobrescribe automáticamente."""
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

    resultado = await extraer_documentos_obligatorios(concurso["bases_texto"], TIPO_DOC_LABELS)
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
    seleccionados = [k for k in TIPO_DOC_LABELS if form.get(f"doc__{k}") == "on"]
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
    """Destila el feedback acumulado en criterios aprendidos por ítem."""
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
        # Perfiles de consultores (cruza proyectos/concursos): destila los que tengan historia
        for c in db.get_all_consultores():
            perfil = await consolidar_perfil_consultor(c.get("feedback", []), c.get("nombre", ""))
            if perfil:
                c["perfil"] = perfil
                c["perfil_fecha"] = _ahora().isoformat()
                db.save_consultor(c)
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

    proyecto_ids = [p["id"] for p in db.get_proyectos()
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
        return RedirectResponse(url="/login")
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
        return RedirectResponse(url="/login")
    db_user = db.get_user(user["username"])

    def _render(error=None, ok=False):
        return templates.TemplateResponse("mi_cuenta.html", {
            "request": request, "user": user, "error": error, "ok": ok
        })

    if not verify_password(password_actual, db_user["password_hash"]):
        return _render("Contraseña actual incorrecta.")
    if password_nuevo != password_confirmar:
        return _render("Las contraseñas nuevas no coinciden.")
    if len(password_nuevo) < 6:
        return _render("La contraseña debe tener al menos 6 caracteres.")
    db.update_password(user["username"], password_nuevo)
    return _render(ok=True)


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
