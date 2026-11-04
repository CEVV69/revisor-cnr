"""Autenticación y manejo de tokens"""
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt

ALGORITHM = "HS256"

# Antes había un valor por defecto fijo escrito acá — con el repositorio público en GitHub,
# cualquiera podía firmar un token de administrador si Railway no tenía SECRET_KEY configurada.
# Sin la variable de entorno, se usa una clave aleatoria generada una vez y guardada en la base
# (sobrevive redeploys; ver Database.obtener_o_crear_clave_sesion).
_secret_key = os.getenv("SECRET_KEY") or None


def _clave() -> str:
    global _secret_key
    if not _secret_key:
        from database import db  # diferido: database.py importa este módulo
        _secret_key = db.obtener_o_crear_clave_sesion()
    return _secret_key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=8)
    return jwt.encode(payload, _clave(), algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, _clave(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
