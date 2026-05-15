"""Base de datos: PostgreSQL en producción, JSON en desarrollo local."""
import json
import os
from pathlib import Path
from auth import hash_password

# ── Configuración ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")          # Railway lo inyecta automáticamente
DATA_DIR     = Path(os.getenv("DATA_DIR", "data"))

# Rutas legacy (solo se usan en modo JSON local)
USERS_FILE     = DATA_DIR / "users.json"
PROYECTOS_FILE = DATA_DIR / "proyectos.json"
CONCURSOS_FILE = DATA_DIR / "concursos.json"

# ── Backend PostgreSQL ─────────────────────────────────────────────────────────
_pg_conn = None

def _get_pg():
    """Retorna conexión PostgreSQL (singleton, reconecta si cayó)."""
    global _pg_conn
    import psycopg2, psycopg2.extras
    try:
        if _pg_conn is None or _pg_conn.closed:
            _pg_conn = psycopg2.connect(DATABASE_URL)
            _pg_conn.autocommit = True
            with _pg_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS storage (
                        key     TEXT PRIMARY KEY,
                        value   TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
    except Exception:
        _pg_conn = psycopg2.connect(DATABASE_URL)
        _pg_conn.autocommit = True
        with _pg_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS storage (
                    key     TEXT PRIMARY KEY,
                    value   TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
    return _pg_conn


def _pg_load(key: str) -> dict:
    conn = _get_pg()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM storage WHERE key = %s", (key,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else {}


def _pg_save(key: str, data: dict):
    conn = _get_pg()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO storage (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(data, ensure_ascii=False)))


# ── Backend JSON (desarrollo local) ───────────────────────────────────────────
def _json_load(filepath: Path) -> dict:
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _json_save(filepath: Path, data: dict):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Clase principal ────────────────────────────────────────────────────────────
class Database:
    def __init__(self):
        self._use_pg = bool(DATABASE_URL)
        if not self._use_pg:
            DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self, key: str, filepath: Path) -> dict:
        if self._use_pg:
            return _pg_load(key)
        return _json_load(filepath)

    def _save(self, key: str, filepath: Path, data: dict):
        if self._use_pg:
            _pg_save(key, data)
        else:
            _json_save(filepath, data)

    # ── Usuarios ──────────────────────────────────────────────────────────────

    def get_user(self, username: str) -> dict:
        users = self._load("users", USERS_FILE)
        return users.get(username)

    def get_all_users(self) -> list:
        users = self._load("users", USERS_FILE)
        return sorted(users.values(), key=lambda u: u["username"])

    def delete_user(self, username: str):
        users = self._load("users", USERS_FILE)
        users.pop(username, None)
        self._save("users", USERS_FILE, users)

    def create_user(self, username: str, password: str, nombre: str, rol: str):
        users = self._load("users", USERS_FILE)
        users[username] = {
            "username": username,
            "password_hash": hash_password(password),
            "nombre": nombre,
            "rol": rol
        }
        self._save("users", USERS_FILE, users)

    def update_password(self, username: str, new_password: str):
        users = self._load("users", USERS_FILE)
        if username in users:
            users[username]["password_hash"] = hash_password(new_password)
            self._save("users", USERS_FILE, users)

    # ── Proyectos ─────────────────────────────────────────────────────────────

    def get_proyectos(self, username: str = None) -> list:
        proyectos = self._load("proyectos", PROYECTOS_FILE)
        all_p = list(proyectos.values())
        if username:
            all_p = [p for p in all_p if p["revisor"] == username]
        return sorted(all_p, key=lambda x: x["fecha_creacion"], reverse=True)

    def get_proyecto(self, proyecto_id: str) -> dict:
        proyectos = self._load("proyectos", PROYECTOS_FILE)
        return proyectos.get(proyecto_id)

    def save_proyecto(self, proyecto: dict):
        proyectos = self._load("proyectos", PROYECTOS_FILE)
        proyectos[proyecto["id"]] = proyecto
        self._save("proyectos", PROYECTOS_FILE, proyectos)

    # ── Concursos ─────────────────────────────────────────────────────────────

    def get_concurso(self, concurso_id: str) -> dict:
        concursos = self._load("concursos", CONCURSOS_FILE)
        return concursos.get(concurso_id)

    def get_all_concursos(self) -> list:
        concursos = self._load("concursos", CONCURSOS_FILE)
        return sorted(concursos.values(), key=lambda c: c.get("id", ""))

    def save_concurso(self, concurso: dict):
        concursos = self._load("concursos", CONCURSOS_FILE)
        concursos[concurso["id"]] = concurso
        self._save("concursos", CONCURSOS_FILE, concursos)

    def add_feedback_concurso(self, concurso_id: str, feedback_entry: dict):
        """Añade una entrada de feedback al historial del concurso (máx. 200)."""
        concurso = self.get_concurso(concurso_id)
        if concurso is None:
            return
        if "feedback" not in concurso:
            concurso["feedback"] = []
        concurso["feedback"].append(feedback_entry)
        concurso["feedback"] = concurso["feedback"][-200:]
        self.save_concurso(concurso)


db = Database()
