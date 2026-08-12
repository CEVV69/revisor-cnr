# CLAUDE.md — Revisor CNR

Guía operativa para Claude. **Español siempre.** Archivos de referencia en `docs/`:
- `docs/items_sep.md` — checklists de los 19 ítems SEP (leer solo al trabajar en análisis)
- `docs/historial_sesiones.md` — historial detallado, arquitectura completa, auditorías

---

## LÍMITE DE TAMAÑO — este archivo NO debe crecer

Este archivo se leyó completo una vez y ocupó 390KB / 4.552 líneas, lo que saturó
el contexto ("Autocompact is thrashing") antes de poder trabajar. Se redujo a esto.

**Regla:** este archivo debe mantenerse bajo ~150 líneas / ~8KB. Antes de agregar
cualquier contenido nuevo:
1. Si es historial de sesión, decisión ya cerrada, o detalle de una función/ítem
   específico → va a `docs/historial_sesiones.md` o `docs/items_sep.md`, NUNCA acá.
2. Si es una decisión pendiente del usuario → reemplazar la sección "Estado actual"
   existente, no acumular decisiones viejas ya resueltas.
3. Si al terminar una edición este archivo supera ~150 líneas, mover el contenido
   más antiguo/detallado a `docs/` en el mismo commit, antes de pushear.

Este archivo es solo el índice + reglas fijas. Todo lo demás vive en `docs/`.

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

**Pendiente de verificar/decidir por el usuario (próxima sesión):**

1. **Desglose de Humedad Aprovechable por capas de suelo (Aspersión/Carrete):** falta confirmar en
   un proyecto real que el checkbox, autocompletado por textura y recálculo en vivo funcionen bien
   (verificado solo con números de prueba, `ad_por_capas()` en calculos_riego.py).

2. **Comparación FV con metodología del consultor — 8 de 9 ítems salen sin información.** Detalle
   y bug ya corregido en `docs/historial_sesiones.md`. Pendiente decidir: ¿verificar con el
   expediente real que el consultor no muestra el desarrollo, o relajar el criterio de estrictez?

3. **Sonnet 5 vs Sonnet 4.6:** hoy corre todo en Sonnet 5 (precio promo hasta 31-08-2026). Evalúa
   mover ítems de texto a 4.6 y dejar Sonnet 5 solo para visión (mayor resolución: 2576px vs
   1568px). Esperando decisión del usuario.

4. **Ítem "Diseño y cálculos hidráulicos":** se aplicó fix (criterio de ingeniero + aviso de N°
   sectores sin respaldo). El usuario lo va a verificar con un proyecto nuevo para confirmar si el
   comportamiento mejoró.

5. **Export→Import Revisor CNR → Diseñador v119 — 3 bugs corregidos, falta probar en la app real:**
   (a) `importProject()` no leía el ARRAY de proyectos con 2+ sistemas; (b) capas de suelo: el
   `<select>` de textura disparaba 'change' al restaurar y pisaba CC/PMP/Da reales con los default
   de la textura; (c) datos FV se descartaban en silencio si la compuerta "¿Incluye FV?" del
   Diseñador no estaba en "Sí". Detalle en `docs/historial_sesiones.md`. Confirmar los 3 en la app.
   Además: Matriz/Terciaria/Lateral de Goteo no exportaban porque el usuario dejó los tramos con
   nombre genérico ("Tramo 1"...) — no es bug, se agregó un aviso en el Chequeo Hidráulico
   explicando la convención de nombres (el usuario va a renombrar sus tramos reales). De paso se
   agregó soporte para varios tramos "Lateral" (uno por sector, normal en Goteo): se exporta el
   más largo (lateral crítico) en vez de descartar el nivel por ambigüedad.

**Pendiente de implementar:** incluir los chequeos del Revisor Fotovoltaico (generación, cobertura
anual, potencia requerida vía perfil solar horario) en la Memoria de Cálculo Completa — bloqueado
porque esos cálculos dependen del perfil solar horario del predio, que solo vive dentro del propio
Revisor Fotovoltaico (`static/fotovoltaico_riego_v15.html`), importado desde el Explorador Solar.

**Fuera de alcance de Revisor CNR:** cualquier verificación que combine cultivos vía Kc mensual (ej.
"horas de riego por mes" reconstruyendo la demanda agronómica) pertenece al **Revisor
Fotovoltaico**, no a esta app — su chequeo FV trabaja con un solo valor diario promedio, no con un
motor agronómico multi-cultivo (ver `docs/historial_sesiones.md`).

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
