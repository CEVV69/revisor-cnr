"""Base de datos: PostgreSQL en producción, JSON en desarrollo local."""
import json
import os
from pathlib import Path
from auth import hash_password

# ── Configuración ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")          # Railway lo inyecta automáticamente
DATA_DIR     = Path(os.getenv("DATA_DIR", "data"))

# Rutas legacy (solo se usan en modo JSON local)
USERS_FILE       = DATA_DIR / "users.json"
PROYECTOS_FILE   = DATA_DIR / "proyectos.json"
CONCURSOS_FILE   = DATA_DIR / "concursos.json"
CONSULTORES_FILE = DATA_DIR / "consultores.json"
PRECIOS_FILE     = DATA_DIR / "precios.json"

# ── Backend PostgreSQL ─────────────────────────────────────────────────────────
_pg_conn = None

def _crear_tablas(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS storage (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Archivos físicos (PDF/Word/Excel) guardados en la base para que sobrevivan a un
        # redeploy de Railway (el disco local es efímero). Uno por documento del proyecto.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS archivos (
                proyecto_id TEXT NOT NULL,
                doc_id      TEXT NOT NULL,
                filename    TEXT NOT NULL,
                contenido   BYTEA NOT NULL,
                tamano      INTEGER NOT NULL,
                fecha       TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (proyecto_id, doc_id)
            )
        """)


def _get_pg():
    """Retorna conexión PostgreSQL (singleton, reconecta si cayó)."""
    global _pg_conn
    import psycopg2
    try:
        if _pg_conn is None or _pg_conn.closed:
            _pg_conn = psycopg2.connect(DATABASE_URL)
            _pg_conn.autocommit = True
            _crear_tablas(_pg_conn)
    except Exception:
        _pg_conn = psycopg2.connect(DATABASE_URL)
        _pg_conn.autocommit = True
        _crear_tablas(_pg_conn)
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


def _pg_load_prefix(prefix: str) -> list:
    """Carga todos los values cuyo key empieza con `prefix` (una sola query)."""
    conn = _get_pg()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM storage WHERE key LIKE %s", (prefix + "%",))
        return [json.loads(r[0]) for r in cur.fetchall()]


def _pg_delete(key: str):
    conn = _get_pg()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM storage WHERE key = %s", (key,))


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
    # En PostgreSQL, cada proyecto vive bajo su propia clave "proyecto:{id}" — antes TODOS
    # los proyectos (con el texto extraído completo de cada documento) se guardaban en un
    # solo blob JSON bajo la clave "proyectos", y cada get/save de UN proyecto cargaba y
    # reescribía el blob entero (megas por clic a medida que se acumulan expedientes).
    # `migrar_proyectos()` (llamada al startup en main.py) traslada el blob legacy a claves
    # separadas una única vez, de forma idempotente. En modo JSON local se conserva el
    # archivo único de siempre (disco local, datos chicos — no vale la pena migrar).

    def migrar_proyectos(self):
        """Migra el blob legacy 'proyectos' a una clave por proyecto (solo PostgreSQL).
        Idempotente: si algo falla a la mitad, al próximo arranque reintenta y sobrescribe."""
        if not self._use_pg:
            return
        legacy = _pg_load("proyectos")
        if not legacy:
            return
        for pid, proyecto in legacy.items():
            _pg_save(f"proyecto:{pid}", proyecto)
        _pg_delete("proyectos")
        print(f"✅ Migrados {len(legacy)} proyecto(s) del blob legacy a claves separadas")

    def get_proyectos(self, username: str = None) -> list:
        if self._use_pg:
            all_p = _pg_load_prefix("proyecto:")
        else:
            all_p = list(_json_load(PROYECTOS_FILE).values())
        if username:
            all_p = [p for p in all_p if p["revisor"] == username]
        return sorted(all_p, key=lambda x: x["fecha_creacion"], reverse=True)

    def get_proyecto(self, proyecto_id: str) -> dict:
        if self._use_pg:
            return _pg_load(f"proyecto:{proyecto_id}") or None
        return _json_load(PROYECTOS_FILE).get(proyecto_id)

    def save_proyecto(self, proyecto: dict):
        if self._use_pg:
            _pg_save(f"proyecto:{proyecto['id']}", proyecto)
            return
        proyectos = _json_load(PROYECTOS_FILE)
        proyectos[proyecto["id"]] = proyecto
        _json_save(PROYECTOS_FILE, proyectos)

    def delete_proyecto(self, proyecto_id: str):
        if self._use_pg:
            _pg_delete(f"proyecto:{proyecto_id}")
            return
        proyectos = _json_load(PROYECTOS_FILE)
        proyectos.pop(proyecto_id, None)
        _json_save(PROYECTOS_FILE, proyectos)

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

    def delete_concurso(self, concurso_id: str):
        concursos = self._load("concursos", CONCURSOS_FILE)
        concursos.pop(concurso_id, None)
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

    # ── Consultores (aprendizaje por consultor, cruza concursos) ────────────────

    def get_consultor(self, key: str) -> dict:
        consultores = self._load("consultores", CONSULTORES_FILE)
        return consultores.get(key)

    def get_all_consultores(self) -> list:
        consultores = self._load("consultores", CONSULTORES_FILE)
        return sorted(consultores.values(), key=lambda c: c.get("nombre", ""))

    def save_consultor(self, consultor: dict):
        consultores = self._load("consultores", CONSULTORES_FILE)
        consultores[consultor["key"]] = consultor
        self._save("consultores", CONSULTORES_FILE, consultores)

    def add_feedback_consultor(self, key: str, nombre: str, feedback_entry: dict):
        """Acumula feedback por consultor (cruza proyectos y concursos, máx. 300)."""
        consultores = self._load("consultores", CONSULTORES_FILE)
        c = consultores.get(key) or {"key": key, "nombre": nombre, "feedback": [], "perfil": ""}
        if nombre:
            c["nombre"] = nombre
        c.setdefault("feedback", []).append(feedback_entry)
        c["feedback"] = c["feedback"][-300:]
        consultores[key] = c
        self._save("consultores", CONSULTORES_FILE, consultores)

    # ── Precios referenciales (tabla única global, sube el revisor vía Excel) ──

    def get_precios(self) -> dict:
        """Tabla de precios referenciales (materiales/equipos) para comparar contra el
        presupuesto declarado. Estructura: {"items": [{categoria, item, unidad, precio}, ...],
        "fecha_actualizado", "actualizado_por", "nombre_archivo"}. {} si nunca se ha subido."""
        return self._load("precios", PRECIOS_FILE)

    def save_precios(self, data: dict):
        self._save("precios", PRECIOS_FILE, data)

    # ── Archivos físicos (persistencia contra deploys efímeros de Railway) ──────
    # Solo aplica en modo PostgreSQL: en modo JSON local el disco ya persiste entre
    # ejecuciones, así que estos métodos son no-op.

    def guardar_archivo(self, proyecto_id: str, doc_id: str, filename: str, contenido: bytes):
        if not self._use_pg:
            return
        import psycopg2
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO archivos (proyecto_id, doc_id, filename, contenido, tamano)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (proyecto_id, doc_id) DO UPDATE
                    SET filename = EXCLUDED.filename, contenido = EXCLUDED.contenido,
                        tamano = EXCLUDED.tamano, fecha = NOW()
            """, (proyecto_id, doc_id, filename, psycopg2.Binary(contenido), len(contenido)))

    def obtener_archivo(self, proyecto_id: str, doc_id: str) -> bytes:
        if not self._use_pg:
            return None
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("SELECT contenido FROM archivos WHERE proyecto_id=%s AND doc_id=%s",
                        (proyecto_id, doc_id))
            row = cur.fetchone()
            return bytes(row[0]) if row else None

    def ids_con_archivo(self, proyecto_id: str) -> set:
        """IDs de documentos con archivo guardado en la base (chequeo en lote, evita N
        consultas al armar la tabla de documentos de un proyecto)."""
        if not self._use_pg:
            return set()
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("SELECT doc_id FROM archivos WHERE proyecto_id=%s", (proyecto_id,))
            return {r[0] for r in cur.fetchall()}

    def eliminar_archivo(self, proyecto_id: str, doc_id: str):
        if not self._use_pg:
            return
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM archivos WHERE proyecto_id=%s AND doc_id=%s",
                        (proyecto_id, doc_id))

    def eliminar_archivos_proyectos(self, proyecto_ids: list):
        """Borra TODOS los archivos guardados de una lista de proyectos (ej. al dar por
        terminado un concurso). No toca texto_extraido/observaciones — solo libera espacio."""
        if not self._use_pg or not proyecto_ids:
            return
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM archivos WHERE proyecto_id = ANY(%s)", (list(proyecto_ids),))

    def resumen_archivos(self, proyecto_ids: list) -> dict:
        """Cantidad y peso total de los archivos guardados para una lista de proyectos."""
        if not self._use_pg or not proyecto_ids:
            return {"n": 0, "bytes": 0}
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*), COALESCE(SUM(tamano), 0) FROM archivos
                WHERE proyecto_id = ANY(%s)
            """, (list(proyecto_ids),))
            n, total = cur.fetchone()
            return {"n": n, "bytes": total}


db = Database()
