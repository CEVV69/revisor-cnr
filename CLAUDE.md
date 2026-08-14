# CLAUDE.md — Revisor CNR

Guía operativa para Claude. **Español siempre.** Archivos de referencia en `docs/`:
- `docs/items_sep.md` — checklists de los 19 ítems SEP (leer solo al trabajar en análisis)
- `docs/historial_sesiones.md` — historial detallado, arquitectura completa, auditorías

---

## LÍMITE DE TAMAÑO — este archivo NO debe crecer

Se leyó completo una vez y ocupó 390KB / 4.552 líneas: saturó el contexto ("Autocompact is
thrashing") antes de poder trabajar. **Debe mantenerse bajo ~150 líneas / ~8KB** — es solo
índice + reglas fijas. Historial de sesión, decisiones ya cerradas y detalle de una función o
ítem específico van a `docs/historial_sesiones.md` / `docs/items_sep.md`, NUNCA acá. Una
decisión pendiente del usuario REEMPLAZA a la anterior en "Estado actual", no se acumula. Si al
terminar una edición supera ~150 líneas, mover lo más antiguo/detallado a `docs/` en el mismo
commit, antes de pushear.

---

## SINCRONIZACIÓN — OBLIGATORIO

El usuario trabaja desde su Mac en casa Y desde `claude.ai/code` en la oficina.
Claude ejecuta git — el usuario NO corre comandos git nunca.

1. **AL EMPEZAR:** `git pull` antes de leer o editar nada.
2. **AL TERMINAR cada cambio:** `git add` + `git commit` + `git push`. Nunca dejar sin pushear.
3. **SIEMPRE directo a `main`, nunca en otra rama.** Si la sesión de `claude.ai/code` asigna
   automáticamente una rama de trabajo distinta a `main` (ej. `claude/algo-xyz`), ignorar esa
   asignación: trabajar igual sobre `main` (`git checkout main && git pull`) y pushear ahí. Railway
   solo despliega desde `main` — pushear a otra rama no actualiza la app y el usuario no tiene
   forma de notarlo (no corre git).

---

## Estado actual (ago-2026)

**El usuario está probando esto en la app y comenta el resultado la próxima sesión.** Todo está
implementado y pusheado; nada de acá se toca sin que él lo reporte primero. Detalle en `docs/`.

1. **Capas de suelo (Aspersión/Carrete):** checkbox, autocompletado por textura y recálculo en
   vivo; y que la Memoria muestre la tabla "AD = Σ Ha por capa" en vez de la fórmula de capa
   única. Solo probado con números y renderizando templates, nunca en un proyecto real.

2. **Campo "Caudal emisor (l/hr)":** debe verse en Goteo/Aspersión/Microaspersión y NO en
   Carrete. Estuvo invisible en los 4 sistemas hasta el fix de ago-2026.

3. **Word con tablas:** subir un .docx con el presupuesto/cuadro en tabla y confirmar que ese
   texto llega al análisis — antes se perdía entero.

4. **Chequeo de Cálculos (hidráulico):** selector "Tubería (catálogo)" con Ø int. propio y fila
   AMT/Q diseño/Desnivel/Pérdida cabezal/"AMT calc.".

5. **Export→Import Revisor CNR → Diseñador v119:** 3 bugs corregidos + varios "Lateral"
   (crítico = el más largo).

**Esperando decisión del usuario:**

6. **Comparación FV con metodología del consultor — 8/9 ítems sin información.** Bug ya corregido.
   ¿Verificar con el expediente que el consultor no muestra el desarrollo, o relajar la estrictez
   del prompt?

7. **Sonnet 5 vs Sonnet 4.6:** hoy todo en Sonnet 5 (precio promo hasta 31-08-2026). ¿Mover ítems
   de texto a 4.6 y dejar Sonnet 5 solo para visión (2576px vs 1568px)?

**Pendiente de implementar:** los chequeos del Revisor Fotovoltaico (generación, cobertura anual,
potencia requerida) en la Memoria de Cálculo Completa — bloqueado: dependen del perfil solar
horario del predio, que solo vive dentro de `static/fotovoltaico_riego_v15.html`.

**Fuera de alcance:** cualquier verificación que combine cultivos vía Kc mensual (ej. "horas de
riego por mes") pertenece al **Revisor Fotovoltaico**, no a esta app — su chequeo FV usa un solo
valor diario promedio, no un motor agronómico multi-cultivo.

---

## Stack

- FastAPI + Jinja2 · PostgreSQL Railway (persiste) · Claude Sonnet 5
- Archivos PDF/Excel: guardados en tabla `archivos` de PostgreSQL (sobreviven deploys)
- Auth: JWT + bcrypt · Extracción: PyMuPDF, python-docx, openpyxl

```
ANTHROPIC_API_KEY, DATABASE_URL, DATA_DIR=/storage/data, UPLOAD_DIR=/storage/uploads
```

Deploy: `git push` → Railway auto-despliega en ~1-2 min → `revisor-cnr-production.up.railway.app`

---

## Archivos clave

```
main.py          Rutas FastAPI (toda la lógica de negocio)
analyzer.py      Claude API: analizar_item(), chatear_item(), consultar_expediente()
                 ITEMS_SEP: dict con 19 ítems (tipo_docs + checklist)
calculos_riego.py Cálculos determinísticos hidráulicos/agronómicos
database.py      Dual: PostgreSQL (prod) / JSON local (dev). Thread-safe con RLock.
extractor.py     Extracción PDF/Word/Excel. MAX_CHARS_GUARDADO=60.000 chars.
templates/       Jinja2. proyecto.html (tabla docs), items.html (panel ítems),
                 calculos.html (chequeo), ficha.html (informe PDF), respuestas.html
static/          Apps hermanas standalone (HTML único, sin build): disenador_riego_v119.html
                 (diseño, exporta/importa vía localStorage+JSON) y fotovoltaico_riego_v15.html
                 (chequeo FV con perfil solar horario — otra metodología, no la de Revisor CNR)
```

### Modelo de datos
- `storage (key, value TEXT)`: users, proyectos, concursos, meta, precios, consultores
- `archivos (proyecto_id, doc_id, filename, contenido BYTEA)`: PDFs guardados en PG
- Textos extraídos: `textos:{proyecto_id}` en storage (separado del proyecto para no inflar)

### Flujo de análisis por ítem
`POST /proyecto/{id}/revisar-item/{item_key}` → `analizar_item()` → `_analizar_grupo()`:
- Toma los documentos del ítem (por `tipo_doc`)
- Documentos con texto: texto truncado inteligentemente (75% inicio + 25% final)
- Documentos imagen/escaneados: hasta 10 páginas por visión (PLANOS siempre por visión)
- Bases del concurso cacheadas como 2° bloque del system prompt
- Resultado: observaciones tageadas con `item` + `item_nombre`, guardadas en proyecto

### Páginas principales
- `/` Dashboard (lista de proyectos)
- `/proyecto/{id}` Documentos del expediente
- `/proyecto/{id}/items` Panel de 19 ítems SEP (revisión principal)
- `/proyecto/{id}/calculos` Chequeo de cálculos hidráulico/agronómico
- `/proyecto/{id}/ficha` Ficha de revisión (PDF imprimible)
- `/proyecto/{id}/respuestas` Subsanación (respuestas del consultor)
- `/admin/concursos` Gestión de bases de concurso

---

## Instrucciones del usuario (SIEMPRE respetar)

1. **Paso a paso** — nunca asumir, guiar con pasos numerados.
2. **Usa Safari** — solo lectura en computer-use.
3. **Nunca Write sobre archivos existentes sin leer primero** — usar Edit.
4. **Español siempre**, incluso en textos técnicos. **Español de Chile — nunca voseo argentino**
   ("tú"/"tienes", no "vos"/"tenés").
5. Sin archivos sueltos de apoyo — entregar scripts/SQL en el chat.
6. Usuario es técnico en riego/CNR — entiende la terminología.
7. **Sin emojis decorativos** — la app debe verse formal. Si aporta señal, usar CSS/SVG,
   no emoji. Ver `.dot`/`.dot-green`/etc. en base.html como referencia.
8. **Minimalismo UI** — mínimo texto de acompañamiento, botones autoexplicativos.
   Aclaraciones indispensables van en `title` (tooltip), no como texto visible.
9. **Ítems base merecen máximo criterio de ingeniero:** Diseño agronómico/hidráulico,
   Presupuesto y Planos son la BASE del proyecto. Su análisis prioriza profundidad de
   juicio por sobre presencia/consistencia de datos. Ante observaciones "superficiales"
   en estos cuatro, tratarlo con prioridad alta.
10. **Todo cambio de cálculo/dato validado por el usuario debe reflejarse también en la Memoria
    de Cálculo** (`informe_calculo.html`/`informe_calculo_completo.html`) — no alcanza con que
    viva solo en el Chequeo de Cálculos interactivo. Antes de dar por cerrado un cambio en
    calculos.html/calculos_riego.py, revisar si la Memoria necesita el mismo dato/fila.
