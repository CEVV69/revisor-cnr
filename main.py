"""
Revisor CNR - Aplicación de revisión de proyectos de riego Ley 18.450
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
import uvicorn
from dotenv import load_dotenv

from auth import create_token, verify_token, hash_password, verify_password
from extractor import extract_text, extract_zip
from analyzer import analyze_document, consultar_expediente, revisar_observaciones_previas
from database import db

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

app = FastAPI(title="Revisor CNR")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
async def startup_event():
    # Diagnóstico de almacenamiento
    from database import DATA_DIR
    storage_path = Path("/storage")
    print(f"📁 DATA_DIR = {DATA_DIR} (absoluta: {DATA_DIR.resolve()})")
    print(f"📁 UPLOAD_DIR = {UPLOAD_DIR} (absoluta: {UPLOAD_DIR.resolve()})")
    print(f"📦 /storage existe: {storage_path.exists()}")
    if storage_path.exists():
        try:
            test_file = storage_path / ".write_test"
            test_file.write_text("ok")
            test_file.unlink()
            print("✅ /storage es escribible — volumen montado correctamente")
        except Exception as e:
            print(f"❌ /storage NO es escribible: {e}")
    else:
        print("❌ /storage NO existe — los datos se guardarán en el contenedor temporal (se borrarán en cada deploy)")

    if not db.get_user("admin"):
        db.create_user("admin", "admin123", "Administrador CNR", "admin")
        print("✅ Usuario admin creado: admin / admin123")


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
    postulante: str = Form(...),
    tipo_revision: str = Form(...)
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
        "tipo_revision": tipo_revision,
        "revisor": user["username"],
        "revisor_nombre": user["nombre"],
        "estado": "En revisión",
        "fecha_creacion": datetime.now().isoformat(),
        "documentos": [],
        "observaciones": []
    }
    db.save_proyecto(proyecto)

    # Crear carpeta para documentos del proyecto
    (UPLOAD_DIR / proyecto_id).mkdir(exist_ok=True)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}", status_code=302)


@app.get("/proyecto/{proyecto_id}", response_class=HTMLResponse)
async def ver_proyecto(request: Request, proyecto_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    proyecto = db.get_proyecto(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
    concurso = db.get_concurso(concurso_id)
    return templates.TemplateResponse("proyecto.html", {
        "request": request,
        "user": user,
        "proyecto": proyecto,
        "concurso": concurso,
        "concurso_id": concurso_id,
    })


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

    content = await archivo.read()
    with open(filepath, "wb") as f:
        f.write(content)

    # Extraer texto
    texto = extract_text(str(filepath), ext)

    doc = {
        "id": doc_id,
        "nombre_original": archivo.filename,
        "filename": filename,
        "tipo_doc": tipo_doc,
        "fecha_subida": datetime.now().isoformat(),
        "texto_extraido": texto[:5000],  # primeros 5000 chars para análisis
        "analizado": False
    }

    proyecto["documentos"].append(doc)
    db.save_proyecto(proyecto)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}", status_code=302)


@app.post("/proyecto/{proyecto_id}/analizar/{doc_id}")
async def analizar_documento(request: Request, proyecto_id: str, doc_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    proyecto = db.get_proyecto(proyecto_id)
    doc = next((d for d in proyecto["documentos"] if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404)

    # Cargar bases y feedback del concurso
    concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
    concurso = db.get_concurso(concurso_id)
    bases_texto       = concurso.get("bases_texto", "") if concurso else ""
    feedback_concurso = concurso.get("feedback", [])   if concurso else []

    # Analizar con Claude — incluye contexto de todos los documentos del proyecto
    observaciones = await analyze_document(
        texto=doc["texto_extraido"],
        tipo_doc=doc["tipo_doc"],
        tipo_revision=proyecto["tipo_revision"],
        nombre_doc=doc["nombre_original"],
        filepath=str(UPLOAD_DIR / proyecto_id / doc["filename"]),
        doc_id=doc_id,
        todos_documentos=proyecto.get("documentos", []),
        bases_texto=bases_texto,
        concurso_id=concurso_id,
        feedback_concurso=feedback_concurso,
    )

    # Guardar nuevas observaciones
    for obs in observaciones:
        obs["id"] = str(uuid.uuid4())[:8]
        obs["doc_id"] = doc_id
        obs["doc_nombre"] = doc["nombre_original"]
        obs["fecha"] = datetime.now().isoformat()
        obs["estado"] = "pendiente"
        proyecto["observaciones"].append(obs)

    doc["analizado"] = True

    # Revisar si este documento invalida observaciones previas de otros documentos
    obs_previas_pendientes = [
        o for o in proyecto["observaciones"]
        if o.get("estado") == "pendiente" and o.get("doc_id") != doc_id
    ]
    if obs_previas_pendientes:
        ids_invalidadas = await revisar_observaciones_previas(
            texto_nuevo=doc["texto_extraido"],
            nombre_doc_nuevo=doc["nombre_original"],
            tipo_doc_nuevo=doc["tipo_doc"],
            observaciones_previas=obs_previas_pendientes
        )
        for obs in proyecto["observaciones"]:
            if obs["id"] in ids_invalidadas:
                obs["estado"] = "descartada"
                obs["texto"] = obs["texto"] + f'\n\n[Auto-descartada: resuelta por {doc["nombre_original"]}]'

    db.save_proyecto(proyecto)

    return RedirectResponse(url=f"/proyecto/{proyecto_id}", status_code=302)


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

    # Extraer y clasificar archivos
    dest_dir = str(UPLOAD_DIR / proyecto_id)
    archivos = extract_zip(str(zip_path), dest_dir)

    # Registrar cada archivo como documento del proyecto
    for arch in archivos:
        doc = {
            "id": str(uuid.uuid4())[:8],
            "nombre_original": arch["nombre_original"],
            "filename": arch["filename"],
            "tipo_doc": arch["tipo_doc"],
            "tipo_doc_label": arch["label"],
            "fecha_subida": datetime.now().isoformat(),
            "texto_extraido": arch["texto_extraido"],
            "analizado": False,
            "origen": "zip"
        }
        proyecto["documentos"].append(doc)

    # Eliminar ZIP temporal
    zip_path.unlink(missing_ok=True)

    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}?zip_ok={len(archivos)}", status_code=302)


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

        content = await archivo.read()
        with open(filepath, "wb") as f:
            f.write(content)

        tipo_doc, label = detectar_anexo(nombre)
        texto = extract_text(str(filepath), ext)

        doc = {
            "id": doc_id,
            "nombre_original": nombre,
            "filename": filename,
            "tipo_doc": tipo_doc,
            "tipo_doc_label": label,
            "fecha_subida": datetime.now().isoformat(),
            "texto_extraido": texto[:5000],
            "analizado": False,
            "origen": "multiple"
        }
        proyecto["documentos"].append(doc)
        registrados += 1

    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}?multi_ok={registrados}", status_code=302)


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
        proyecto["documentos"] = [d for d in proyecto["documentos"] if d["id"] != doc_id]
        proyecto["observaciones"] = [o for o in proyecto["observaciones"] if o.get("doc_id") != doc_id]
        db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}", status_code=302)


# ─── Cambiar tipo de documento ───────────────────────────────────────────────

# Mapa completo tipo_doc → label (coincide con las opciones del select en proyecto.html)
TIPO_DOC_LABELS = {
    "plano_ubicacion":        "Anexo 9.1 — Plano de ubicación",
    "identificacion_riego":   "Anexo 9.2 — Identificación área de riego",
    "estudio_hidrologico":    "Anexo 9.4 — Análisis Hidrológico",
    "pruebas_bombeo":         "Anexo 9.4.2 — Prueba de bombeo",
    "diseno_hidraulico":      "Anexo 9.5 — Diseño y cálculos hidráulicos",
    "estudios_complementarios":"Anexo 9.6 — Estudios complementarios",
    "especificaciones_tecnicas":"Anexo 9.8 — Especificaciones técnicas",
    "cronograma":             "Anexo 9.8.1 — Cronograma",
    "cubicaciones":           "Anexo 9.9 — Cubicaciones",
    "presupuesto":            "Anexo 9.10.1 — Presupuesto obras",
    "presupuesto_electrico":  "Anexo 9.10.2 — Presupuesto electrificación",
    "cotizaciones_facturas":  "Anexo 9.10.3 — Cotizaciones y Facturas",
    "cotizaciones":           "Anexo 9.10.4 — Cotizaciones",
    "declaracion_iva":        "Anexo 9.10.5 — Declaración No Contribuyente IVA",
    "planos_tecnificacion":   "Anexo 9.12.1.1 — Planos tecnificación",
    "planos_obras_civiles":   "Anexo 9.12.1.2 — Planos obras civiles",
    "memoria_superficies":    "Anexo 9.13.1 — Memoria cálculo superficies",
    "estudio_suelos":         "Anexo 9.13.2 — Estudio de suelos",
    "evaluacion_social":      "Anexo 9.14 — Evaluación Social MIDESO",
    "antecedentes_legales":   "Antecedentes legales",
    "lista_beneficiarios":    "Lista de beneficiarios",
    "otro":                   "Otro documento",
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
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

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
    obs_aprobadas = [o for o in proyecto.get("observaciones", [])
                     if o.get("estado") == "aprobada" and o.get("severidad") != "informativa"]
    from datetime import date
    return templates.TemplateResponse("ficha.html", {
        "request": request,
        "proyecto": proyecto,
        "user": user,
        "obs_aprobadas": obs_aprobadas,
        "fecha_ficha": date.today().strftime("%d-%m-%Y")
    })


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
        "fecha": datetime.now().isoformat(),
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
        proyectos = db._load(db._proyectos_file())
        proyectos.pop(proyecto_id, None)
        db._save(db._proyectos_file(), proyectos)
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
    obs_actualizada = None
    for obs in proyecto["observaciones"]:
        if obs["id"] == obs_id:
            obs["estado"] = estado
            if texto_editado:
                obs["texto"] = texto_editado
            obs["revisado_por"] = user["nombre"]
            obs_actualizada = obs
            break

    db.save_proyecto(proyecto)

    # ── Guardar feedback en el concurso para aprendizaje futuro ──────────────
    if obs_actualizada and estado in ("aprobada", "descartada"):
        concurso_id = _extraer_concurso_id(proyecto.get("codigo_sep", ""))
        # Encontrar el tipo_doc del documento al que pertenece la observación
        doc_de_obs = next(
            (d for d in proyecto.get("documentos", [])
             if d["id"] == obs_actualizada.get("doc_id")), None
        )
        tipo_doc_obs = doc_de_obs["tipo_doc"] if doc_de_obs else "otro"
        db.add_feedback_concurso(concurso_id, {
            "id":        obs_actualizada["id"],
            "fecha":     datetime.now().isoformat(),
            "tipo_doc":  tipo_doc_obs,
            "texto_obs": obs_actualizada["texto"][:300],
            "accion":    estado,   # "aprobada" o "descartada"
            "revisor":   user["username"],
        })

    return RedirectResponse(url=f"/proyecto/{proyecto_id}", status_code=302)


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
        "fecha_creacion": datetime.now().isoformat(),
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
            "fecha_creacion": datetime.now().isoformat(),
            "feedback": []
        }
        db.save_concurso(concurso)
        msg_ok = "creado"
    elif not concurso:
        raise HTTPException(status_code=404, detail="Concurso no encontrado")
    else:
        msg_ok = request.query_params.get("ok")
    return templates.TemplateResponse("admin_concurso_detalle.html", {
        "request": request, "user": user, "concurso": concurso, "msg_ok": msg_ok
    })


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
    concurso["fecha_actualizacion"] = datetime.now().isoformat()
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

    # Extraer texto
    from extractor import extract_text
    texto = extract_text(str(tmp_path), ext)
    tmp_path.unlink(missing_ok=True)

    if texto.strip() == "__PDF_ESCANEADO__":
        return RedirectResponse(url=f"/admin/concursos/{concurso_id}?error=escaneado", status_code=302)

    if nombre.strip():
        concurso["nombre"] = nombre.strip()
    concurso["bases_texto"] = texto.strip()
    concurso["fecha_actualizacion"] = datetime.now().isoformat()
    db.save_concurso(concurso)
    return RedirectResponse(url=f"/admin/concursos/{concurso_id}?ok=pdf_cargado", status_code=302)


@app.post("/admin/concursos/{concurso_id}/eliminar")
async def admin_eliminar_concurso(request: Request, concurso_id: str):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return RedirectResponse(url="/")
    from database import CONCURSOS_FILE
    concursos_data = db._load(CONCURSOS_FILE)
    concursos_data.pop(concurso_id, None)
    db._save(CONCURSOS_FILE, concursos_data)
    return RedirectResponse(url="/admin/concursos?ok=eliminado", status_code=302)


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
