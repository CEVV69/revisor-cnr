# CLAUDE.md — Revisor CNR

Guía para Claude (Claude Code, claude.ai/code o chat web) al trabajar en este repositorio.
**Escribe siempre en español**, incluso en notas técnicas y de versión.

---

## Qué hace este proyecto

**Revisor CNR** es una app web para los revisores de la Comisión Nacional de Riego (CNR)
de Chile. Permite validar proyectos de riego postulados bajo la **Ley N° 18.450**.
El revisor sube los documentos del proyecto (PDF, Word, Excel, ZIP), Claude los analiza
contra la normativa CNR + las bases del concurso, y genera observaciones estructuradas
(mayor / menor / informativa) que alimentan una **ficha de revisión** imprimible y
descargable en PDF.

---

## Cómo trabajar en este proyecto

### Desde la oficina (navegador, sin instalar nada)
Todo el código está en GitHub: **`CEVV69/revisor-cnr`**. Cada `git push` a `main`
dispara automáticamente un deploy en Railway. Para trabajar desde el navegador:
- **Recomendado:** `claude.ai/code` → conectar el repo `CEVV69/revisor-cnr` → editar,
  commitear y pushear desde la nube (dispara el deploy solo).
- El chat normal de claude.ai con el conector de GitHub sirve para leer/razonar, pero
  para commitear/pushear es limitado.

### Desde Claude Code local (Mac)
```bash
cd ~/revisor-cnr
source venv/bin/activate
python3 main.py          # corre en http://localhost:8000 (sin hot-reload)
```
El usuario corre los comandos de servidor él mismo — dale el comando, no lo levantes tú.

### Deploy
`git push` a `main` → Railway despliega en ~1-2 min → `revisor-cnr-production.up.railway.app`.
El push automático ya está configurado por SSH (no pide credenciales).

---

## Stack

- **Backend:** FastAPI + Jinja2 (renderizado server-side, sin framework JS)
- **Base de datos:** PostgreSQL en Railway (persiste). En local sin `DATABASE_URL` usa JSON.
- **IA:** Anthropic API — Claude Haiku 4.5 (simples) / Sonnet 4.5 (complejos)
- **Auth:** JWT (HS256, 8 h, en cookie) + bcrypt
- **Extracción:** PyMuPDF (fitz), python-docx, openpyxl, xlrd

## Variables de entorno (Railway)
```
ANTHROPIC_API_KEY   → clave Anthropic
DATABASE_URL        → postgresql://...@postgres.railway.internal:5432/railway
DATA_DIR            → /storage/data     (solo fallback JSON local)
UPLOAD_DIR          → /storage/uploads
```
> **Los volúmenes de Railway NO funcionan** en esta cuenta (no montan). La persistencia
> se resolvió con **PostgreSQL**. Ignorar cualquier volumen que aparezca en el dashboard.

---

## Arquitectura de archivos

```
main.py          Rutas FastAPI — toda la lógica de negocio vive aquí
analyzer.py      Llamadas a Claude (análisis, invalidación cruzada, consulta libre)
extractor.py     Extracción de texto de PDF / Word / Excel / ZIP + clasificación de anexos
database.py      Capa dual: PostgreSQL si hay DATABASE_URL, si no JSON local
auth.py          bcrypt + JWT
normativa/       *.txt de normativa CNR, cargados al inicio (máx 4.000 chars c/u)
uploads/         Una subcarpeta por proyecto (NO persiste entre deploys)
templates/       Jinja2 (base.html, proyecto.html, ficha.html, admin_concursos.html, …)
```

### Modelo de datos (PostgreSQL: tabla `storage (key TEXT, value TEXT)`)
Tres colecciones guardadas como JSON bajo las claves `users`, `proyectos`, `concursos`.

- **proyectos** → dict keyed por UUID: `id, nombre, codigo_sep, postulante, tipo_revision,
  revisor, revisor_nombre, estado, documentos[], observaciones[], consultas[]`.
  - `documentos[]`: `id, nombre_original, filename, tipo_doc, label, texto_extraido,
    analizado (bool), fecha_subida`.
  - `observaciones[]`: `id, doc_id, doc_nombre, texto, categoria, severidad
    (mayor|menor|informativa), referencia_normativa, estado (pendiente|aprobada|descartada),
    fecha`.
- **concursos** → `id (ej "204-2026"), nombre, bases_texto, feedback[], fecha_*`.
  - `feedback[]`: decisiones reales del revisor (`accion: aprobada|descartada, tipo_doc,
    texto_obs, fecha`) — alimenta el aprendizaje. Máx 200 por concurso.

`database.py` lee/escribe la colección completa en cada llamada (sin transacciones).
Suficiente para uso mono-usuario.

---

## Flujo de análisis IA (`analyzer.py`)

1. **Selección de modelo** — `seleccionar_modelo(tipo_doc, es_escaneado)`:
   - `DOCS_FORZAR_HAIKU` (ej. `reporte_explorador_solar`) → Haiku aunque sea imagen
   - `DOCS_COMPLEJOS` o escaneado → Sonnet
   - resto → Haiku
2. **Detección de imagen** — PDF con < `MIN_CHARS_TEXTO` (300) de texto → se trata como
   escaneado y se procesa con **visión**. `DOCS_FORZAR_VISION` (solar) siempre usa visión.
3. **Visión** — `render_pdf_as_images()` (JPEG 70%, zoom 0.8×). Páginas máx por tipo en
   `MAX_PAGINAS_POR_TIPO` (solar=15, FV/hidráulico/agronómico=8, resto=5).
4. **Límite de caracteres por tipo** — `MAX_CHARS_POR_TIPO` (solar 40k, agronómico 35k,
   presupuesto 30k, FV/hidráulico 25k, …). Truncación inteligente: 75% inicio + 25% final.
5. **Contexto del expediente** — `_construir_contexto_expediente()` inyecta el manifiesto
   de todos los documentos + extractos de los ya analizados, para evitar falsos "falta X".
6. **Bases del concurso** — se inyectan como 2º bloque cacheado del system prompt.
7. **Feedback** — `_construir_bloque_feedback()` mete ejemplos reales aprobados/descartados.
8. **Prompt caching** — normativa + bases con `cache_control: ephemeral` (header beta).
9. **Auto-invalidación** — `revisar_observaciones_previas()` descarta obs de otros
   documentos que este nuevo documento resuelve.
10. **Parser JSON** — dos intentos; el 2º cierra llaves/corchetes abiertos si se truncó.

### Tipos de documento (`TIPOS_DOC` / `TIPO_DOC_ORDEN` / `TIPO_DOC_LABELS`)
Plano ubicación · Identificación área riego · Análisis hidrológico · Prueba de bombeo ·
Diseño hidráulico · Diseño agronómico · Diseño fotovoltaico · Reporte Explorador Solar ·
Estudios complementarios · Especificaciones técnicas · Cronograma · Cubicaciones ·
Presupuesto obras · Presupuesto electrificación · Cotizaciones y Facturas · Cotizaciones ·
Declaración IVA · Planos tecnificación · Planos obras civiles · Memoria superficies ·
Estudio suelos · Evaluación Social MIDESO · Antecedentes legales · Lista beneficiarios · Otro.

---

## Criterio de análisis (SYSTEM_PROMPT en `analyzer.py`)

Tres preguntas guía antes de observar:
1. ¿El proyecto va a **funcionar** correctamente como sistema de riego?
2. ¿Los **precios** son razonables, sin sobreprecios?
3. ¿El **diseño** tiene lógica técnica y es proporcional a la escala?

- **Regla de oro:** ante la duda, NO observar. Máx ~10-15 obs por documento.
- Observaciones describen **solo incumplimientos** — nunca mencionan lo que sí cumple.
- **Notación chilena** reforzada en cada prompt: coma = decimal, punto = miles.
- Criterio de ingeniero: ¿puede construirse?, ¿ejecutable en terreno?, ¿precios de mercado?

---

## Funcionalidades implementadas ✅

- Subida PDF/Word/Excel/ZIP → extracción → clasificación por anexo
- **Revisión por EJES TEMÁTICOS** (método único — ver abajo). El análisis documento-por-documento
  fue eliminado de raíz (ruta, funciones y UI removidas).
- **🗑 Limpiar revisión** — borra obs/notas/estado, conserva los archivos
- Bases del concurso (admin `/admin/concursos`): subir PDF → extrae texto → se cachea
- Feedback del revisor (aprobar/descartar) → aprendizaje
- Dark mode automático 19:00–07:00 con toggle manual (localStorage)
- Estados del proyecto: En revisión / Revisado / Observado / Rechazado
- Documentos ordenados por tipo · conteo analizados/pendientes
- **Ficha de revisión** (`/proyecto/{id}/ficha`): HTML imprimible + descargar PDF
  (html2pdf.js), letra 13px, título centrado, sin firmas ni "R)"
- Ver documento: si el archivo físico no existe (post-deploy), muestra el texto extraído

---

## Revisión por EJES TEMÁTICOS (método único)

**Problema que resuelve:** revisar documento por documento era erróneo porque los documentos
son complementarios (el agronómico define la demanda que el hidráulico satisface; el plano
debe reflejar el diseño; el presupuesto debe cuadrar con las obras). Evaluarlos aislados
generaba falsas observaciones. Ese método fue **eliminado**.

**Implementado (backbone):** `EJES_REVISION` en `analyzer.py` define los 9 ejes (tipo_docs +
checklist). `analizar_eje()` cruza TODOS los documentos del eje en UNA llamada a Sonnet y
devuelve observaciones tageadas con `eje`. Ruta `POST /proyecto/{id}/revisar-eje/{eje_key}`.
UI: panel de 9 ejes en `proyecto.html` bajo la tabla de documentos. Las obs de eje se guardan
con `obs.eje`, `obs.eje_nombre`; el feedback se etiqueta por eje.

**Visión en ejes:** `analizar_eje` usa texto extraído + IMÁGENES para documentos escaneados/planos
(los que no tienen texto). Renderiza páginas con `render_pdf_as_images` (tope global `MAX_IMG_EJE=10`)
y las envía como bloques de imagen. Requiere que el archivo físico exista (`ruta_uploads`); como los
uploads NO persisten entre deploys, para ver planos/escaneados hay que tenerlos subidos en la sesión
actual. El eje Coherencia es solo texto (no visión, por costo).

**Chat de refinamiento por eje (implementado):** `chatear_eje()` en `analyzer.py`, ruta
`POST /proyecto/{id}/eje/{eje_key}/chat`. El historial se guarda en `proyecto["eje_chats"][eje_key]`
(lista de `{rol: revisor|ia, texto, fecha}`, últimos 40 turnos). UI: sección "💬 Debatir con la IA"
con un `<details>` por eje revisado. La IA responde con contexto del eje (documentos + observaciones
actuales + bases). Aún NO modifica observaciones automáticamente — el revisor edita/descarta a mano.

**Pendiente:** consolidación de aprendizaje por eje (destilar feedback en criterios).

**Los 9 ejes definidos:**
| # | Eje | Documentos que cruza |
|---|---|---|
| 1 | **Superficie** ⭐ | Memoria superficies · Identificación área riego · Planos · Estudio suelos · Título dominio |
| 2 | Agronómico | Diseño agronómico · Estudio suelos · Superficie |
| 3 | Hidrológico | Estudio hidrológico · Derechos de agua · Prueba de bombeo |
| 4 | Hidráulico | Diseño hidráulico · Planos tecnificación · Especificaciones técnicas · Prueba bombeo |
| 5 | Energético/Fotovoltaico | Diseño FV · Explorador solar · Presupuesto eléctrico · Diseño hidráulico |
| 6 | Obras civiles | Planos obras civiles · Especificaciones técnicas · Cubicaciones |
| 7 | Presupuesto y costos | Presupuesto obras · Presupuesto eléctrico · Cubicaciones · APU · Cotizaciones |
| 8 | Legal/administrativo | Antecedentes legales · F22 · Títulos · Derechos agua · OUA · Lista benef. · IVA · Consultor MOP |
| 9 | **Coherencia global** ⭐ | *Todos* — cierre transversal: superficie ↔ demanda ↔ caudal ↔ diseño ↔ presupuesto ↔ monto bonificable |

Eje 1 (Superficie) es la base: define demanda, escala, presupuesto y monto bonificable.
Eje 9 (Coherencia global) es el cierre que atrapa los errores entre documentos.

**Plan de aprendizaje ("revisor experto"):** consolidar periódicamente el `feedback[]` de
cada concurso en un documento de **criterios aprendidos por eje** (reglas concretas), que
se inyecta en el prompt. Deja de ser ejemplos sueltos y pasa a ser un manual de criterio
propio que se afina con el uso.

---

## Restricciones y gotchas

- **Archivos subidos NO persisten entre deploys** (Railway efímero). El `texto_extraido`
  sí persiste (PostgreSQL). Para re-análisis con visión hay que volver a subir el archivo.
- **Límite de imagen Claude API:** 5 MB. `render_pdf_as_images` usa JPEG con fallback.
- **Sin hot-reload local:** reiniciar el server tras cambios en Python.
- **Normativa estática:** `NORMATIVA_CNR` se carga al importar; agregar .txt requiere reinicio.
- **Sin UI de registro:** crear usuarios con `db.create_user(...)`. Admin por defecto:
  `admin / admin123` (se crea al inicio si no existe).

---

## Instrucciones del usuario (SIEMPRE respetar)

1. **Paso a paso** — nunca asumir, guiar con pasos numerados.
2. **Usa Safari** — el navegador solo tiene acceso de lectura en computer-use.
3. **Nunca reescribir archivos completos sin leer primero** — usar Edit, no Write sobre
   archivos existentes (salvo docs claramente obsoletos como este, ya leídos).
4. **Español siempre**, incluso en textos técnicos.
5. No acumular archivos sueltos de apoyo — entregar SQL/scripts en el chat.
6. El usuario es técnico en riego/CNR — entiende la terminología.
