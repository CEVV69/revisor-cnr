# CLAUDE.md — Revisor CNR

Guía para Claude (Claude Code, claude.ai/code o chat web) al trabajar en este repositorio.
**Escribe siempre en español**, incluso en notas técnicas y de versión.

---

## ⚠️ SINCRONIZACIÓN — OBLIGATORIO (léelo primero)

El usuario trabaja este proyecto desde DOS lugares (su Mac en casa y `claude.ai/code` en la
oficina). Para que nunca se pierda ni se pise trabajo, TODA sesión de Claude debe:

1. **AL EMPEZAR:** hacer `git pull` como primer paso, ANTES de leer o editar nada más.
   Así se baja lo que haya hecho el otro entorno. (En `claude.ai/code` el repo suele venir
   ya actualizado, pero igual verifica el último commit.)
2. **AL TERMINAR cada cambio:** hacer `git add` + `git commit` + `git push` para subir todo
   a GitHub. Nunca dejar cambios sin pushear al cerrar la sesión.

El usuario NO ejecuta comandos git — los ejecuta Claude. El usuario no necesita pedirlo:
es el comportamiento por defecto en cada sesión. Si hay decisiones de fondo, anótalas en
este CLAUDE.md y súbelas, para que el otro entorno las lea.

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
- **IA:** Anthropic API — Claude **Sonnet 5** (revisión por ejes/ítems, chat y consultas) ·
  Haiku 4.5 (tareas de resumen: autocompletar resumen, destilar aprendizaje)
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
> se resolvió con **PostgreSQL** — datos (`storage`) y, desde jul-2026, también los
> **archivos subidos** (tabla `archivos`, ver sección "Restricciones y gotchas" más abajo).
> Ignorar cualquier volumen que aparezca en el dashboard.

---

## Arquitectura de archivos

```
main.py          Rutas FastAPI — toda la lógica de negocio vive aquí
analyzer.py      Llamadas a Claude (análisis, invalidación cruzada, consulta libre)
extractor.py     Extracción de texto de PDF / Word / Excel / ZIP + clasificación de anexos
database.py      Capa dual: PostgreSQL si hay DATABASE_URL, si no JSON local
auth.py          bcrypt + JWT
normativa/       *.txt de normativa CNR, cargados al inicio (máx 4.000 chars c/u)
                 Incluye DT-*, IL-*, Manual_Supervision y criterios destilados de los
                 Instructivos de Tecnificación (ITT-01 a ITT-04 + ITT_Criterios), extraídos
                 del PDF oficial del Drive para guiar la revisión sin cargar el PDF completo.
uploads/         Una subcarpeta por proyecto. El disco NO persiste entre deploys, pero cada
                 archivo se respalda también en Postgres (tabla `archivos`) y se restaura
                 solo cuando hace falta — ver "Restricciones y gotchas".
templates/       Jinja2 (base.html, proyecto.html, ficha.html, admin_concursos.html, …)
```

### Modelo de datos (PostgreSQL: tabla `storage (key TEXT, value TEXT)`)
CUATRO colecciones guardadas como JSON: `users`, `proyectos`, `concursos`, `consultores`.

- **proyectos** → dict keyed por UUID: `id, nombre, codigo_sep, postulante, tipo_revision,
  revisor, revisor_nombre, estado, documentos[], observaciones[], consultas[]`, y además
  `resumen{}` (ficha-formulario), `ejes_revisados{}`, `items_revisados{}`, `eje_chats{}`.
  - `documentos[]`: `id, nombre_original, filename, tipo_doc, tipo_doc_label, texto_extraido,
    analizado (bool), fecha_subida`.
  - `observaciones[]`: `id, texto, categoria, severidad (mayor|menor|informativa),
    referencia_normativa, estado (pendiente|aprobada|descartada), numero, fecha`. Las de EJE
    llevan `eje`+`eje_nombre`; las de ÍTEM SEP llevan `item`+`item_nombre`.
- **concursos** → `id (ej "204-2026"), nombre, bases_texto, feedback[], fecha_*`, más
  `criterios_aprendidos{}` (clave eje_key o "item_"+item_key → texto destilado) y `criterios_fecha`.
  - `feedback[]`: decisiones reales del revisor (`accion: aprobada|descartada, tipo_doc,
    texto_obs, fecha`). `tipo_doc` = eje_key, "item_"+item_key o tipo_doc real. Máx 200.
- **consultores** → keyed por nombre normalizado (`_consultor_key`): `key, nombre, feedback[]
  (máx 300, cruza concursos), perfil (texto destilado), perfil_fecha`.

`database.py` lee/escribe la colección completa en cada llamada (sin transacciones).
Suficiente para uso mono-usuario.

---

## Flujo de análisis IA (`analyzer.py`) — núcleo `_analizar_grupo()`

El análisis documento-por-documento fue **eliminado**. Hoy todo pasa por `_analizar_grupo()`,
que revisa un GRUPO de documentos (un eje temático o un ítem del SEP) en UNA llamada a Sonnet 5.
`analizar_eje()` y `analizar_item()` son envoltorios delgados sobre él.

1. **Selección de documentos** — el envoltorio pasa los documentos del grupo (`_documentos_del_eje`
   para ejes; filtro por `tipo_docs` para ítems). Coherencia global usa todos los con texto.
2. **Texto vs imagen** — docs con `texto_extraido` van como texto; escaneados/planos (texto
   `< MIN_CHARS_TEXTO` = 300, o `__PDF_ESCANEADO__`) van por **visión** si el archivo físico
   existe (`render_pdf_as_images`, JPEG, tope global `MAX_IMG_EJE=10`). Coherencia NO usa visión.
3. **Presupuesto de caracteres** — `MAX_CHARS_EJE_TOTAL=45000` repartido entre los docs del
   grupo (`_truncar_inteligente`).
4. **Manifiesto del expediente** — se inyecta la lista de TODOS los tipos de documento presentes,
   para que la IA detecte faltantes obligatorios ("Se sugiere declarar no admitido.").
5. **System cacheado** — `SYSTEM_PROMPT` (normativa) + bases del concurso, con
   `cache_control: ephemeral` (header beta de prompt caching).
6. **Aprendizaje** — si el concurso tiene `criterios_aprendidos` del grupo, se inyectan (compactos);
   si no, `_construir_bloque_feedback` mete ejemplos crudos. Además `_construir_bloque_consultor`
   inyecta el perfil/historial del consultor del proyecto.
7. **max_tokens** — `MAX_TOKENS_SONNET=12000` (Sonnet 5 gasta parte en *thinking*, ver bug abajo).
8. **Parser JSON** — dos intentos; el 2º cierra llaves/corchetes si se truncó. Si vuelve vacío,
   loguea `stop_reason` + preview.

`seleccionar_modelo`, `MAX_CHARS_POR_TIPO`, `MAX_PAGINAS_POR_TIPO`, `DOCS_FORZAR_*` siguen
definidos pero eran del flujo viejo; hoy el análisis por grupo usa siempre Sonnet 5.

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
- **Redacción de la observación (`texto`):** breve y directa (máx 2-3 líneas), sin relatar
  antecedentes largos. Cada obs mayor/menor cierra con una frase explícita:
  `"Debe aclarar."` (precisar/resolver ambigüedad), `"Debe justificar."` (falta fundamento
  técnico/normativo) o `"Se sugiere declarar no admitido."` (falta un documento obligatorio
  exigido por las bases). Las notas informativas no llevan cierre.
- **Documentos obligatorios:** `_analizar_grupo` inyecta un manifiesto de TODOS los tipos de
  documento presentes en el expediente para que la IA detecte faltantes obligatorios.
- **Observaciones agrupadas por eje/ítem:** en `proyecto.html` y en la ficha, las obs se
  muestran bajo UN solo título por eje/ítem (no un encabezado por observación). El
  agrupamiento se arma en `ver_proyecto()` / `ficha_revision()` y se pasa a la plantilla.
  **OJO Jinja:** la clave de la lista de observaciones dentro de cada grupo es `obs`
  (`grupo.obs`), NO `items` — `grupo.items` colisiona con el método `dict.items()` y rompe
  el render en runtime (bug ya sufrido). Nunca usar `items` como nombre de clave de grupo.

## Cuatro PÁGINAS del proyecto (no pestañas) — navegación arriba

`proyecto.html` es **una sola plantilla** que renderiza 4 páginas según la variable `pagina`,
con una barra de navegación arriba (`.proj-nav`/`.proj-tab`). Son URLs reales (navegación de
página completa, no toggle JS). El helper `_render_proyecto(request, id, pagina)` arma el
contexto; hay una ruta GET por página:
- `/proyecto/{id}` → redirige a `/resumen` (al abrir un proyecto se entra al Resumen).
- `/proyecto/{id}/resumen` → ficha-formulario (ver sección Resumen).
- `/proyecto/{id}/documentos` → subida + gestión + tabla de documentos.
- `/proyecto/{id}/ejes` → 9 ejes (`EJES_REVISION`/`EJES_ORDEN`) + chat + obs de eje.
- `/proyecto/{id}/items` → 16 ítems SEP (`ITEMS_SEP`/`ITEMS_ORDEN`) + obs de ítem. Sin chat.

Ambos métodos **conviven**. Núcleo unificado en `_analizar_grupo()`; `analizar_eje()`/
`analizar_item()` son envoltorios. Obs de eje: `obs.eje`/`obs.eje_nombre`; de ítem:
`obs.item`/`obs.item_nombre`. Rutas de análisis: `POST /proyecto/{id}/revisar-eje/{key}` y
`.../revisar-item/{key}`. Avance en `proyecto["ejes_revisados"]` / `["items_revisados"]`.
**Limpieza INDEPENDIENTE por sistema:** `POST /proyecto/{id}/limpiar-ejes` (borra solo obs de
eje + ejes_revisados + eje_chats) y `.../limpiar-items` (solo obs de ítem + items_revisados).
Los redirects de cada acción vuelven a su página (`_volver_a` usa el Referer para el estado).

**Grupos de observaciones desplegables (`<details>`):** en `bloque_observaciones()`/
`bloque_notas()` (proyecto.html), cada grupo (eje/ítem) es un `<details>` — evita tener que
bajar cada vez más al ir sumando revisiones. Se abre automáticamente el grupo recién analizado
(`eje_ok`/`item_ok`, el query param del redirect) o si no hay ninguno en la URL, el más
reciente por fecha (`eje_reciente`/`item_reciente`, calculado en `_render_proyecto()` con
`max(revisados.items(), key=fecha)`); el resto queda contraído pero expandible a mano. El
grupo se identifica por `grupo.key` (eje_key o item_key), agregado en `_agrupar()`.

**Mensaje de cumplimiento cuando no hay observaciones:** si un eje/ítem fue revisado y no
generó ninguna observación ni nota, antes no aparecía nada — ahora `bloque_cumplimiento()`
muestra una tarjeta verde "✅ Cumple con la normativa" listando esos ejes/ítems (calculado en
`_render_proyecto()`: `ejes_cumplen`/`items_cumplen`, filtrando `revisados[key].n_obs==0 and
n_notas==0`).

**Ver qué archivos reales se usaron en cada análisis:** cada tarjeta de eje/ítem ya revisado
tiene un `<details>` "📄 Ver los N archivos usados en este análisis" con el nombre real de cada
archivo (`nombre_original`, no solo el tipo/label) — para que el revisor pueda comprobar que
la asignación de documentos a cada eje/ítem fue correcta. Antes `ejes_revisados[key]["docs"]`
/ `items_revisados[key]["docs"]` solo guardaba `d["label"]` (el tipo, ej. "Estudio
hidrológico"), perdiendo el nombre real del archivo — si dos documentos comparten `tipo_doc`
(ej. 2 archivos clasificados como "Análisis Hidrológico"), no se podía distinguir cuál se usó.
Ahora se guarda `docs_incluidos` completo (`{id, nombre, label}` por documento, ya devuelto por
`_analizar_grupo()` pero antes descartado al persistir). La plantilla soporta ambos formatos
(`{% if d is mapping %}`) para no romper con proyectos que ya tenían el formato viejo (lista de
strings) guardado antes de este cambio.
**Si un eje/ítem "solo declara 1" documento existiendo 2 clasificados con ese tipo_doc:**
revisar en la página Documentos si el que falta tiene el indicador 🔴 "necesita resubir" — un
documento escaneado/con poco texto cuyo archivo físico ya no existe (post-deploy) se descarta
en silencio en `_analizar_grupo` (ni texto ni imagen disponible). Solución: resubirlo.

## Resumen del proyecto (página, formulario)

Ficha tipo formulario con los datos mínimos del proyecto (`RESUMEN_SECCIONES` en analyzer.py:
identificación, legal, predios, DAA, uso de suelo, obras, cultivo, características de obras).
Campos `text` / `textarea` / `sino` (select Sí/No). Se guarda en `proyecto["resumen"]` (dict
key→valor). Botón **Autocompletar con IA** → `resumir_proyecto()` (analyzer) lee los documentos
y devuelve JSON con lo que encuentra (no inventa; "" si no consta); en el backend solo rellena
campos VACÍOS (no pisa lo que el revisor escribió). Campos con `auto` (código, postulante,
nombre) se pre-rellenan desde el propio proyecto si están vacíos. Rutas:
`POST /proyecto/{id}/resumen` (guardar) y `POST /proyecto/{id}/resumen/autocompletar`.
`nombre_proyecto` es `tipo: "textarea"` (no "text") — un `<input>` de una línea no muestra
nombres de proyecto largos completos, había que hacer scroll dentro del campo.

---

## Funcionalidades implementadas ✅

- Subida PDF/Word/Excel/ZIP → extracción → clasificación por anexo
- **Proyecto en 4 páginas** (Resumen / Documentos / Revisión por Ejes / Revisión por Ítems SEP),
  navegación arriba — ver sección "Cuatro PÁGINAS del proyecto".
- **DOS métodos de revisión que conviven:** por 9 EJES temáticos y por 16 ÍTEMS del SEP. El
  análisis documento-por-documento fue eliminado de raíz.
- **Resumen del proyecto** tipo formulario, autocompletable con IA y editable (campos Sí/No).
- **🗑 Limpieza INDEPENDIENTE** por sistema: limpiar ejes no toca ítems y viceversa.
- **Aprendizaje**: por eje/ítem (criterios destilados del feedback) y por CONSULTOR (perfil que
  cruza proyectos/concursos). Se consolida desde `/admin/concursos/{id}`.
- **Normativa de tecnificación** destilada (ITT-01 a ITT-04) guía cada análisis.
- Bases del concurso (admin `/admin/concursos`): subir PDF → extrae texto → se cachea
- Chat de refinamiento por eje E ÍTEM (AJAX, sin recargar) — la IA puede modificar la
  observación (descartar/reclasificar a nota/editar) directamente desde la conversación
- Consulta libre al expediente
- Dark mode automático 19:00–07:00 con toggle manual (localStorage)
- Estados del proyecto: En revisión / Revisado / Observado / Rechazado
- Documentos ordenados por tipo · indicador de cuáles resubir tras un deploy
- **Ficha de revisión** (`/proyecto/{id}/ficha`): HTML imprimible + descargar PDF
  (html2pdf.js), obs agrupadas por eje/ítem, sin firmas ni "R)"
- Ver documento: si el archivo físico no existe (post-deploy), muestra el texto extraído

---

## Revisión por EJES TEMÁTICOS (uno de los dos métodos)

**Problema que resuelve:** revisar documento por documento era erróneo porque los documentos
son complementarios (el agronómico define la demanda que el hidráulico satisface; el plano
debe reflejar el diseño; el presupuesto debe cuadrar con las obras). Evaluarlos aislados
generaba falsas observaciones. Ese método fue **eliminado**; hoy conviven ejes + ítems SEP.

**Implementado (backbone):** `EJES_REVISION` en `analyzer.py` define los 9 ejes (tipo_docs +
checklist). `analizar_eje()` cruza TODOS los documentos del eje en UNA llamada a Sonnet y
devuelve observaciones tageadas con `eje`. Ruta `POST /proyecto/{id}/revisar-eje/{eje_key}`.
UI: panel de 9 ejes en la **página "Revisión por Ejes"** (`/proyecto/{id}/ejes`). Las obs de eje
se guardan con `obs.eje`, `obs.eje_nombre`; el feedback se etiqueta por eje.

**Visión en ejes:** `analizar_eje` usa texto extraído + IMÁGENES para documentos escaneados/planos
(los que no tienen texto). Renderiza páginas con `render_pdf_as_images` (tope global `MAX_IMG_EJE=10`)
y las envía como bloques de imagen. Requiere que el archivo físico exista (`ruta_uploads`); como los
uploads NO persisten entre deploys, para ver planos/escaneados hay que tenerlos subidos en la sesión
actual. El eje Coherencia es solo texto (no visión, por costo).

**Chat de refinamiento — eje E ÍTEM (implementado):** núcleo unificado `_chatear_grupo()` en
`analyzer.py`; `chatear_eje()`/`chatear_item()` son envoltorios (mismo patrón que
`_analizar_grupo`). Rutas `POST /proyecto/{id}/eje/{eje_key}/chat` y `.../item/{item_key}/chat`
(comparten `_manejar_chat()` en main.py). Historial en `proyecto["eje_chats"][key]` /
`["item_chats"][key]` (últimos 40 turnos). UI: macro `bloque_chat()` en `proyecto.html`,
reusado en ambas páginas.

**La IA SÍ puede modificar la observación desde el chat:** si el revisor pide un cambio
concreto (descartar, bajar a nota, corregir texto, ELIMINAR) y la IA está de acuerdo, agrega
al final de su respuesta un marcador oculto `ACCION_JSON: {"id","accion","texto_nuevo"}`
(accion: descartar|reclasificar_nota|editar|eliminar|mantener). `_extraer_accion()` lo separa
del texto que ve el revisor; `_aplicar_accion_chat()` en main.py aplica el cambio real a la
observación (por `id`, no por número — el bloque de observaciones del prompt incluye
`[id:...]` de cada una) y registra feedback (concurso + consultor) con `accion="descartada"`
si fue descartar/reclasificar/**eliminar** (misma señal de aprendizaje: "esta observación no
era válida"; solo cambia si el registro se conserva marcado o se borra). El frontend detecta
`modificado: true` en la respuesta AJAX y recarga la página (único caso en que el chat SÍ
recarga, porque la observación puede cambiar de sección o mover contadores).

**Descartar vs Eliminar:** "descartar" es reversible (queda con `estado="descartada"`, el
revisor puede volver a marcarla pendiente a mano) y sirve de registro/auditoría. "eliminar"
borra la observación de `proyecto["observaciones"]` por completo, sin dejar rastro — NO
reversible. La IA solo usa "eliminar" si el revisor lo pide explícitamente ("elimínala"/
"bórrala"), y por defecto prefiere "descartar" ante la duda (instrucción explícita en el
prompt). Además del chat, hay botón manual "🗑 Eliminar" en cada observación/nota
(`POST /proyecto/{id}/observacion/{obs_id}/eliminar`), con `confirm()` en el frontend.

**Bug resuelto — chat decía que aplicó un cambio pero no lo aplicaba (jul-2026):** al agregar
el marcador ACCION_JSON, `max_tokens=4000` del chat volvió a ser insuficiente (mismo patrón
del bug de thinking ya documentado): el modelo a veces terminaba la respuesta conversacional
pero el JSON quedaba cortado a mitad (o directamente la respuesta llegaba vacía). Síntomas
reportados: "eliminar" que decía haberse aplicado pero la observación seguía ahí; funcionaba
con una observación pendiente pero no con una ya descartada; y el error conocido "La IA no
devolvió una respuesta" al pedir explícitamente eliminar. Arreglado: `max_tokens` del chat
4000→8000, y `_extraer_accion()` ahora reintenta cerrando llaves/corchetes abiertos si el
JSON quedó cortado (mismo patrón que el parser de `_analizar_grupo`), con log de diagnóstico
si aun así no se puede parsear. **Si el patrón "dice que lo hizo pero no pasó" persiste
después de esto** (sin el error de respuesta vacía), ya no sería un problema de tokens sino
de que el modelo no está incluyendo el marcador pese a la instrucción — reforzar el prompt.

**Aprendizaje por eje/ítem (implementado):** `consolidar_aprendizaje()` (analyzer, usa Haiku)
destila el `feedback[]` de un eje/ítem en CRITERIOS APRENDIDOS (reglas concretas). Se guarda en
`concurso["criterios_aprendidos"][clave]` (clave = eje_key o "item_"+item_key). Se dispara desde
`/admin/concursos/{id}` con el botón "🧠 Consolidar aprendizaje" (ruta POST `/consolidar`; requiere
≥3 decisiones por grupo). En cada revisión, `_analizar_grupo` inyecta esos criterios destilados
en vez de los ejemplos crudos (más compacto y generalizable). El feedback se etiqueta por eje,
por ítem ("item_"+key) o por tipo_doc según el origen de la observación.

**Optimización de velocidad:** el chat (`chatear_eje`) mueve el contexto pesado (documentos +
observaciones + guía del eje) a bloques CACHEADOS del `system`, así en conversaciones de varios
turnos no se reenvía ni reprocesa (más rápido y barato). `consultar_expediente` subió su límite
a `max_tokens=4000` (evita el mismo corte por thinking) con aviso si llega vacía.

**Aprendizaje por CONSULTOR (implementado):** colección `consultores` en `database.py`
(`get_consultor`, `save_consultor`, `add_feedback_consultor`), keyed por nombre normalizado
(`_consultor_key` en main.py: minúsculas, sin acentos). El consultor se toma de
`proyecto["resumen"]["consultor"]` (el revisor debe llenar ese campo). Cada aprobar/descartar
acumula feedback en el consultor además del concurso. En cada revisión, `_construir_bloque_consultor`
inyecta el PERFIL destilado del consultor (o su historial crudo de decisiones si aún no se
consolida) — patrones recurrentes para revisar más rápido sus proyectos siguientes.
`consolidar_perfil_consultor()` (Haiku) destila ese historial; se dispara junto al botón
"🧠 Consolidar aprendizaje" (que ahora también procesa consultores). La colección cruza
proyectos y concursos. Perfiles visibles en `/admin/concursos/{id}`.

**Bug conocido y resuelto — respuestas vacías por límite de tokens bajo (jul-2026):**
Con la migración a Sonnet 5, el modelo empezó a incluir bloques de "pensamiento" (thinking)
dentro de la misma respuesta, antes del texto final. Si el límite de tokens de la respuesta
(`max_tokens`) era muy bajo, ese pensamiento consumía todo el cupo y el JSON de observaciones
(o el texto del chat) llegaba vacío o cortado — y el parser lo tragaba en silencio, sin avisar
error, devolviendo `observaciones: []` o una respuesta de chat vacía. Así se manifestó: 3 ejes
seguidos con 0 observaciones (cobrando costo real) y el chat de eje sin mostrar respuesta.
Arreglado subiendo los límites (`MAX_TOKENS_SONNET` en `analizar_eje`: 6000→12000; en
`chatear_eje`: 1200→4000) y agregando logs de diagnóstico (`print`) cuando la respuesta viene
vacía, con el `stop_reason` de la API, para detectarlo rápido si vuelve a pasar. En el chat,
además, si la respuesta llega vacía se guarda un aviso explícito en vez de un mensaje en
blanco. `consultar_expediente` también se subió a `max_tokens=4000` con el mismo aviso.
**Regla general:** cualquier llamada a Sonnet 5 necesita `max_tokens` holgado (≥4000) por el
thinking; si una respuesta llega vacía, loguear `stop_reason` en vez de tragarlo en silencio.

**Reintento automático cuando `max_tokens` corta la respuesta a 0 (jul-2026):** el bug anterior
seguía dándose puntualmente en grupos con imágenes (planos/escaneados) — el thinking extra que
implica "mirar" una imagen a veces se comía TODO el cupo de `MAX_TOKENS_SONNET` (12000) y la
respuesta llegaba con `stop_reason=max_tokens` y `content_len=0`. Detectado en producción con
"Memoria de cálculo de superficies" (justo el eje que define superficie/demanda/monto
bonificable — el más grave para perder en silencio). Arreglado en `_analizar_grupo`: si la
respuesta viene vacía Y `stop_reason == "max_tokens"`, reintenta una vez automáticamente con
`MAX_TOKENS_SONNET + 8000`. Sigue logueando el mismo aviso de diagnóstico si tras el reintento
igual quedan 0 observaciones (puede ser un resultado legítimo — ver criterios de énfasis abajo
para cómo confirmarlo).

**Criterios de énfasis por eje/ítem (implementado, jul-2026):** distinto del "aprendizaje"
automático de abajo. Es un campo `concurso["criterios_enfasis"][clave]` (misma clave que
`criterios_aprendidos`: eje_key o "item_"+item_key) que el revisor **escribe y edita a mano**
en `/admin/concursos/{id}` (card "🎯 Criterios de énfasis por eje/ítem", un `<textarea>` por
grupo, ruta `POST .../criterios-enfasis`). Se inyecta en `_analizar_grupo` con prioridad
explícita sobre el resto del prompt ("verifícalos SIEMPRE, tienen prioridad"). A diferencia de
`criterios_aprendidos` (que `consolidar_aprendizaje()` puede sobrescribir cada vez que se
consolida el feedback), este campo **nunca se toca automáticamente** — es la supervisión
humana explícita que decide qué debe aprender la IA como "revisor experto", útil desde el
primer proyecto de un concurso (no hace falta esperar ≥3 decisiones de feedback como con el
aprendizaje automático). Ejemplos reales que motivaron esto (cruces que la IA no captaba sola):
"el cronograma debe incluir instalación del sistema fotovoltaico si el proyecto lo contempla",
"tratar el pozo como embalse según ITT-02 al calcular superficie".

**Verificación numérica determinística — hidráulica y agronómica (implementado, jul-2026):**
`calculos_riego.py` (módulo nuevo, funciones puras sin dependencias) porta las fórmulas del
**Diseñador de Riego** (app hermana del mismo usuario, misma fuente normativa: Manuales e
Instructivos CNR en Drive) — Hazen-Williams (`hazen_williams`, `velocidad_tuberia`,
`diametro_sugerido_mm`, `factor_christiansen`) y la cadena agronómica ETo→ETc→AD→Dn→Fr→Db
(`cadena_agronomica`). La idea: en vez de que la IA haga la matemática de memoria a partir de
texto libre (poco confiable para números), se **recalcula con las mismas fórmulas** que usa el
propio diseñador de proyectos y se compara contra lo declarado por el consultor.
Flujo en `analizar_eje()` (analyzer.py), solo para `eje_key in ("hidraulico", "agronomico")`:
1. `_extraer_datos_hidraulicos()` / `_extraer_datos_agronomicos()` — llamada barata a Haiku que
   extrae SOLO datos numéricos explícitos del expediente (tramos de tubería: caudal/diámetro/
   longitud/material; o cadena agronómica: CC/PMP/Da/profundidad/Kc/ETo/factor agotamiento/
   eficiencia + los resultados declarados Dn/Fr/Db). Nunca inventa — usa `null` si no aparece.
2. `_bloque_verificacion_hidraulica()` / `_bloque_verificacion_agronomica()` — con esos datos,
   llama a `calculos_riego` y arma un bloque de texto con el recálculo y, si corresponde, las
   discrepancias con lo declarado (tolerancia 10-15%, y rango de velocidad 0,5-2,0 m/s).
3. El bloque se inyecta en `_analizar_grupo` como `bloque_verificacion` (nuevo parámetro),
   etiquetado explícitamente como "cálculo determinístico, no estimación de la IA" — con
   instrucción de citar los números exactos si hay discrepancia, y de NO mencionar nada si
   todo cuadra (evita ruido/falsos positivos cuando no hay datos suficientes para comparar).
Si la extracción no encuentra datos (documento sin esos números, o no es un PDF con texto), el
bloque queda vacío y el análisis sigue igual que antes — no rompe nada, es puramente aditivo.
**Alcance actual (v1):** solo velocidad/pérdida de carga por tramo (Hazen-Williams) y la cadena
Dn/Db agronómica — deliberadamente NO se portó la cadena completa de CDT/potencia de bomba
(necesita más campos por extraer: succión, elevación, pérdidas menores, margen de seguridad —
mayor riesgo de extracción errónea). Tampoco se portaron aún las fórmulas de carrete/pivote
(INIA-Carillanca) ni el dimensionamiento fotovoltaico — quedan para una siguiente iteración,
mismo patrón (el 80% de los proyectos reales de esta cuenta usan goteo/aspersión + FV; carrete
y microaspersión son ~20% — priorizar FV antes que carrete/pivote en la siguiente iteración).

**Página "🧮 Chequeo de Cálculos" (implementado, jul-2026):** `/proyecto/{id}/calculos`
(`templates/calculos.html`), quinta página del proyecto — mismo estilo de navegación arriba
que las otras 4, pero con su propia ruta/template (no pasa por `_render_proyecto`, para no
cargar ese contexto pesado). Resuelve el riesgo de que la extracción automática (Haiku) se
equivoque: el revisor ve los datos extraídos (tramos de tubería para Hidráulico, cadena
agronómica para Agronómico) en un formulario editable, con el recálculo mostrado al lado de
cada campo, y puede corregirlos a mano antes de darlos por buenos.
- Botón **"🤖 Extraer de los documentos"** (`POST .../calculos/{eje}/extraer`) — corre la
  misma extracción de `analyzer.py` bajo demanda y sobrescribe el formulario. NO marca como
  validado.
- Botón **"💾 Guardar"** + checkbox **"Ya revisé estos datos"** (`POST .../calculos/{eje}/guardar`)
  — guarda lo que haya en el formulario (editado o no) en `proyecto["verificacion_calculos"][eje]`;
  si el checkbox está marcado, `validado=True` + `fecha_validado` + `validado_por`.
- Hidráulico: hasta `N_TRAMOS_HIDRAULICOS=6` tramos fijos (tabla server-rendered, sin JS de
  agregar/quitar filas — suficiente para el tamaño típico de estos proyectos). Agronómico: un
  solo formulario con los 8 campos base + los 3 valores declarados por el consultor (Dn/Fr/Db).
  Fotovoltaico: bomba/sitio + panel/inversor/sistema + los 3 valores declarados (N° paneles,
  kWp, sección cable DC).
- **Efecto en el análisis:** en `revisar_eje()` (main.py), si `verificacion_calculos[eje_key]
  ["validado"]` es `True`, esos datos (ya revisados por el humano) se pasan a `analizar_eje()`
  como `datos_verificacion` y se usan DIRECTO, sin volver a llamar a Haiku para extraer — la
  supervisión humana reemplaza la extracción automática. Si no está validado, sigue
  extrayendo automáticamente en cada revisión (comportamiento de siempre, sin cambios).
Cubre Hidráulico, Agronómico y (desde jul-2026) Fotovoltaico. Carrete/pivote (INIA-Carillanca)
y microaspersión todavía no tienen fórmula ni página.

**Verificación fotovoltaica (implementado, jul-2026):** `calculos_riego.dimensionamiento_fv()`
porta `calcFV()` del Diseñador de Riego — energía diaria requerida (P_bomba×horas bombeo),
derating por temperatura, N° de paneles mínimo, configuración serie/paralelo según voltaje del
sistema, y sección de cable DC por caída de tensión (2%, distancia campo→inversor asumida en
50 m — mismo supuesto que la app hermana). `_extraer_datos_fv()` / `_bloque_verificacion_fv()`
en `analyzer.py`, mismo patrón que hidráulico/agronómico, conectado en `analizar_eje()` para
`eje_key == "energetico"`. **Cobertura parcial a propósito** (igual que hidráulico/agronómico):
no incluye cableado AC, protecciones (DPS/fusibles), estructura de montaje, ni contraste
explícito con el Explorador Solar — el propio Diseñador de Riego tampoco los tiene desarrollados
todavía. Prioridad de fuente: el ~80% de los proyectos de esta cuenta llevan sistema FV (goteo/
aspersión + FV), por eso se implementó antes que carrete/pivote (~20%, sin fórmula portada aún).

**Archivo de normativa DT-09 eliminado por corrupción (jul-2026):**
`normativa/DT-09_Proyectos_Electricos.txt` (el que debía tener los requisitos eléctricos/FV) se
detectó con texto ilegible en TODO el archivo — problema de codificación en el PDF fuente (glifos
mal mapeados), no del extractor de la app: incluso la vista previa nativa de Google Drive y la
conversión "Abrir con Google Docs" (que debería correr OCR) reproducen el mismo texto roto, lo
que sugiere que el defecto está en la fuente/encoding del PDF, no solo en la capa de texto. Se
eliminó el archivo del repo porque se cargaba completo (hasta 4.000 caracteres) en el
`SYSTEM_PROMPT` de **cada** llamada a la IA sin aportar nada — puro costo sin valor. Mientras no
haya una copia legible, el eje Energético/Fotovoltaico se apoya en `ITT_Criterios_Tecnificacion.txt`
(ítems esperados en presupuesto FV) y `Manual_Supervision_Obras.txt` (certificación SEC on-grid/
off-grid) — ambos sí están limpios. Si se consigue una copia legible del PDF de DT-09 (o alguien
transcribe manualmente las secciones clave), agregar `normativa/DT-09_...txt` de nuevo con texto
real — no reincorporar el archivo corrupto.

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

Los **16 ítems del SEP** (`ITEMS_SEP`/`ITEMS_ORDEN`) son el segundo método: cada uno revisa
su(s) documento(s) tal como se ingresan al Sistema Electrónico de Postulación, para copiar las
observaciones directo al SEP. Página "Revisión por Ítems SEP" (`/proyecto/{id}/items`).

---

## Restricciones y gotchas

- **Archivos subidos: persistencia solucionada vía PostgreSQL (jul-2026).** El disco de
  Railway sigue siendo efímero (se borra en cada deploy), pero ahora cada archivo subido
  (PDF/Word/Excel) se guarda también como `bytea` en una tabla nueva de Postgres, `archivos`
  (`proyecto_id, doc_id, filename, contenido, tamano, fecha` — ver `database.py`:
  `guardar_archivo/obtener_archivo/ids_con_archivo/eliminar_archivo/eliminar_archivos_proyectos/
  resumen_archivos`). Se guarda al subir (`subir`, `subir-multiple`, `subir-zip` en `main.py`)
  y se recupera solo. **En modo JSON local estos métodos son no-op** (el disco del Mac ya
  persiste entre ejecuciones, no hace falta duplicar en la base).
  - `ver_documento()`: si el archivo no está en disco, lo sirve directo desde el `bytea`
    guardado (sin tocar el disco) antes de caer al fallback de solo-texto.
  - `revisar_eje`/`revisar_item`: antes de analizar, `_restaurar_archivos_necesarios()`
    reescribe a disco (desde Postgres) los archivos que necesitan VISIÓN (escaneados/poco
    texto) que se hayan perdido tras un redeploy — así el análisis con imágenes sigue
    funcionando sin que el revisor tenga que resubir nada, mientras el archivo siga
    guardado en la base.
  - `doc.archivo_presente` (tabla de documentos en `proyecto.html`) ahora es `True` si el
    archivo está en disco **O** en la base (`db.ids_con_archivo()`), calculado en
    `_render_proyecto()`. El indicador 🔴 "necesita resubir" solo aparece si de verdad no
    hay ninguna copia en ningún lado (ej. documentos subidos antes de este cambio).
  - **Liberar archivos al terminar un concurso:** en `/admin/concursos/{id}` hay un botón
    "🗑 Dar por terminado — liberar archivos" (ruta `POST .../liberar-archivos`) que borra
    de Postgres y del disco los archivos de TODOS los proyectos de ese concurso (identificados
    por `_extraer_concurso_id(codigo_sep)`), para no acumular espacio indefinidamente. Solo
    borra el archivo original — `texto_extraido`, observaciones, ficha y todo el resto del
    análisis quedan intactos (mismo estado que si el archivo se hubiera perdido en un deploy).
    No hace falta ninguna acción para "empezar a guardar" el próximo concurso — el guardado es
    automático por proyecto/documento, no exclusivo de un concurso a la vez.
  - Solo hace falta resubir a mano un documento si nunca se guardó en la base (subido antes
    de este cambio) o si ya se liberó a propósito. La tabla de documentos en `proyecto.html`
    muestra por fila si el archivo sigue disponible (🟢), si hay que resubirlo (🔴,
    `doc.necesita_archivo` y no `doc.archivo_presente`) o si no hace falta (⚪).
- **Bug resuelto — carpeta de subida faltante tras deploy:** las rutas `subir` y
  `subir-multiple` en `main.py` intentaban guardar el archivo sin recrear la carpeta del
  proyecto (`UPLOAD_DIR/{proyecto_id}`), que se borra en cada deploy. Al subir un documento
  a un proyecto creado antes del último deploy, fallaba con "Error Interno del Servidor"
  (`FileNotFoundError`). Arreglado agregando `filepath.parent.mkdir(parents=True,
  exist_ok=True)` antes de escribir, igual que ya tenía `subir-zip`.
- **Bug resuelto — chat de eje/ítem "siempre fallaba" con error genérico:** causa raíz real:
  en `enviarChat()` (proyecto.html) se hacía `textarea.value = ''` y RECIÉN DESPUÉS
  `new FormData(form)` — como `FormData(form)` lee el valor actual del campo en ese momento,
  el mensaje viajaba **vacío** al servidor en cada envío (sin importar lo que el revisor
  escribiera). El backend respondía correctamente `{"ok": false, "error": "vacio"}`, pero
  el revisor nunca veía su mensaje real procesado. Arreglado: se arma `FormData` con el
  mensaje ya capturado ANTES de limpiar el textarea. Antes de encontrar esto se reforzó
  también el manejo de errores en `_manejar_chat()` (try/except ahora cubre toda la función,
  no solo la llamada a la IA) — cambio válido igual, pero no era la causa de este síntoma.
  **Lección:** con un bug de "siempre igual, sin importar el input", sospechar primero de
  que el input nunca llega, antes de asumir que es un fallo del backend.
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
7. **Sin emojis/íconos decorativos (jul-2026):** la app debe verse formal y no distraer con
   emojis — se ven distinto en cada equipo/SO y le restan seriedad. Regla: si un emoji/ícono
   no es estrictamente informativo, se elimina sin reemplazo (el texto ya dice lo mismo). Si
   SÍ aporta señal real a simple vista, no se usa emoji sino CSS/SVG simple que se vea igual
   en cualquier equipo — ejemplos ya implementados: `.dot`/`.dot-green`/`.dot-red`/`.dot-gray`
   en `base.html` para el semáforo de archivos (documentos.html), y los íconos SVG inline de
   sol/luna del toggle de modo oscuro (`base.html`, sustituyen 🌙/☀️). Las alertas (`.alert-success`/
   `.alert-error`) y badges de estado ya se distinguen por color de fondo — no necesitan emoji
   encima. Aplica este criterio a cualquier UI nueva que se agregue de aquí en adelante.
