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

## Estado actual (sep-2026)

**El usuario prueba en la app y comenta la próxima sesión.** Todo pusheado; nada de acá se toca
sin que él reporte primero. Detalle en `docs/`.

1. **Auditoría técnica del motor de Aspersión (ago-2026) — CERRADA:** unidades del aspersor,
   ciclo-vs-día, Da en kg/m³, los 3 bugs del Diseñador de Riego (app en
   `static/disenador_riego_v129.html`, era v123→v126→v129), y V/Hf en blanco en la Memoria
   Completa — todos corregidos y verificados. Detalle y validación numérica en `docs/`.

2. **Caudal por turnos + CDT por ruta crítica (ago-2026) — implementado, usuario probando:**
   (a) campos "Horas disponibles por turno" (placeholder "Continuo") + "Cada cuántos días"
   (default 7) — caudal EFECTIVO (nominal × horas/(período×24)) para superficie segura/balance
   diario/acumulador requerido, en vez de asumir 24h continuas. Generalizado a "cada X días" (no
   fijo a semana) tras feedback del usuario — turnos de canalistas pueden ser cada 15/30 días.
   (b) La CDT (`amt_calculada_m`) ya NO suma todos los tramos — 2+ del mismo nivel jerárquico son
   ramales alternativos, solo cuenta el de mayor Hf (ruta crítica). (c) **Bug real encontrado por
   el usuario y corregido:** "Volumen mínimo del estanque" usaba volumen del CICLO COMPLETO menos
   el aporte de UN día — sobrestimaba hasta 3× en ciclos multi-día, casi siempre daba "no
   alcanza". Ahora usa ΔQ × Tiempo de UN día (misma fórmula que los datos de autonomía). Los 3
   lados + espejo JS, ver `docs/`. Pendiente: mismo par de bugs (turno + ruta crítica) en el
   Diseñador de Riego: v129 subido (sep-2026). Pendiente en v129: turno "cada X días" (aún
   usa ÷168) y bug reponeOk multi-día — prompt de handoff actualizado entregado en sep-2026.

3. **Sistema de doble bombeo (sep-2026) — implementado, usuario probando:** cuando un tramo se
   nombra con "acumulador/embalse/tranque/estanque/cisterna/llenado/reservorio", aparece un
   checkbox "Bomba independiente (excluir del CDT)" solo en ese tramo. El revisor lo marca si
   efectivamente hay una bomba separada para ese tramo — solo ahí se excluye del CDT. En tramos
   sin nombre clave, no aparece ningún checkbox (sin ruido). El checklist del ítem
   `diseno_hidraulico` (IA) ya instruye que dos bombas con acumulador intermedio NO es observable.

4. **Menú "Apps" (probado y OK):** botón único al final de `.proj-nav` (`_apps_menu.html`) — 5
   apps hermanas. Agregar apps nuevas: solo editar `_apps_menu.html`.

5. **Pendientes de sesiones anteriores** (detalle en `docs/`): caudal del emisor por sistema;
   Word con presupuesto en tabla; Memoria COMPLETA con paridad total; Evaluación del Consultor
   (nunca probada); costo de API en Memorias standalone (sin confirmar).

**Pendiente de implementar:** los chequeos del Revisor Fotovoltaico (generación, cobertura anual,
potencia requerida) en la Memoria Completa — bloqueado: dependen del perfil solar horario del
predio, que solo vive dentro de `static/fotovoltaico_riego_v15.html`.

**Fuera de alcance:** verificaciones que combinen cultivos vía Kc mensual (ej. "horas de riego por
mes") pertenecen al **Revisor Fotovoltaico** — su chequeo FV usa un solo valor diario promedio, no
un motor agronómico multi-cultivo.

---

## Stack

- FastAPI + Jinja2 · PostgreSQL Railway (persiste) · Claude Sonnet 5 (visión) + Sonnet 4.6 (texto)
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
templates/       Jinja2. proyecto.html (resumen/documentos/items, un template con `pagina`),
                 calculos.html (chequeo), ficha.html (informe PDF), respuestas.html,
                 _apps_menu.html (menú "Apps" de `.proj-nav` — único punto de mantención)
static/          Apps hermanas standalone (HTML único, sin build), se abren desde el menú "Apps":
                 disenador_riego_v129.html, scall_diseno_v21.html, fotovoltaico_riego_v15.html
                 (otra metodología, no la de Revisor CNR), embalses_diseno_v9.html,
                 desarenador_diseno_v5.html
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
- Modelo: Sonnet 5 si el ítem incluye imágenes, Sonnet 4.6 si es texto puro
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
10. **Todo cambio de cálculo/dato validado debe llegar a los TRES lados**, no solo al Chequeo
    interactivo: (1) `calculos.html`/`calculos_riego.py`, (2) la Memoria de Cálculo
    (`informe_calculo.html` **y** `informe_calculo_completo.html`), y (3) el `.json` de
    exportación (`exportar_disenador.py`). Antes de cerrar un cambio, revisar los tres.
    En el export, confirmar el ID contra `static/disenador_riego_v129.html` — **nunca adivinarlo**;
    si el Diseñador no tiene campo equivalente, anotar el porqué en el docstring del módulo.
11. **Prompts de handoff a otra sesión (ej. Diseñador de Riego):** antes de armar uno nuevo,
    revisar si queda algo pendiente de una ronda anterior del mismo tema e incluirlo siempre —
    nunca armar solo con el hallazgo más reciente (se perdió un punto así una vez, ago-2026).
