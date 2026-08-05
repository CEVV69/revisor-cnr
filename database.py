"""Base de datos: PostgreSQL en producción, JSON en desarrollo local."""
import functools
import json
import os
import threading
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
CRITERIOS_ITEM_FILE = DATA_DIR / "criterios_item.json"
META_FILE        = DATA_DIR / "meta.json"
# Textos extraídos de los documentos, uno por proyecto (modo JSON local — en PostgreSQL van
# bajo la clave "textos:{proyecto_id}" de la tabla storage). Ver la nota en
# Database.get_textos_proyecto() sobre por qué viven aparte del proyecto.
TEXTOS_DIR       = DATA_DIR / "textos"

# ── Backend PostgreSQL ─────────────────────────────────────────────────────────
_pg_conn = None

# Toda la app compartía UNA sola conexión psycopg2 y, hasta ago-2026, todo el código que la usaba
# corría en el mismo hilo (el event loop), así que no hacía falta sincronizar nada. Desde que
# `_restaurar_archivos_necesarios` se llama vía `asyncio.to_thread` (main.py — restaura desde la
# base los PDF perdidos en un redeploy, y bloqueaba el event loop entero mientras lo hacía), hay
# un segundo hilo tocando la misma conexión.
#
# psycopg2 declara `threadsafety = 2` ("threads may share the module and connections"), y cada
# función de acá abre su PROPIO cursor (`with conn.cursor()`), que es la condición que exige —
# los cursores no se comparten. Lo que NO cubre esa garantía es el camino de reconexión de
# `_reintenta_si_cae`: cierra y reemplaza la variable global `_pg_conn` mientras otro hilo podría
# estar usando la conexión vieja. Este lock cierra esa ventana.
#
# Va en `_reintenta_si_cae` porque las 12 funciones que tocan Postgres pasan sin excepción por
# ese decorador — un solo punto en vez de 12. Es RLock (re-entrante) por prudencia: si alguna vez
# una función decorada llama a otra, un Lock simple se trabaría solo. No cuesta rendimiento: el
# acceso a la base YA estaba serializado de hecho (un solo hilo); esto solo lo hace explícito y
# seguro ahora que hay dos.
_pg_lock = threading.RLock()

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


def _reintenta_si_cae(fn):
    """Reintenta UNA vez con conexión nueva si la consulta falla porque la conexión guardada
    estaba muerta.

    `_get_pg()` por sí solo NO alcanza: psycopg2 marca `conn.closed` solo cuando el cliente
    cierra la conexión, no cuando el servidor la cortó por su cuenta (reinicio de Postgres en
    Railway, timeout de inactividad, corte de red). En ese caso `_get_pg()` devuelve tan campante
    una conexión muerta y el error recién aparece al ejecutar la consulta — como esa excepción no
    la atrapaba nadie, la app quedaba devolviendo error 500 en TODAS las páginas hasta que se
    reiniciara el proceso completo. Con esto se recupera sola.

    El reintento es seguro para lectura y escritura: todas las escrituras de este módulo son
    idempotentes (UPSERT con ON CONFLICT DO UPDATE, o DELETE), así que repetirlas no duplica ni
    corrompe nada."""
    @functools.wraps(fn)
    def envoltorio(*args, **kwargs):
        global _pg_conn
        import psycopg2
        with _pg_lock:               # ver la nota de _pg_lock, arriba
            try:
                return fn(*args, **kwargs)
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                print(f"⚠️ Conexión PostgreSQL caída en {fn.__name__} ({e}) — reconectando y reintentando…")
                try:
                    if _pg_conn is not None and not _pg_conn.closed:
                        _pg_conn.close()
                except Exception:
                    pass
                _pg_conn = None      # fuerza reconexión limpia en el _get_pg() de adentro
                return fn(*args, **kwargs)
    return envoltorio


@_reintenta_si_cae
def _pg_load(key: str) -> dict:
    conn = _get_pg()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM storage WHERE key = %s", (key,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else {}


@_reintenta_si_cae
def _pg_save(key: str, data: dict):
    conn = _get_pg()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO storage (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(data, ensure_ascii=False)))


@_reintenta_si_cae
def _pg_load_prefix(prefix: str) -> list:
    """Carga todos los values cuyo key empieza con `prefix` (una sola query)."""
    conn = _get_pg()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM storage WHERE key LIKE %s", (prefix + "%",))
        return [json.loads(r[0]) for r in cur.fetchall()]


@_reintenta_si_cae
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


@_reintenta_si_cae
def _pg_load_campos(key: str, campos: list) -> dict:
    """Como _pg_load, pero deja que Postgres arme un objeto SOLO con los `campos` pedidos, en vez
    de traer y deserializar el JSON completo de la fila. Misma advertencia que
    _pg_load_prefix_campos: `campos` son nombres FIJOS del código, nunca input de un request."""
    conn = _get_pg()
    partes = ", ".join(f"'{c}', v -> '{c}'" for c in campos)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT jsonb_build_object({partes})
            FROM (SELECT value::jsonb AS v FROM storage WHERE key = %s) t
        """, (key,))
        row = cur.fetchone()
        return row[0] if row else None


@_reintenta_si_cae
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

    def update_nombre(self, username: str, nuevo_nombre: str):
        users = self._load("users", USERS_FILE)
        if username in users:
            users[username]["nombre"] = nuevo_nombre
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
        # `or ""`: la proyección de Postgres devuelve el campo en null (no ausente) si el proyecto
        # no lo tiene, y ordenar mezclando None con str revienta con TypeError — tumbaría el
        # dashboard entero por un solo proyecto legado sin fecha_creacion.
        return sorted(all_p, key=lambda x: x.get("fecha_creacion") or "", reverse=True)

    def get_proyecto(self, proyecto_id: str) -> dict:
        if self._use_pg:
            return _pg_load(f"proyecto:{proyecto_id}") or None
        return _json_load(PROYECTOS_FILE).get(proyecto_id)

    def get_proyecto_campos(self, proyecto_id: str, campos: list) -> dict:
        """Como get_proyecto(), pero trae SOLO los `campos` pedidos — para endpoints que se
        consultan seguido y no necesitan el proyecto entero. El caso que motivó esto es el
        *polling* de `estado_item` (cada 4 segundos mientras dura un análisis en segundo plano):
        con `get_proyecto()` traía y deserializaba todas las observaciones del proyecto en cada
        vuelta solo para leer 3 campos de estado.

        Devuelve None si el proyecto no existe. `campos` son nombres FIJOS del propio código,
        nunca datos de un request (ver la advertencia de _pg_load_prefix_campos)."""
        if not self._use_pg:
            p = _json_load(PROYECTOS_FILE).get(proyecto_id)
            return {k: p.get(k) for k in campos} if p else None
        return _pg_load_campos(f"proyecto:{proyecto_id}", campos)

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

    # ── Criterios de énfasis por ítem (PERMANENTES, jul-2026) ──────────────────
    # Antes vivían colgados de cada concurso por separado — en la práctica casi siempre
    # aplicaban igual sin importar el concurso, así que pasaron a ser un blob único GLOBAL
    # (mismo patrón que precios), editado por el revisor en /admin/aprendizaje. El campo
    # `criterios_enfasis` que queda en cada concurso ahora es solo para EXCEPCIONES puntuales
    # de ese concurso en particular (ver migrar_criterios_enfasis y CLAUDE.md).

    def get_criterios_item(self) -> dict:
        """Estructura: {"criterios": {"item_"+item_key: "texto"}, "fecha_actualizado",
        "actualizado_por"}. {} si nunca se ha guardado nada."""
        return self._load("criterios_item", CRITERIOS_ITEM_FILE)

    def save_criterios_item(self, data: dict):
        self._save("criterios_item", CRITERIOS_ITEM_FILE, data)

    def migrar_criterios_enfasis(self):
        """Migración única (jul-2026): los "Criterios de énfasis por ítem" pasaron de ser por
        concurso a PERMANENTES/globales. Copia lo que ya hubiera guardado en cada
        concurso["criterios_enfasis"] al nuevo blob global (gana el primero que se encuentre
        por item_key — en la práctica solo un concurso tenía datos reales al momento de este
        cambio) y deja el campo de cada concurso vacío, listo para su nuevo uso: excepciones
        puntuales de ESE concurso en particular. Idempotente vía marcador, mismo patrón que
        migrar_textos_documentos()."""
        marcador = self._load("meta_criterios_enfasis_migrados", META_FILE)
        if marcador.get("hecho"):
            return
        globales = self.get_criterios_item()
        criterios = dict(globales.get("criterios", {}))
        migrados = 0
        for concurso in self.get_all_concursos():
            propios = concurso.get("criterios_enfasis") or {}
            if not propios:
                continue
            for k, v in propios.items():
                if v and k not in criterios:
                    criterios[k] = v
                    migrados += 1
            concurso["criterios_enfasis"] = {}
            self.save_concurso(concurso)
        if migrados:
            globales["criterios"] = criterios
            self.save_criterios_item(globales)
            print(f"✅ Migrados {migrados} criterio(s) de énfasis de concursos a la colección global")
        self._save("meta_criterios_enfasis_migrados", META_FILE, {"hecho": True})

    # ── Archivos físicos (persistencia contra deploys efímeros de Railway) ──────
    # Solo aplica en modo PostgreSQL: en modo JSON local el disco ya persiste entre
    # ejecuciones, así que estos métodos son no-op.

    @_reintenta_si_cae
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

    @_reintenta_si_cae
    def obtener_archivo(self, proyecto_id: str, doc_id: str) -> bytes:
        if not self._use_pg:
            return None
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("SELECT contenido FROM archivos WHERE proyecto_id=%s AND doc_id=%s",
                        (proyecto_id, doc_id))
            row = cur.fetchone()
            return bytes(row[0]) if row else None

    @_reintenta_si_cae
    def ids_con_archivo(self, proyecto_id: str) -> set:
        """IDs de documentos con archivo guardado en la base (chequeo en lote, evita N
        consultas al armar la tabla de documentos de un proyecto)."""
        if not self._use_pg:
            return set()
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("SELECT doc_id FROM archivos WHERE proyecto_id=%s", (proyecto_id,))
            return {r[0] for r in cur.fetchall()}

    @_reintenta_si_cae
    def eliminar_archivo(self, proyecto_id: str, doc_id: str):
        if not self._use_pg:
            return
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM archivos WHERE proyecto_id=%s AND doc_id=%s",
                        (proyecto_id, doc_id))

    @_reintenta_si_cae
    def eliminar_archivos_proyectos(self, proyecto_ids: list):
        """Borra TODOS los archivos guardados de una lista de proyectos (ej. al dar por
        terminado un concurso). No toca texto_extraido/observaciones — solo libera espacio."""
        if not self._use_pg or not proyecto_ids:
            return
        conn = _get_pg()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM archivos WHERE proyecto_id = ANY(%s)", (list(proyecto_ids),))

    @_reintenta_si_cae
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
