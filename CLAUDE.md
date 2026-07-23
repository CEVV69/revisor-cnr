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

## Estado al cierre de esta sesión (jul-2026) — leer antes de seguir

El usuario ya está usando la app con el concurso 202-2026 **con proyectos reales** — va en el
**segundo proyecto real** revisado. Todos los fixes de la auditoría de rendimiento y las
funcionalidades nuevas de esta sesión (ver secciones dedicadas más abajo) ya están en producción
y en uso real, no solo probados con mocks. No hay ningún bug abierto conocido a esta fecha —
si retomas y el usuario reporta algo raro, lo más probable es que sea un caso nuevo, no una
regresión de lo ya resuelto.

**Checklists de los 18 ítems del SEP reescritos con normativa real (jul-2026):** el pendiente de
la sesión anterior (revisar los `checklist` fijos de `ITEMS_SEP`) se cerró. Proceso: 4 lecturas
en paralelo de la carpeta de normativa CNR en Drive (DT-01 a DT-20, IL-01/04, Instructivos de
Tecnificación 2017 — ITT-01 a ITT-04, Instructivos de Obras Civiles 2019 — ITC-05/07/08, Manual
de Supervisión de Obras, formatos FT-01/03/04), presentadas al usuario como propuesta en un
Artifact HTML (tabla actual vs. propuesto + fuente citada + notas por ítem), que el usuario
revisó, corrigió y devolvió con contenido adicional propio (topes numéricos de presupuesto,
tratamiento de IVA por tipo de beneficiario, etc.) — ese texto final es el que quedó en
`ITEMS_SEP`. Los 18 checklists ahora son considerablemente más técnicos y específicos que la
versión anterior (genérica de una o dos líneas en la mayoría). Cambios más relevantes:
- **`diseno_hidraulico`**: se sacó la cita "(DT-04/05/06)" que no correspondía al contenido real
  de esos documentos (confirmado por el usuario) — ahora detalla lo exigido por ITT-03 (diseño
  agronómico + cálculos hidráulicos, con nota explícita de que CDT y potencia de bomba NO se
  recalculan automáticamente en la app, a diferencia de Hazen-Williams/cadena agronómica que sí).
- **`presupuesto`**: pasó de una línea genérica a una lista de reglas concretas con montos y
  porcentajes (a–k: antigüedad de cotizaciones, tope de Gastos Generales, límite del 15%
  GG+Imprevistos+Estudio+ITO, costos prohibidos, tope de $/m² para invernaderos según tipo de
  cubierta, etc.) — contenido aportado directamente por el usuario, no de los documentos leídos.
- **`declaracion_iva`**: agregado el criterio real (usuarios INDAP: IVA incluido en la
  bonificación si tienen inicio de actividades; no-INDAP: IVA lo paga el postulante aunque figure
  en el presupuesto) — también aportado por el usuario, no había documento CNR que lo cubriera.
- **`presupuesto_electrico`**: se confirmó (búsqueda en DT-18) que la CNR NO tiene tabla de
  precios unitarios para equipos eléctricos/FV — el checklist ahora lo explicita, para que la
  verificación de precio dependa solo de cotizaciones + la tabla de precios referenciales de la
  app, sin asumir un DT-18 "eléctrico" que no existe.
- **`pruebas_bombeo`**: se mantuvo el ALCANCE ya existente (solo aspectos técnicos, no legales) y
  se sumó qué mirar en la curva de la prueba (caudal, tiempos, curvas de descenso/recuperación,
  anomalías o manipulación de datos).
- **`planos_tecnificacion`**: se fusionaron al checklist ya detallado los puntos nuevos de ITT-03
  §4 (Cuadro 1 Resumen en el plano, escala según superficie, equidistancia de curvas de nivel,
  etc.) en vez de dejarlos aparte.
- **`planos_obras_civiles`**: el alcance de "obras civiles" para este revisor se confirmó con el
  usuario — casetas, muros de protección, tranques/pequeños acumuladores y fundaciones de
  invernaderos u otras obras del proyecto (no obras colectivas de conducción tipo canal/bocatoma,
  que es el objeto principal de los Instructivos de Obras Civiles de donde salió el resto del
  checklist).
- **`cotizaciones_facturas`**: confirmado que el alcance de este ítem es solo la etapa de
  POSTULACIÓN — la acreditación/supervisión posterior a la adjudicación (que regula IL-04, la
  fuente usada para este checklist) queda fuera del trabajo de este revisor.
**Corrección registrada para no repetir el error:** al repartir la lectura de documentos entre 4
investigaciones en paralelo, el "Manual técnico de tecnificación" (`Manual de Tecnificacion
2017.pdf` en Drive) se le pasó solo a una de las 4, así que las otras 3 (que sí lo necesitaban,
para `plano_ubicacion` e `identificacion_riego`) reportaron el documento como "no disponible en
la carpeta" — el usuario detectó el error y hay que tenerlo presente: antes de repartir lectura
de normativa entre varias investigaciones paralelas, verificar que cada una tenga acceso a TODOS
los documentos que puede necesitar, no solo a los "obviamente" temáticos de su grupo.

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
- **IA:** Anthropic API — Claude **Sonnet 5** (revisión por ítems, chat y consultas) ·
  **Haiku 4.5** (TODA extracción de datos: autocompletar resumen, extracciones del Chequeo de
  Cálculos —hidráulica/agronómica/FV/partidas de presupuesto—, documentos obligatorios, y
  destilar aprendizaje/perfiles). Regla de costo: si la tarea es leer texto y devolver JSON
  estructurado, usa Haiku; Sonnet 5 solo para lo que exige razonamiento técnico (análisis por
  ítems, chat, consulta libre). El autocompletar del Resumen usaba Sonnet por error hasta
  jul-2026 — corregido a Haiku.
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
analyzer.py      Llamadas a Claude (análisis por ítem, chat de refinamiento, consulta libre)
extractor.py     Extracción de texto de PDF / Word / Excel / ZIP + clasificación de anexos
database.py      Capa dual: PostgreSQL si hay DATABASE_URL, si no JSON local
auth.py          bcrypt + JWT
normativa/       *.txt de normativa CNR, cargados al inicio (máx 4.000 chars c/u)
                 Incluye DT-*, IL-*, Manual_Supervision y criterios destilados de los
                 Instructivos de Tecnificación (ITT-01 a ITT-04 + ITT_Criterios), extraídos
                 del PDF oficial del Drive para guiar la revisión sin cargar el PDF completo.
                 También `Invernaderos_Criterios.txt` (jul-2026, ver sección dedicada) —
                 mismo patrón: extracto destilado, no el documento fuente completo.
uploads/         Una subcarpeta por proyecto. El disco NO persiste entre deploys, pero cada
                 archivo se respalda también en Postgres (tabla `archivos`) y se restaura
                 solo cuando hace falta — ver "Restricciones y gotchas".
templates/       Jinja2 (base.html, proyecto.html, ficha.html, admin_concursos.html, …)
```

### Modelo de datos (PostgreSQL: tabla `storage (key TEXT, value TEXT)`)
CINCO colecciones guardadas como JSON: `users`, `proyectos`, `concursos`, `consultores`, `precios`.

- **proyectos** → dict keyed por UUID: `id, nombre, codigo_sep, postulante, tipo_revision,
  revisor, revisor_nombre, estado, documentos[], observaciones[], consultas[]`, y además
  `resumen{}` (ficha-formulario), `items_revisados{}`, `item_chats{}`.
  - `documentos[]`: `id, nombre_original, filename, tipo_doc, tipo_doc_label, texto_extraido,
    analizado (bool), fecha_subida`.
  - `observaciones[]`: `id, texto, categoria, severidad (mayor|menor|informativa),
    referencia_normativa, estado (pendiente|aprobada|descartada), numero, fecha`, y
    `item`+`item_nombre`. Las observaciones **aprobadas** pueden llevar además `subsanacion:
    {rondas: [{ronda, respuesta, evaluacion (resuelta|reiterada), comentario, fecha, por}]}` —
    el hilo de respuestas del consultor (ver sección "Subsanación" más abajo). **Nota
    histórica:** proyectos revisados antes de jul-2026 (cuando
    existía el método por Ejes, ver más abajo) pueden tener observaciones antiguas con
    `eje`+`eje_nombre` en vez de `item`/`item_nombre` — la ficha las sigue mostrando (agrupadas
    al final, sin orden específico), pero ya no se pueden generar más ni gestionar desde la UI.
- **concursos** → `id (ej "204-2026"), nombre, bases_texto, feedback[], fecha_*`, más
  `criterios_aprendidos{}` (clave "item_"+item_key → texto destilado), `criterios_fecha`,
  `documentos_obligatorios[]` (claves tipo_doc), `documentos_obligatorios_referencia` (punto de
  las bases citado, ej. "6.3"), `documentos_obligatorios_revisado` (bool — VB del revisor, ver
  sección dedicada más abajo), `documentos_obligatorios_fecha/_por`.
  - `feedback[]`: decisiones reales del revisor (`accion: aprobada|descartada, tipo_doc,
    texto_obs, fecha`). `tipo_doc` = "item_"+item_key o tipo_doc real. Máx 200.
- **consultores** → keyed por nombre normalizado (`_consultor_key`): `key, nombre, feedback[]
  (máx 300, cruza concursos), perfil (texto destilado), perfil_fecha`.
- **precios** → blob único global (no keyed, no es por concurso/proyecto): `items[]
  ({categoria, item, unidad, precio}), fecha_actualizado, actualizado_por, nombre_archivo`.
  Tabla de precios referenciales PROMEDIO subida a mano por el revisor (NO es una copia
  oficial certificada por la CNR) — ver la sección "Verificación de precios contra tabla de
  referencia promedio" más abajo.

`database.py` lee/escribe cada colección completa en cada llamada (sin transacciones) — con
UNA excepción desde jul-2026: en PostgreSQL, los **proyectos** viven en una clave separada por
proyecto (`proyecto:{id}`), porque el blob único con el texto extraído de todos los documentos
de todos los proyectos crecía a varios MB y cada clic pagaba cargar+reescribir todo.
`db.migrar_proyectos()` (llamada al startup en main.py) migró el blob legacy `proyectos` a
claves separadas una única vez, idempotente. En modo JSON local se conserva el archivo único
de siempre. `get_proyectos()` en PG usa `SELECT ... WHERE key LIKE 'proyecto:%'` (una query).

---

## Flujo de análisis IA (`analyzer.py`) — núcleo `_analizar_grupo()`

El análisis documento-por-documento fue **eliminado**. Hoy todo pasa por `_analizar_grupo()`,
que revisa un GRUPO de documentos (un ítem del SEP) en UNA llamada a Sonnet 5. `analizar_item()`
es un envoltorio delgado sobre él.

1. **Selección de documentos** — el envoltorio filtra por `tipo_docs` del ítem. Coherencia
   global usa todos los documentos con texto.
2. **Texto vs imagen** — docs con `texto_extraido` van como texto; escaneados/planos (texto
   `< MIN_CHARS_TEXTO` = 300, o `__PDF_ESCANEADO__`) van por **visión** si el archivo físico
   existe (`render_pdf_as_images`, JPEG, tope global `MAX_IMG_EJE=10`). Coherencia NO usa visión.
3. **Presupuesto de caracteres** — `MAX_CHARS_EJE_TOTAL=45000` repartido EQUITATIVAMENTE entre
   los docs del grupo (`max_chars_total // len(docs_texto)`, luego `_truncar_inteligente` por
   documento). **Ampliado a 120.000** (`MAX_CHARS_POR_ITEM`, jul-2026) para los ítems densos en
   datos: `diseno_hidraulico` (incluye el agronómico), `diseno_fotovoltaico`, `presupuesto`,
   `presupuesto_electrico`, `coherencia` y `especificaciones_tecnicas` (este último agregado más
   tarde — ver el bug dedicado más abajo, el detonante ahí no es 2-3 archivos grandes sino MUCHOS
   documentos repartiéndose el mismo presupuesto) — el resto de los ítems sigue en 45.000.
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
- **Observaciones agrupadas por ítem:** en `proyecto.html` y en la ficha, las obs se
  muestran bajo UN solo título por ítem (no un encabezado por observación). El
  agrupamiento se arma en `_render_proyecto()` / `ficha_revision()` y se pasa a la plantilla.
  **OJO Jinja:** la clave de la lista de observaciones dentro de cada grupo es `obs`
  (`grupo.obs`), NO `items` — `grupo.items` colisiona con el método `dict.items()` y rompe
  el render en runtime (bug ya sufrido). Nunca usar `items` como nombre de clave de grupo.

## Páginas del proyecto (no pestañas) — navegación arriba

`proyecto.html` es **una sola plantilla** que renderiza 3 páginas según la variable `pagina`,
con una barra de navegación arriba (`.proj-nav`/`.proj-tab`). Son URLs reales (navegación de
página completa, no toggle JS). El helper `_render_proyecto(request, id, pagina)` arma el
contexto; hay una ruta GET por página:
- `/proyecto/{id}` → redirige a `/resumen` (al abrir un proyecto se entra al Resumen).
- `/proyecto/{id}/resumen` → ficha-formulario (ver sección Resumen).
- `/proyecto/{id}/documentos` → subida + gestión + tabla de documentos.
- `/proyecto/{id}/items` → 18 ítems SEP (`ITEMS_SEP`/`ITEMS_ORDEN`) + chat + obs de ítem.

Dos páginas más, `/proyecto/{id}/calculos` (Chequeo de Cálculos) y `/proyecto/{id}/respuestas`
(Respuestas del consultor / subsanación), tienen su propia plantilla y ruta, fuera de
`_render_proyecto()` — ver las secciones dedicadas más abajo.

Núcleo de análisis en `_analizar_grupo()`; `analizar_item()` es su envoltorio. Obs de ítem:
`obs.item`/`obs.item_nombre`. Ruta de análisis: `POST /proyecto/{id}/revisar-item/{key}`.
Avance en `proyecto["items_revisados"]`. Limpieza: `POST /proyecto/{id}/limpiar-items` (borra
obs de ítem + items_revisados + item_chats). Los redirects de cada acción vuelven a su página.

**Revisión por EJES TEMÁTICOS eliminada (jul-2026):** existió como método alternativo que
convivía con Ítems SEP. Se eliminó por completo a pedido del usuario — detalle completo del
cambio (qué se portó, qué se preservó, compatibilidad con datos históricos) en el changelog
"Revisión por Ejes eliminada por completo" dentro de la sección "Revisión por ÍTEMS DEL SEP",
más abajo.

**Grupos de observaciones desplegables (`<details>`):** en `bloque_observaciones()`/
`bloque_notas()` (proyecto.html), cada grupo (ítem) es un `<details>` — evita tener que bajar
cada vez más al ir sumando revisiones. Se abre automáticamente el grupo recién analizado
(`item_ok`, el query param del redirect) o si no hay ninguno en la URL, el más reciente por
fecha (`item_reciente`, calculado en `_render_proyecto()` con `max(revisados.items(),
key=fecha)`); el resto queda contraído pero expandible a mano. El grupo se identifica por
`grupo.key` (item_key), agregado en `_agrupar()`.

**Bug resuelto — aprobar/descartar una observación cerraba el ítem y saltaba a otro (jul-2026):**
las rutas `POST /proyecto/{id}/observacion/{obs_id}/estado` (aprobar/descartar/pendiente) y
`.../eliminar` (`actualizar_observacion`/`eliminar_observacion`, main.py) redirigían a
`/proyecto/{id}/items` a secas, sin `item_ok`. Como `abrir_item = item_ok or item_reciente`
(ver arriba), sin `item_ok` el `<details>` que se auto-abre pasaba a ser `item_reciente` (el
ítem más recientemente ANALIZADO por fecha, no el que el revisor tenía abierto) — el ítem en el
que estaba trabajando se colapsaba y la página "saltaba" a otro. Arreglado: ambas rutas ahora
capturan `item_key = obs.get("item")` ANTES de aplicar el cambio y redirigen con
`?item_ok={item_key}#item-{item_key}` (mismo patrón que `revisar_item()`), así el mismo ítem
queda abierto. De paso se le agregó `id="item-{{ grupo.key }}"` (`bloque_observaciones`) /
`id="item-nota-{{ grupo.key }}"` (`bloque_notas`, prefijo distinto para no duplicar id cuando un
ítem tiene ambos tipos) a los `<details>` — el ancla `#item-...` no apuntaba a nada antes de
esto (no rompía nada, pero tampoco hacía scroll). Si `obs.get("item")` es `None` (observación
histórica de Ejes, sin `item`/`item_nombre`), cae al comportamiento anterior sin `item_ok`.

**Mensaje de cumplimiento cuando no hay observaciones:** si un ítem fue revisado y no generó
ninguna observación ni nota, antes no aparecía nada — ahora `bloque_cumplimiento()` muestra una
tarjeta verde "Cumple con la normativa" listando esos ítems (calculado en `_render_proyecto()`:
`items_cumplen`, filtrando `revisados[key].n_obs==0 and n_notas==0`).

**Ver qué archivos reales se usaron en cada análisis:** cada tarjeta de ítem ya revisado tiene
un `<details>` "Ver los N archivos usados en este análisis" con el nombre real de cada archivo
(`nombre_original`, no solo el tipo/label) — para que el revisor pueda comprobar que la
asignación de documentos a cada ítem fue correcta. Se guarda `docs_incluidos` completo (`{id,
nombre, label}` por documento, devuelto por `_analizar_grupo()`). La plantilla soporta ambos
formatos (`{% if d is mapping %}`) para no romper con proyectos que ya tenían el formato viejo
(lista de strings) guardado antes de ese cambio.
**Cada archivo del listado es un link al documento (jul-2026):** el nombre de archivo en ese
`<details>` ahora es un `<a href="/proyecto/{id}/documento/{doc_id}/ver" target="_blank">` —
misma ruta `ver_documento()` que ya usaba la página Documentos, sin lógica nueva en el backend.
Solo aplica si `d is mapping and d.id` (formato nuevo con id); el formato legado (string, sin id)
sigue mostrándose como texto plano porque no hay id para armar el link.
**Si un ítem "solo declara 1" documento existiendo 2 clasificados con ese tipo_doc:** revisar
en la página Documentos si el que falta tiene el indicador rojo "necesita resubir" — un
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

**Campo "Características obras" — resumen en prosa autocompletado por IA (implementado,
jul-2026):** primer campo de la sección "Características de obras" (antes de Volumen embalsado,
FV, N° placas, etc.), `textarea` de tope 300 caracteres donde la IA explica de qué se trata el
proyecto (qué construye/instala y para qué), no una lista de datos sueltos. Se agregó un
mecanismo GENERALIZABLE en `RESUMEN_SECCIONES` (antes solo existía el caso especial `tipo:
"sino"` para Sí/No): cualquier campo puede llevar `maxlen` (int) + `resumen_ia` (instrucción de
estilo/contenido para la IA) — `resumir_proyecto()` arma `campos_lista` agregando
`(máx {maxlen} caracteres — {resumen_ia})` a la línea de ese campo en el prompt, igual que ya
hacía con `(responde "Sí" o "No")`. El límite de 300 se refuerza también en la UI
(`maxlength="{{ campo.maxlen }}"` en el `<textarea>` de `proyecto.html`, condicional a que el
campo declare `maxlen`) para que una edición manual del revisor tampoco pueda superarlo. Sirve
de patrón reutilizable para futuros campos de resumen con restricción de longitud/estilo, sin
tocar la lógica de `resumir_proyecto()` de nuevo.

**Campos de "3. Predios" y "5. Uso actual del suelo" — aclarados y ampliados (jul-2026):** a
pedido del usuario, insumo directo para los ítems "Memoria de cálculo de superficies" y
"Estudio de suelos":
- `clase` renombrado de "Clase" a **"Clase declarada en SEP"** — evita confundirlo con el campo
  siguiente.
- Campo nuevo **`superficie_clase_sep`** ("Superficie (SEP)") en "3. Predios", justo después de
  `clase` — la superficie declarada en el SEP POR esa clase de uso de suelo (no la superficie
  predial total, que ya tiene su propio campo `superficie_predial` al inicio de la sección).
- `uso_actual_suelo` renombrado de "Uso actual del suelo (revisar Rol)" a **"Uso Actual Suelo
  (SEP)"** — el usuario aclaró que este campo NO es la clase de uso de suelo (clasificación,
  campo `clase` de arriba) sino el CULTIVO/uso existente actualmente en el predio; el label
  anterior ("revisar Rol") inducía a confundirlo con la clasificación de uso de suelo del Rol,
  que es otro dato — de ahí la confusión que reportó el usuario.
- **Fila combinada en el Informe Resumen impreso:** para que `clase` + `superficie_clase_sep`
  no sigan agregando altura al informe (formulario ya bastante largo), se imprimen en LA MISMA
  fila de la tabla en vez de una fila por campo. Mecanismo GENERALIZABLE nuevo en
  `RESUMEN_SECCIONES` (mismo espíritu que `maxlen`/`resumen_ia`): cualquier campo puede llevar
  `"linea_con": "otro_key"` para indicar que, en `informe_resumen.html`, se imprime junto al
  campo referenciado en una sola fila de 4 celdas (label/valor/label/valor) en vez de 2 —
  `clase` es hoy el único campo que lo usa (`"linea_con": "superficie_clase_sep"`). El loop de
  `informe_resumen.html` calcula `combinados` (los `linea_con` de la sección) para saltarse el
  campo ya combinado como fila propia, y les agrega `colspan="3"` a las filas normales de esa
  misma sección para que el total de columnas cuadre con la fila de 4 celdas. **No afecta el
  formulario de edición** (`proyecto.html`, página Resumen) — ahí cada campo sigue en su propia
  línea como siempre, el mecanismo `linea_con` solo lo lee el informe impreso.

**El Resumen se inyecta como contexto en TODO análisis de ítem (implementado, jul-2026):** bug
real reportado por el usuario — en "Prueba de bombeo" la IA observaba que faltaba la inscripción
del derecho de agua, pese a que el Resumen del proyecto ya declaraba "No tiene derechos de agua
inscritos" (campo `daa`). Causa raíz: ningún análisis de ítem recibía `proyecto["resumen"]` como
contexto — cada ítem solo veía sus propios documentos, a ciegas de lo que el revisor ya había
confirmado en el formulario, así que asumía incumplimientos por ausencia sin poder cruzarlos.
Solución GENERALIZABLE (no un parche puntual para este caso): `_construir_bloque_resumen(resumen)`
(analyzer.py) arma un bloque con los campos no vacíos de `RESUMEN_SECCIONES` — etiquetado
explícitamente "YA VALIDADO por el revisor humano, no observes su ausencia; si un documento lo
CONTRADICE sí obsérvalo" — y se inyecta en **todo** `analizar_item()` (parámetro `resumen`,
wireado desde `revisar_item()` en main.py con `proyecto.get("resumen", {})`). Va en el prompt
por-llamada (NO en los bloques `system_con_cache`), porque a diferencia de las bases del concurso
(compartidas entre proyectos) el Resumen es específico de CADA proyecto — mezclarlo en el system
cacheado rompería la reutilización de caché entre proyectos del mismo concurso. Al ser genérico
por diseño, de paso corrige el mismo patrón de falso positivo con cualquier otro campo del
Resumen (Servidumbres, INDAP, uso de suelo, etc.), no solo con derechos de agua.
**Costo:** despreciable — el Resumen son ~25 campos cortos (tope 500 caracteres cada uno,
`MAX_CHARS_CAMPO_RESUMEN`), nada comparable a los 45.000–120.000 caracteres de los documentos.

**Checklist de "Pruebas de Bombeo" — aclarado el alcance (jul-2026):** junto con el bug de
arriba, el usuario corrigió una primera hipótesis mía: NO es cierto que "si el agua está
inscrita no se requiere prueba de bombeo" — varias bases la exigen igual, con derechos inscritos
o no, para dar certeza técnica del caudal. Por eso el fix NO fue una regla de "cuándo se
requiere" (sería falsa en algunos concursos), sino aclarar el ALCANCE del ítem: verifica SOLO
aspectos técnicos (caudal, nivel dinámico, eficiencia del pozo) y NO debe observar el estado
legal/inscripción del derecho de agua — eso es de otro ítem (Antecedentes legales). Si el
expediente presenta la prueba, se revisa por sus méritos técnicos sin cuestionar si correspondía
exigirla o no.

**Botón "Ver en Google Maps" junto a Huso (implementado, jul-2026):** el Resumen guarda un punto
en `coord_e`, `coord_n`, `coord_h` (Este/Norte/Huso). **El formato de esos 3 campos varía
mucho** — normalmente los llena el botón "Autocompletar con IA" copiando tal cual lo que
encontró en el documento del consultor, y cada consultor/topógrafo escribe distinto: UTM WGS84
(la mayoría), lat/long decimal, o grados/minutos/segundos (DMS). `_parse_coord()` (main.py)
intenta interpretar cualquiera de los tres:
1. **DMS** (`_parse_coord_dms`) — solo se activa con símbolos ° ' " o con 2-3 números separados
   ESPECÍFICAMENTE por espacios con letra de hemisferio opcional al final (ej. `33°26'43"S`,
   `33 26 43 S`, `-33 26 43`) — deliberadamente exige espacios, no puntos, para no confundirse
   con una coordenada UTM en notación chilena de miles (`6.294.127` también tiene varios grupos
   de dígitos, pero separados por puntos, no espacios).
2. **Número simple** (`_parse_coord_numero`, UTM o grado decimal) — mismo problema de notación
   que los precios: si hay coma, es notación chilena completa (punto=miles, coma=decimal, igual
   que `_parse_precio` en extractor.py); si no hay coma pero el número queda dividido en grupos
   de EXACTAMENTE 3 dígitos tras cada punto (ej. `349.876` o `6.294.127`), son separadores de
   miles y se eliminan; cualquier otro patrón de un solo punto se trata como decimal (ej.
   `349876.32` o `-70.6158` quedan intactos). Si el número simple trae una letra de hemisferio
   suelta sin patrón DMS completo (ej. `70.6158 O`), `_parse_coord` igual le aplica el signo.
`_mapa_url_resumen()` decide qué es cada número YA PARSEADO por su magnitud (no por el
formato original): si Este/Norte caen dentro de ±180/±90, son longitud/latitud directas (sin
necesidad de Huso ni conversión); si no, se tratan como UTM — ahí sí exige un Huso válido y que
Este/Norte caigan en un rango UTM plausible (100.000–900.000 / 1.000.000–10.000.000), y se
convierte con `geo.py` (módulo nuevo, función pura sin dependencias, fórmula estándar de Snyder
sobre el elipsoide WGS84 — datum WGS84/SIRGAS-Chile y hemisferio sur). Si el parseo da un
número fuera de rango en cualquiera de los dos casos, no se muestra el botón en vez de ubicar
un pin en un lugar disparatado. El link usa el formato clásico de Google Maps
`https://maps.google.com/maps?q=LAT,LON(ETIQUETA)`, que ubica un pin en las coordenadas exactas
con el código del proyecto como etiqueta (a diferencia del formato `search/?api=1&query=...`
más nuevo, que no permite una etiqueta custom en un punto arbitrario). Se calcula en
`_render_proyecto()` y se pasa como `mapa_url` (None si falta algún dato o no se puede
interpretar). En la plantilla, el botón (`btn btn-outline btn-sm`, no un link de texto) aparece
junto a la etiqueta "Huso (H)" en la página Resumen — solo visible si `mapa_url` existe, se abre
en pestaña nueva.
**Alcance:** cubre los 3 formatos que reportó el usuario como los más comunes. Formatos más
exóticos (otros datums declarados explícitamente, coordenadas con separadores no estándar)
pueden seguir sin interpretarse — en ese caso simplemente no aparece el botón, nunca se
adivina ni se muestra un pin en un lugar incorrecto.

---

## Funcionalidades implementadas ✅

- Subida PDF/Word/Excel/ZIP → extracción → clasificación por anexo
- **Proyecto en 3 páginas** (Resumen / Documentos / Revisión por Ítems SEP), navegación arriba
  — ver sección "Páginas del proyecto", más una 5ª página aparte "Chequeo de Cálculos".
- **Revisión por 18 ÍTEMS del SEP** (único método vigente — el método por Ejes se eliminó, ver
  sección "Páginas del proyecto"). El análisis documento-por-documento fue eliminado de raíz.
- **Resumen del proyecto** tipo formulario, autocompletable con IA y editable (campos Sí/No).
- **Limpieza** de la revisión por ítems (`limpiar-items`).
- **Aprendizaje**: por ítem (criterios destilados del feedback) y por CONSULTOR (perfil que
  cruza proyectos/concursos). Se consolida desde `/admin/concursos/{id}`.
- **Normativa de tecnificación** destilada (ITT-01 a ITT-04) guía cada análisis.
- Bases del concurso (admin `/admin/concursos`): subir PDF → extrae texto → se cachea
- Chat de refinamiento por ÍTEM (AJAX, sin recargar) — la IA puede modificar la
  observación (descartar/reclasificar a nota/editar) directamente desde la conversación
- Consulta libre al expediente
- Dark mode automático 19:00–07:00 con toggle manual (localStorage)
- Estados del proyecto: En revisión / Revisado / Observado / Aprobado Técnicamente / Rechazado
  (el estado "Aprobado Técnicamente" se agregó jul-2026 junto con la subsanación — ver sección
  dedicada más abajo)
- Documentos ordenados por tipo · indicador de cuáles resubir tras un deploy
- **Ficha de revisión** (`/proyecto/{id}/ficha`): HTML imprimible + descargar PDF
  (html2pdf.js), obs agrupadas por ítem, sin firmas ni "R)"
  **Sin badges de Mayor/Menor ni de categoría por observación (jul-2026):** el usuario pidió
  quitarlos porque el SEP no tiene esa categorización — se eliminaron los `<span class="badge
  badge-{{ obs.severidad }}">`/`badge-{{ obs.categoria }}"` de cada ítem de observación (y el
  CSS `.badge*` que quedó sin uso). El resumen de arriba ("Resumen observaciones aprobadas:
  Mayor: X · Menor: Y") NO se tocó — es una ayuda interna para juzgar admisibilidad, no un
  rótulo que se copie punto por punto al SEP, que es lo que pidió eliminar el usuario.
  **Margen izquierdo +0,5cm para perforar y archivar (jul-2026):** mismo bug de doble margen ya
  resuelto antes en `informe_resumen.html` (ver esa entrada más abajo) — `ficha.html` es el
  template MÁS ANTIGUO con ese patrón (standalone, Imprimir/Descargar PDF con html2pdf), y no
  tenía el fix. Aplicado igual: `@page { margin: 0; }` + `padding: 1.5cm 1.5cm 2cm 2cm` (el
  cambio real: left 1,5→2cm, el resto intacto) como ÚNICA fuente de margen en los dos caminos —
  se quitó el `body { padding: 0; }` que tenía `@media print` (dejaba el margen nativo del
  navegador, no controlado) y se cambió `margin: [10,10,10,10]` a `margin: 0` en el `opt` de
  `descargarPDF()` (sumaba con el padding del body, doblando el margen en el PDF descargado).
  **Margen superior desde la 2ª hoja (jul-2026):** mismo síntoma que en `informe_resumen.html`
  (título/texto pegado arriba en las hojas siguientes a la 1ª) pero con una diferencia clave: en
  `ficha.html` los saltos de página son NATURALES, no forzados por una clase `.salto-pagina` en
  un elemento fijo — el N° de hojas depende de cuántas observaciones tenga el proyecto (2 o 3
  hojas típicamente), así que no hay un único elemento al que agregarle `padding-top` como se
  hizo en el otro informe. Solución general para cualquier cantidad de hojas: `@page` pasó de
  `margin: 0` a `margin: 0.5cm 0 0 0` — a diferencia del padding del body (que solo empuja el
  inicio del flujo en la primera hoja), el margen de `@page` lo repite el navegador en CADA hoja
  automáticamente, así que cubre la 2ª, 3ª o las que hagan falta sin depender de dónde caiga el
  corte. Mismo criterio en "Descargar PDF": el `opt.margin` de html2pdf pasó de `0` a
  `[5, 0, 0, 0]` (formato `[top, left, bottom, right]` en mm) — html2pdf también repite ese
  margen en cada página del PDF generado.
  **Corrección — la 1ª hoja NO debía tocarse (jul-2026):** la primera versión de este fix dejaba
  que la 1ª hoja también ganara el medio centímetro extra (efecto secundario asumido por
  analogía con `informe_resumen.html`, donde sí se había aceptado) — pero el usuario aclaró que
  acá, igual que allá, la 1ª hoja YA estaba bien y no debía cambiar; solo faltaba margen desde la
  2ª en adelante. Como `@page margin` y `opt.margin` de html2pdf se aplican PAREJO a todas las
  páginas (no hay forma nativa de excluir "solo la primera" con `opt.margin` de html2pdf, y
  `@page :first` para excluirla en impresión nativa tiene soporte inconsistente entre navegadores
  — no se usó por eso), la solución fue restarle a la 1ª hoja, por JS, el mismo 0,5cm que
  `@page`/html2pdf le suman a todas: se agregó la clase `body.imprimiendo { padding-top: 1cm; }`
  (dentro de `@media print`, así no afecta la pantalla) que se activa/desactiva con los eventos
  nativos `beforeprint`/`afterprint` para el camino de Imprimir — la 1ª hoja queda en 1cm (body)
  + 0,5cm (`@page`) = 1,5cm de siempre, y las hojas 2+ (que no heredan el padding del body) en
  0 + 0,5cm = el margen nuevo. Para "Descargar PDF", como html2canvas no dispara `@media print`
  de forma confiable (mismo motivo documentado para la sección Notas de `informe_resumen.html`),
  `descargarPDF()` hace el mismo ajuste directo por JS (`document.body.style.paddingTop = '1cm'`
  antes de llamar a html2pdf, restaurado a `''` en el `.then()`) en vez de depender de la clase.
- **Informe Resumen** (`/proyecto/{id}/resumen/informe`, jul-2026): versión imprimible de la
  página Resumen (`templates/informe_resumen.html`, mismo patrón standalone que `ficha.html` —
  no extiende `base.html`, botones Imprimir/Descargar PDF con html2pdf.js). Encabezado con
  "{código del proyecto} — {sistema(s) de riego}" (`_sistemas_riego_proyecto()` en main.py, lee
  `verificacion_calculos["agronomico"]` con los mismos helpers multi-sistema del Chequeo de
  Cálculos — con 2 sistemas los une "Goteo + Aspersión"; sin ninguno declarado, "No
  especificado"). Todas las secciones/campos del Resumen en solo lectura (tablas label:valor,
  "—" si está vacío). Sección **"Notas"** al final — SOLO aparece en la versión impresa/PDF
  (`display:none` en pantalla, `@media print { display:block }`; en `descargarPDF()` se fuerza
  `display:block` a mano porque html2canvas no dispara `@media print` de forma confiable) — un
  recuadro con líneas en blanco para que el revisor anote a mano sobre el papel, nunca se
  guarda ni se envía al backend. Botón "Imprimir informe" (`target="_blank"`) en la página
  Resumen, mismo patrón que el botón "Generar Ficha de Revisión" de la página Ítems SEP.
  **Ajustado tras probarlo (jul-2026):** 24 líneas en vez de 6 (a pedido del usuario, en dos
  rondas: primero triplicado a 18, después subido a 24 al ver que sobraba espacio en la hoja) y
  `padding-left` del `body` a 2cm (vs. 1,5cm del resto) tanto en la regla base como dentro de
  `@media print` — deja margen para perforar y archivar. **Bug encontrado y corregido en la
  primera vuelta: el margen quedaba de 3,8cm en vez de los 2,8cm pedidos** — la causa era que
  `descargarPDF()` tenía su PROPIO margen (`margin: [10,10,10,10]` en el `opt` de html2pdf, 10mm
  = 1cm) que se sumaba al `padding` del CSS (2,8 + 1 = 3,8). Se corrigió por partida doble: (1)
  `margin: 0` en el `opt` de html2pdf, para que el padding del `body` sea la ÚNICA fuente de
  margen en el PDF descargado (recordar: html2canvas usa el padding de la regla BASE, no el de
  `@media print`, mismo motivo por el que la sección Notas se fuerza a mano ahí); (2) `@page {
  margin: 0; }` agregado al inicio del `<style>`, para que `window.print()` nativo tampoco sume
  el margen de impresión propio del navegador — el `padding` del `body` dentro de `@media print`
  queda como única fuente también en ese camino. Verificado midiendo el PDF resultante con
  PyMuPDF (posición x mínima del texto): exactamente 2,0cm en el camino de impresión nativa; el
  camino de html2pdf no se pudo probar en este entorno (el CDN de html2pdf.js está bloqueado por
  la red del sandbox — no es un problema de la app, es la misma librería que ya usa `ficha.html`
  en producción sin problemas) pero la lógica es la misma (padding base + margin:0 = 2cm exactos,
  sin doble suma) y quedó verificado indirectamente confirmando que el `padding-left` de la regla
  BASE (la que usa html2canvas) es exactamente 2cm.
  **Ajuste posterior con datos reales (jul-2026):** 24→32 líneas de Notas (a pedido del usuario,
  volvió a quedar corto tras usarlo con proyectos reales del 202-2026) — con 32 el documento se
  corría a una 3ª hoja, así que se bajó a 28 (en prueba, el usuario puede seguir ajustando el
  número exacto). Además, "Características
  de obras" (última sección del Resumen) quedaba cortada a mitad entre la primera y la segunda
  hoja al imprimir — se le agregó la clase `.salto-pagina` (`page-break-before: always; break-
  before: page;`) a su `.titulo-seccion` para forzar que arranque siempre en hoja nueva. La regla
  se dejó FUERA de `@media print` a propósito (sin efecto visual en pantalla, pero necesaria para
  que el modo `pagebreak: {mode: ['css', ...]}` de html2pdf —usado en "Descargar PDF"— la
  respete; si quedara solo dentro de `@media print`, html2canvas no la vería, mismo motivo por el
  que la sección Notas se fuerza a mano vía JS en vez de depender de `@media print`).
  **Ajuste 28→26 líneas (jul-2026):** al agregar el campo "Características obras" (ver sección
  "Resumen del proyecto" más arriba) se le restaron 2 líneas a Notas para darle espacio en la
  hoja al contenido nuevo, a pedido explícito del usuario.
  **Margen superior de la 2ª hoja (jul-2026):** el usuario reportó que el título de
  "Características de obras" (que arranca la 2ª hoja gracias a `.salto-pagina`) quedaba pegado
  arriba del todo, con parte del texto cortado — el padding del `body` NO se repite en cada
  hoja impresa (solo empuja el inicio del flujo en la 1ª), así que una hoja que arranca por un
  salto de página explícito no hereda ningún margen superior. Se agregó `padding-top: 0.5cm`
  directo a la regla `.salto-pagina` (no a `@page`, que sigue en `margin: 0` a propósito, ver
  nota del margen izquierdo) — al estar DENTRO del elemento que arranca la hoja nueva, el
  padding se renderiza como espacio en blanco antes del título tanto en impresión nativa
  (`window.print()`) como en el PDF descargado (html2canvas capta el padding porque es parte
  del layout real del DOM, a diferencia de un margen `@page` que no ve).
- Ver documento: si el archivo físico no existe (post-deploy), muestra el texto extraído
- **Verificación de precios** en Presupuesto/Presupuesto electrificación contra una tabla de
  precios referenciales PROMEDIO subida a mano (`/admin/precios`, no oficial de la CNR) —
  detecta sobreprecio y subvaluación. Botón "Precios referenciales CNR ↗" al dashboard oficial
  en las tarjetas de esos ítems (consulta manual — ver sección dedicada más abajo).
- **Instalable como PWA** (jul-2026): `static/manifest.json` + `static/sw.js` (service worker
  mínimo, sin caché — solo existe para que el navegador ofrezca "Instalar app") + íconos en
  `static/icons/` (192/512/apple-touch/favicons), generados desde una imagen que subió el
  usuario. Enlazados en el `<head>` de `base.html` y `login.html` (este último NO extiende
  `base.html`, tiene su propio `<head>` — hay que mantener el manifest/íconos/SW duplicados
  ahí también si se edita uno). `ficha.html` (documento imprimible) queda afuera a propósito.
  Para cambiar el ícono: reemplazar los PNG en `static/icons/` con el mismo nombre y tamaño.
- **Documentos obligatorios de admisibilidad** (jul-2026): la IA sugiere, desde las bases,
  qué documentos son obligatorios (`/admin/concursos/{id}`) — requiere VB explícito del
  revisor antes de usarse. Si al proyecto le falta alguno confirmado, se muestra un banner
  rojo (no bloqueante) al entrar — ver sección dedicada más abajo.

---

## Subsanación — revisión de las respuestas del consultor (implementado, jul-2026)

Nueva **página aparte** `/proyecto/{id}/respuestas` (`templates/respuestas.html`, standalone como
`calculos.html`, misma nav de tabs, fuera de `_render_proyecto`). Cubre la fase POSTERIOR a
generar observaciones: una vez enviadas al consultor, este tiene 10 días hábiles para responder
(fuera de la app, vía SEP), y el revisor revisa esas respuestas para verificar que resuelven cada
punto. Decisiones de diseño confirmadas con el usuario: (1) página aparte, no dentro de Ítems SEP;
(2) el consultor NO usa la app — el revisor **transcribe** la respuesta y sube los antecedentes
nuevos por la página Documentos; (3) tras las 2 rondas sin resolver, el punto queda "no resuelta"
y el revisor decide a mano (no hay rechazo automático).
- **Qué observaciones entran:** SOLO las `estado == "aprobada"` (las que efectivamente se
  enviaron con la ficha). Las pendientes/descartadas no aparecen. Se agrupan por ítem (mismo
  `orden_item` de `ITEMS_ORDEN`).
- **Modelo de datos:** cada observación aprobada gana `obs["subsanacion"]["rondas"]` — lista de
  `{ronda, respuesta, evaluacion (resuelta|reiterada), comentario, fecha, por}`. No hay estado
  guardado aparte: `_estado_subsanacion(obs)` (main.py) lo **deriva** de las rondas → `esperando`
  (falta la respuesta de la ronda actual) | `resuelta` (última ronda resuelta) | `no_resuelta`
  (2 rondas y la última reiterada). `MAX_RONDAS_SUBSANACION = 2`.
- **Rutas (main.py):** `GET .../respuestas` (`pagina_respuestas`), `POST
  .../observacion/{id}/responder` (registra una ronda: `respuesta`+`evaluacion`+`comentario`;
  valida que la obs sea aprobada, que `puede_responder`, y que la respuesta no esté vacía),
  `POST .../observacion/{id}/subsanacion/deshacer` (borra la última ronda, por si el revisor se
  equivocó), `POST .../aprobar-tecnicamente` (marca el proyecto "Aprobado Técnicamente", **solo
  si TODAS las aprobadas quedaron resueltas** — guard en el backend, no solo en la UI).
- **UI:** tarjeta de resumen arriba (X de Y resueltas · esperando · no resueltas) con el botón
  "Dar por Aprobado Técnicamente" (visible solo si `todas_resueltas`); si hay `no_resuelta`, un
  aviso de que decida a mano con el menú de estado (Rechazar u otra vía). Cada observación es una
  tarjeta con su texto (solo lectura), su hilo de rondas ya registradas (respuesta + veredicto +
  nota + fecha/por), y —si `puede_responder`— un formulario con textarea de respuesta + nota
  opcional + dos botones ("Marcar como resuelta" / "Reiterar"). Ancla `#obs-{id}` para volver a
  la misma observación tras cada acción.
- **Evaluación con IA (parte del proceso de revisión, no solo transcripción):** botón "Evaluar
  respuesta con IA" en el formulario de cada observación → AJAX `POST
  .../observacion/{id}/evaluar-respuesta` → `analyzer.evaluar_respuesta_subsanacion()` (Sonnet 5,
  streaming). La IA cruza la respuesta transcrita con TODOS los antecedentes ACTUALES del ítem
  (los documentos ya incluyen lo que el consultor haya presentado/corregido y el revisor haya
  vuelto a subir) + el Resumen + las bases, y devuelve `{recomendacion: resuelta|no_resuelta,
  fundamento}`. Es SOLO un apoyo — la decisión final (marcar resuelta / reiterar) la toma el
  revisor. Selección de documentos: los del `tipo_docs` del ítem (todos con texto para
  "coherencia"/ítem desconocido), reparto adaptativo, solo texto (sin visión, por costo/latencia
  — se puede sumar visión en una iteración futura). El JS muestra la recomendación en un recuadro
  verde/rojo y rellena dos hidden inputs (`ia_recomendacion`/`ia_fundamento`) que, al registrar la
  ronda, se guardan JUNTO al veredicto humano (quedan visibles en el hilo como "IA sugirió:
  resuelve/no resuelve — <fundamento>", para auditoría). Si el revisor edita la respuesta después
  de evaluar, `limpiarIA()` borra la recomendación previa (ya no corresponde). Regla de siempre:
  la llamada usa streaming + `get_final_message()` (input grande) y va envuelta en
  `asyncio.to_thread`.
- **Estado del proyecto:** se agregó **"Aprobado Técnicamente"** a `estados_validos`
  (`cambiar_estado_proyecto`) y al menú/badge de estado en `proyecto.html` (verde, como
  "Revisado"). El botón guardado de la página Respuestas es el camino previsto; el menú de estado
  sigue permitiendo fijarlo a mano (el revisor es la autoridad).
- **Documentos de respaldo del consultor (implementado, jul-2026):** la respuesta puede ser solo
  texto, o texto + archivos (una nueva prueba de bombeo, cálculo estructural corregido, etc.).
  Decisión de diseño: esos archivos SON documentos del proyecto (única fuente de verdad — es lo
  que leen la evaluación IA y el re-análisis), pero se suben **directo desde la página
  Respuestas**, sin cambiar a Documentos. Botón "Adjuntar" en el formulario de cada observación →
  AJAX `POST .../observacion/{id}/adjuntar-respaldo` (multipart: archivo + tipo_doc) → reusa el
  MISMO pipeline de subida que la página Documentos (extracción de texto en `to_thread`, respaldo
  en Postgres, `truncar_texto_guardado`), agrega el doc a `proyecto["documentos"]` con
  `origen_subsanacion=obs_id`, y lo enlaza a la observación en
  `obs["subsanacion"]["adjuntos_pendientes"]`. El `tipo_doc` se elige de un `<select>` con las
  opciones del ítem observado (todas si es "coherencia") — así cae en su grupo y el re-análisis
  lo ve. Al registrar la ronda, los `adjuntos_pendientes` pasan a `ronda["adjuntos"]` (quedan
  visibles en el hilo como "Documentos adjuntados: X"). **Importante:** la evaluación IA
  (`evaluar_respuesta_subsanacion`, parámetro `doc_ids_extra`) incluye SIEMPRE esos adjuntos
  aunque su `tipo_doc` no pertenezca al ítem observado (ej. una prueba de bombeo adjuntada a una
  observación de Diseño hidráulico) — si no, el respaldo quedaría invisible para el juicio. Flujo:
  adjuntar (AJAX, no recarga, preserva el texto) → evaluar con IA (ya ve el doc nuevo) → decidir.
  El JS avisa subirlo ANTES de evaluar; `adjuntar()` llama a `limpiarIA()` porque una evaluación
  previa no consideraba el documento recién subido.
- **Retención:** el proyecto, sus antecedentes y las observaciones deben permanecer disponibles
  hasta Aprobado/Rechazado. Nada se borra automáticamente — la única purga es el botón manual
  "Liberar archivos" del concurso (`/admin/concursos/{id}`), que NO debe usarse hasta cerrar el
  proyecto. La subsanación no agrega ninguna limpieza automática.
- **Alcance actual (v1):** el revisor transcribe la respuesta como texto y puede pedir la
  evaluación con IA (ver arriba); los archivos nuevos van por Documentos (se puede re-revisar el
  ítem si hace falta). No hay: recordatorio del plazo de 10 días hábiles, ni versión imprimible
  del pliego de reiteración para el SEP, ni acceso del consultor, ni visión en la evaluación IA —
  quedan como posibles iteraciones futuras.

---

## Revisión por ÍTEMS DEL SEP (único método)

**Problema que resuelve:** revisar documento por documento era erróneo porque los documentos
son complementarios (el agronómico define la demanda que el hidráulico satisface; el plano
debe reflejar el diseño; el presupuesto debe cuadrar con las obras). Evaluarlos aislados
generaba falsas observaciones. Ese método fue **eliminado** desde el inicio; el análisis
siempre cruza documentos por grupo.

Este método existió junto a un método por 9 EJES TEMÁTICOS que fue **eliminado por completo
en jul-2026** (ver el changelog al final de esta sección) — hoy Ítems SEP es el único método
de revisión.

**Implementado (backbone):** `ITEMS_SEP` en `analyzer.py` define los 18 ítems (tipo_docs +
checklist). `analizar_item()` cruza TODOS los documentos del ítem en UNA llamada a Sonnet y
devuelve observaciones tageadas con `item`. Ruta `POST /proyecto/{id}/revisar-item/{item_key}`.
UI: panel de ítems en la página "Revisión por Ítems SEP" (`/proyecto/{id}/items`). Las obs de
ítem se guardan con `obs.item`, `obs.item_nombre`; el feedback se etiqueta por ítem
("item_"+key).

**Visión en ítems:** `analizar_item` (vía `_analizar_grupo`) usa texto extraído + IMÁGENES para
documentos escaneados/planos (los que no tienen texto). Renderiza páginas con
`render_pdf_as_images` (tope global `MAX_IMG_EJE=10`) y las envía como bloques de imagen.
Requiere que el archivo físico exista (`ruta_uploads`); como los uploads NO persisten entre
deploys, para ver planos/escaneados hay que tenerlos subidos en la sesión actual. El ítem
Coherencia Global es solo texto (no visión, por costo).

**Análisis de PLANOS en alta resolución (implementado, jul-2026):** los tipos en
`TIPOS_PLANO_VISION` (`planos_tecnificacion`, `planos_obras_civiles`, `plano_ubicacion`,
`identificacion_riego` — este último agregado más tarde, ver entrada dedicada más abajo) van a
visión **siempre** que el archivo PDF exista — aunque tengan capa de texto extraíble (un plano
exportado de AutoCAD trae las cotas/rótulos como texto, pero el trazado solo se ve en imagen):
entran por AMBOS canales a la vez (texto + imagen; en "archivos usados" aparece "(texto +
imagen)"). Se renderizan con `render_plano_tiles()` (extractor.py): por página, una vista
completa MÁS 4 cuadrantes ampliados (2×2) — la API reduce cada imagen a ~1.568 px de lado, así
que un plano A1/A0 completo pierde las cotas; los cuadrantes recuperan ese detalle (~2× de
resolución efectiva por eje). 5 imágenes por página, máx 2 páginas por plano (tope global
`MAX_IMG_EJE=10` intacto). El prompt advierte explícitamente que los cuadrantes son la MISMA
página (no duplicar conteos) y que lea diámetros/longitudes/números SOLO de cotas y rótulos
anotados (no "medir a escala"). Los checklists de ambos ítems de planos se detallaron:
diámetros y longitudes rotulados por tramo vs. diseño hidráulico, sectores, marco de
plantación, viñeta/escala, y dimensiones acotadas vs. cubicaciones/presupuesto en obras
civiles — la ausencia de rotulado clave ES observación. **Sobre AutoCAD nativo:** DWG es
formato binario propietario — no se puede leer directo; DXF sí sería parseable (ezdxf) si el
consultor lo entregara, pero el SEP recibe PDF — no implementado.

**"Identificación del área de riego" agregado a `TIPOS_PLANO_VISION` (jul-2026):** el usuario
reportó que la revisión de ese ítem observaba que la superficie no constaba, cuando en realidad
SÍ estaba anotada — pero gráficamente, sobre el mapa/plano de delimitación del área (polígonos
con rótulos de hectáreas), no como texto plano extraíble del PDF. Ese tipo de documento no
estaba en `TIPOS_PLANO_VISION`, así que nunca iba a visión (solo texto), y la IA no podía "ver"
esas anotaciones. Se agregó `identificacion_riego` al set — mismo tratamiento que los planos:
visión siempre que el archivo exista (aunque tenga texto), renderizado con
`render_plano_tiles()` (vista completa + cuadrantes ampliados). El texto de aviso de imágenes
en el prompt (`nota_imagenes`, `_analizar_grupo`) se generalizó de "planos" a "planos/mapas de
delimitación de áreas" y ahora menciona explícitamente leer "SUPERFICIES/hectáreas rotuladas",
no solo diámetros/longitudes (antes redactado pensando solo en planos de tecnificación/obras).

**"Pruebas de Bombeo" agregado a visión SIEMPRE — nuevo `TIPOS_SIEMPRE_VISION` separado de
`TIPOS_PLANO_VISION` (jul-2026):** el usuario reportó que este ítem "no conocía la mitad de la
información" — el informe trae una tabla de datos (caudal, tiempos, niveles) y la curva de
descenso/recuperación como GRÁFICO, ninguno de los dos capturable por texto extraído, así que si
el PDF tenía algo de texto narrativo (metodología, antecedentes) el ítem se analizaba solo con
eso, sin ver la tabla ni la curva — mismo patrón de bug que `identificacion_riego`/
`plano_ubicacion`, pero en `pruebas_bombeo` no aplicaba porque ese tipo no estaba en
`TIPOS_PLANO_VISION`.
- **No se agregó directo a `TIPOS_PLANO_VISION`** porque ese set además dispara
  `render_plano_tiles()` (vista completa + 4 cuadrantes ampliados, pensado para dibujos técnicos
  grandes donde el texto se pierde a escala normal) — un informe de prueba de bombeo es un
  documento tamaño carta con una tabla y un gráfico, no necesita cuadrantes de zoom, así que
  forzarlo habría gastado cupo de `MAX_IMG_EJE` sin necesidad. Se creó `TIPOS_SIEMPRE_VISION =
  TIPOS_PLANO_VISION | {"pruebas_bombeo"}` — el set amplio decide QUÉ documentos van a visión
  siempre (aunque tengan texto); `TIPOS_PLANO_VISION` (sin cambios en su contenido) sigue
  decidiendo, dentro de ese subconjunto, cuáles además usan cuadrantes. `pruebas_bombeo` entra al
  primero pero no al segundo → visión sí, pero con el renderizado básico de página completa
  (`render_pdf_as_images`).
- Los 3 puntos que antes leían `TIPOS_PLANO_VISION` para decidir "necesita el archivo físico
  siempre" pasaron a leer `TIPOS_SIEMPRE_VISION`: `_analizar_grupo` (analyzer.py, decisión de
  incluir en `docs_imagen`), `_restaurar_archivos_necesarios()` y el cálculo de
  `doc["necesita_archivo"]` en `_render_proyecto()` (ambos en main.py) — así una prueba de bombeo
  con archivo perdido tras un redeploy también se restaura desde Postgres antes de analizar, y
  también se marca "necesita resubir" en la página Documentos si no hay ninguna copia disponible.
- `nota_imagenes` (el aviso que ve la IA sobre las imágenes adjuntas) ahora distingue: el aviso de
  "cada página viene con 4 cuadrantes, no dupliques conteos" solo se agrega si de verdad se usó
  `render_plano_tiles` en al menos un documento del grupo (nuevo `ids_con_tiles`, poblado en el
  loop de render) — antes era un texto fijo pensado solo para planos y le habría dicho a la IA
  que esperara cuadrantes que no existen para una prueba de bombeo. La instrucción de qué leer se
  generalizó para cubrir también "valores de TABLAS, y la forma de CURVAS o gráficos (ej.
  descenso/recuperación de una prueba de bombeo)", no solo diámetros/longitudes/superficies.

**Bug resuelto — el archivo físico de un plano no se restauraba tras un redeploy pese a tener
texto (jul-2026):** reportado junto con lo anterior para "Plano de Ubicación del proyecto"
(`plano_ubicacion`, que YA estaba en `TIPOS_PLANO_VISION` desde antes — el problema no era falta
de cobertura sino que la visión nunca llegaba a dispararse). Causa: `_restaurar_archivos_
necesarios()` (main.py) — el helper que recupera desde Postgres el archivo físico perdido tras
un redeploy de Railway antes de analizar — solo restauraba documentos "escaneados o con poco
texto" (`texto == "__PDF_ESCANEADO__" or len(texto) < MIN_CHARS_TEXTO`), sin considerar que los
tipos de `TIPOS_PLANO_VISION` necesitan el archivo físico SIEMPRE (van a visión aunque tengan
texto). Un plano con harto texto extraíble (ej. exportado de AutoCAD, con las cotas como texto)
cuyo archivo se perdía en un redeploy quedaba sin restaurar — la visión nunca se disparaba pese
a que el código la esperaba siempre para ese tipo, y no había ningún aviso: el análisis simplemente
seguía solo con el texto, silenciosamente. Arreglado: `_restaurar_archivos_necesarios()` ahora
también restaura si `doc.tipo_doc in TIPOS_PLANO_VISION` (importado de `analyzer.py`). Mismo fix
aplicado al indicador 🔴 "necesita resubir" de la página Documentos (`doc["necesita_archivo"]`
en `_render_proyecto()`), que tenía la misma omisión — antes un plano con texto pero sin archivo
en ningún lado (ni disco ni Postgres) no se marcaba como "necesita resubir", dejando al revisor
sin forma de notar que la visión no estaba disponible para ese documento.

**Chat de refinamiento por ÍTEM (implementado):** núcleo `_chatear_grupo()` en `analyzer.py`;
`chatear_item()` es su envoltorio (mismo patrón que `_analizar_grupo`). Ruta
`POST /proyecto/{id}/item/{item_key}/chat` (vía `_manejar_chat()` en main.py). Historial en
`proyecto["item_chats"][key]` (últimos 40 turnos). UI: macro `bloque_chat()` en `proyecto.html`.

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
prompt). Además del chat, hay botón manual "Eliminar" en cada observación/nota
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

**Observaciones agregadas A MANO por el revisor (implementado, jul-2026):** botón "+ Agregar
observación manual" (`<details>` desplegable, macro `_form_obs_manual()`) → formulario simple
(texto, categoría, severidad, referencia normativa opcional) → `POST
/proyecto/{id}/item/{item_key}/observacion/agregar-manual`. Pensado para cuando el revisor ya
sabe que algo debe observarse (sin depender de que la IA lo detecte) y quiere dejarlo junto con
el resto en vez de anotarlo aparte en el SEP — así se beneficia del mismo seguimiento
(subsanación) y queda todo en un solo lugar.
- **Ubicación (ajustada tras probarla — no en la tarjeta de selección del ítem, que ya estaba
  sobrecargada):** al FINAL de la lista de observaciones de cada ítem, dentro de su `<details>`
  ya desplegado (`bloque_observaciones()`) — y también junto al nombre de cada ítem en el banner
  verde "Cumple con la normativa" (`bloque_cumplimiento()`, que ahora recibe `proyecto_id`), para
  el caso en que la IA no haya encontrado nada pero el revisor sí tenga algo que observar. En
  cuanto se agrega una manual a un ítem que estaba en ese banner, dejar de estar "en cumplimiento"
  es automático: la ruta incrementa `items_revisados[item_key]["n_obs"/"n_notas"]`, y el filtro de
  `items_cumplen` (`n_obs==0 and n_notas==0`) ya lo excluye sin código adicional — en el siguiente
  render el ítem sale del banner y aparece en su posición normal junto a los demás observados
  (mismo `orden_item` de `ITEMS_ORDEN` que usa `_agrupar()`).
- **"La IA la hace suya para todos los efectos" — por diseño, sin código especial en ningún otro
  lado.** La observación manual se guarda con EXACTAMENTE la misma forma que una de la IA (`item`,
  `item_nombre`, `estado="pendiente"`, `categoria`, `severidad`, `texto`, `referencia_normativa`,
  `numero`) — solo se le agrega `manual: True` + `agregada_por`. Como toda la lógica que ya trata
  "las observaciones del proyecto" (Coherencia Global para no repetirlas, la invalidación cruzada
  para auto-descartarla si otro ítem la resuelve, `_registrar_feedback_obs` para alimentar el
  aprendizaje del ítem/consultor al aprobar/descartar, la ficha de revisión, y el flujo de
  Respuestas/subsanación una vez aprobada) opera sobre `proyecto["observaciones"]` sin mirar el
  origen, una observación manual entra automáticamente a TODOS esos mecanismos apenas se crea —
  no hizo falta tocar ninguno de ellos.
- **Se conserva al re-analizar el ítem** (`obs.get("manual")` excluye la observación del borrado
  que hace `revisar_item()` antes de insertar los resultados nuevos de la IA) — a diferencia de
  las observaciones de la IA, no es un resultado del análisis que deba reemplazarse.
- **Numeración:** continúa la secuencia de "Obs. N" ya existente en ese ítem (`max(numero) + 1`).
  El contador del badge de la tarjeta ("N obs") se incrementa igual al agregar una manual, sin
  necesidad de re-analizar para que se refleje.
- **Indicador visual:** badge gris "manual" (con el nombre del revisor en el `title`) junto a
  categoría/severidad, en `bloque_observaciones()` y `bloque_notas()` — para distinguir de un
  vistazo cuáles observaciones vinieron de la IA y cuáles se escribieron a mano.

**Aprendizaje por ítem (implementado):** `consolidar_aprendizaje()` (analyzer, usa Haiku) destila
el `feedback[]` de un ítem en CRITERIOS APRENDIDOS (reglas concretas). Se guarda en
`concurso["criterios_aprendidos"]["item_"+item_key]`. Se dispara desde `/admin/concursos/{id}`
con el botón "Consolidar aprendizaje" (ruta POST `/consolidar`; requiere ≥3 decisiones por
grupo). En cada revisión, `_analizar_grupo` inyecta esos criterios destilados en vez de los
ejemplos crudos (más compacto y generalizable). El feedback se etiqueta por ítem ("item_"+key)
o por tipo_doc según el origen de la observación.

**Optimización de velocidad:** el chat (`chatear_item`) mueve el contexto pesado (documentos +
observaciones + guía del ítem) a bloques CACHEADOS del `system`, así en conversaciones de varios
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
error, devolviendo `observaciones: []` o una respuesta de chat vacía. Así se manifestó: 3 grupos
seguidos con 0 observaciones (cobrando costo real) y el chat sin mostrar respuesta.
Arreglado subiendo los límites (`MAX_TOKENS_SONNET` en `_analizar_grupo`: 6000→12000; en
`_chatear_grupo`: 1200→4000) y agregando logs de diagnóstico (`print`) cuando la respuesta viene
vacía, con el `stop_reason` de la API, para detectarlo rápido si vuelve a pasar. En el chat,
además, si la respuesta llega vacía se guarda un aviso explícito en vez de un mensaje en
blanco. `consultar_expediente` también se subió a `max_tokens=4000` con el mismo aviso.
**Regla general:** cualquier llamada a Sonnet 5 necesita `max_tokens` holgado (≥4000) por el
thinking; si una respuesta llega vacía, loguear `stop_reason` en vez de tragarlo en silencio.

**Reintento automático cuando `max_tokens` corta la respuesta a 0 (jul-2026):** el bug anterior
seguía dándose puntualmente en grupos con imágenes (planos/escaneados) — el thinking extra que
implica "mirar" una imagen a veces se comía TODO el cupo de `MAX_TOKENS_SONNET` (12000) y la
respuesta llegaba con `stop_reason=max_tokens` y `content_len=0`. Detectado en producción con
"Memoria de cálculo de superficies" (justo el ítem que define superficie/demanda/monto
bonificable — el más grave para perder en silencio). Arreglado en `_analizar_grupo`: si la
respuesta viene vacía Y `stop_reason == "max_tokens"`, reintenta una vez automáticamente con
`MAX_TOKENS_SONNET + 8000`. Sigue logueando el mismo aviso de diagnóstico si tras el reintento
igual quedan 0 observaciones (puede ser un resultado legítimo — ver criterios de énfasis abajo
para cómo confirmarlo).

**Bug resuelto — la revisión del ítem Presupuesto se colgaba varios minutos sin respuesta
(jul-2026):** al revisar "Presupuesto detallado de obra" con un proyecto real, la app quedaba
colgada 5+ minutos y no devolvía nada. Causa: la llamada a Sonnet 5 dentro de `_analizar_grupo`
usaba `client.messages.create` **sin streaming**. Presupuesto es el ítem con mayor presupuesto de
caracteres (`MAX_CHARS_POR_ITEM["presupuesto"]=120000`) y encima el análisis puede reintentar con
`MAX_TOKENS_SONNET+8000` (20.000 tokens de salida) — una petición con tanto input y `max_tokens`
tan alto choca contra el timeout HTTP del SDK (`create()` no envía nada hasta tener la respuesta
completa), y desde el navegador se ve como la app "colgada". Arreglado pasando la llamada a
**streaming**: `client.messages.stream(...)` como context manager + `get_final_message()` (patrón
recomendado por la guía de la API de Anthropic para peticiones con mucho input o `max_tokens`
alto — mantiene la conexión viva y evita el timeout de request). `get_final_message()` devuelve el
MISMO objeto `Message` que `create()`, así que `.stop_reason`, `_texto_respuesta()` y el reintento
por respuesta vacía + `max_tokens` no cambiaron. Se envuelve en un helper síncrono
(`_stream_final`) llamado vía `asyncio.to_thread` (el SDK es síncrono, misma regla de siempre).
**Regla para código nuevo:** cualquier llamada a Sonnet 5 con input grande (análisis por ítem) o
`max_tokens` alto debe usar streaming + `get_final_message()`, no `create()` a secas. El chat
(8.000 tokens) y la consulta libre (4.000) quedaron con `create()` por ahora — son más chicos y no
se colgaron; si alguno empieza a hacerlo, aplicar el mismo patrón.

**Seguimiento — "Error Interno del Servidor" en Presupuesto pese a que el análisis SÍ terminó bien
(jul-2026):** el streaming de arriba evita el timeout propio del SDK/httpx esperando a Anthropic,
pero no evita que una solicitud MUY larga desde el navegador choque con un timeout de una capa
más externa (el proxy de Railway — `uvicorn` corre sin ningún flag de timeout propio en
`railway.toml`, así que no es la app). El usuario reportó ver una página en blanco con error al
revisar Presupuesto, pero al volver a entrar las observaciones YA estaban guardadas — confirma
que el proceso en el servidor siguió corriendo hasta el final y guardó todo con normalidad; solo
se cortó la respuesta HTTP de vuelta al navegador. Causa de fondo: el log mostró el reintento ya
documentado arriba (`respuesta vacía por max_tokens — reintentando con más cupo`) — el primer
intento (12.000 tokens) se quedó corto pensando y el reintento completo (20.000) sí funcionó, pero
la SUMA de ambos intentos secuenciales (uno desperdiciado + uno completo) puede tardar varios
minutos, suficiente para topar con el timeout externo. Coincide con que el checklist de
Presupuesto se había ampliado poco antes (de una línea a las 11 reglas a–k con montos/porcentajes,
ver la sección de checklists más abajo) — más exigencia de razonamiento por partida, más chance de
quedarse corto en el primer intento. Mitigación aplicada: `MAX_TOKENS_SONNET` 12.000→16.000 (el
reintento pasa a 24.000) — reduce cuántas veces hace falta el segundo llamado completo, que es lo
que dobla el tiempo total de la solicitud. No es una solución completa (un Excel muy grande/con
muchas partidas puede seguir necesitando el reintento) — si vuelve a pasar, el dato clave para el
usuario es que **igual se guarda en el servidor aunque el navegador muestre error**: conviene
esperar un momento y volver a entrar antes de asumir que hay que revisar el ítem de nuevo.

**Criterios de énfasis por ítem (implementado, jul-2026):** distinto del "aprendizaje"
automático de abajo. Es un campo `concurso["criterios_enfasis"]["item_"+item_key]` (misma clave
que `criterios_aprendidos`) que el revisor **escribe y edita a mano** en
`/admin/concursos/{id}` (card "Criterios de énfasis por ítem", un `<textarea>` por
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
Flujo en `analizar_item()` (analyzer.py), para el ítem `diseno_hidraulico` (corre tanto la
verificación hidráulica como la agronómica — ver el bloque "Revisión por Ejes eliminada" al
final de esta sección):
1. `_extraer_datos_hidraulicos()` / `_extraer_datos_agronomicos()` — llamada barata a Haiku que
   extrae SOLO datos numéricos explícitos del expediente (tramos de tubería: caudal/diámetro/
   longitud/material; o cadena agronómica: CC/PMP/Da/profundidad/Kc/ETo/factor agotamiento/
   eficiencia + los resultados declarados Dn/Fr/Db). Nunca inventa — usa `null` si no aparece.
   El texto que reciben lo arma `_texto_grupo_para_extraccion()`: **reparte 60.000 caracteres
   EQUITATIVAMENTE** entre los documentos del grupo con truncado inteligente (inicio 75% +
   final 25%). Antes repartía 20.000 "por orden de llegada" — un primer documento largo dejaba
   a los demás fuera, y solo tomaba el inicio de cada uno (perdía los resultados declarados, que
   suelen ir al final). Corregido jul-2026 junto con subir el Resumen a 80.000 y `consultar_
   expediente` a 90.000, ambos con el mismo reparto equitativo + inicio/final.
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

**Verificación de diseño base — Superficie de riego, Caudal de diseño, Tiempo de riego y N°
de sectores (implementado, jul-2026):** extensión del Chequeo Agronómico a pedido del usuario:
"tener a la vista la información indispensable para verificar los cálculos que arrojen los
resultados base del diseño". Fórmula portada del Diseñador de Riego (`disenador_riego_v96.html`,
funciones `calcGA`/`calcGE` de goteo y `calcMA`/`calcME` de microaspersión — ambas comparten
exactamente la misma relación):

```
Demanda[l/s/ha]         = Db / 8,64                              (1 mm/día/ha = 1/8,64 l/s/ha)
Superficie riego segura = Caudal disponible / Demanda[l/s/ha]
Tiempo de riego          = Db / Precipitación del sistema         [hr/día]
N° de sectores           = ⌊Horas disponibles al día / Tiempo de riego⌋
```

`calculos_riego.verificacion_diseno_riego(db_mm_dia, superficie_ha, caudal_disponible_ls,
precipitacion_mmhr, horas_disponibles_dia)` — usa el **Db recalculado** (no el declarado, para
no arrastrar un error de la cadena agronómica) y es aditivo campo por campo: sin caudal
disponible no calcula superficie segura; sin precipitación no calcula tiempo de riego; sin horas
disponibles no calcula N° de sectores. También `calculos_riego.requiere_acumulador(caudal_diseno_ls,
caudal_disponible_ls)` — regla ITT-03 encontrada en el mismo archivo fuente (línea ~6136): si el
caudal de diseño del sistema supera el caudal disponible × 1,2, se requiere acumulador (estanque).
**Alcance deliberadamente NO replicado:** aspersión/carrete usan en el Diseñador de Riego un
modelo de "posturas" distinto (caudal y tiempo por postura, N° de posturas por superficie) —
a pedido explícito del usuario ("No se trata de replicar algo similar a la app de Diseño de
Proyectos") no se portó ese modelo; esta verificación es una relación general
demanda↔caudal↔tiempo↔sectores, válida como referencia para cualquier sistema pero calcada del
patrón de goteo/microaspersión. "Precipitación del sistema" se trata como un dato **declarado/
extraído** del expediente (no derivado de emisor+marco), evitando portar 4 sub-modelos distintos
de selección de emisor. El prompt de verificación se lo advierte explícitamente a la IA.
- `_extraer_datos_agronomicos()` (analyzer.py) ahora también extrae `superficie_riego_ha`,
  `caudal_disponible_ls`, `precipitacion_sistema_mmhr`, `horas_disponibles_dia`, y en
  `declarado`: `caudal_diseno_ls`, `tiempo_riego_hr`, `n_sectores`.
- `_bloque_verificacion_agronomica()` agrega el bloque "VERIFICACIÓN DE DISEÑO BASE" después
  del bloque de la cadena Db, con las mismas discrepancias/tolerancias que el resto (15% para
  tiempo de riego, comparación exacta para N° de sectores) y el aviso de ITT-03 si corresponde.
- Página "Chequeo de Cálculos" → tarjeta Agronómico: nueva subsección "Datos de diseño"
  (Superficie de riego, Caudal disponible, Precipitación del sistema, Horas disponibles al día)
  y 3 campos nuevos en "Resultados declarados por el consultor" (Caudal de diseño, Tiempo de
  riego, N° sectores) — campos existentes se angostaron (`.agro-grid` de 150px a 115px mínimo)
  para que quepan más por fila, a pedido del usuario.

**Label "Factor agotamiento" → "Criterio de Riego" (jul-2026):** el campo `factor_agotamiento_pct`
(% del agua aprovechable del suelo consumible antes de regar, usado en `Dn = AD × factor`) se
llamaba "Factor agotamiento" en `calculos.html` — término agronómico estándar (FAO-56), pero NO
es el nombre que usa el usuario en el Diseñador de Riego (ahí es "Criterio de Riego [%HA]",
campos `a-crit`/`c-crit`/`m-crit`) ni aparece con ese sentido en la normativa CNR indexada en
`normativa/` (se buscó explícitamente; el único match de "Agotamiento" es en DT-06 y se refiere
a agotamiento/drenaje de napa en excavaciones, sin relación). Se renombró el label a "Criterio
de Riego (%)" para que coincida con la app hermana — el nombre interno de la variable/clave
(`factor_agotamiento_pct`) NO se tocó, solo el texto visible. El prompt de extracción
(`_extraer_datos_agronomicos` en analyzer.py) menciona ambos términos ("factor de agotamiento"
y "criterio de riego") para reconocer cualquiera que use el documento del consultor.

**Verificación de Kc contra DT-05 (implementado, jul-2026):** a pedido del usuario, el Kc
declarado en el diseño agronómico se valida contra `normativa/DT-05_Rangos_Kc_Cultivos.txt`
(rangos oficiales CNR por cultivo, ~30 especies) — cálculo determinístico (lookup exacto), no
una estimación de la IA a partir del texto. `KC_RANGOS_DT05` (analyzer.py) porta la tabla
completa del DT-05 a un dict Python; `_buscar_rango_kc(cultivo)` normaliza el nombre (minúsculas,
sin tildes) e intenta, en orden: coincidencia exacta, alias común (`_KC_ALIAS_DT05` — nombres
chilenos habituales que no calzan literal con la columna "Cultivo" del DT-05: "Palta"→"Palto",
"Durazno"→"Duraznero y Nectarino", "Uva de mesa"→"Vid de mesa", etc.), y como última opción
substring en cualquiera de los dos sentidos (para variedades/nombres compuestos, ej. "Uva
Vinífera cv. Cabernet Sauvignon" → "Vides Viníferas"). Si el nombre es ambiguo (ej. "Olivo"
solo, sin especificar "para mesa"/"para aceite" — dos entradas del DT-05 calzarían) o el
cultivo no está cubierto por el DT-05 (ej. "Trigo"), retorna `None` — no adivina.
- `_extraer_datos_agronomicos()` ahora también extrae `"cultivo"` (nombre/especie del proyecto).
- `_bloque_verificacion_agronomica()` arma un bloque "VERIFICACIÓN Kc vs. DT-05" **independiente**
  del resto de la cadena agronómica (solo necesita `cultivo`+`kc`, no los otros 6 campos base) —
  si el Kc declarado cae fuera del rango, instruye a la IA a citar el rango oficial y el DT-05
  exige que un Kc fuera de rango se respalde con publicaciones de instituciones reconocidas.
- Página "Chequeo de Cálculos" → tarjeta Agronómico: nuevo campo "Cultivo" (texto libre) en
  "Datos base declarados", y nueva fila "Kc vs. rango DT-05" en la tabla de resultados —
  también independiente del resto (se puebla aunque falten los otros campos de la cadena).
  `_kc_dt05_calculo()` (main.py) replica la misma independencia en el preview Python.
- **La tabla DT-05 y `_buscar_rango_kc` están duplicadas en JS** dentro de `calculos.html`
  (`KC_RANGOS_DT05`/`KC_ALIAS_DT05`/`buscarRangoKc`, mismo algoritmo) para el recálculo en vivo
  — se verificó paridad exacta contra la versión Python con los mismos casos de prueba (18
  cultivos/variantes, incluida la ambigüedad de "Olivo") antes de desplegar. Si se agrega o
  corrige un cultivo en `KC_RANGOS_DT05`/`_KC_ALIAS_DT05` (analyzer.py), replicar el cambio a
  mano en el `<script>` de `calculos.html`.

**Chequeo Agronómico — tabla sin duplicar, marco de plantación y sistema de riego declarado
(implementado, jul-2026):** primera revisión con datos reales del concurso 202-2026 mostró tres
mejoras necesarias en la tarjeta Agronómico de `calculos.html`:
1. **Sección "Resultados declarados por el consultor" eliminada** — duplicaba exactamente lo que
   ya mostraba la columna "Extraído/declarado" de la tabla de comparación (Dn, Fr, Db, Caudal de
   diseño, Tiempo de riego, N° sectores). Esos 6 inputs (`decl_dn`/`decl_fr`/`decl_db`/
   `decl_qdiseno`/`decl_triego`/`decl_nsec` — mismos `id`/`name`, sin cambios en el backend) se
   movieron DENTRO de la celda izquierda de su fila correspondiente en la tabla — ahora se edita
   en un solo lugar, no dos. (`agro-sup-decl`, la fila "Superficie de riego segura", quedó como
   estaba: no es un duplicado, compara la superficie declarada del proyecto —dato de "Datos de
   diseño"— contra la superficie SEGURA calculada, dos conceptos distintos.)
2. **Marco de plantación y espaciamiento del sistema** — campos nuevos en "Datos base
   declarados": Distancia entre hileras, Distancia entre plantas/sobre hilera (comunes a
   cualquier sistema), N° líneas de emisor y Espaciamiento entre emisores (Goteo/Microaspersión),
   Espaciamiento entre aspersores y Espaciamiento entre laterales (Aspersión/Carrete). Son datos
   de referencia para que el revisor los cruce a mano contra el plano y el presupuesto — a
   propósito NO se conectaron a ninguna fórmula nueva (sigue la misma decisión de no derivar
   precipitación desde emisor+marco, documentada más abajo en "Verificación de diseño base").
3. **"Sistema de riego" declarado al inicio de la tarjeta** (select: Goteo/Microaspersión/
   Aspersión/Carrete/Mixto) — controla qué campos de marco se muestran (JS, `.campo-goteo`/
   `.campo-aspersion` con clase `.activo`; **ojo con la especificidad CSS**: la regla que oculta
   necesita `.agro-grid > div.sistema-riego-campo` completo, no solo `.sistema-riego-campo` —
   la regla genérica `.agro-grid > div` ya trae `display:flex` con más especificidad y gana si no
   se iguala). Si no hay sistema declarado o es "Mixto", se muestran AMBOS grupos de campos (no
   se oculta nada por defecto — solo se oculta cuando el sistema es inequívoco).
   **Sobre proyectos con MÁS DE UN sistema de riego** (caso real encontrado por el usuario: un
   proyecto con Goteo Y Aspersión a la vez, donde la extracción automática había tomado en
   silencio los datos de Aspersión —eficiencia 75%— sin que el revisor supiera cuál sistema
   estaba viendo): `_extraer_datos_agronomicos()` ahora extrae también `sistema_riego`, con
   instrucción explícita de responder `"Mixto"` si detecta más de un sistema (en vez de mezclar
   datos de ambos en un mismo campo) y de usar los datos del sistema de MAYOR superficie/
   principal para el resto de los campos. Cuando el valor es "Mixto": (a) la UI muestra un aviso
   en rojo explicando que el chequeo de abajo corresponde a un solo sistema a la vez y que el
   revisor debe repetirlo a mano para el otro si hace falta verificarlo — mismo criterio que ya
   se le explicó al usuario para proyectos con múltiples cultivos/sistemas (revisar el más
   exigente primero); (b) `_bloque_verificacion_agronomica()` inyecta el mismo aviso en el
   prompt de la IA, para que no asuma que Kc/eficiencia/factor de agotamiento aplican a todo el
   proyecto. Esta detección de "Mixto" sigue existiendo como aviso dentro de cada tarjeta de
   sistema (por si el propio documento mezcla datos pese a la extracción explícita), pero el
   caso real "dos sistemas de riego" ya no depende de este aviso — está resuelto de raíz, ver
   "Chequeo Agronómico multi-sistema" más abajo (jul-2026, la versión completa que superó a este
   parche liviano).

**Chequeo Agronómico e Hidráulico multi-sistema — tarjetas duplicadas por sistema de riego
(implementado, jul-2026):** la versión "Mixto" de arriba era un parche — declaraba la ambigüedad
pero seguía mostrando UN solo chequeo, así que el revisor tenía que repetirlo a mano para el
segundo sistema. El usuario pidió la solución real: "que tanto el Chequeo del Cálculo del Diseño
Agronómico, como el de Diseño hidráulico, se duplicaran según los sistemas de riego del proyecto"
y aportó el dato clave que lo hizo viable: los consultores presentan el cálculo de cada sistema
en un bloque separado con su propio encabezado (ej. "Cálculo agronómico — Sector Goteo" / "—
Sector Aspersión"), así que separar los datos deja de ser "adivinar dónde mezclar" y pasa a ser
"identificar encabezados y extraer cada bloque" — mucho más confiable. Se implementó primero
Agronómico y, una vez verificado, el mismo patrón exacto se replicó a Hidráulico en la misma
sesión — ambos ya en producción. El selector de N° de sistemas es GLOBAL y ÚNICO para los dos
chequeos (ver la sección "Selector unificado" más abajo — corrección explícita del usuario sobre
el diseño inicial, que tenía el selector solo en la tarjeta Agronómico).
- **Selector "N° de sistemas de riego" (1 o 2, tope fijo)**, hoy único y compartido (ver más
  abajo) — el revisor lo fija ANTES de extraer. Tope fijo en 2 (no lista dinámica), mismo patrón
  que `N_TRAMOS_HIDRAULICOS=6` en la tabla de tramos hidráulicos: si algún proyecto raro tiene 3+
  sistemas, el revisor trata el tercero como observación manual aparte.
- `_extraer_datos_agronomicos(docs_grupo, n_sistemas)` (analyzer.py) — UNA sola llamada a Haiku
  (no N llamadas). Si `n_sistemas=2`, el prompt instruye a la IA a identificar los encabezados de
  cada sistema en el expediente y devolver el array `"sistemas"` con exactamente 2 objetos, en el
  mismo orden en que aparecen en el texto — sin mezclar datos de un sistema con otro. Con
  `n_sistemas=1` (default, compatible con la firma anterior) devuelve un array de 1 objeto. Nunca
  inventa: mismo criterio null-si-no-aparece de siempre. `max_tokens` escala con `n_sistemas`
  (doble cupo con 2, ya que el JSON de salida duplica campos).
- `_bloque_verificacion_agronomica(datos)` — ahora recibe `{"sistemas": [...]}` y es el punto de
  entrada: con 1 sistema arma el mismo bloque de siempre (delegado a
  `_bloque_verificacion_agronomica_sistema()`, que es la función vieja renombrada, sin cambios
  de lógica); con 2, recalcula cada sistema por separado y concatena ambos bloques etiquetados
  `=== SISTEMA DE RIEGO 1 (Goteo) ===` / `=== SISTEMA DE RIEGO 2 (Aspersión) ===`, con una
  instrucción explícita a la IA de NO cruzar/comparar parámetros (Kc, eficiencia, factor de
  agotamiento) entre los dos bloques — cada uno es independiente y ambos pueden ser correctos con
  valores distintos. Conectado en `analizar_item()` vía el parámetro nuevo `n_sistemas_agronomico`
  (default 1), que en `revisar_item()` (main.py) se lee de
  `verificacion_calculos["agronomico"]["n_sistemas"]` normalizado (ver abajo) — se aplica tanto en
  el flujo de auto-extracción como cuando el revisor ya validó los datos a mano.
- **Modelo de datos** — `proyecto["verificacion_calculos"]["agronomico"]` pasó de un dict plano
  (un solo sistema) a `{"n_sistemas": 1|2, "sistemas": [ {...}, ... ], "validado", "fecha_validado",
  "validado_por"}`. `_normalizar_verif_agronomico()` (main.py) es el único punto que lee este
  campo — envuelve datos guardados ANTES de este cambio (dict plano sin clave `"sistemas"`, real
  en producción para el concurso 202-2026) en `{"n_sistemas": 1, "sistemas": [ese dict plano]}`
  de forma transparente, así que proyectos ya cargados siguen funcionando sin migración de datos
  ni acción del revisor — se usa tanto en `pagina_calculos()` (para renderizar) como en
  `revisar_item()` (para alimentar `analizar_item()`).
- **UI (`calculos.html`)** — la tarjeta Agronómico ahora itera `agro_sistemas` (lista de
  `{idx, datos, calc}` armada en `pagina_calculos()`) y duplica el bloque completo (Sistema de
  riego + Datos base + Datos de diseño + tabla Extraído/declarado vs. calculado) una vez por
  sistema, con TODOS los `id`/`name` de campos prefijados `s{idx}_` (ej. `s0_cultivo`,
  `s1_kc`, `s0_agro-etc`) — con 1 solo sistema sigue siendo `s0_...`, sin caja visual extra; con
  2, cada tarjeta queda envuelta en un borde propio con encabezado "Sistema 1 — Goteo" / "Sistema
  2 — Aspersión". El formulario de guardado (`form-agro`) es UNO SOLO que envía todos los campos
  de ambos sistemas a la vez, más un campo oculto `n_sistemas`; `calculos_guardar_agronomico()`
  (main.py) itera `range(n_sistemas)` leyendo cada prefijo `s{i}_` del form. El botón "Ya revisé
  estos datos" sigue siendo uno solo (valida ambos sistemas juntos, no por separado).
- **JS (recálculo en vivo)** — `recalcAgro()` itera `N_SISTEMAS` llamando a
  `recalcAgroSistema(prefijo)` por cada sistema — función parametrizada por prefijo de id
  (`numVal(p+"cc_pct")`, `setText(p+"agro-etc", ...)`, etc.), sin cambios de fórmula. El toggle
  de campos Goteo/Aspersión (`.campo-goteo`/`.campo-aspersion`) quedó scopeado por tarjeta
  (`wrap.querySelectorAll(...)` sobre el contenedor `#s{idx}_wrap` de ESE sistema, no
  `document.querySelectorAll` global) — necesario para que seleccionar "Aspersión" en el sistema 2
  no oculte los campos de goteo del sistema 1. Verificado con Playwright: ambas tarjetas
  recalculan de forma independiente con datos distintos (Kc/ETc/rango DT-05 no se mezclan entre
  sistemas), el toggle CSS no se filtra entre tarjetas, y los datos persisten correctamente tras
  guardar y recargar la página — incluyendo el caso de volver de 2 sistemas a 1 (la tarjeta del
  sistema 2 desaparece sin errores).

**Selector "N° de sistemas de riego" unificado — Hidráulico completa el patrón multi-sistema
(implementado, jul-2026):** al pedir extender el mismo patrón a Diseño Hidráulico, el usuario
hizo una corrección importante: "el selector de 1 o 2 sistemas de riego es global, se debe elegir
solo una vez y se aplica a los dos chequeos, hidráulico y agronómico, porque no puede ser que
solo el agronómico se haga para 2 y el hidráulico sea para 1 eso no se da" — un proyecto con 2
sistemas de riego tiene 2 diseños completos (agronómico E hidráulico), nunca uno de cada. El
selector individual que vivía dentro del form "Extraer" de Agronómico (versión anterior) se
eliminó y se reemplazó por uno ÚNICO arriba de ambas tarjetas.
- **Modelo de datos** — `proyecto["verificacion_calculos"]["n_sistemas"]` (1|2) pasó a vivir a
  nivel RAÍZ, no colgado de `agronomico` como en la versión anterior — es la fuente de verdad
  única para ambos chequeos. `hidraulico` y `agronomico` ya NO guardan su propio `n_sistemas`,
  solo `{"sistemas": [...], "validado", "fecha_validado", "validado_por"}`. Para Hidráulico,
  cada sistema es `{"tramos": [...]}` (antes era un dict plano `{"tramos": [...], "validado"}`
  sin envoltorio por sistema).
- **Compatibilidad con datos ya en producción** — este cambio pisa DOS generaciones de formato
  anteriores, ambas reales (concurso 202-2026 ya se usó con la versión anterior): (1) el formato
  histórico pre-multisistema (dict plano de un solo sistema, sin clave `"sistemas"` — Agronómico
  con campos sueltos tipo `{"cultivo":..., "kc":...}`, Hidráulico con `{"tramos": [...]}`), y (2)
  el formato intermedio de la iteración anterior (`n_sistemas` colgado DENTRO de `agronomico`).
  `_n_sistemas_proyecto(verif)` (main.py) resuelve el N° global: usa `verif["n_sistemas"]` si
  existe: si no, cae a `verif["agronomico"]["n_sistemas"]` (formato intermedio). Con ese número ya
  resuelto, `_normalizar_verif_multisistema(datos, n_sistemas, campo_legacy=None)` (reemplaza a la
  función `_normalizar_verif_agronomico` de la iteración anterior, ahora genérica para ambos
  chequeos) envuelve cualquiera de los dos formatos viejos en `{"sistemas": [...]}`, rellena con
  `{}` hasta completar `n_sistemas` si hace falta, y no toca nada si los datos ya vienen en el
  formato nuevo. `campo_legacy="tramos"` para Hidráulico (el dato viejo estaba bajo esa clave);
  Agronómico no pasa ese parámetro (el dato viejo eran campos sueltos directos en el dict). Sin
  esto, un proyecto real cargado con la versión anterior (2 sistemas guardados en Agronómico, 1
  tramo plano guardado en Hidráulico) se habría roto o mostrado datos incompletos.
- `analyzer.py`: `_extraer_datos_hidraulicos(docs_grupo, n_sistemas)` — mismo patrón que la
  extracción agronómica (identifica encabezados por sistema, devuelve `{"sistemas": [{"tramos":
  [...]}, ...]}`, `max_tokens` escala con `n_sistemas`). `_bloque_verificacion_hidraulica(datos)`
  es ahora el punto de entrada multi-sistema (delega a `_bloque_verificacion_hidraulica_sistema()`,
  la función vieja renombrada) — con 2 sistemas etiqueta cada bloque `=== SISTEMA DE RIEGO N —
  DISEÑO HIDRÁULICO ===` e instruye a la IA a no cruzar tramos/velocidades entre sistemas.
  `analizar_item()` unificó el parámetro — antes `n_sistemas_agronomico` (solo para la extracción
  agronómica), ahora `n_sistemas` a secas, usado para AMBAS extracciones (hidráulica y
  agronómica) dentro del ítem `diseno_hidraulico`.
- **Nueva ruta** `POST /proyecto/{id}/calculos/n-sistemas` (main.py) — guarda el selector global;
  es el ÚNICO lugar que lo edita. Las rutas de extraer/guardar de cada tarjeta (Agronómico e
  Hidráulico) ya no leen `n_sistemas` de su propio formulario — lo resuelven siempre desde
  `_n_sistemas_proyecto(proyecto["verificacion_calculos"])`, así no puede haber desincronización
  entre lo que el revisor ve y lo que efectivamente se extrae/guarda.
- **UI (`calculos.html`)** — tarjeta azul nueva arriba de Agronómico/Hidráulico con el `<select>`
  único ("N° de sistemas de riego del proyecto"), auto-submit por `onchange` (con `<noscript>`
  de respaldo). La tabla de tramos de Hidráulico se duplica igual que Agronómico, con ids/names
  prefijados `s{idx}_t{j}_...` (ej. `s0_t0_caudal`, `s1_t2_diametro`); `N_TRAMOS_HIDRAULICOS=6`
  sigue siendo el tope POR sistema, no cambia. `pagina_calculos()` arma `hid_sistemas` (lista de
  `{idx, tramos}`, con `_tramos_con_calculo()` aplicado a cada sistema por separado) y pasa
  `n_sistemas` (ya no `agro_n_sistemas`) como única variable de conteo para ambas tarjetas.
- **JS** — `N_AGRO_SISTEMAS` se renombró a `N_SISTEMAS` (compartida entre `recalcAgro()` y el
  nuevo `recalcHidraulico()`, que ahora itera `N_SISTEMAS` llamando a
  `recalcHidraulicoSistema(prefijo)` — la función vieja renombrada y parametrizada igual que se
  hizo con Agronómico). `N_TRAMOS` (tope por sistema) se calcula desde
  `hid_sistemas[0].tramos|length` en vez de la variable `tramos` que ya no se pasa al contexto.
  Verificado con Playwright: cambiar el selector global de 1→2 muestra AMBAS tarjetas nuevas
  (Agronómico Y Hidráulico) sin tener que elegir nada en cada una por separado, el recálculo de
  tramos es independiente por sistema (velocidades distintas con datos distintos), persiste tras
  guardar/recargar, y volver a 1 sistema oculta limpiamente las tarjetas del sistema 2 en ambos
  chequeos a la vez. También se verificó compatibilidad completa con un proyecto sintético que
  simula datos guardados en AMBOS formatos viejos a la vez (Agronómico + Hidráulico pre-
  multisistema) — se normalizan y muestran correctamente sin acción del revisor.
- Carrete/pivote (INIA-Carillanca) y microaspersión siguen sin fórmula propia — fuera de alcance,
  sin cambios en esta iteración.

**Exportar a archivo del Diseñador de Riego (implementado, jul-2026):** el usuario pidió generar,
desde la página Chequeo, un `.json` del mismo formato que guarda/abre su otra app, el **Diseñador
de Riego** (`disenador_riego_v97.html`, single-file HTML que corre en su Mac) — así puede abrir ese
archivo en el Diseñador y evaluar a mano aspectos que Revisor no cubre, sin recargar Revisor con
esos cálculos. Módulo nuevo `exportar_disenador.py` (función pura `construir(...)`), ruta
`GET /proyecto/{id}/calculos/exportar-disenador/{idx}` (descarga con `Content-Disposition
attachment`), y un botón "Exportar para el Diseñador de Riego (.json)" en cada tarjeta de sistema
Agronómico de `calculos.html`.
- **Formato del Diseñador**: `{"__sys": "got"|"mic"|"asp"|"car", "__name", "__date", "fields":
  {...}}`. Cada sistema de riego usa un PREFIJO de campo distinto (`g-`/`m-`/`a-`/`c-`) y su
  código `__sys`; el mapeo `SISTEMA_A_DR` traduce el `sistema_riego` declarado en Revisor
  (Goteo/Microaspersión/Aspersión/Carrete) a ese par. `__name` = "{sistema} {codigo_sep}" (a
  pedido del usuario); `__date` en el formato del Diseñador ("dd-mm-aaaa, h:mm:ss a.m./p.m.",
  helper `_fecha_disenador()` en main.py). El nombre de archivo se pasa por
  `unicodedata`→ASCII (sin tildes/ñ) porque el header Content-Disposition no es unicode-safe; el
  `__name` interno sí conserva la tilde.
- **REGLA — solo lo que hay, no inventar**: se exportan ÚNICAMENTE los campos con dato real
  (identificación desde el Resumen; cadena agronómica + superficie/caudal/horas/criterio de riego
  desde el Chequeo; los 11 campos FV con los MISMOS sufijos en ambas apps). Las claves sin dato NO
  se incluyen (se omiten, no van con ""), así el Diseñador conserva sus defaults al cargar. El
  revisor completa el resto en el Diseñador.
- **Diferencias por sistema** (verificadas contra archivos reales que subió el usuario, uno por
  sistema): el campo de superficie a regar cambia de nombre (`-sup` en goteo/micro, `-strie` en
  aspersión, `-supr` en carrete); "criterio de riego"/agotamiento (`-crit`) solo existe en
  aspersión/carrete; carrete no tiene campo de horas de riego (`-hrs`). Los TRAMOS de tubería solo
  se exportan a la lista genérica `__tramos` (l/q) en aspersión y carrete — goteo/microaspersión
  usan en el Diseñador un modelo matriz/terciaria/lateral (`-lm/-dm/-cm`, etc.) que NO mapea desde
  nuestra tabla de tramos plana sin adivinar cuál tramo es cuál, así que ahí los tramos no se
  exportan (quedan para el Diseñador). En `__tramos`, `l`=longitud y `q`=caudal (que sí tenemos);
  `t` y `z` van vacíos (no existen en Revisor, no se inventan).
- **Marco de plantación / espaciamiento** (agregado jul-2026 tras prueba real — los IDs difieren
  por sistema): Goteo → `deh` (dist. entre hileras) ← `distancia_hileras_m`, `dsh` (dist. sobre
  hilera/entre plantas) ← `distancia_plantas_m`, `nlin` ← `n_lineas_emisor`, `espm` (esp. entre
  goteros) ← `espaciamiento_emisores_m`. Microaspersión → `dl` (entre laterales/hileras) ←
  `distancia_hileras_m`, `de` (entre emisores) ← `espaciamiento_emisores_m`. Aspersión → `easp` ←
  `espaciamiento_aspersores_m`, `elat` ← `espaciamiento_laterales_m`. Carrete no tiene marco de
  plantación en el Diseñador.
- **UTM normalizada** (fix jul-2026): la UTM del Resumen puede venir en notación chilena de miles
  ("5.946.762"), y el `<input type="number">` del Diseñador la rechaza y queda vacía. La ruta de
  export pasa `coord_n`/`coord_e` por `_parse_coord_numero` (el mismo parser del botón de Google
  Maps) para dejar un número plano antes de exportar (`g-utmn`/`g-utme`).
- **Alcance**: exporta los datos GUARDADOS de `verificacion_calculos` (no los del formulario sin
  guardar) — el botón avisa "guarda primero si acabas de editar". El botón solo aparece si el
  sistema declarado es uno de los cuatro conocidos (si está sin declarar o "Mixto", no aparece).
  FV es global al proyecto (un solo `energetico`), así que con 2 sistemas ambos exportan el mismo
  bloque FV. Verificado con los 4 sistemas: el JSON generado calza campo por campo con el formato
  de los archivos de ejemplo.
- **Botón "Abrir Diseñador de Riego" (implementado, jul-2026)**: el usuario pasó el HTML del
  Diseñador (`disenador_riego_v97.html`, single-file 4,4 MB) y se subió a `static/` del repo, así
  que se sirve desde `/static/disenador_riego_v97.html` (mismo origen — funciona en la oficina y
  en cualquier equipo, a diferencia del `file://` local que los navegadores bloquean desde una
  página `https://`). El botón está alineado a la derecha, en la misma línea del selector "N° de
  sistemas de riego" (tarjeta azul superior de `calculos.html`), abre en pestaña nueva
  (`target="_blank" rel="noopener"`). Flujo completo: exportar el `.json` desde Revisor → abrir el
  Diseñador con este botón → en el Diseñador, "Importar proyecto" y elegir el archivo. Se verificó
  contra la función `restoreFieldData()`/`importProject()` del Diseñador que el formato exportado
  calza (solo asigna las claves presentes, conserva sus defaults para el resto; tramos por
  `l/q/t/z`). **Ojo — el import del Diseñador NO cambia de sistema solo**: usa el sistema
  activo en su pantalla, así que el revisor debe seleccionar Goteo/Aspersión/etc. en el Diseñador
  ANTES de importar (el prefijo de campos del archivo —g-/a-/…— debe coincidir con el sistema
  activo). Si se actualiza el HTML del Diseñador, reemplazar `static/disenador_riego_v97.html` (y
  si cambia el nombre de archivo, actualizar el enlace en `calculos.html`).

**Chequeo Agronómico — modelo de GOTEO sin criterio de riego (fix jul-2026):** al probar la
exportación el usuario notó que el Chequeo pedía "Criterio de Riego" (factor de agotamiento) en
goteo y sin él NO calculaba, pese a que en goteo ese dato no se usa. Es correcto: el Diseñador de
Riego calcula goteo con `calcGA` como `Db = ETc / Ef` DIRECTO (riego diario de alta frecuencia,
la demanda repone la ETc del día, Fr=1, sin pasar por el agotamiento AD→Dn→Fr), y por eso goteo
no tiene campo `-crit`. Aspersión/Carrete (`calcAA`) y Microaspersión (`calcMA`) sí usan la cadena
con agotamiento. Se alineó el Chequeo con ese modelo, SOLO para Goteo:
- `calculos_riego.cadena_agronomica(...)` ganó el parámetro `alta_frecuencia` (default False =
  comportamiento de siempre). Con `True`: `Db = ETc/Ef`, `Fr_adj=1`, `Dn=Dn_adj=ETc`; el
  `factor_agotamiento_pct` se ignora (puede venir None); `ad` se calcula solo si están CC/PMP/Da/
  Prof (dato informativo), si no queda None.
- `_es_goteo(datos)` (main.py) y la misma condición `sistema_riego == "Goteo"` en
  `_bloque_verificacion_agronomica_sistema` (analyzer.py) eligen el modelo. En goteo la lista de
  campos requeridos NO incluye `factor_agotamiento_pct`, así que su ausencia ya no bloquea. El
  bloque de verificación de la IA, en goteo, muestra solo `ETc` y `Db = ETc/Ef` (sin Dn/AD/Fr) y
  no compara Dn/Fr declarados (solo Db).
- **UI (`calculos.html`)**: el campo "Criterio de Riego (%)" tiene la clase `campo-criterio-riego`
  y el JS lo OCULTA (`display:none`) cuando el sistema es Goteo; `recalcAgroSistema` usa
  `esGoteo` para armar la lista `base` sin `fa`, calcular `Db=ETc/Ef` con `Fr="1 (riego diario)"`,
  mostrar `AD`/`Dn` como "—", y ajustar el hint para no pedir el criterio de riego. Verificado con
  Playwright (goteo calcula con criterio de riego vacío/oculto; al cambiar a Aspersión el campo
  reaparece y se vuelve a exigir). Si se cambia una fórmula, recordar la regla de siempre:
  replicar el cambio en `calculos_riego.py` (Python) Y en el `<script>` de `calculos.html` (JS).
- **Alcance**: solo Goteo usa el modelo directo. Microaspersión sigue con la cadena de agotamiento
  (en el Diseñador `calcMA` usa un criterio por defecto de 50 aunque no exponga el campo) — no se
  tocó porque el usuario reportó específicamente goteo; si en el futuro molesta lo mismo en micro,
  aplicar el mismo patrón o un default 50.

**Acumulador (estanque/tranque regulador) en el Chequeo Agronómico (implementado, jul-2026):**
caso real del concurso 202-2026: un proyecto con caudal disponible de la fuente muy bajo (0,4 l/s)
declara un acumulador de 10 m³ para regar una superficie mayor de la que el caudal de la fuente
solo permitiría. El usuario lo agregó primero al Diseñador de Riego (subió `disenador_riego_v98.html`,
reemplazó a v97 en `static/` — actualizar el link de "Abrir Diseñador de Riego" en `calculos.html`
si se vuelve a actualizar el archivo) y pidió portar el mismo criterio al Chequeo. Se leyó
directo el código del Diseñador (`calcAcum`, línea ~6172) para no adivinar la fórmula:
```
Q_acumulador[l/s] = Volumen[m³] × 1000 / (horas_disponibles_dia × 3600)
```
**Importante — el Diseñador usa "Horas Riego Disp." (Paso 1, el dato que declara el consultor),
NO el "tiempo de riego" calculado** (que sí fue lo que el usuario planteó de palabra al pedir el
cambio) — se le hizo notar la diferencia y se implementó fiel al código real del Diseñador para
que ambas apps den el mismo número si el revisor exporta/importa el mismo proyecto.
- `calculos_riego.verificacion_diseno_riego(...)` ganó el parámetro `volumen_acumulador_m3`. Si
  viene junto con `horas_disponibles_dia`, calcula `caudal_acumulador_ls` con la fórmula de
  arriba y lo usa como **caudal EFECTIVO** en vez del `caudal_disponible_ls` de la fuente para:
  (a) `superficie_segura_ha`, y (b) el chequeo ITT-03 (`requiere_acumulador`) — el caudal de la
  fuente pasa a ser solo el que recarga el acumulador entre riegos, no el que se usa durante el
  riego. Sin acumulador declarado, el comportamiento es exactamente el de antes (fallback al
  caudal de la fuente).
- `_extraer_datos_agronomicos()` (analyzer.py) extrae también `volumen_acumulador_m3` (null si el
  expediente no declara acumulador). `_bloque_verificacion_agronomica_sistema()` inyecta el
  cálculo del caudal equivalente en el prompt de la IA y ajusta el mensaje de ITT-03: si hay
  acumulador y el caudal de diseño lo supera ×1,2, la observación dice que el VOLUMEN DECLARADO
  no alcanza (en vez de "se requiere acumulador", que ya no aplica porque el proyecto sí declaró
  uno — el problema pasa a ser su tamaño).
- **UI (`calculos.html`)**: campo nuevo "Volumen acumulador (m³)" en "Datos de diseño" (por
  sistema, junto a Superficie/Caudal disponible/Precipitación/Horas disponibles). La fila
  "Superficie de riego segura" de la tabla ganó un `<span id="{p}agro-sup-info">` (nota neutra,
  no roja) que muestra el caudal equivalente cuando hay acumulador — separado del
  `agro-sup-nota` existente (que sigue siendo solo la alerta roja de superficie insuficiente,
  para no mezclar un mensaje informativo con uno de alerta en el mismo span). El chequeo ITT-03
  también cambia de texto con acumulador ("El volumen de acumulador declarado no alcanza" en vez
  de "Requiere acumulador"). Mismo patrón de siempre: la fórmula se duplicó a mano en el
  `<script>` de `calculos.html` (`recalcAgroSistema`), verificada con Playwright contra el
  cálculo Python (mismo caudal equivalente, misma superficie segura, mismo mensaje ITT-03).
- `exportar_disenador.py`: se agregó `put("acum-vol", sistema_agro.get("volumen_acumulador_m3"))`
  para los 4 sistemas (el Diseñador v98+ tiene el campo `{prefijo}-acum-vol` en los cuatro). El
  checkbox `{prefijo}-acum-chk` NO se exporta a propósito — es un `<input type="checkbox">` y
  `restoreFieldData()` del Diseñador lo restaura con `el.value = ...`, que no marca `.checked`
  (limitación del propio Diseñador, no de Revisor) — el revisor debe tildar "¿Acumula agua?" a
  mano en el Diseñador después de importar para que se muestre el volumen ya cargado.
- **Alcance**: solo cubre la superficie segura y el chequeo ITT-03 — no toca el resto de la
  cadena agronómica (ETc/Dn/Fr/Db) ni el diseño hidráulico (tramos), que no dependen del caudal
  de la fuente en el modelo actual.

**VIB (Velocidad de Infiltración Básica) y limpieza del marco de plantación en Aspersión
(implementado, jul-2026):** dos ajustes al Chequeo Agronómico pedidos juntos por el usuario tras
usar la app con proyectos reales:
1. **VIB nueva, solo Aspersión** — verifica que la Precipitación del sistema (tasa de aplicación,
   ya existente en "Datos de diseño") no supere la Velocidad de Infiltración Básica del suelo
   (mm/hr); si la supera, hay riesgo de escorrentía. Mismo criterio que usa el Diseñador de Riego
   ("VIB > VA" en aspersión, `calcAA`). Campo nuevo "VIB del suelo (mm/hr)" en "Datos base
   declarados", visible solo si el sistema declarado es Aspersión (o sin declarar/Mixto, mismo
   criterio "mostrar si es ambiguo" del resto de la tarjeta) — `calculos_riego.verificacion_vib()`
   nueva, usada en `_bloque_verificacion_agronomica_sistema` (analyzer.py, prompt de la IA) y en
   `_agronomico_calculo` (main.py, independiente del resto de la cadena, igual que Kc-DT05). Fila
   nueva en la tabla de resultados ("VIB vs. Precipitación del sistema (Aspersión)"), y exportado
   al Diseñador como `{prefijo}-vib` en Aspersión y Microaspersión (el Diseñador expone el campo
   en ambos, aunque el Chequeo hoy solo lo pide para Aspersión).
2. **Marco de plantación (Distancia entre hileras/entre plantas) — eliminado para Aspersión.**
   Bug real reportado por el usuario: esos dos campos eran incondicionales (se mostraban para
   TODOS los sistemas) y en Aspersión la extracción automática los rellenaba con los MISMOS
   valores que el espaciamiento entre aspersores/laterales — confuso, porque en aspersión el
   "marco de plantación del cultivo" no es un dato relevante (a diferencia de Goteo/Microaspersión,
   donde el emisor se ubica respecto a cada planta). Se movieron esos dos campos a la clase
   `campo-goteo` (el mismo grupo que N° líneas de emisor/espaciamiento entre emisores) — ahora se
   ocultan junto con el resto del grupo Goteo cuando el sistema es Aspersión/Carrete, dejando solo
   Espaciamiento entre aspersores/laterales visibles para esos dos. Confirma además, de paso, lo
   que ya reflejaba `exportar_disenador.py` (el Diseñador tampoco tiene DEH/DSH para Aspersión ni
   Carrete) — el Chequeo quedó consistente con eso.
- Verificado con Playwright: en Goteo se ve el marco de plantación y NO la VIB; al cambiar a
  Aspersión se invierte (VIB visible, marco de plantación oculto), el cálculo VIB reacciona en
  vivo (alerta de escorrentía si Precipitación ≥ VIB, "OK" si no), y la exportación al Diseñador
  incluye `a-vib` y ya no incluye `a-deh`/`a-dsh`.

**Página "Chequeo de Cálculos" (implementado, jul-2026):** `/proyecto/{id}/calculos`
(`templates/calculos.html`), página aparte del proyecto — mismo estilo de navegación arriba
que las otras, pero con su propia ruta/template (no pasa por `_render_proyecto`, para no
cargar ese contexto pesado). Resuelve el riesgo de que la extracción automática (Haiku) se
equivoque: el revisor ve los datos extraídos (tramos de tubería para Hidráulico, cadena
agronómica para Agronómico) en un formulario editable, con el recálculo mostrado al lado de
cada campo, y puede corregirlos a mano antes de darlos por buenos. Las claves de guardado
(`hidraulico`/`agronomico`/`energetico`) son independientes de los ítems SEP — se mantuvieron
tal cual al portar la verificación desde el método por Ejes (ver más abajo).
- Botón **"Extraer de los documentos"** (`POST .../calculos/{grupo}/extraer`) — corre la
  misma extracción de `analyzer.py` bajo demanda y sobrescribe el formulario. NO marca como
  validado.
- Botón **"Guardar"** + checkbox **"Ya revisé estos datos"** (`POST .../calculos/{grupo}/guardar`)
  — guarda lo que haya en el formulario (editado o no) en `proyecto["verificacion_calculos"][grupo]`;
  si el checkbox está marcado, `validado=True` + `fecha_validado` + `validado_por`.
- Hidráulico: hasta `N_TRAMOS_HIDRAULICOS=6` tramos fijos (tabla server-rendered, sin JS de
  agregar/quitar filas — suficiente para el tamaño típico de estos proyectos). Agronómico: un
  solo formulario con los 8 campos base + los 3 valores declarados por el consultor (Dn/Fr/Db).
  Fotovoltaico: bomba/sitio + panel/inversor/sistema + los 3 valores declarados (N° paneles,
  kWp, sección cable DC).
- **Efecto en el análisis:** en `revisar_item()` (main.py), si `verificacion_calculos[grupo]
  ["validado"]` es `True` para el ítem correspondiente (`diseno_hidraulico` lee
  `hidraulico`+`agronomico`; `diseno_fotovoltaico` lee `energetico`), esos datos (ya revisados
  por el humano) se pasan a `analizar_item()` como `datos_verificacion_*` y se usan DIRECTO,
  sin volver a llamar a Haiku para extraer — la supervisión humana reemplaza la extracción
  automática. Si no está validado, sigue extrayendo automáticamente en cada revisión
  (comportamiento de siempre, sin cambios).
Cubre Hidráulico, Agronómico y (desde jul-2026) Fotovoltaico. Carrete/pivote (INIA-Carillanca)
y microaspersión todavía no tienen fórmula ni página.

**Recálculo en vivo + tabla "Extraído/declarado vs. calculado" (implementado, jul-2026):** a
pedido del usuario, dos cambios sobre `calculos.html` para que el chequeo sea realmente útil de
un vistazo:
1. **Tabla de resultados, no párrafo.** Antes el recálculo se mostraba como un párrafo de texto
   corrido (`.calc-resultado`) — "revuelto", según el usuario. Ahora cada tarjeta (Agronómico,
   Fotovoltaico) tiene una tabla `.calc-resultados-tbl` con 3 columnas: Resultado · Extraído/
   declarado · Calculado por la app, una fila por concepto (Dn, Fr, Db, Superficie de riego
   segura, Tiempo de riego, N° de sectores, Caudal de diseño/ITT-03 para Agronómico; N° paneles,
   kWp, sección cable DC para Fotovoltaico) — el mismo concepto siempre aparece en ambas columnas
   para poder comparar de un vistazo, con una nota roja (`.calc-nota.calc-alerta`) debajo del
   valor calculado cuando no coincide con lo declarado. Hidráulico ya tenía esta idea (columna
   "V declarada" + resultado recalculado con la discrepancia inline) — sirvió de referencia para
   el formato de las otras dos tarjetas.
2. **Recálculo en tiempo real (JS), no solo al guardar.** Antes el recálculo mostrado era el que
   Python calculó en el último render de la página (`_agronomico_calculo`/`_fv_calculo`/
   `_tramos_con_calculo` en main.py) — cambiar un campo no actualizaba nada hasta guardar y
   recargar. Ahora hay un `<script>` al final de `calculos.html` que porta las MISMAS fórmulas de
   `calculos_riego.py` a JS puro (sin librerías): `recalcAgro()`, `recalcHidraulico()`,
   `recalcFV()`, cada una escuchando el evento `input` de su `<form>` (delegación de eventos, un
   solo listener por formulario) y recalculando al vuelo con lo que haya en los campos, sin
   submit ni recarga. Se ejecutan también una vez al cargar la página, así que la tabla nace ya
   poblada sin depender del primer `input`. **Duplica las fórmulas en dos lenguajes a propósito**
   (Python sigue siendo la fuente de verdad para el análisis real y el guardado; JS es solo para
   feedback visual instantáneo) — se verificaron manualmente ambas versiones con los mismos
   datos de prueba para confirmar que dan resultados idénticos antes de desplegar. Si se cambia
   una fórmula en `calculos_riego.py`, hay que replicar el cambio a mano en el `<script>` de
   `calculos.html` — no hay una fuente única compartida.

**Verificación fotovoltaica (implementado, jul-2026):** `calculos_riego.dimensionamiento_fv()`
porta `calcFV()` del Diseñador de Riego — energía diaria requerida (P_bomba×horas bombeo),
derating por temperatura, N° de paneles mínimo, configuración serie/paralelo según voltaje del
sistema, y sección de cable DC por caída de tensión (2%, distancia campo→inversor asumida en
50 m — mismo supuesto que la app hermana). `_extraer_datos_fv()` / `_bloque_verificacion_fv()`
en `analyzer.py`, mismo patrón que hidráulico/agronómico, conectado en `analizar_item()` para
`item_key == "diseno_fotovoltaico"`. **Cobertura parcial a propósito** (igual que hidráulico/agronómico):
no incluye cableado AC, protecciones (DPS/fusibles), estructura de montaje, ni contraste
explícito con el Explorador Solar — el propio Diseñador de Riego tampoco los tiene desarrollados
todavía. Prioridad de fuente: el ~80% de los proyectos de esta cuenta llevan sistema FV (goteo/
aspersión + FV), por eso se implementó antes que carrete/pivote (~20%, sin fórmula portada aún).

**Verificación de precios contra tabla de referencia promedio (implementado, jul-2026):**
distinto del resto de las verificaciones (Hazen-Williams, cadena agronómica, FV): esas son
fórmulas exactas, esta es texto libre comparado contra un catálogo — inherentemente
aproximada, no un cálculo determinístico. **La tabla NO es una copia oficial certificada por
la CNR** — es una tabla de precios PROMEDIO que el revisor arma y mantiene por su cuenta
(nombre elegido a propósito para no sobre-representar su autoridad frente al revisor ni frente
a la IA en el prompt). Origen del problema: la CNR publica sus propios precios referenciales de
materiales/equipos en un dashboard de Power BI (`app.powerbi.com/view?r=...`) para detectar
sobreprecios y subvaluaciones en el presupuesto, pero ese dashboard **no tiene API ni export de
datos** — es solo visualización, y `app.powerbi.com` además está bloqueado por la política de
red del entorno de ejecución de Claude Code (403 al intentar conectar), así que la app nunca
puede leerlo en vivo. Solución: el revisor sube su propia copia en Excel (columnas
`categoria`/`item`/`unidad`/`precio`, reconstruida a mano o con ayuda de otra IA leyendo
capturas del dashboard u otras fuentes) en `/admin/precios` — reemplaza la tabla completa cada
vez, no hay merge. Mientras no se haya subido ninguna, la verificación simplemente no corre
(puramente aditivo, cero cambio de comportamiento).
- `database.py`: `get_precios()`/`save_precios()`, colección global nueva `precios` (no
  keyed, un solo blob `{items: [...], fecha_actualizado, actualizado_por, nombre_archivo}`).
- `extractor.py`: `parse_tabla_precios()` lee la primera hoja del Excel celda por celda
  (distinto de `_from_excel`, que concatena todo a texto plano) — encabezados case-insensitive
  sin tildes, en cualquier orden; `categoria`/`item`/`precio` obligatorios, `unidad` opcional.
  `_parse_precio()` interpreta notación chilena: si hay coma, punto=miles y coma=decimal; si
  NO hay coma, cualquier punto se trata como separador de miles (nunca decimal) — la app usa
  esa convención en todos lados y los precios de esta tabla son montos en pesos, no fracciones.
- `analyzer.py`: `_extraer_partidas_presupuesto()` (Haiku, mismo patrón que
  `_extraer_datos_hidraulicos`) saca `{item, unidad, cantidad, precio_unitario}` de cada
  partida del presupuesto — usa `max_tokens=4000` (más que el resto de las extracciones,
  `MAX_TOKENS_EXTRACCION=1500`, porque un presupuesto real puede tener muchas partidas) y
  `_extraer_json_tolerante()` (reintenta cerrando llaves/corchetes si el JSON quedó cortado,
  mismo patrón que `_analizar_grupo`). `_mejor_match_precio()` compara cada partida contra la
  tabla por solapamiento de palabras (Jaccard sobre tokens, sin stopwords) — más robusto que
  comparar caracteres ante reordenamientos ("Tubería PVC 110mm C-10" vs "Tubería PVC clase 10
  diámetro 110mm"); umbral mínimo 0,35, si no hay match sobre ese umbral la partida se ignora.
  `_bloque_verificacion_precios()` arma el bloque solo con las partidas cuya diferencia excede
  `TOLERANCIA_PRECIO_PCT=30` (más ancho que la tolerancia de 10-15% de hidráulica/agronómica,
  porque precios de mercado varían más que una fórmula de ingeniería) y avisa a la IA que el
  match es aproximado — verificar que corresponda al mismo producto antes de observar.
  Conectado en `analizar_item()` para `item_key in ("presupuesto", "presupuesto_electrico")`
  vía el nuevo parámetro `tabla_precios`.
- **Por qué NO se implementó con búsqueda web de la IA en vivo:** se evaluó y se descartó como
  mecanismo principal. Una búsqueda de mercado genérica no es reproducible (mismo ítem revisado
  en fechas distintas puede dar resultados distintos, mal para un informe que se traspasa al
  SEP), tiene menos autoridad que el precio oficial que la propia CNR usa para juzgar
  sobreprecios, y suma costo/latencia a cada revisión de presupuesto. La tabla subida a mano
  (actualizada periódicamente, igual que la normativa) es más lenta de mantener pero
  consistente y auditable.
- **Botón "Precios referenciales CNR ↗"** en las tarjetas de los ítems Presupuesto y
  Presupuesto electrificación (`proyecto.html`, página Ítems SEP) — abre el dashboard original
  en pestaña nueva para consulta manual del revisor. Es un link externo simple, no un embed
  (Power BI no lo permitiría y tampoco aporta valor embeberlo). URL en la constante
  `URL_PRECIOS_CNR` (main.py).
- **Administración** (`/admin/precios`, nav "Precios" solo para admin): ver cuántos ítems hay
  cargados, cuándo y quién los subió, tabla completa agrupada por categoría en `<details>`
  desplegables, formulario para subir/reemplazar el Excel, botón para eliminar la tabla.

**Botón "Roles y uso de suelo (IDE Minagri) ↗" (implementado, jul-2026):** mismo patrón que el
botón de precios CNR — link externo simple (no embed) al visor IDE Minagri/CIREN
(`esri.ciren.cl`, constante `URL_IDEMINAGRI` en main.py) para que el revisor consulte
manualmente el rol y la clasificación de uso de suelo del predio. En las tarjetas de los ítems
**Estudio de suelos**, **Memoria de cálculo de superficies** e **Identificación del área de
riego** (`proyecto.html`, página Ítems SEP) — los tres cuyo checklist toca clasificación/
capacidad de uso del suelo o delimitación de superficies. Sin integración de datos (el visor no
expone API).

**Documentos obligatorios de admisibilidad (implementado, jul-2026):** las bases de cada
concurso señalan qué documentos son obligatorios — su no presentación deja el proyecto como
NO ADMITIDO — pero no siempre están en el mismo lugar del texto, hay que buscarlos. Se agregó
una extracción con IA (Haiku) que corre **una vez por concurso** (las bases son las mismas
para todos sus proyectos, no tiene sentido repetir la extracción por proyecto) y que **siempre
requiere revisión y confirmación explícita del revisor humano** antes de usarse — nunca dispara
advertencias en un proyecto por sí sola, evitando que un error de la IA declare "no admitido"
algo que en realidad sí califica (ej. documentos "en trámite" que las bases a veces permiten
igual).
- `analyzer.py`: `extraer_documentos_obligatorios(bases_texto, catalogo_tipo_doc)` — recibe el
  catálogo `TIPO_DOC_LABELS` (definido en main.py, se pasa como parámetro para evitar import
  circular) y devuelve `{"obligatorios": [...], "referencia": "..."}` — la lista de claves
  tipo_doc que las bases marcan EXPLÍCITAMENTE con la consecuencia de inadmisibilidad ("causal
  de inadmisibilidad", "se declarará inadmisible", etc.) — nunca marca un documento solo porque
  las bases lo listan como parte del expediente — más el punto/numeral exacto de las bases
  donde encontró esa lista (ej. "6.3"), para que el revisor lo verifique directamente ahí; vacío
  si no logra identificar uno específico (nunca inventa un número). La lista de obligatorios se
  filtra siempre contra el catálogo real, sin confiar ciegamente en la IA. La referencia también
  es editable a mano por el revisor en el formulario (campo `documentos_obligatorios_referencia`
  en el concurso), por si la IA no la encuentra o se equivoca.
- **Flujo de confirmación** (`/admin/concursos/{id}`, card "Documentos obligatorios
  (admisibilidad)"): botón "Extraer sugerencia de las bases" (`POST .../documentos-
  obligatorios/extraer`) guarda el resultado de la IA en `concurso["documentos_obligatorios"]`
  pero deja `documentos_obligatorios_revisado = False` — en este estado NO se advierte nada
  todavía en los proyectos. Un checklist de los 25 tipos de documento (`TIPO_DOC_LABELS`, orden
  del SEP) se muestra pre-marcado según la sugerencia; el revisor corrige lo que haga falta y
  hace clic en "Guardar y confirmar" (`POST .../documentos-obligatorios/guardar`), que recién
  ahí pone `documentos_obligatorios_revisado = True` + `_fecha` + `_por` — ese guardado explícito
  ES el visto bueno humano, no hay un checkbox "validado" separado como en Chequeo de Cálculos.
  Volver a extraer resetea `_revisado` a `False`, para forzar una nueva revisión si las bases
  cambiaron.
- **Advertencia en el proyecto** (`_render_proyecto()` en main.py → `faltan_obligatorios`):
  solo se calcula si `documentos_obligatorios_revisado` es `True`. Compara
  `concurso["documentos_obligatorios"]` contra los `tipo_doc` presentes en el proyecto y arma
  un banner rojo (no bloqueante — `proyecto.html`, antes de la barra de navegación, visible en
  Resumen/Documentos/Ítems SEP) listando lo que falta. **A propósito NO bloquea los botones de
  revisar ítem** — es una advertencia para que el revisor decida con esa información antes de
  invertir tiempo revisando, no un candado, porque un falso positivo de la IA no debe impedir
  revisar un proyecto que en realidad sí es admisible.

**Archivo de normativa DT-09 eliminado por corrupción (jul-2026):**
`normativa/DT-09_Proyectos_Electricos.txt` (el que debía tener los requisitos eléctricos/FV) se
detectó con texto ilegible en TODO el archivo — problema de codificación en el PDF fuente (glifos
mal mapeados), no del extractor de la app: incluso la vista previa nativa de Google Drive y la
conversión "Abrir con Google Docs" (que debería correr OCR) reproducen el mismo texto roto, lo
que sugiere que el defecto está en la fuente/encoding del PDF, no solo en la capa de texto. Se
eliminó el archivo del repo porque se cargaba completo (hasta 4.000 caracteres) en el
`SYSTEM_PROMPT` de **cada** llamada a la IA sin aportar nada — puro costo sin valor. Mientras no
haya una copia legible, el ítem Diseño Fotovoltaico se apoya en `ITT_Criterios_Tecnificacion.txt`
(ítems esperados en presupuesto FV) y `Manual_Supervision_Obras.txt` (certificación SEC on-grid/
off-grid) — ambos sí están limpios. Si se consigue una copia legible del PDF de DT-09 (o alguien
transcribe manualmente las secciones clave), agregar `normativa/DT-09_...txt` de nuevo con texto
real — no reincorporar el archivo corrupto.

Los **18 ítems del SEP** (`ITEMS_SEP`/`ITEMS_ORDEN`) revisan su(s) documento(s) tal como se
ingresan al Sistema Electrónico de Postulación, para copiar las observaciones directo al SEP.
Página "Revisión por Ítems SEP" (`/proyecto/{id}/items`). Memoria de superficies e
Identificación del área de riego son la base (definen demanda, escala, presupuesto y monto
bonificable); Coherencia Global (último ítem) es el cierre transversal que atrapa los errores
entre documentos — ver el changelog más abajo.

**Bug resuelto — Diseño Fotovoltaico mezclado dentro de "Diseño y cálculos hidráulicos"
(jul-2026):** el ítem `diseno_hidraulico` incluía `diseno_fotovoltaico` y
`reporte_explorador_solar` en su `tipo_docs`, así que al revisar ese ítem se agrupaban también
los archivos de FV — aunque en el SEP real son un anexo aparte (Anexo 9.5, según el propio
`tipo_doc_label`: "Anexo 9.5 — Diseño fotovoltaico"). Se separó en un ítem nuevo
**`diseno_fotovoltaico`** ("Diseño Fotovoltaico"), insertado en `ITEMS_ORDEN` justo después de
`diseno_hidraulico`; este último quedó solo con `["diseno_hidraulico", "diseno_agronomico"]`.
Si aparece un caso similar en otro ítem (documentos agrupados que no correspondan), revisar el
`tipo_docs` de `ITEMS_SEP` contra el `tipo_doc_label` real de `TIPO_DOC_LABELS` en `main.py`.

**"Diseño agronómico" eliminado como opción de clasificación (jul-2026):** el usuario pidió
eliminar "el ítem Diseño Agronómico" porque no existe como anexo propio en el SEP real — es el
MISMO Anexo 9.5 que "Diseño y cálculos hidráulicos" (`TIPO_DOC_LABELS["diseno_agronomico"]` ya
decía literalmente "Anexo 9.5 — Diseño agronómico", mismo número que `diseno_hidraulico`).
Investigado antes de tocar nada: no existía como ítem separado en `ITEMS_SEP`/`ITEMS_ORDEN`
(nunca lo fue) — lo que el usuario llamaba "ítem" era la OPCIÓN del `<select>` de clasificación
de documentos, que sí permitía marcar un archivo como "diseno_agronomico" en vez de
"diseno_hidraulico" pese a compartir el mismo anexo. Se quitó la opción de los dos `<select>` de
`proyecto.html`: (1) el de subida individual (línea ~413), sin condición — ya no se puede elegir
para un documento nuevo; (2) el de reclasificar un documento existente (línea ~522), con
condición `{% if doc.tipo_doc=='diseno_agronomico' %}` — la opción solo aparece (marcada
`selected`, etiquetada "clasificación antigua") si el documento YA está clasificado así, para
que el revisor la vea y pueda cambiarla a "Diseño y cálculos hidráulicos" si quiere, pero sin que
el `<select>` quede sin ninguna opción coincidente (lo que habría arriesgado reclasificar el
documento a la primera opción de la lista sin querer, si el formulario se guardara sin tocar el
campo). El botón "subir-multiple" (auto-clasificación por nombre de archivo, `extractor.
detectar_anexo`/`ANEXOS_SEP`) NUNCA asignó "diseno_agronomico" — ya mapeaba "9.5" directo a
"diseno_hidraulico", así que no necesitó cambios.
**Seguimiento — también sacado del checklist de "Documentos obligatorios" del concurso:** ese
checklist (`/admin/concursos/{id}`, sección "Documentos obligatorios (admisibilidad)") recorría
`TIPO_DOC_LABELS` completo (todos los tipo_doc, con "diseno_agronomico" incluido) tanto para
mostrar el checklist como para el catálogo que se le pasa a la IA en la extracción sugerida
(`extraer_documentos_obligatorios`) — el usuario pidió sacarlo de ahí también, "para no causar
inconveniente inconsistencias", ya que no tiene sentido poder marcarlo obligatorio por separado
de "Diseño y cálculos hidráulicos" si ya no es seleccionable al clasificar un documento. Se
agregó `TIPO_DOC_LABELS_OBLIGATORIOS` (main.py, justo después de `TIPO_DOC_LABELS`) — el mismo
diccionario sin esa clave — y se usa en los 3 puntos de esta función: armar
`checklist_doc_obligatorios`, el catálogo pasado a `extraer_documentos_obligatorios`, y el
filtro de `seleccionados` al guardar. `TIPO_DOC_LABELS` (el diccionario completo) se dejó
intacto — lo sigue usando el resto de la app (tabla de Documentos, selects de clasificación
para docs ya clasificados así, etc.) donde SÍ hace falta poder mostrar/reclasificar documentos
antiguos.
**Deliberadamente NO se tocó nada más** (compatibilidad con proyectos ya cargados, incluido el
concurso 202-2026 en curso): `ITEMS_SEP["diseno_hidraulico"]["tipo_docs"]` sigue incluyendo
`"diseno_agronomico"` (así que cualquier documento ya clasificado así sigue agrupándose y
analizándose normalmente dentro de "Diseño y cálculos hidráulicos", sin necesidad de
reclasificarlo a mano), igual que `DOCS_VERIFICACION["hidraulico"/"agronomico"]` (Chequeo de
Cálculos) y `TIPO_DOC_LABELS`/`TIPO_DOC_ORDEN` en `main.py` (para que la tabla de Documentos siga
mostrando la etiqueta y el orden correctos de los documentos ya clasificados así). El cambio es
puramente de UI hacia adelante — nada se migra ni se rompe hacia atrás.

**"Coherencia Global" como ÍTEM, al final de `ITEMS_ORDEN` (jul-2026):** cuando este método
convivía con el de Ejes, se agregó `ITEMS_SEP["coherencia"]` como el equivalente al eje
homónimo (que hacía de cierre transversal): usa TODOS los documentos con texto del proyecto
(`tipo_docs: []`, sin filtrar), sin visión — caso especial en `analizar_item()`
(`if item_key == "coherencia"`) y en `_render_proyecto()` de main.py (cálculo de `n_docs` para
la tarjeta del ítem). Al eliminar el método por Ejes (ver siguiente entrada), el checklist de
Coherencia Global se inlineó directamente en `ITEMS_SEP["coherencia"]` (antes lo tomaba de
`EJES_REVISION["coherencia"]["checklist"]`).

**Derivar observaciones de Coherencia Global a un ítem real del SEP (implementado, jul-2026):**
"Coherencia Global" no existe como ítem en el SEP real — es un cierre transversal interno de la
app (ver entrada anterior). El revisor necesita poder trasladar cada observación de este grupo al
ítem del SEP que realmente le corresponde para copiarla ahí, incluyendo el caso de que la propia
observación sea "falta tal documento" de un ítem que ni siquiera se pudo evaluar (0 documentos,
nunca analizado) — esa ausencia es justamente la observación a derivar, así que el ítem destino
NO necesita tener un análisis previo.
- Botón/selector **"Derivar a ítem del SEP"** (`_form_derivar_item()`, macro nueva en
  `proyecto.html`) — aparece SOLO en las observaciones y notas cuyo `grupo.key == 'coherencia'`
  (tanto en `bloque_observaciones()` como en `bloque_notas()`, que ahora reciben `items_info`
  como parámetro nuevo para armar el `<select>`). Lista los 18 ítems reales (excluye
  "coherencia" — no tiene sentido derivar a sí mismo).
- Ruta `POST /proyecto/{id}/observacion/{obs_id}/derivar-item` (`derivar_observacion_item`,
  main.py) — valida que el ítem destino exista en `ITEMS_SEP` y no sea "coherencia", reasigna
  `obs["item"]`/`obs["item_nombre"]` al ítem elegido, y recalcula `obs["numero"]` como
  `max(numero de las obs YA existentes en el ítem destino) + 1` (mismo criterio que
  `agregar_observacion_manual`) — así la observación derivada continúa la numeración real de ese
  ítem en vez de arrastrar el número que tenía en Coherencia Global.
- **Auditoría del origen:** `obs["derivada_de"]` guarda el nombre del ítem de origen ("Coherencia
  Global") la PRIMERA vez que se deriva — si se vuelve a derivar después (de un ítem a otro), no
  se pisa con el ítem intermedio, conserva el origen real. Se muestra como badge gris "derivada"
  (mismo estilo que el badge "manual") con el origen en el `title`, en ambos macros.
  **Deliberadamente NO se resta la observación de Coherencia Global** hacia atrás ni se
  recalculan `items_revisados["coherencia"]["n_obs"]`/`n_notas` al derivar — esos contadores
  reflejan lo que la IA generó en su momento (auditable), y la observación simplemente pasa a
  contarse en el ítem destino en el siguiente render (que agrupa por `obs.item` actual, no por lo
  que fue al crearse) — sin código adicional, mismo patrón ya usado para observaciones
  manuales/invalidadas.
- **Sin restricción sobre el origen real de la observación** en el backend (cualquier
  observación puede derivarse a cualquier ítem que no sea "coherencia") — la UI solo expone el
  control para las de Coherencia Global porque es el único caso real hoy (es el único ítem sin
  equivalente en el SEP), pero no hay una regla que lo impida a nivel de ruta.

**Bug resuelto — Coherencia Global repetía observaciones ya hechas en otros ítems (jul-2026):**
con un proyecto real (12 de 21 documentos entran a este ítem), de 6 observaciones generadas 3
eran duplicados de hallazgos ya registrados al revisar Memoria de superficies, Presupuesto, etc.
Causa: la IA revisaba el expediente completo sin ninguna noción de qué ya se había observado en
los ítems individuales, así que era natural que re-encontrara el mismo problema (ej. una
superficie inconsistente) al mirar los mismos documentos de nuevo. Arreglado en dos frentes:
1. **Se le pasa lo ya observado.** `revisar_item()` (main.py), solo para `item_key == "coherencia"`,
   arma `observaciones_previas` = las observaciones de `proyecto["observaciones"]` de los DEMÁS
   ítems ya revisados (excluye las del propio "coherencia" y las `estado == "descartada"`) y se
   lo pasa a `analizar_item()` → `_analizar_grupo()` (parámetro nuevo `observaciones_previas`,
   solo se usa si `es_coherencia=True`). `_analizar_grupo` arma un bloque explícito
   "OBSERVACIONES YA REGISTRADAS... NO LAS REPITAS" con instrucción de que su tarea es EXCLUSIVA
   detectar lo que solo se ve mirando el expediente completo, y que "no hay hallazgos nuevos" es
   un resultado válido (evita que fuerce una observación para no volver con la lista vacía).
   **Efecto colateral esperado y deseado:** como depende de `proyecto["observaciones"]` en el
   momento de la llamada, mientras MÁS ítems se hayan revisado antes de correr Coherencia Global,
   mejor funciona el filtro — es más preciso revisarlo al final (que es como ya está pensado el
   orden de `ITEMS_ORDEN`, coherencia va último).
2. **Checklist reenfocado.** `ITEMS_SEP["coherencia"]["checklist"]` explicita ahora la pregunta
   real que responde este ítem (tal como la planteó el usuario): si la IDEA del proyecto —su
   forma de operar, su lógica de diseño y de construcción— es coherente y viable como un todo, no
   una segunda pasada que repite el detalle de cada documento. La lista de relaciones a verificar
   (superficie↔caudal↔presupuesto, etc.) se mantuvo como EJEMPLOS no exhaustivos, y se agregó un
   punto sobre la secuencia constructiva (cronograma/obras civiles/tecnificación/energización con
   orden lógico y ejecutable).

**Invalidación cruzada — auto-descartar observaciones que otro ítem resuelve (implementado,
jul-2026):** el método viejo de análisis documento-por-documento (eliminado antes de que Ítems
SEP fuera el único método) SÍ tenía esto: al analizar cada documento nuevo, revisaba si su
contenido resolvía observaciones pendientes de documentos ya analizados y las auto-descartaba
(`revisar_observaciones_previas`, borrado junto con ese método). El usuario notó que ya no pasa
y pidió reincorporarlo sin disparar el costo — se portó a la unidad de trabajo actual (ítem, no
documento):
- `analyzer.revisar_invalidacion_cruzada(item_nombre_nuevo, texto_resumen_nuevo,
  observaciones_pendientes_otras)` — dado el resumen del ítem recién revisado, decide cuáles
  observaciones PENDIENTES de OTROS ítems quedan resueltas. **Barata a propósito:** usa
  **Haiku** (no Sonnet — misma regla de costo de siempre: leer texto y devolver JSON
  estructurado es tarea de Haiku), `max_tokens=800`, y un resumen corto del ítem —
  `_texto_grupo_para_extraccion(docs_grupo, max_chars=8000)`, la MISMA función ya usada para las
  extracciones numéricas (reparto equitativo entre documentos, no el presupuesto completo de
  120.000 caracteres del análisis principal). **Corre en PARALELO** al análisis principal
  (`asyncio.gather` en `analizar_item()`), así que no agrega latencia — el revisor no espera más
  por esto. Y **solo se llama si hay observaciones pendientes de OTROS ítems** — en un proyecto
  recién empezado (nada revisado aún) esta llamada extra ni siquiera ocurre, cero costo.
- **Deliberadamente conservadora**, incluso más que el resto de la app: el prompt insiste "ante
  la duda, NO la marques como resuelta" y exige una resolución DIRECTA y explícita, no una
  relación tangencial. Motivo: acá el costo de equivocarse NO es simétrico con generar una
  observación de más — un falso positivo (invalidar algo que en realidad seguía pendiente)
  esconde un hallazgo real sin que el revisor lo note; un falso negativo (dejarla pendiente
  aunque ya esté resuelta) solo deja una observación de más, que el revisor descarta a mano
  igual que siempre.
- **Alcance:** solo toca observaciones con `estado == "pendiente"` — una observación que el
  revisor ya **aprobó** NO se auto-descarta nunca (el visto bueno humano tiene prioridad), y una
  ya **descartada** no se vuelve a tocar. Al auto-descartar, se le agrega al texto de la
  observación `[Auto-descartada: resuelta al revisar "{ítem}"]` (mismo patrón que el método
  viejo) — reversible por el revisor igual que cualquier descarte manual (puede volver a marcarla
  pendiente si no está de acuerdo).
- **Wiring:** `main.py` → `revisar_item()` arma `observaciones_pendientes_otros` (pendientes de
  cualquier ítem distinto al que se está revisando) y se lo pasa a `analizar_item()`, que
  devuelve `resultado["invalidadas"]` (lista de IDs). Tras guardar las observaciones nuevas del
  ítem, se aplican esos IDs sobre `proyecto["observaciones"]` (respetando el filtro
  `estado=="pendiente"` una segunda vez, por si cambió entre medio). El redirect agrega
  `?item_invalidadas=N` si hubo alguna; `proyecto.html` muestra un banner verde
  (`alert-success`) avisando cuántas se resolvieron, para que el revisor sepa que pasó y pueda
  confirmarlo si quiere — no queda en silencio como antes de este cambio.
- **No se aplica a `criterios_aprendidos`/feedback de consultor:** a diferencia de un descarte
  manual del revisor (que sí alimenta el aprendizaje del ítem/consultor), un auto-descarte por
  invalidación cruzada NO registra feedback — es una corrección automática del sistema, no una
  señal de juicio del revisor, y mezclarla contaminaría esa fuente de aprendizaje.

**Revisión por Ejes eliminada por completo (jul-2026):** existió como método alternativo que
convivía con Ítems SEP — 9 ejes temáticos (`EJES_REVISION`/`EJES_ORDEN`: Superficie,
Agronómico, Hidrológico, Hidráulico, Energético/Fotovoltaico, Obras civiles, Presupuesto y
costos, Legal/administrativo, Coherencia global), con su propia página (`/proyecto/{id}/ejes`),
rutas de análisis (`revisar-eje/{key}`) y chat (`chatear_eje`/`.../eje/{key}/chat`), y su propio
estado (`proyecto["ejes_revisados"]`/`["eje_chats"]`), botón de limpieza independiente
(`limpiar-ejes`) y secciones de aprendizaje/criterios de énfasis en `/admin/concursos/{id}`. Se
eliminó por completo a pedido explícito del usuario porque en la práctica solo usa el método
por Ítems SEP (mismo orden que el SEP real, para copiar observaciones directo al sistema de
postulación) — mantener dos métodos era trabajo duplicado sin uso real del segundo. Al
eliminarlo:
- La verificación numérica determinística (Hazen-Williams / cadena agronómica / dimensionamiento
  FV) que antes vivía en `analizar_eje()` para `eje_key in ("hidraulico", "agronomico",
  "energetico")` se **portó a `analizar_item()`**, para no dejar huérfana la página "Chequeo de
  Cálculos": el ítem `diseno_hidraulico` ahora corre tanto la verificación hidráulica como la
  agronómica (concatenadas en `bloque_verificacion`), y `diseno_fotovoltaico` corre la FV.
- Los `tipo_docs` que cada eje usaba para alimentar su verificación (más amplios que los
  `tipo_docs` del ítem SEP correspondiente — ej. el eje Hidráulico también incluía
  `pruebas_bombeo`) se preservaron en la constante `DOCS_VERIFICACION` (analyzer.py) + helper
  `_documentos_para_verificacion(grupo_key, documentos)`, que reemplazó a `_documentos_del_eje()`.
  Las 3 rutas de extracción de "Chequeo de Cálculos" en main.py (`/calculos/{hidraulico,
  agronomico,energetico}/extraer`) pasaron a usar este helper.
- **Proyectos revisados antes de este cambio** pueden tener observaciones históricas con
  `eje`/`eje_nombre` en vez de `item`/`item_nombre` — la ficha de revisión las sigue
  mostrando (agrupadas al final, ya no aparecen en el `orden` por nombre de ítem), pero no
  hay UI para gestionarlas ni se pueden generar más. No se hizo ninguna migración de datos.

**Invernaderos — criterios inyectados vía normativa, SIN ítem propio (implementado, jul-2026):**
el invernadero es una obra anexa/complementaria que NO aparece siempre, y cuando aparece el
consultor la agrupa en carpetas distintas según el caso (Planos de tecnificación, Planos de
obras civiles, Estudios complementarios, Especificaciones técnicas o el Presupuesto) — no tiene
un `tipo_doc` propio en el SEP ni conviene forzarle uno. El usuario aportó la "Planilla de
verificación de invernaderos"
que usa la CNR (Excel con geometría de cercha, cubicación de perfiles METALCON, tabla de
sobrecarga de nieve y combinación de cargas estructurales) y se evaluó portar el cálculo
completo como se hizo con hidráulica/agronómico/FV — **se descartó a propósito**: es un salto de
complejidad mucho mayor (geometría trigonométrica + catálogo de perfiles + tabla de ~150
localidades) y el propio archivo fuente está incompleto (las hojas de Cargas de viento y
Cimentación no tienen fórmulas, solo el encabezado — se ignoraron, igual que le pidió el
usuario: "esas no se consideran, solo las primeras").
En su lugar, se destiló un extracto de criterios de revisión — igual patrón que
`ITT_Criterios_Tecnificacion.txt` — en `normativa/Invernaderos_Criterios.txt` (2.850 caracteres,
dentro del límite `MAX_CHARS_POR_NORMATIVA=4000`, no se trunca). Al cargarse en `NORMATIVA_CNR`
queda dentro del `SYSTEM_PROMPT` (cacheado) de **toda** revisión, así que sin importar en qué
documento el consultor haya metido el invernadero, la IA reconoce el diseño y aplica los
criterios: qué debe incluir (dimensiones, estructura, memoria de cálculo estructural), y
verificaciones de coherencia (pendiente de techo 30-45 %, cubicación de perfiles vs.
presupuesto, sobrecarga de nieve/viento declarada y justificada según la ubicación real del
proyecto, proporcionalidad de la superficie). Es solo CRITERIO para la IA (como el resto de
`normativa/`) — no hay verificación numérica determinística ni módulo Python nuevo, cero cambio
de código en `main.py`/ítems/rutas. Costo extra: ninguno apreciable (el bloque va cacheado con
`cache_control: ephemeral`, igual que el resto de `NORMATIVA_CNR`).

**Bug resuelto — "Especificaciones técnicas" se quedaba corta con muchos documentos (jul-2026):**
caso real: 8 documentos clasificados bajo este ítem, entre ellos las especificaciones y el
cálculo estructural de un invernadero (ver entrada anterior) intercalados con los demás. El
análisis "no los tomó en cuenta" — solo referenció los documentos que el revisor identificó como
el primero y el último. Causa: este ítem seguía con el presupuesto por defecto
`MAX_CHARS_EJE_TOTAL=45.000` repartido EQUITATIVAMENTE entre los documentos del grupo — con 8
documentos, ~5.600 caracteres cada uno. Los documentos SÍ entraban al prompt (no se excluía
ninguno por posición ni orden), pero un documento denso (memoria de cálculo estructural, con
tablas de cubicación y sobrecarga de nieve/viento) truncado a ~5.600 caracteres perdía casi todo
su contenido relevante en el recorte — la IA no tenía de dónde sacar observaciones sobre él,
dando la apariencia de que se hubiera "saltado" ese documento. A diferencia de los otros 5 ítems
ampliados a 120.000 (donde el detonante son 2-3 archivos GRANDES), acá el detonante es la
CANTIDAD de documentos — el mismo presupuesto total dividido entre más documentos deja menos
espacio a cada uno. Arreglado agregando `especificaciones_tecnicas` a `MAX_CHARS_POR_ITEM`
(120.000) — con 8 documentos, ~15.000 caracteres cada uno (2,7× más).

**Reparto de presupuesto ADAPTATIVO entre documentos (implementado, jul-2026):** al revisar el
fix anterior, el usuario notó el problema de fondo: de esos 8 documentos, 5 eran manuales o
folletos de equipos (motobomba, aspersores) — pocas hojas, mucha imagen, poco texto — y con la
cuota FIJA (`total // n`) cada uno recibía la MISMA cuota que la memoria estructural del
invernadero, aunque le sobrara casi todo su margen sin usar. "Si se reparte fijo se distribuye
muy mal" cuando los documentos de un grupo tienen tamaños muy dispares (2 hojas vs. 20 hojas),
algo habitual en cualquier ítem, no solo Especificaciones técnicas.
- `_repartir_presupuesto(tamanos, total_chars, minimo)` (analyzer.py) — algoritmo *water-filling*:
  ordena los documentos ascendente por tamaño real; a cada uno que cabe completo dentro de la
  cuota equitativa del momento se le da su tamaño EXACTO (nada de margen desperdiciado) y sale
  del reparto; el presupuesto restante se recalcula entre los que quedan. Cuando un documento
  excede la cuota, él y todos los que siguen (≥ en tamaño, por el orden ascendente) se reparten
  en partes iguales lo que sobra. `minimo`: piso por documento para que ninguno quede en 0 si
  hay muchísimos documentos y el presupuesto total no alcanza ni para eso.
- **Reemplaza la cuota fija en LOS DOS puntos del código que la usaban:** `_analizar_grupo`
  (`bloque_docs`, el análisis principal de observaciones — antes `max_chars_total //
  len(docs_texto)`) y `_texto_grupo_para_extraccion` (extracciones numéricas de Haiku —
  hidráulica/agronómica/FV/presupuesto — antes `max_chars // len(docs_utiles)`, la función que
  ya tenía el reparto "equitativo" pero seguía siendo una cuota fija, no adaptativa).
- **Costo:** nunca supera el presupuesto total ya establecido para cada ítem — solo lo usa
  mejor. Verificado con el caso real: 8 documentos (5 manuales cortos + memoria del invernadero
  de 80.000 caracteres reales) sobre un presupuesto de 120.000 — con la cuota fija anterior la
  memoria recibía 15.000 caracteres; con el reparto adaptativo recibe 65.400 (4,4× más), porque
  los 5 manuales solo toman lo que necesitan (sus tamaños reales, sin desperdicio) y el resto se
  lo lleva el documento que sí lo requiere. Si la demanda total de un grupo es menor al
  presupuesto (documentos cortos en su mayoría), TODOS entran completos, sin truncar nada.

**Bug resuelto — documentos escaneados sin archivo disponible desaparecían del análisis SIN
NINGÚN AVISO (implementado, jul-2026):** con el reparto adaptativo ya desplegado, el usuario
seguía sin ver el cálculo estructural del invernadero mencionado en las observaciones. Al
investigar, confirmó que el "Ver archivos usados en este análisis" del ítem mostraba 5 de los 8
documentos declarados — el cálculo estructural (y otros 2) simplemente no aparecía, pese a estar
bien clasificado y verse "en verde" (sin necesidad de resubir) en la página Documentos.
- **Causa encontrada en el código:** en `_analizar_grupo`, un documento queda TOTALMENTE
  excluido (ni texto ni imagen) solo en un caso puntual: `texto_extraido == "__PDF_ESCANEADO__"`
  (cero texto extraíble, típico de un PDF escaneado/con cálculos manuscritos o firmados) **Y**
  `pdf_disponible` es `False` en ese momento — que se calcula chequeando el archivo en DISCO
  (`_os.path.exists`), no en Postgres. `_restaurar_archivos_necesarios()` (main.py) debería
  haber copiado el archivo desde Postgres al disco ANTES de este chequeo (si `necesita_vision`
  detecta el caso escaneado, que sí lo hace) — pero si esa copia falla o el archivo nunca se
  guardó en Postgres para ese documento puntual (aunque `archivo_presente` en la página
  Documentos muestre "verde" por otra razón, o el archivo siga siendo visible vía
  `ver_documento()` sirviendo directo desde Postgres sin escribir a disco), el resultado es el
  mismo: `pdf_disponible=False`, `es_imagen=True` → el documento no entra a `docs_texto` (no
  tiene texto real) NI a `docs_imagen` (no hay archivo para renderizar) — **desaparece del
  prompt sin dejar rastro**, ni en "archivos usados", ni en ningún log.
- **Arreglado con una red de seguridad, no adivinando la causa exacta de cada caso:** en vez de
  perseguir todos los motivos posibles por los que la restauración pudo fallar (pueden ser
  varios y distintos según el documento), `_analizar_grupo` ahora **detecta explícitamente**
  cualquier documento del grupo que no haya entrado ni a `docs_texto` ni a `docs_imagen`
  (`docs_excluidos`, comparando IDs contra `docs_grupo` completo) y, por cada uno:
  1. Loguea un `print()` de diagnóstico en Railway con el nombre exacto del documento y el
     motivo — mismo patrón que los demás avisos de diagnóstico de este archivo.
  2. Genera una **observación informativa DETERMINÍSTICA** ("El documento '...' no pudo
     leerse... Debe resubirse para poder evaluarlo") — no depende de que la IA decida
     mencionarlo, se agrega siempre en código, así nunca puede "olvidarse" de avisar.
  3. Se agrega a `docs_incluidos` con la etiqueta `"... (NO SE PUDO LEER)"`, así aparece en el
     `<details>` "Ver archivos usados" de la página Ítems SEP, visible para el revisor.
  Esto corre INCLUSO en los casos donde el grupo queda sin ningún documento legible en absoluto
  (antes esos casos devolvían silenciosamente `sin_documentos: True`, un banner genérico sin
  explicar por qué) — se movió el cálculo de `docs_excluidos` ANTES de los `return` tempranos de
  la función para cubrir también ese caso extremo.
- **Alcance de este fix:** garantiza que el revisor SIEMPRE se entera cuando un documento no se
  pudo leer, sin importar la causa exacta de fondo (restauración fallida, nunca respaldado en
  Postgres, archivo corrupto, etc.) — es una red de seguridad de visibilidad, no una corrección
  de la causa raíz de por qué la restauración específica falló en este caso. Si el problema
  persiste tras resubir el documento (ver el nuevo aviso/nota que ahora aparece explicando cuál
  falló), revisar el log de Railway por el nuevo `print()` de diagnóstico para investigar la
  causa puntual (ej. comparar si `db.obtener_archivo()` realmente devuelve contenido para ese
  documento).

**Segundo punto de falla silenciosa encontrado — el render de la imagen puede fallar DESPUÉS de
pasar el chequeo de archivo disponible (jul-2026):** el fix anterior cubre el caso "sin texto Y
sin archivo" (`pdf_disponible=False`), pero el usuario reportó que **incluso resubiendo** el
documento del invernadero (archivo físico recién escrito a disco, sin duda alguna disponible),
seguía sin aparecer — probando que el primer fix no bastaba. Causa: un documento escaneado con
archivo disponible SÍ entra a `docs_imagen`, pero el render real (`render_pdf_as_images` /
`render_plano_tiles`, PyMuPDF) puede fallar por su cuenta (PDF con estructura inusual, y en este
caso probablemente un documento con planos/gráficos vectoriales pesados tipo cálculo
estructural) — el `except Exception: imgs = []` original tragaba el error POR COMPLETO, sin
loguearlo siquiera, y el documento quedaba fuera de `imagenes_por_doc`/`docs_incluidos` sin
ningún rastro, igual que el bug anterior pero en un punto distinto del flujo. Mismo patrón de
solución: (1) el `except` ahora loguea la excepción real; (2) tras el loop de render, se
detectan los documentos de `docs_imagen` que NO lograron renderizarse (`ids_imagen_lograda`,
por tope `MAX_IMG_EJE` alcanzado o por excepción) y reciben la misma nota informativa
determinística + marca `"(NO SE PUDO RENDERIZAR)"` en "archivos usados" — salvo que el
documento YA tenga cobertura por texto (plano con capa de texto que sí entró, solo falló el
canal de imagen), caso en que no se duplica el aviso porque el documento sigue analizándose por
su texto. **Lección para el futuro:** un documento puede "desaparecer" del análisis en más de un
punto del pipeline (clasificación → disponibilidad de archivo → render de imagen) — cualquier
`except Exception: ... = []` silencioso en este flujo es sospechoso por defecto; debe loguear
como mínimo, y si el resultado es que el documento queda sin ninguna representación en el
prompt, debe generar la misma nota determinística que los casos ya cubiertos.

**Tercer hallazgo — el tope `MAX_IMG_EJE` era estrictamente "por orden de llegada" (jul-2026):**
con el aviso del punto anterior ya en producción, el usuario probó de nuevo (resubiendo el
documento del invernadero) y esta vez SÍ aparecieron los 8 documentos en "archivos usados", pero
3 con la nota "no se pudo renderizar" — incluyendo otra vez el cálculo estructural. Causa: el
render de imágenes repartía el cupo `MAX_IMG_EJE` (entonces 10) estrictamente en el ORDEN en que
aparecían los documentos — el primero (o los primeros) podían agotar TODO el cupo antes de que
le tocara el turno a los demás, dejando a los últimos sin ninguna posibilidad real (no es que
fallara su render, ni siquiera se intentaba). Mismo patrón de bug que el reparto de caracteres
antes de volverse adaptativo (ver más arriba), esta vez con el cupo de IMÁGENES.
- **Cuota FIJA por documento** (no water-filling completo, a diferencia del reparto de
  caracteres): `cuota_por_doc = max(1, MAX_IMG_EJE // n_docs_imagen)`, calculada UNA vez antes
  del loop — cada documento que necesita visión reserva de entrada un cupo parejo, así el primero
  de la lista no puede consumir todo el presupuesto y dejar a los demás en cero. No se hizo
  water-filling completo (redistribuir el sobrante de un documento corto a uno más largo) porque,
  a diferencia del texto, no se sabe cuántas páginas necesita un PDF sin abrirlo — el costo de
  calcularlo de antemano (abrir cada archivo dos veces) no se justificaba frente a la cuota fija,
  que ya resuelve el problema real (nadie se queda en cero).
- **Degradación elegante para planos con cuota insuficiente:** `render_plano_tiles` (vista +
  4 cuadrantes) exige mínimo 5 imágenes por página — con muchos planos compitiendo por el mismo
  cupo, la cuota individual puede caer bajo ese mínimo y antes NINGUNO se renderizaba (ni
  siquiera en baja resolución). Ahora, si la cuota no alcanza para el modo alta resolución, cae
  al renderizado básico de página completa (`render_pdf_as_images`) con las páginas que sí
  alcancen — mejor ver todos los planos en resolución normal que perder algunos por completo.
- **`MAX_IMG_EJE` subido de 10 a 14** — más margen para grupos con varios documentos que
  necesitan visión a la vez (como el caso real: 3 de 8 documentos escaneados en un mismo ítem).
  Costo extra marginal (unos pocos miles de tokens de imagen más por revisión, solo en los
  grupos que efectivamente necesitan visión).
- **Diagnóstico preciso, no genérico:** antes el aviso decía "tope alcanzado o error de
  render" sin poder distinguir cuál — ahora `motivo_fallo_imagen` (dict doc_id→motivo) rastrea
  exactamente `"tope"` (se acabó el cupo global antes de llegar a este documento), `"cuota"`
  (caso residual, hoy prácticamente inalcanzable gracias a la degradación elegante) o
  `"error: <detalle real de la excepción>"` — y tanto el `print()` de Railway como el texto de
  la observación citan la causa específica, no un genérico.

- **Auditoría de rendimiento y fallas (jul-2026)** — revisión completa del código a pedido del
  usuario; 5 arreglos aplicados de una vez:
  1. **Texto extraído ya NO se trunca a 5.000 caracteres al subir.** `subir`, `subir-multiple`
     y `extract_zip` capaban `texto_extraido` a 5.000 chars (~2 páginas) — el análisis por ítem
     reparte hasta 45.000 entre los documentos del grupo y las extracciones numéricas buscan
     datos que suelen estar al final del documento, así que ese tope silencioso degradaba TODO
     (análisis, Chequeo de Cálculos, autocompletar resumen, consultas). Ahora
     `extractor.truncar_texto_guardado()` guarda hasta `MAX_CHARS_GUARDADO=60000` conservando
     inicio (75%) + final (25%). **Documentos subidos ANTES de este fix siguen con el texto
     capado a 5.000 en la base — para que la IA vea el documento completo hay que resubirlos.**
  2. **Las llamadas a la API Anthropic ya no bloquean el servidor.** El cliente es sincrónico y
     se llamaba directo dentro de rutas async — durante un análisis (1-2 min) la app ENTERA
     quedaba congelada (ninguna página respondía). Ahora las 11 llamadas van envueltas en
     `await asyncio.to_thread(...)` (regla para código nuevo: toda llamada
     `client.messages.create` debe ir así), igual que `extract_text`/`extract_zip`/
     `render_pdf_as_images` (PyMuPDF también bloquea).
  3. **Proyectos por clave separada en PostgreSQL** — ver la nota en "Modelo de datos".
  4. **`actualizar_observacion` con proyecto inexistente devolvía 500** (AttributeError sobre
     None) — ahora 404 limpio.
  5. **Aprobar/descartar/eliminar una observación histórica de Ejes redirigía a
     `/proyecto/{id}/ejes`**, página eliminada (404). Ahora siempre vuelve a `/items`;
     `_volver_a()` también dejó de listar "ejes" (y ganó "calculos").

- **Solo revisión técnica (jul-2026):** la app se usa exclusivamente para revisión técnica —
  se eliminó la opción "Revisión legal" del formulario de creación de proyecto
  (`nuevo_proyecto.html`); `crear_proyecto()` en `main.py` ahora fija `tipo_revision = "tecnica"`
  siempre, sin leerlo del form. El campo `tipo_revision` y su badge (`badge-legal` en
  `dashboard.html`/`proyecto.html`/`ficha.html`) se dejaron intactos por si algún registro
  antiguo lo tuviera en "legal" — no se hizo migración de datos, es solo display. La rama
  "legal" en `analyzer.py` (`revision_nombre` dentro de `_analizar_grupo`) tampoco se tocó —
  queda como código muerto inofensivo, ya no alcanzable desde ningún proyecto nuevo.
- **Bug resuelto — verificación hidráulica/agronómica no veía datos cruzados (jul-2026):**
  `DOCS_VERIFICACION["hidraulico"]` y `["agronomico"]` (analyzer.py) filtraban documentos
  SOLO por su propio `tipo_doc` (diseno_hidraulico vs. diseno_agronomico), pero en la práctica
  el consultor a veces mete datos agronómicos dentro del documento clasificado como diseño
  hidráulico (o viceversa), o entrega un único documento combinado con ambos cálculos — la
  extracción correspondiente no los veía según cómo hubiera quedado clasificado el archivo.
  Arreglado: ambas listas ahora incluyen `diseno_hidraulico` Y `diseno_agronomico` (unión, no
  exclusivo) — cada extracción igual solo saca del texto los datos que le corresponden (Haiku
  recibe instrucciones específicas por tipo de cálculo), así que compartir el mismo pool de
  documentos no mezcla resultados, solo evita el falso negativo de no encontrar datos que sí
  estaban presentes en el archivo, solo que mal clasificado o combinado.

- **Bug resuelto — huso horario y formato de fecha (jul-2026):** Railway corre los contenedores
  en UTC, así que `datetime.now()` a secas quedaba ~3-4 h adelantado respecto a la hora real de
  Chile (ej: una subida a las 09:07 local se guardaba como 13:07). Además, las fechas se
  mostraban en varias partes de la app en formato ISO invertido (`aaaa-mm-dd`) en vez de la
  notación chilena `dd/mm/aaaa`. Arreglado en `main.py`:
  - `TZ_CHILE = ZoneInfo("America/Santiago")` + helper `_ahora()` — reemplaza las 22 llamadas a
    `datetime.now()` (y el `date.today()` de la ficha) en todo el archivo. `tzdata` agregado a
    `requirements.txt` por si el contenedor de Railway no trae la base de datos de husos
    horarios del sistema operativo (evita que `ZoneInfo` falle en producción).
  - Filtros Jinja `fecha` (`dd/mm/aaaa`) y `fecha_hora` (`dd/mm/aaaa HH:MM`) registrados en
    `templates.env.filters`, usando `_fmt_fecha()`. Reemplazan todo el slicing manual de
    strings ISO que había regado por los templates (`fecha[:10]`, `fecha[:16].replace('T',' ')`,
    `fecha[8:10]-fecha[5:7]-fecha[:4]`, etc.) — antes cada plantilla lo hacía a su manera y
    ninguna reordenaba a formato chileno.
  - **Registros guardados antes de este fix son `naive`** (sin huso horario, hora UTC cruda) —
    no se migraron. `_fmt_fecha()` los sigue mostrando tal cual estaban (sin reordenar la hora),
    solo los timestamps nuevos quedan correctos en hora de Chile desde ahora en adelante.
  - **Regla para código nuevo:** cualquier timestamp que se guarde debe usar `_ahora()`, nunca
    `datetime.now()` directo. Cualquier fecha que se muestre en un template debe usar el filtro
    `| fecha` o `| fecha_hora`, nunca slicing manual del string ISO.

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
  - `revisar_item`: antes de analizar, `_restaurar_archivos_necesarios()`
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
- **Bug resuelto — chat de ítem "siempre fallaba" con error genérico:** causa raíz real:
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
