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
META_FILE        = DATA_DIR / "meta.json"
# Textos extraídos de los documentos, uno por proyecto (modo JSON local — en PostgreSQL van
# bajo la clave "textos:{proyecto_id}" de la tabla storage). Ver la nota en
# Database.get_textos_proyecto() sobre por qué viven aparte del proyecto.
TEXTOS_DIR       = DATA_DIR / "textos"

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


def _pg_load_prefix_campos(prefix: str, campos: list) -> list:
    """Como _pg_load_prefix, pero le pide a Postgres que arme un objeto SOLO con los `campos`
    pedidos (vía jsonb_build_object) en vez de traer y deserializar el JSON completo de cada
    fila. Pensado para listados livianos (ej. el dashboard) donde el resto del dato — en
    proyectos, el texto extraído de cada documento, que puede pesar varios MB por proyecto —
    no hace falta: evita transferirlo por red y evita el `json.loads()` en Python de ese
    volumen. `campos` son nombres de campo FIJOS definidos en el propio código (nunca datos de
    un request) — se insertan directo en el SQL sin parametrizar, por eso esta función NUNCA
    debe llamarse con una lista construida a partir de input externo."""
    conn = _get_pg()
    partes = ", ".join(f"'{c}', v -> '{c}'" for c in campos)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT jsonb_build_object({partes})
            FROM (SELECT value::jsonb AS v FROM storage WHERE key LIKE %s) t
        """, (prefix + "%",))
        return [r[0] for r in cur.fetchall()]


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

    def get_proyectos_ligero(self, campos: list, username: str = None) -> list:
        """Como get_proyectos(), pero solo trae los `campos` pedidos — para listados donde no
        hace falta el resto (dashboard, filtrar proyectos de un concurso, etc). En PostgreSQL
        evita transferir y deserializar el blob completo de cada proyecto (ver
        _pg_load_prefix_campos); en modo JSON local no vale la pena optimizar (disco local,
        datos chicos), se recorta igual para que el shape de retorno sea consistente."""
        if self._use_pg:
            all_p = _pg_load_prefix_campos("proyecto:", campos)
        else:
            all_p = [{k: p.get(k) for k in campos}
                     for p in _json_load(PROYECTOS_FILE).values()]
        if username:
            all_p = [p for p in all_p if p.get("revisor") == username]
        return sorted(all_p, key=lambda x: x.get("fecha_creacion", ""), reverse=True)

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
            _pg_delete(f"textos:{proyecto_id}")
            return
        proyectos = _json_load(PROYECTOS_FILE)
        proyectos.pop(proyecto_id, None)
        _json_save(PROYECTOS_FILE, proyectos)
        self.eliminar_textos_proyecto(proyecto_id)

    # ── Textos extraídos de los documentos (aparte del blob "liviano" del proyecto) ─────────
    # `proyecto["documentos"][i]` NO lleva `texto_extraido` embebido — solo `texto_len` (0 si
    # no tiene texto usable). El texto real vive en su propia clave "textos:{proyecto_id}"
    # ({doc_id: texto}), para que leer/guardar el proyecto (Resumen, aprobar/descartar una
    # observación, el dashboard, etc.) NO tenga que transferir ni deserializar el texto de
    # todos los documentos — puede pesar varios MB en un proyecto con muchos documentos
    # grandes — en cada click. Solo se cargan estos textos cuando de verdad hacen falta:
    # análisis de un ítem, chat, autocompletar Resumen, consulta libre, Chequeo de Cálculos y
    # evaluación de respuestas de subsanación (ver `_con_texto()` en main.py).

    def get_textos_proyecto(self, proyecto_id: str) -> dict:
        """{doc_id: texto_extraido} de un proyecto. {} si no tiene ninguno guardado."""
        if self._use_pg:
            return _pg_load(f"textos:{proyecto_id}")
        return _json_load(TEXTOS_DIR / f"{proyecto_id}.json")

    def set_texto_documento(self, proyecto_id: str, doc_id: str, texto: str):
        """Guarda/reemplaza el texto extraído de UN documento, sin tocar el resto de los
        textos del proyecto ni el blob liviano del proyecto."""
        self.set_textos_documentos(proyecto_id, {doc_id: texto})

    def set_textos_documentos(self, proyecto_id: str, nuevos: dict):
        """Como set_texto_documento(), pero para VARIOS documentos a la vez (subida múltiple o
        de un ZIP) — una sola lectura + escritura del blob de textos en vez de una por
        documento."""
        if not nuevos:
            return
        textos = self.get_textos_proyecto(proyecto_id)
        textos.update(nuevos)
        if self._use_pg:
            _pg_save(f"textos:{proyecto_id}", textos)
        else:
            _json_save(TEXTOS_DIR / f"{proyecto_id}.json", textos)

    def eliminar_texto_documento(self, proyecto_id: str, doc_id: str):
        textos = self.get_textos_proyecto(proyecto_id)
        if doc_id not in textos:
            return
        del textos[doc_id]
        if self._use_pg:
            _pg_save(f"textos:{proyecto_id}", textos)
        else:
            _json_save(TEXTOS_DIR / f"{proyecto_id}.json", textos)

    def eliminar_textos_proyecto(self, proyecto_id: str):
        if self._use_pg:
            _pg_delete(f"textos:{proyecto_id}")
            return
        filepath = TEXTOS_DIR / f"{proyecto_id}.json"
        if filepath.exists():
            filepath.unlink()

    def migrar_textos_documentos(self):
        """Migra el texto extraído embebido en `documentos[]` (formato legacy, de antes de
        separar los textos en su propia clave) a `textos:{proyecto_id}`, dejando en el
        documento liviano `texto_len` en vez del texto completo. Corre una vez al startup;
        en los despliegues siguientes se salta de inmediato gracias al marcador de abajo (sin
        el marcador, esta migración —que recorre el blob COMPLETO de cada proyecto— se
        repetiría en cada deploy de Railway, que en este proyecto son frecuentes)."""
        marcador = self._load("meta_textos_migrados", META_FILE)
        if marcador.get("hecho"):
            return
        migrados = 0
        for proyecto in self.get_proyectos():
            cambios = False
            textos = None
            for doc in proyecto.get("documentos", []):
                if "texto_extraido" not in doc:
                    continue
                if textos is None:
                    textos = self.get_textos_proyecto(proyecto["id"])
                texto = doc.pop("texto_extraido")
                textos[doc["id"]] = texto
                doc["texto_len"] = len(texto) if texto and texto != "__PDF_ESCANEADO__" else 0
                cambios = True
            if cambios:
                if self._use_pg:
                    _pg_save(f"textos:{proyecto['id']}", textos)
                else:
                    _json_save(TEXTOS_DIR / f"{proyecto['id']}.json", textos)
                self.save_proyecto(proyecto)
                migrados += 1
        self._save("meta_textos_migrados", META_FILE, {"hecho": True})
        print(f"✅ Migrados los textos de {migrados} proyecto(s) a su propia clave")

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
