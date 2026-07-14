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

**MAÑANA el usuario ingresa el concurso 202-2026 con proyectos REALES** — primera carga de
trabajo real desde la auditoría de rendimiento y todos los cambios de esta sesión. Cuando
retomes: no asumas que nada de lo de abajo ya se probó con datos reales de producción — se
verificó todo con pruebas propias (servidor local + Playwright + mocks), pero el uso real
puede revelar cosas distintas. Presta especial atención a:
- **Documentos que el revisor haya subido ANTES de hoy siguen truncados a 5.000 caracteres**
  en la base (el fix de texto completo solo aplica a subidas nuevas) — si algo del concurso
  202-2026 se cargó en una sesión anterior a esta, puede hacer falta resubirlo para que el
  análisis vea el documento completo.
- Que la migración automática de proyectos a claves separadas en PostgreSQL
  (`db.migrar_proyectos()`, corre sola al primer arranque tras el deploy) no haya tenido
  problemas — revisar el log de Railway al desplegar por si imprime error en vez de
  "✅ Migrados N proyecto(s)...".
- Que el análisis de los ítems con límite ampliado (`diseno_hidraulico`, `diseno_fotovoltaico`,
  `presupuesto`, `presupuesto_electrico`, `coherencia` — 120.000 caracteres) no dispare timeouts
  ni costos inesperados con documentos reales grandes.
- Que los planos (tecnificación/obras civiles) con el nuevo renderizado de cuadrantes
  (`render_plano_tiles`) se vean bien interpretados por la IA — es la primera vez que corre
  con planos reales, no solo el PDF de prueba sintético usado para verificar.
- Que el botón "Ver en Google Maps" interprete bien las coordenadas reales del expediente
  (UTM, lat/long o DMS) — se probó con varios formatos sintéticos, no con datos reales del SEP.
- Que los criterios de invernaderos (`normativa/Invernaderos_Criterios.txt`) efectivamente
  disparen observaciones útiles si el concurso 202-2026 tiene algún proyecto con invernadero —
  es solo criterio para la IA, no cálculo, así que vale la pena ver si el nivel de detalle es
  suficiente o si conviene portar el cálculo real más adelante (quedó pendiente, el usuario
  prefirió probar primero con el criterio simple).
- Cualquier error 500 nuevo — revisar el log de Railway primero.

**Resumen de lo que cambió en esta sesión** (todo ya en `main`, ver secciones dedicadas más
abajo para el detalle completo de cada uno):
- Chequeo Agronómico: nuevos datos de diseño (superficie, caudal disponible, precipitación,
  horas disponibles) + verificación de Superficie de riego segura/Tiempo de riego/N° de
  sectores/ITT-03, con tabla "extraído/declarado vs. calculado" y recálculo en vivo por JS.
- Label "Factor agotamiento" → "Criterio de Riego" (para que coincida con el Diseñador de Riego).
- Botón "Ver en Google Maps" en el Resumen, con parser que acepta UTM/lat-long/DMS.
- **Auditoría completa de rendimiento y fallas**: texto ya no se trunca a 5.000 al subir,
  llamadas a la API ya no bloquean el servidor, proyectos en clave separada en PostgreSQL,
  varios bugs 500/redirects rotos corregidos.
- Límite de análisis ampliado a 120.000 caracteres en los 5 ítems más densos en datos.
- Planos en alta resolución (vista completa + 4 cuadrantes ampliados por página).
- Extracción de datos optimizada: reparto equitativo entre documentos (antes se perdían los
  que no fueran el primero) + Resumen pasado a Haiku (antes usaba Sonnet 5 por error).
- Botón "Roles y uso de suelo (IDE Minagri)" en 3 ítems relacionados con suelo/superficies.
- Criterios de invernaderos vía normativa (sin ítem nuevo, ver sección dedicada).

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
analyzer.py      Llamadas a Claude (análisis, invalidación cruzada, consulta libre)
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
    `item`+`item_nombre`. **Nota histórica:** proyectos revisados antes de jul-2026 (cuando
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
3. **Presupuesto de caracteres** — `MAX_CHARS_EJE_TOTAL=45000` repartido entre los docs del
   grupo (`_truncar_inteligente`). **Ampliado a 120.000** (`MAX_CHARS_POR_ITEM`, jul-2026) para
   los ítems densos en datos a pedido del usuario: `diseno_hidraulico` (incluye el agronómico),
   `diseno_fotovoltaico`, `presupuesto`, `presupuesto_electrico` y `coherencia` — así 2-3
   archivos grandes (40.000 c/u) entran casi completos; el resto de los ítems sigue en 45.000.
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

Una quinta página, `/proyecto/{id}/calculos` (Chequeo de Cálculos), tiene su propia plantilla y
ruta, fuera de `_render_proyecto()` — ver la sección dedicada más abajo.

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
- Estados del proyecto: En revisión / Revisado / Observado / Rechazado
- Documentos ordenados por tipo · indicador de cuáles resubir tras un deploy
- **Ficha de revisión** (`/proyecto/{id}/ficha`): HTML imprimible + descargar PDF
  (html2pdf.js), obs agrupadas por ítem, sin firmas ni "R)"
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
`TIPOS_PLANO_VISION` (`planos_tecnificacion`, `planos_obras_civiles`, `plano_ubicacion`) van a
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

**"Coherencia Global" como ÍTEM, al final de `ITEMS_ORDEN` (jul-2026):** cuando este método
convivía con el de Ejes, se agregó `ITEMS_SEP["coherencia"]` como el equivalente al eje
homónimo (que hacía de cierre transversal): usa TODOS los documentos con texto del proyecto
(`tipo_docs: []`, sin filtrar), sin visión — caso especial en `analizar_item()`
(`if item_key == "coherencia"`) y en `_render_proyecto()` de main.py (cálculo de `n_docs` para
la tarjeta del ítem). Al eliminar el método por Ejes (ver siguiente entrada), el checklist de
Coherencia Global se inlineó directamente en `ITEMS_SEP["coherencia"]` (antes lo tomaba de
`EJES_REVISION["coherencia"]["checklist"]`).

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
obras civiles, Estudios complementarios o el Presupuesto) — no tiene un `tipo_doc` propio en el
SEP ni conviene forzarle uno. El usuario aportó la "Planilla de verificación de invernaderos"
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

---

## Restricciones y gotchas

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
