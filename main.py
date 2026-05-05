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

app = FastAPI(title="Revisor CNR")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
async def startup_event():
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

@app.get("/debug-env")
async def debug_env(request: Request):
    user = get_current_user(request)
    if not user or user.get("rol") != "admin":
        return {"error": "forbidden"}
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "tiene_api_key": bool(key),
        "primeros_chars": key[:10] if key else "(vacio)",
        "longitud": len(key),
        "DATA_DIR": os.environ.get("DATA_DIR", "(no definida)"),
        "UPLOAD_DIR": os.environ.get("UPLOAD_DIR", "(no definida)"),
        "todas_las_variables": sorted(os.environ.keys()),
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
    return templates.TemplateResponse("proyecto.html", {
        "request": request,
        "user": user,
        "proyecto": proyecto
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

    # Analizar con Claude — incluye contexto de todos los documentos del proyecto
    observaciones = await analyze_document(
        texto=doc["texto_extraido"],
        tipo_doc=doc["tipo_doc"],
        tipo_revision=proyecto["tipo_revision"],
        nombre_doc=doc["nombre_original"],
        filepath=str(UPLOAD_DIR / proyecto_id / doc["filename"]),
        doc_id=doc_id,
        todos_documentos=proyecto.get("documentos", [])
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
    for obs in proyecto["observaciones"]:
        if obs["id"] == obs_id:
            obs["estado"] = estado
            if texto_editado:
                obs["texto"] = texto_editado
            obs["revisado_por"] = user["nombre"]
            break

    db.save_proyecto(proyecto)
    return RedirectResponse(url=f"/proyecto/{proyecto_id}", status_code=302)


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
