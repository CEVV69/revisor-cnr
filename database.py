"""Base de datos simple en JSON para el prototipo"""
import json
import os
from pathlib import Path
from auth import hash_password

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
PROYECTOS_FILE = DATA_DIR / "proyectos.json"
CONCURSOS_FILE = DATA_DIR / "concursos.json"


class Database:
    def _load(self, filepath: Path) -> dict:
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self, filepath: Path, data: dict):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Usuarios ──────────────────────────────────────────────────────────────

    def get_user(self, username: str) -> dict:
        users = self._load(USERS_FILE)
        return users.get(username)

    def get_all_users(self) -> list:
        users = self._load(USERS_FILE)
        return sorted(users.values(), key=lambda u: u["username"])

    def delete_user(self, username: str):
        users = self._load(USERS_FILE)
        users.pop(username, None)
        self._save(USERS_FILE, users)

    def create_user(self, username: str, password: str, nombre: str, rol: str):
        users = self._load(USERS_FILE)
        users[username] = {
            "username": username,
            "password_hash": hash_password(password),
            "nombre": nombre,
            "rol": rol
        }
        self._save(USERS_FILE, users)

    def update_password(self, username: str, new_password: str):
        users = self._load(USERS_FILE)
        if username in users:
            users[username]["password_hash"] = hash_password(new_password)
            self._save(USERS_FILE, users)

    # ── Proyectos ─────────────────────────────────────────────────────────────

    def get_proyectos(self, username: str = None) -> list:
        proyectos = self._load(PROYECTOS_FILE)
        all_p = list(proyectos.values())
        if username:
            all_p = [p for p in all_p if p["revisor"] == username]
        return sorted(all_p, key=lambda x: x["fecha_creacion"], reverse=True)

    def get_proyecto(self, proyecto_id: str) -> dict:
        proyectos = self._load(PROYECTOS_FILE)
        return proyectos.get(proyecto_id)

    def save_proyecto(self, proyecto: dict):
        proyectos = self._load(PROYECTOS_FILE)
        proyectos[proyecto["id"]] = proyecto
        self._save(PROYECTOS_FILE, proyectos)

    def _proyectos_file(self):
        return PROYECTOS_FILE

    # ── Concursos ─────────────────────────────────────────────────────────────

    def get_concurso(self, concurso_id: str) -> dict:
        concursos = self._load(CONCURSOS_FILE)
        return concursos.get(concurso_id)

    def get_all_concursos(self) -> list:
        concursos = self._load(CONCURSOS_FILE)
        return sorted(concursos.values(), key=lambda c: c.get("id", ""))

    def save_concurso(self, concurso: dict):
        concursos = self._load(CONCURSOS_FILE)
        concursos[concurso["id"]] = concurso
        self._save(CONCURSOS_FILE, concursos)

    def add_feedback_concurso(self, concurso_id: str, feedback_entry: dict):
        """Añade una entrada de feedback al historial del concurso (máx. 200)."""
        concurso = self.get_concurso(concurso_id)
        if concurso is None:
            return
        if "feedback" not in concurso:
            concurso["feedback"] = []
        concurso["feedback"].append(feedback_entry)
        # Conservar solo los últimos 200 para no inflar el archivo
        concurso["feedback"] = concurso["feedback"][-200:]
        self.save_concurso(concurso)


db = Database()
