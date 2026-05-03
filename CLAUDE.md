# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

**Revisor CNR** is a web app for reviewers at Chile's *Comisión Nacional de Riego* (CNR) to validate irrigation project submissions under Ley N° 18.450. Reviewers upload project documents (PDFs, Word, Excel, ZIP bundles), Claude analyzes each one against CNR regulations, and generates structured observations (mayor / menor / informativa) that feed into a printable review form (*ficha de revisión*).

## Running the server

```bash
# Start (from project root, with venv active)
source venv/bin/activate
python3 main.py

# Kill whatever is on port 8000 and restart cleanly
lsof -ti :8000 | xargs kill -9 2>/dev/null; sleep 1
python3 main.py > /tmp/cnr_server.log 2>&1 &
sleep 3 && curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/login

# Tail live errors
tail -f /tmp/cnr_server.log
```

The server runs on `http://localhost:8000`. There is no hot-reload — restart after any Python change.

## Environment

```
ANTHROPIC_API_KEY=sk-ant-...   # in ~/revisor-cnr/.env
SECRET_KEY=...                  # optional JWT override
```

`main.py` reads `.env` via `python-dotenv` and `os.chdir`s to its own directory on startup, so relative paths (`data/`, `uploads/`, `normativa/`, `static/`, `templates/`) always resolve from the project root regardless of where Python is invoked.

## Architecture

```
main.py          FastAPI routes — all business logic lives here
analyzer.py      Claude API calls (analysis, invalidation, consultation)
extractor.py     Text extraction from PDF / Word / Excel / ZIP
database.py      Thin JSON wrapper around data/proyectos.json + data/users.json
auth.py          bcrypt passwords + HS256 JWT (8 h expiry, stored in cookie)
normativa/       *.txt files loaded at startup into a single string (NORMATIVA_CNR)
uploads/         One sub-folder per project UUID; flat file layout
data/            proyectos.json, users.json (no SQL)
templates/       Jinja2 HTML (base.html, proyecto.html, ficha.html, consultar.html, …)
```

### Data model (proyectos.json)

Each project is a dict keyed by UUID:
```json
{
  "id": "uuid",
  "nombre": "...",
  "tipo_revision": "tecnica|legal",
  "revisor": "username",
  "estado": "En revisión",
  "documentos": [
    {
      "id": "uuid",
      "nombre_original": "...",
      "filename": "...",
      "tipo_doc": "estudio_hidrologico",
      "label": "Anexo 9.4 - ...",
      "texto_extraido": "... (up to 5000 chars)",
      "fecha_subida": "ISO datetime"
    }
  ],
  "observaciones": [
    {
      "id": "uuid",
      "doc_id": "...",
      "texto": "...",
      "severidad": "mayor|menor|informativa",
      "estado": "pendiente|aprobada|descartada",
      "articulo": "...",
      "fecha": "ISO datetime"
    }
  ],
  "consultas": []
}
```

`database.py` reads and writes the entire JSON file on every call — no transactions, no concurrency safety. Fine for single-user prototype.

### AI analysis flow (`analyzer.py`)

1. **Model selection** — `seleccionar_modelo(tipo_doc, es_escaneado)`:  
   - `DOCS_COMPLEJOS` set → `claude-sonnet-4-5` (2 500 tokens)  
   - everything else → `claude-haiku-4-5` (1 500 tokens)  
   - Scanned PDFs always use Sonnet (Vision API)

2. **Scanned PDFs** — `_from_pdf()` returns `"__PDF_ESCANEADO__"` sentinel when no text is found. `analyze_document()` detects this, calls `render_pdf_as_images()` (JPEG 75%, zoom 1.0×, max 4 pages, fallback to 0.7× if > 4 MB), and sends images via Claude Vision.

3. **Expediente context** — `_construir_contexto_expediente()` builds a manifest of all other documents in the project plus 500-char excerpts. This is injected into every analysis prompt so Claude can reference sibling documents and avoid false "missing document" observations.

4. **Response format** — Claude must return JSON:
   ```json
   {"observaciones": [{"texto": "...", "severidad": "mayor", "articulo": "..."}]}
   ```
   A two-attempt parser handles truncated JSON (closes open arrays/objects and retries).

5. **Auto-invalidation** — after saving new observations, `revisar_observaciones_previas()` is called with pending observations from *other* documents. Claude returns a list of IDs now resolved by the new document; those are auto-discarded with an appended note `[Auto-descartada: resuelta por <filename>]`.

6. **Prompt caching** — system prompt uses `cache_control: {"type": "ephemeral"}` (Anthropic beta header). Normativa is loaded once at startup.

### Annex auto-classification (`extractor.py`)

`ANEXOS_SEP` maps CNR annex numbers (`"9.4"`, `"9.4.2"`, …) to `(tipo_doc, label)`. Keys are sorted longest-first (`ANEXOS_ORDEN`) so `"9.4.2"` matches before `"9.4"`. Pattern matching uses `re.search` against the filename.

### Observation states and UI

| Estado | Meaning |
|---|---|
| `pendiente` | Suggested by AI, not yet reviewed |
| `aprobada` | Reviewer confirmed it |
| `descartada` | Rejected or auto-invalidated |

In `proyecto.html`: mayor/menor observations render in a red-tinted card; `informativa` observations render in a separate blue "💡 Notas" card. The ficha (`/proyecto/{id}/ficha`) only includes `aprobada` non-informative observations.

## Key constraints and gotchas

- **Image size limit**: Claude API rejects images > 5 MB. `render_pdf_as_images` uses JPEG (not PNG) at 75% quality, zoom 1.0×, with automatic fallback to 0.7× for large pages. `media_type` in the API call must be `"image/jpeg"`.
- **JSON parse failures**: If Claude returns truncated JSON (max_tokens hit), the parser appends `]}` and retries. Increasing `MAX_TOKENS_*` reduces this risk; do not lower them.
- **No hot-reload**: Changes to Python files require a manual server restart.
- **Normativa is static**: `NORMATIVA_CNR` is loaded at import time from `normativa/*.txt`. Adding new `.txt` files there requires a restart to take effect.
- **User creation**: There is no registration UI. Add users programmatically via `db.create_user(username, password, nombre, rol)` or by editing `data/users.json` directly.
