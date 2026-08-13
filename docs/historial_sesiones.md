## Sesión ago-2026 — nuevo campo: Presión Operación del Emisor (mca)

Pedido del usuario: agregar "Presión Operación del Emisor" al Chequeo Agronómico, para TODOS los
sistemas (no específico de Goteo/Aspersión/Carrete, a diferencia de VIB o el marco de plantación).
Implementado como `presion_emisor_mca` en `templates/calculos.html` (junto a Eficiencia sistema),
`main.py` (guardado + Memoria de Cálculo, siguiendo la regla nueva de CLAUDE.md #10), extracción
por IA (`_extraer_datos_agronomicos`, con instrucción de convertir bar/kg·cm² a mca si el
expediente usa otra unidad), y `exportar_disenador.py` — mapea a `a-pres`/`c-pres` (Aspersión/
Carrete) o `g-pem`/`m-pem` (Goteo/Microaspersión) en el Diseñador de Riego, confirmado en su HTML
fuente (mismo dato, mismas unidades mca, en los 4 sistemas). No se agregó ninguna verificación/
comparación automática (no hay un rango oficial CNR conocido para contrastar, a diferencia de Kc o
Eficiencia) — por ahora es solo un dato de referencia declarado.

---

## Sesión ago-2026 — fix: selector de catálogo no recordaba la elección al guardar

El usuario probó en la app real y reportó que, al elegir un producto en "Tubería (catálogo)" y
guardar, el selector volvía a mostrar "— elegir —" — se perdía la elección visualmente (el dato
Ø int./Material sí quedaba guardado bien, era solo el `<select>` el que no reflejaba nada al
recargar). Causa: las `<option>` del catálogo nunca marcaban `selected` según lo ya guardado en
el tramo. Fix en `templates/calculos.html`: `{% if t.diametro_mm == tb.dint and t.material ==
tb.material %}selected{% endif %}` en cada `<option>`. Probado con un tramo PVC 110mm PN10
(dint=99.4) — la opción correspondiente queda marcada selected tras el render.

También se agregó, a la Memoria de Cálculo (`informe_calculo.html`/`informe_calculo_completo.html`),
Desnivel y Pérdida de carga en cabezal como filas propias — antes solo se sumaban en silencio
dentro de "AMT calc." sin mostrar sus valores declarados por separado (el usuario preguntó si esto
llegaba a la Memoria; al revisar se encontró y corrigió este hueco).

**Regla nueva del usuario, agregada a CLAUDE.md (instrucción #10):** todo cambio de cálculo/dato
que el usuario valide en el Chequeo de Cálculos debe reflejarse también en la Memoria de Cálculo —
no alcanza con que viva solo en la página interactiva. Revisar esto antes de cerrar cualquier
cambio futuro en calculos.html/calculos_riego.py.

---

## Sesión ago-2026 — Chequeo Hidráulico: AMT/Q diseño restaurados, catálogo con columnas separadas

Corrección sobre las 2 sesiones anteriores (ver secciones de abajo), en 3 rondas de feedback de UI
del usuario tras ver el resultado en la app real.

**AMT declarada y Q diseño declarado — restaurados por completo.** La sesión anterior los había
eliminado interpretando literalmente "Elimínate el AMT y Qdiseño declarado, nunca te pedí eso" —
el usuario aclaró después que NO había que eliminarlos. Se revirtió en los 4 lugares donde se
habían retirado: `templates/calculos.html` (los 2 `<input>` vuelven a la fila, junto a Desnivel/
Pérdida cabezal/AMT calc., mismo estilo sin flechas + más separación), `main.py` (guardado en
`calculos_guardar_hidraulico`, despliegue en `pagina_calculos`/`informe_calculo`/
`informe_calculo_completo`), `analyzer.py` (`_extraer_datos_hidraulicos` vuelve a pedírselos a la
IA; `_bloque_verificacion_hidraulica_sistema` vuelve a compararlos contra los tramos y contra la
AMT calculada). Los informes (`informe_calculo.html`/`informe_calculo_completo.html`) ahora
muestran los 3 juntos en la sección "Equipo de bombeo": AMT declarada, Q diseño declarado, AMT
calculada — con alerta si calculada y declarada difieren >15%, preservando el contraste de caudal
máximo por tramo que ya existía antes de esta sesión.

**Catálogo de tuberías — vuelta a columnas separadas.** La sesión anterior había fusionado
"Tubería (catálogo)" y "Ø int. (mm)" en una sola celda (select arriba, número abajo) para bajar el
ancho de la tabla — el usuario dijo que se veía mal apilado. Se separaron de nuevo en 2 columnas
angostas, una al lado de la otra (`select` de catálogo | `input` de Ø int., mismo `onchange`
`aplicarTuboCatalogo` sin cambios de lógica).

**Columna Material — eliminada de la vista, no del dato.** El usuario notó que, al elegir un
producto del catálogo, el C de Hazen-Williams ya queda determinado — mostrar el `<select>` de
Material aparte es redundante. Se cambió a `<input type="hidden">` con el mismo `name`/`id` de
siempre (ningún cambio en `main.py`: el form sigue mandando `material` igual, solo cambió de qué
tipo de elemento HTML sale). Sigue autocompletándose vía `aplicarTuboCatalogo` al elegir un
producto del catálogo. Limitación aceptada (no pedida resolver): un tramo con diámetro tipeado a
mano SIN elegir ningún producto del catálogo se queda sin `material`, y por lo tanto sin C para
calcular Hf — antes tenía un `<select>` de Material independiente para cubrir ese caso, ahora no.

**Nota técnica de implementación (informes):** al remover temporalmente `amt_declarada_m`/
`caudal_bombeo_ls` del contexto de `informe_calculo.html`/`informe_calculo_completo.html` en la
sesión anterior, se detectó (con un test aislado en Jinja2) que OMITIR una clave del contexto deja
la variable `Undefined` en la plantilla, y `Undefined is not none` evalúa `True` — el bloque
condicional habría intentado mostrar el dato igual, sin ocultarse. La lección para futuras
sesiones: si se retira un dato de un template, pasar `None` explícito en vez de omitir la clave, o
tocar también la condición del template — nunca asumir que "no pasar la clave" es equivalente a
pasar `None`.

---

## Sesión ago-2026 — Chequeo Hidráulico: corrección de UI atochada + AMT/Q diseño declarado eliminados

Feedback del usuario tras la sesión del catálogo de tuberías (ver más abajo): la tabla de tramos
quedó con 9 columnas, muy ancha — la última (Resultado) quedaba fuera de vista con scroll
horizontal, y los textos de ayuda eran demasiado largos. Además, aclaró que AMT/Q diseño
DECLARADOS nunca los pidió — solo Desnivel + Pérdida cabezal + el resultado calculado.

**Fusión de columnas:** "Tubería (catálogo)" y "Ø int. (mm)" (2 columnas separadas) pasan a UNA
sola celda — `<select>` de catálogo arriba, `<input>` numérico abajo, mismo `onchange`
(`aplicarTuboCatalogo`) sin cambios de lógica. `min-width` de `.calc-tbl` baja de 970px a 820px.

**Textos recortados:** los 2 párrafos de ayuda (Hazen-Williams/Ø interior, convención de nombres
Matriz/Terciaria/Lateral) se comprimieron a una línea cada uno; el detalle se movió a `title`
(tooltip) — mismo criterio que ya pedía CLAUDE.md ("aclaraciones indispensables van en `title`,
no como texto visible") y que no se había aplicado bien en la sesión anterior.

**AMT/Q diseño declarados — eliminados por completo, no solo ocultados.** Se retiraron de:
- `templates/calculos.html`: los 2 `<input>` (quedan solo Desnivel, Pérdida cabezal, AMT calc.).
- `main.py` `calculos_guardar_hidraulico`: ya no lee esos 2 campos del form.
- `main.py` `pagina_calculos`/`informe_calculo`/`informe_calculo_completo`: ya no los pasan al
  template (importante: se pasó `None` explícito para `amt_calculada_m`, NO se omitió la clave —
  omitirla deja la variable `Undefined` en Jinja, y `Undefined is not none` da `True` — verificado
  con un test aislado — así que el bloque condicional habría intentado renderizar sin dato en vez
  de ocultarse. Confirmado con `env.from_string(...).render(sis={})` vs. `sis={"amt_calculada_m":
  None}` — solo el segundo caso, el real, oculta el bloque correctamente).
- `analyzer.py` `_extraer_datos_hidraulicos`: el prompt ya no le pide a la IA extraer AMT/Q diseño.
- `analyzer.py` `_bloque_verificacion_hidraulica_sistema`: se quitó el bloque de comparación
  "DATOS DECLARADOS PARA EL EQUIPO DE BOMBEO" que se le inyectaba a la IA del ítem.

**Informes (`informe_calculo.html`/`informe_calculo_completo.html`):** la sección "Equipo de
bombeo" existía ANTES de esta sesión con los valores declarados, envuelta en `paso()`/`paso_mc()`
— macros que también renderizan la comparación con la "metodología del consultor" (columna
"Consultor: cita del expediente") cuando existe. Simplemente borrar la sección habría apagado esa
comparación (una feature previa e independiente, no pedida para eliminar). Se cambió el CONTENIDO
de la sección (ahora muestra "AMT/CDT calculada" en vez de "declarada") manteniendo el wrapper
`paso()`/`paso_mc()` intacto, para no perder esa comparación.

**Espaciado:** gap entre Desnivel/Pérdida cabezal subido de 0.6rem a 1.1rem; "AMT calc." alineado
a la derecha con `margin-left:auto`; clase `.input-sin-flechas` (oculta las flechas nativas de
`<input type=number>`) aplicada a Ø int., Desnivel y Pérdida cabezal.

---

## Sesión ago-2026 — Chequeo Hidráulico: fix validación, Desnivel/Pérdida cabezal, AMT calculada

**Bug reportado:** al intentar guardar datos corregidos en el Chequeo Hidráulico, el navegador
mostraba "Ingrese un valor válido. Los dos valores válidos más aproximados son X y Y" y no
guardaba nada. Causa: los inputs de Q/Ø/Longitud/V declarada/Hf declarada de cada tramo, y de AMT/
Q diseño, tenían `step` restrictivo (0.01/0.1/0.001) — la validación HTML5 nativa del navegador
revisa TODOS los number inputs del formulario al hacer submit, no solo el que se está editando; un
valor extraído por la IA con más decimales que el `step` permitido (ej. diámetro convertido desde
pulgadas, o un caudal repartido entre tramos) bloqueaba el envío del formulario COMPLETO, aunque el
revisor solo quisiera corregir otro campo. Fix: `step="any"` en los 7 campos de
`templates/calculos.html` dentro del formulario hidráulico (`form-hid`).

**Nuevos campos:** Desnivel del área de riego (m) y Pérdidas de carga en cabezal (m), junto a AMT/
Q diseño — extraíbles por la IA (`_extraer_datos_hidraulicos` en analyzer.py) o a mano. Se agregó
`calculos_riego.amt_calculada_m(tramos, desnivel_m, perdida_cabezal_m)`: suma Σ Hf de los tramos
(Hazen-Williams, mismo criterio de `evaluar_tramo`) + desnivel + pérdida de cabezal → "AMT
calculada", mostrada en un campo de solo lectura junto a los demás, con recálculo en vivo en JS
(espejo exacto de la función Python, mismo patrón que el resto del Chequeo). Explícitamente NO es
la cadena CDT completa — le falta succión aparte (si el consultor no la declaró como un tramo más
de la tabla) y margen de seguridad — así que se contrasta contra la AMT declarada en vez de
reemplazarla (mismo criterio ya usado para Hf/velocidad por tramo). También se sumó al bloque de
contexto que recibe la IA al analizar el ítem SEP "Diseño y cálculos hidráulicos"
(`_bloque_verificacion_hidraulica_sistema`), con alerta si AMT calculada no coincide con la
declarada (>15%, sin explicación técnica evidente).

**Compactación:** la fila de AMT/Q diseño (antes 2 campos en `agro-grid`, generosos) ahora es una
sola línea flex con los 5 campos (AMT, Q diseño, Desnivel, Pérdida cabezal, AMT calc.), labels
abreviados a sigla+unidad, inputs de 68px.

**Diámetro interior vs. exterior — resuelto, catálogo portado del Diseñador.** El usuario reportó
que el recálculo de pérdida de carga usa el diámetro tal como se declara en la tabla de tramos,
que en la práctica suele ser el diámetro COMERCIAL/exterior (ej. "PVC Ø110mm" en la memoria), no
el interior real que exige Hazen-Williams, y pidió que la app reste el espesor "que corresponda"
según el material. El Diseñador de Riego (`static/disenador_riego_v119.html`, array `TUBOS`
~línea 1691) ya tenía esto resuelto con un catálogo de productos comerciales reales (PVC/PE/
Aluminio, por diámetro nominal Y clase de presión PN — el espesor NO es un único valor por
diámetro+material, depende también de la clase; ej. "PVC 110mm PN6" dint=103.6mm vs. "PVC 110mm
PN10" dint=99.4mm). El usuario eligió portar ese mismo catálogo (para no perder automatización).

Implementado: `calculos_riego.TUBOS_CATALOGO` — copia literal de los 19 productos del array
`TUBOS` del Diseñador (mismos nombres/dext/dint/C, no inventados). En cada tramo del Chequeo
Hidráulico se agregó un `<select>` "Tubería (catálogo)" (`templates/calculos.html`): al elegir un
producto, JS (`aplicarTuboCatalogo`) completa el `Ø int. (mm)` con el `dint` del catálogo y el
`Material` correspondiente, y dispara `recalcHidraulico()`. Deliberadamente NO reemplaza los
campos Ø/Material existentes — solo los autocompleta — así que un tramo con un producto fuera del
catálogo sigue editable a mano exactamente como antes (misma columna, mismo dato, mismo flujo de
guardado en `main.py` y de export a `exportar_disenador.py`: ninguno de los dos necesitó cambios,
porque el catálogo resuelve HACIA los mismos campos `diametro_mm`/`material` de siempre). El
campo Ø se relabeló a "Ø int. (mm)" y se agregó un `title` + texto de ayuda aclarando que debe ser
el interior real. La extracción por IA (`_extraer_datos_hidraulicos`) se instruyó para preferir el
interior si el expediente lo distingue explícitamente del comercial, aunque en la práctica seguirá
extrayendo lo que declare el documento (probablemente el comercial) — el catálogo es la
herramienta para que el revisor lo corrija en un clic si conoce el producto exacto.

Limitación conocida (no resuelta, de alcance menor): si el usuario agregó tuberías personalizadas
en el Diseñador (localStorage `dr_tubos`, botón "+ Agregar tubería" del propio Diseñador), esas
NO aparecen en el catálogo de Revisor CNR — son datos de sesión/navegador del Diseñador, no
sincronizados con la base de datos de Revisor. Si hace falta, se puede agregar una gestión de
catálogo propia en Revisor más adelante; no se implementó por no haber sido pedida.

---

## Sesión ago-2026 — Goteo: lateral crítico cuando hay varios tramos "Lateral"

Seguimiento del punto (c) de la sesión anterior (Matriz/Terciaria/Lateral de Goteo sin exportar).
El usuario confirmó que sus tramos quedaron con nombre genérico ("Tramo 1"...) — no era un bug de
matching, así que el aviso agregado en `templates/calculos.html` (visible solo para Goteo/
Microaspersión, junto a la tabla de tramos hidráulicos) es la solución: el usuario va a renombrar
sus tramos reales usando las palabras clave.

De paso, el usuario aclaró una regla de negocio nueva: puede haber VARIOS tramos "Lateral" (uno
por sector/hilera — normal en Goteo, a diferencia de Matriz/Terciaria que son troncales únicos),
y pidió exportar el "lateral crítico" = el más largo, para simplificar. Se implementó en
`_clasificar_tramos_jerarquico()` (`exportar_disenador.py`): Matriz/Terciaria siguen exigiendo un
único candidato (ambiguo con 2+ → no se exporta, sin cambios); Lateral con 2+ candidatos ahora
exporta el de mayor `longitud_m`; si ninguno de los múltiples candidatos tiene longitud declarada,
sigue sin poder determinar cuál es el crítico y no se exporta (mismo criterio de "nunca adivinar").
Probado con 4 casos (`python3 -c "..."`, ver commit `fa3dec0`): 1 lateral, varios laterales con
longitud, matriz ambigua, varios laterales sin longitud — los 4 se comportan como se espera.

---

## Sesión ago-2026 — auditoría export→import Diseñador v119: 2 bugs más + 1 pendiente

Tras el fix del array (ver sección de abajo), el usuario reportó 3 problemas más al probar la
importación real y pidió auditoría completa. Resultado:

**(a) Capas de suelo: CC/PMP/Da llegaban con los valores por defecto de la textura, no los reales.**
Causa en `restoreFieldData()` (`static/disenador_riego_v119.html`): al restaurar cada capa,
`addCapaA`/`addCapaC` ya dejaban CC/PMP/Da correctos (los del archivo importado), pero el código
además hacía `sel.value = cp.tex` seguido de `sel.dispatchEvent(new Event('change'))` sobre el
`<select>` de textura — y el `onchange` de ese `<select>` (definido en `_capaRowHTML`, línea
~2404) autocompleta CC/PMP/Da con una tabla `SDB_` fija por textura, pisando los valores reales
que se acababan de restaurar. Fix: fijar `sel.value` sin disparar `change`.

**(b) Datos de Chequeo Fotovoltaico no aparecían al abrir el archivo.** Causa: los campos
`<pfx>-fv-*` (pkw, hbom, hsp, fp, wp, vmp, imp, ct, temp, einv, vsis) NO existen en el DOM hasta
que el usuario responde "Sí, incluir FV" para ese sistema — es una compuerta por sistema
(`dr_fv_include_<sys>` en localStorage) que por defecto es `null` en cualquier sesión/navegador
nuevo del Diseñador. Si la compuerta no está en `true`, `renderFVUI()` muestra la pregunta en vez
del formulario, así que esos elementos simplemente no existen y `restoreFieldData` los descarta en
silencio (mismo patrón que (a): sin error, sin aviso). Fix: si el archivo trae algún dato `-fv-*`,
forzar la compuerta a `true` y llamar `renderFVUI(sys)` ANTES del loop de restauración — y además
llamar `saveFVData(sys)` después, porque `renderFVUI` reconstruye el formulario desde un caché
propio (`dr_fv_<sys>`, formato de claves cortas: pkw/hbom/diasriego/hsp/... — DISTINTO del
autoguardado general) cada vez que se revisita el paso 6 del asistente; sin este segundo paso, los
valores importados se perderían la próxima vez que el usuario abra esa pestaña.

Nota al margen (NO se tocó, no confirmado como causa del reporte): existen campos `-fv-cdt` y
`-fv-qm3` en el formulario FV del Diseñador (calculadora auxiliar de potencia de bomba) que ni
siquiera están en `FIELD_IDS`, así que nunca se restauran vía import — pero como Revisor ya manda
`fv-pkw` directo (el dato definitivo), esto es a lo sumo un dato de conveniencia perdido, no la
causa de "no aparecen los datos FV". Los datos equivalentes existen en Revisor bajo `hidraulico`
(`amt_declarada_m`, `caudal_bombeo_ls`) pero `exportar_disenador.construir()` ni siquiera los
recibe hoy (main.py solo le pasa la lista de tramos, no el dict completo). Pendiente de decidir si
vale la pena, no es prioritario.

**(c) Matriz/Terciaria/Lateral (Goteo/Microaspersión) NO exporta — pendiente, no resuelto.**
`_clasificar_tramos_jerarquico()` en `exportar_disenador.py` exige que el campo `nombre` de cada
tramo hidráulico de Revisor contenga un alias reconocido (matriz/principal, terciaria/secundaria/
submatriz, lateral/portagotero/portaemisor/regante) Y que sea el ÚNICO tramo que calce con ese
nivel — si hay cero o dos-o-más tramos con el mismo nivel, ese nivel no se exporta (deliberado:
"mejor no exportar que adivinar mal", ver docstring del módulo). Dos causas posibles, sin poder
confirmar cuál aplica sin ver el proyecto real del usuario:
  1. El campo `nombre` de sus tramos de Goteo no usa ninguno de esos alias (ej. quedó con el
     default "Tramo 1"/"Tramo 2"/"Tramo 3" que pone main.py cuando no se completa).
  2. Tiene más de un tramo por nivel (ej. varios tramos "Lateral" — uno por sector — en vez de un
     valor representativo único), lo que dispara la regla de ambigüedad.
  Ninguna de las dos se corrige adivinando (violaría la regla "NUNCA se inventan valores" del
  módulo) — queda pendiente preguntarle al usuario cuál es su caso antes de decidir el fix: ¿ampliar
  los alias, o pedirle un criterio de desempate cuando hay varios tramos por nivel (¿el primero?
  ¿el de mayor diámetro? ¿sumar longitudes?).

---

## Sesión ago-2026 — fix import Diseñador de Riego v119 (array multi-sistema)

Bug reportado: exportar un proyecto de Revisor CNR con más de un sistema declarado (ej. Goteo +
Aspersión, mismo predio) y abrirlo en el Diseñador no cargaba ningún dato — "no aparece ninguno".

Causa: `/proyecto/{id}/calculos/exportar-disenador` (main.py) arma un ARRAY de objetos cuando hay
2+ sistemas exportables (uno por sistema, mismo formato `{__sys, __name, __date, fields}` que un
archivo de un solo sistema). Pero `importProject()` en `static/disenador_riego_v119.html` hacía
`var data = obj.fields || obj;` — con un array, `obj.fields` es `undefined`, así que `data` quedaba
siendo el array completo, y `restoreFieldData` nunca encontraba las claves de campo esperadas
(itera `data[id]` buscando strings, no encuentra nada en un array de objetos). No lanzaba error:
el `try/catch` no detectaba nada raro, por eso el fallo era silencioso — coincide con el reporte.

Fix (`static/disenador_riego_v119.html`, función `importProject`): normaliza siempre a una lista
(`Array.isArray(obj) ? obj : [obj]`) y restaura cada entrada con `restoreFieldData(entry.__sys ||
sys, data)` — usa el `__sys` propio de la entrada, NO el de la pestaña donde se hizo clic en
"Abrir". Esto tiene un beneficio extra: como los campos de los 4 sistemas (got/mic/asp/car)
conviven en la misma página HTML (confirmado: `openProjectsMgr('asp'|'car'|'got'|'mic')` está
hardcodeado por sección, no hay show/hide de un "sys activo" que oculte el resto del DOM), un
archivo con varios sistemas los carga TODOS de una vez sin importar en qué pestaña se abrió el
diálogo, y de paso un archivo de un solo sistema ya no depende de que el usuario esté en la
pestaña "correcta" — antes, si el `__sys` del archivo no coincidía con la pestaña abierta, también
fallaba en silencio (mismo síntoma, causa distinta).

Verificado: nombres de campo (`g-*`/`a-*`/`c-*`) de `exportar_disenador.py` contra 3 archivos
reales exportados DESDE el Diseñador v119 que el usuario adjuntó (Goteo, Aspersión y Carrete de
proyectos reales/en curso) — coinciden.

De paso, al revisar esos 3 archivos se notó que `exportar_disenador.py` NUNCA exportaba el
Desglose de Humedad Aprovechable por capas de suelo (`capas_suelo` en Revisor → `__capasA`/
`__capasC` en el Diseñador, mismo formato `{on, capas:[{desde,hasta,tex,cc,pmp,da}]}` confirmado
contra el archivo de Aspersión adjuntado, que sí traía capas reales). Se agregó en `construir()`
(solo Aspersión/Carrete, mismas claves de textura en ambas apps). Probado con
`python3 -c "import exportar_disenador..."` (sin la app corriendo) — arma el dict esperado.

Pendiente: el usuario probar la exportación real desde Revisor CNR → import en el Diseñador, con
el proyecto Goteo+Aspersión que motivó el reporte, y confirmar que las capas de suelo también
llegan cuando el sistema (Aspersión/Carrete) las tiene cargadas.

---

## Estado al cierre de esta sesión (ago-2026) — leer antes de seguir

El usuario sigue usando la app con el concurso 202-2026 con proyectos reales. No hay ningún bug
abierto conocido a esta fecha — si retomas y el usuario reporta algo raro, lo más probable es
que sea un caso nuevo, no una regresión de lo ya resuelto.

**PENDIENTE para la próxima sesión — dos decisiones del usuario, no acciones nuestras:**
1. El usuario va a revisar un proyecto nuevo casi idéntico a otros ya revisados, específicamente
   para ver si el ítem "Diseño y cálculos hidráulicos" cambia de comportamiento con el fix de
   ago-2026 (ver más abajo — criterio de ingeniero + aviso de N° de sectores sin respaldo). Si
   reporta que sigue viendo observaciones "simples" pese al fix, profundizar desde ahí — no
   asumir que el fix ya cerró el tema.
2. El usuario va a revisar la comparación Sonnet 5 vs. Sonnet 4.6 (se le explicó en prosa, sin
   tabla ancha, porque la vio desde el celular) y decidirá si migra a 4.6 como modelo por defecto
   dejando Sonnet 5 solo para los ítems que van por visión (planos, ubicación, identificación de
   riego, pruebas de bombeo). Datos clave que ya tiene para decidir: (a) hoy Sonnet 5 sale más
   barato pese a tokenizar ~30% más, por el precio promocional vigente hasta el 31-08-2026 — si
   migra a 4.6 solo para los ítems de texto, esa fecha deja de importar para esos ítems (siguen
   yéndose a 4.6 sea antes o después del 31-08); (b) el código NUNCA fija `thinking`/`effort`
   explícito en ninguna llamada a Sonnet, así que corre con el default de cada modelo — Sonnet 5
   piensa (adaptativo) por defecto, Sonnet 4.6 NO piensa por defecto — es probablemente el mayor
   factor de costo real, más que el precio por token, y explica parte de los reintentos por
   `max_tokens` ya documentados; (c) Sonnet 5 tiene visión de mayor resolución (2576px vs 1568px),
   por eso la idea del usuario de dejarlo solo para los ítems de planos/imagen tiene sentido
   técnico, no es solo por costo.

**Lo último de esta sesión (ago-2026) — botón "Eliminar todos" en Documentos del expediente:**
a pedido del usuario, tras subir por error los mismos ~40 archivos dos veces al mismo proyecto —
borrar uno por uno con la confirmación individual de siempre es tedioso a esa escala. Botón nuevo
`POST /proyecto/{id}/documentos/eliminar-todos` (`eliminar_todos_documentos()`, main.py),
alineado a la derecha en la misma línea del título "Documentos del expediente"
(`templates/proyecto.html`, mismo patrón `<span style="flex:1;"></span>` de separador ya usado en
otras filas de la app) — visible solo cuando el proyecto tiene documentos (dentro del
`{% if proyecto.documentos %}` que ya envuelve toda la tarjeta), con `confirm()` citando la
cantidad real de documentos y clase `btn-danger` (mismo rojo del botón "Eliminar" individual de
cada fila, por ser igual de destructivo).
- **Mismo efecto neto que borrar cada documento uno por uno, pero en LOTE**, no un mecanismo
  nuevo: borra la carpeta física del proyecto entera de una vez (`shutil.rmtree`, en vez de
  archivo por archivo) y usa `db.eliminar_archivos_proyectos([proyecto_id])` +
  `db.eliminar_textos_proyecto(proyecto_id)` — las mismas dos funciones EN LOTE que ya existían
  para "liberar archivos" al cerrar un concurso (ver esa sección más abajo), reusadas acá para un
  solo proyecto en vez de iterar `eliminar_archivo`/`eliminar_texto_documento` documento por
  documento. `proyecto["documentos"]` queda `[]`.
- **Mismo alcance que el borrado individual** (`eliminar_documento()`): filtra de
  `proyecto["observaciones"]` solo las que tengan `doc_id` (formato legado, del método por
  documento ya eliminado) — las observaciones de ítem (`item`/`item_nombre`, sin `doc_id`) NO se
  tocan, ni tampoco `items_revisados`/`items_en_progreso`/`items_error` — el revisor puede volver
  a subir los documentos y re-analizar los ítems normalmente, sin perder el historial de qué ya
  se había revisado.
- Si el proyecto ya no tiene documentos (`doc_ids` vacío), la ruta es no-op — no llama a la base
  ni reescribe el proyecto (aunque en la práctica el botón nunca se muestra en ese caso, por el
  `{% if proyecto.documentos %}` que envuelve la tarjeta completa).
- Verificado con `eliminar_todos_documentos()` real (mocks de `db.get_proyecto`/`save_proyecto`/
  `eliminar_archivos_proyectos`/`eliminar_textos_proyecto`, carpeta temporal real para confirmar
  que `shutil.rmtree` borra el directorio físico): caso con documentos (carpeta borrada, las 2
  llamadas en lote con los argumentos correctos, `documentos=[]`, observación de `doc_id` filtrada
  y observación de ítem conservada), caso sin documentos (no-op, no toca la base) y caso sin
  sesión (redirige a `/login`). Más el snippet HTML del botón renderizado de forma aislada,
  confirmando alineación a la derecha, cantidad correcta en el `confirm()` y la URL de acción.

**Antes de eso, en la misma sesión — calidad de análisis en "Diseño y cálculos hidráulicos":**
el usuario reportó, con casos reales, que las observaciones de ese ítem eran "simples" (superficies
distintas, un caudal faltante en una tabla) y nunca evaluaban la lógica de ingeniería del diseño
— dio como ejemplo un N° de sectores que "aparece mágicamente" sin que la IA lo advirtiera. Se
agregó (SIN borrar nada del checklist existente, a pedido explícito) un párrafo de "criterio de
ingeniero" al checklist del ítem, y se corrigió un bug real: el bloque de verificación
determinística del N° de sectores quedaba en silencio total cuando el expediente no declaraba la
base del cálculo (superficie/precipitación/caudal disponible) — exactamente el caso "número
mágico" — ahora avisa explícitamente y pide evaluar si la memoria al menos justifica la cifra. Ver
la entrada dedicada "Ítem 'Diseño y cálculos hidráulicos' — de checklist de presencia a criterio
de ingeniero" más abajo (dentro de "Verificación de diseño base"). **Principio de producto que
dejó el usuario para las próximas sesiones: los ítems Diseño agronómico/hidráulico, Presupuesto y
Planos son la BASE del proyecto de riego — su análisis debe tener el mayor criterio de ingeniería
posible, más que el resto de los ítems** (ver punto 9 de "Instrucciones del usuario" al final).

**Antes de eso, en la misma sesión:** tres ajustes puntuales — color/alineación del botón
"Revisar todos" (pasó a `btn-outline`, alineado con `grid-column:-1` a la fila de Coherencia
Global) y avance visual tarjeta por tarjeta durante la tanda (antes solo el contador de texto se
actualizaba); y un **bug de precio real**: `PRECIOS_USD_POR_MTOK` tenía el precio de LISTA de
Sonnet 5 (USD 3/15) en vez del promocional vigente hoy (USD 2/10, hasta el 31-08-2026) —
sobreestimaba el costo real ~40 % desde que existe el contador. `_precio_sonnet5()` ahora calcula
el precio según la fecha, sin necesidad de tocar código después del 31-08 (ver "Bug de precio
real encontrado" más abajo, dentro de la sección del contador de costo).

**Y antes de eso, en la misma sesión:** auditoría completa de la app (ver "Auditoría general
(ago-2026)" más abajo — 7 puntos: bug de bloqueo del event loop, `database.py` thread-safe, dos
extracciones de Haiku paralelizadas, reuso de la extracción del Chequeo sin exigir el tilde
"validado", código muerto, `_log_uso` en las 8 llamadas de Haiku) y, a partir de un proyecto real
que salió USD 4,48 contra los ~3 habituales, un **contador de costo por proyecto visible en la
app** (punto 7 de esa sección): US$ discreto en el encabezado, con desglose por paso y por ítem al
hacer clic. Antes de esto el costo solo existía en el log de Railway, así que el usuario lo
verificaba a mano comparando el saldo de la consola de Anthropic antes y después de revisar.
También se agregó el botón **"Revisar todos"** (tanda secuencial de ítems), el tope duro de 300
caracteres en "Características obras" del Resumen, y el mecanismo para que un ítem NO repita una
observación ya hecha en otro (ver "Observaciones repetidas entre ítems").

**Y antes de eso, en la misma sesión:** a partir de dos Excel reales de un consultor que el
usuario compartió (memoria de cálculo de Goteo/invernadero con SCALL + balance hídrico), se
reforzó el checklist de Coherencia Global (consistencia de cultivo entre documentos, N° de
sectores justificado, invernadero vs. aire libre identificado — ver "Checklist de Coherencia
Global" más abajo) y se construyó la **"Memoria de cálculo explicada"** (`/proyecto/{id}/
calculos/informe/{idx}`, botón junto a "Exportar para el Diseñador de Riego" en la tarjeta de
cada sistema del Chequeo de Cálculos): un informe paso a paso, sin recalcular ni extraer nada
nuevo (reutiliza los mismos datos ya guardados), con un botón opcional "Comparar con la
metodología del consultor (usa IA)" que arma una vista en 2 columnas (cómo lo calculó el
consultor, citado textual del expediente — vs. cómo lo calcula la app) para los 14 conceptos de
`CONCEPTOS_METODOLOGIA` — ver la sección dedicada "Memoria de cálculo explicada" más abajo para
el detalle completo (diseño, costo ~US$0,15–0,25/sistema, alcance acotado, verificación).
**Pasada de minimalismo (ago-2026):** a pedido explícito del usuario, se quitó el texto
explicativo que acompañaba a los botones "Ver memoria de cálculo explicada", "Exportar para el
Diseñador de Riego" y "Comparar con la metodología del consultor" (los botones ya son
autoexplicativos por su etiqueta) y los dos primeros se pusieron en la misma fila — ver el
punto 8 de "Instrucciones del usuario" al final de este documento: **por defecto, para toda UI
nueva, minimizar texto de acompañamiento y preferir botones autoexplicativos** (aclaraciones
indispensables van en el `title`/tooltip, no como texto siempre visible).

**Nota:** el resto de esta sección ("Checklists de los 18 ítems del SEP reescritos...") es el
cierre de una sesión bastante anterior (jul-2026) — se mantiene como historial/referencia, no
como el estado más reciente.

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
   `presupuesto_electrico`, `coherencia`, `especificaciones_tecnicas` (este último agregado más
   tarde — ver el bug dedicado más abajo, el detonante ahí no es 2-3 archivos grandes sino MUCHOS
   documentos repartiéndose el mismo presupuesto) y `cubicaciones` (agregado jul-2026 junto con
   el ítem, ver "Ítem Cubicaciones agregado" más abajo — tabla de cantidades, igual de densa en
   datos que presupuesto) — el resto de los ítems sigue en 45.000.
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
- `/proyecto/{id}/items` → 19 ítems SEP (`ITEMS_SEP`/`ITEMS_ORDEN`) + chat + obs de ítem.

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

**Orden de secciones en la página Ítems SEP — "Debatir con la IA" DESPUÉS de Observaciones/Notas
(jul-2026):** a pedido del usuario, por practicidad de su flujo real: abre un ítem, revisa sus
documentos y observaciones, y solo a veces necesita discutirlo con la IA — con el chat primero
(orden original) tenía que bajar de más en cada vuelta para llegar a las observaciones. Se
invirtió el orden en `proyecto.html` (página `/proyecto/{id}/items`): ahora
`bloque_observaciones()` y `bloque_notas()` van primero, `bloque_chat()` después, y
`bloque_cumplimiento()` al final (sin cambios). Es solo un reordenamiento de las mismas 4 llamadas
a macro, con los mismos argumentos — no cambió nada del contenido ni del comportamiento de cada
bloque (anclas `#chat-item-...`, auto-apertura por `item_ok`, etc., siguen funcionando igual, no
dependen del orden en el DOM).

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
- `superficie_predial` renombrado de "Superficie" a **"Superficie Cert. Avalúo"** — deja
  explícito que ese dato sale del Certificado de Avalúo Fiscal del predio (superficie predial
  total), distinto de `superficie_clase_sep` ("Superficie (SEP)", ver abajo).
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

**Campo "Costo total (UF)" en Identificación (implementado, jul-2026):** a pedido del usuario,
campo nuevo `costo_total_uf` (tipo `text`, sin `auto` ni `maxlen`) al final de la sección
"Identificación" de `RESUMEN_SECCIONES` — el monto total del proyecto, en UF. Al ser puramente
declarativo del mecanismo ya genérico de `RESUMEN_SECCIONES` (documentado en el resto de esta
sección), no requirió tocar `main.py` ni las plantillas: aparece solo en el formulario editable
(`proyecto.html`, página Resumen), en el Informe Resumen impreso, y queda disponible para el
autocompletar con IA y para `_construir_bloque_resumen()` (se inyecta como contexto en todo
análisis de ítem, ver la entrada siguiente) — los tres puntos iteran `RESUMEN_SECCIONES` sin
conocer las claves de antemano. No lleva `resumen_ia` porque no hace falta una instrucción de
estilo especial (a diferencia de "Características obras") — la IA ya interpreta "UF" del label.
**Combinado con "Código proyecto" en el informe impreso (jul-2026):** a pedido del usuario, para
no seguir sumando altura al informe — mismo mecanismo `"linea_con"` ya usado por `clase` +
`superficie_clase_sep` en "3. Predios" (ver esa entrada más arriba), acá aplicado a `codigo`
(`"linea_con": "costo_total_uf"`). Solo afecta `informe_resumen.html` — el formulario editable
sigue con cada campo en su propia línea, sin cambios.

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
- **Revisión por 19 ÍTEMS del SEP** (único método vigente — el método por Ejes se eliminó, ver
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
  **Fix de destello blanco al navegar (jul-2026):** el cálculo de si toca modo oscuro vivía en
  un `<script>` al final del `<body>` — con navegación de página completa (sin SPA), cada
  cambio de página pintaba primero en claro y recién al final aplicaba `dark-mode`, un destello
  molesto reportado por el usuario (más notorio ahora que la navegación entre páginas del
  proyecto es más rápida, ver la separación del texto extraído del blob del proyecto más
  arriba). Se movió el cálculo (localStorage + hora automática) a un `<script>` sincrónico al
  inicio del `<head>`, antes de cualquier `<link>`/`<style>` — corre y aplica la clase
  `dark-mode` al `<html>` antes de que el navegador pinte nada. El script del final del `<body>`
  quedó solo con lo que sí necesita el DOM ya cargado: actualizar el ícono sol/luna y el
  `toggleModo()` manual.
- **Estados del proyecto (6, jul-2026):** En revisión · Pendiente · Observado · Con respuesta
  Observaciones · Aprobado Técnicamente · Rechazado — única fuente de verdad: `ESTADOS_PROYECTO`
  (lista, define también el orden del selector) + `ESTADOS_PROYECTO_BADGE` (clase `badge-*` para
  el color) + `ESTADOS_PROYECTO_COLOR_SOLIDO` (hex, para el botón/opciones del selector), las 3 en
  main.py. Se retiró **"Revisado"** (el usuario lo consideró redundante con el resto de la
  clasificación) y se agregó **"Con respuesta Observaciones"** (el consultor ya respondió, en
  línea con la página Respuestas/subsanación). `cambiar_estado_proyecto()` valida contra
  `ESTADOS_PROYECTO` directamente (antes era un `set` hardcodeado aparte, quedaba fácil que se
  desincronizara del selector). **Colores** (mismo criterio en el badge del dashboard y en el
  badge/selector del encabezado del proyecto — filtro Jinja `estado_badge`, registrado junto a
  `fecha`/`fecha_hora`): reutiliza las clases `badge-*` YA existentes en `base.html` en vez de CSS
  nuevo — En revisión → `badge-estado` (celeste), Observado → `badge-menor` (amarillo), Con
  respuesta Observaciones → `badge-legal` (morado claro), Aprobado Técnicamente → `badge-tecnica`
  (verde), Rechazado → `badge-mayor` (rojo). Un valor legado que ya no está en la lista (ej.
  "Revisado" en un proyecto viejo) cae al fallback neutro `badge-estado` en vez de romper — el
  estado guardado en un proyecto antiguo no se migra, solo deja de poder volver a asignarse desde
  el selector. (El estado "Aprobado Técnicamente" se agregó originalmente junto con la
  subsanación — ver sección dedicada más abajo.)
  **"Pendiente" agregado (jul-2026):** a pedido del usuario, para proyectos que empezó a revisar
  pero dejó a medio camino por atender otro más urgente — necesita un color BIEN DISTINTO de los
  demás para no perderlo de vista en el dashboard. Como los 5 colores/badges existentes ya
  estaban todos tomados por los otros 5 estados, se creó una clase nueva `badge-pendiente`
  (rosa/magenta — `#ffe3f1` fondo, `#c2185b` texto, en `base.html`, mismo patrón de las demás
  `.badge-*`) en vez de reutilizar una — es el único estado de los 6 que no comparte clase con
  ningún otro. Insertado justo después de "En revisión" en `ESTADOS_PROYECTO` (segunda posición,
  define el orden del selector) por ser conceptualmente un sub-estado de ese — un proyecto que
  ya se empezó a trabajar, no uno nuevo sin tocar.
  **Bug de z-index resuelto (jul-2026):** el menú desplegable del selector (`#menu-estado`)
  quedaba tapado detrás de las pestañas "Chequeo de Cálculos"/"Respuestas" — causa: el selector
  genérico `nav { position:sticky; z-index:100; }` de `base.html` (pensado para la barra
  superior del sitio) también alcanza a `<nav class="proj-nav">` (la barra de pestañas del
  proyecto), porque sigue siendo un `<nav>`. Se subió el z-index del menú a `200` (por encima
  de 100) en vez de tocar el selector genérico de `base.html`, para no arriesgar otras páginas.
- **Dashboard — columna "Revisión" eliminada, botón Eliminar como "×" (jul-2026):** a pedido
  del usuario, para dar más espacio al resto de la información de la tabla. Se quitó la
  columna con el badge Técnica/Legal (ya no aporta nada — la app solo hace revisión técnica,
  ver "Solo revisión técnica" más abajo) y `db.get_proyectos_ligero()` en `dashboard()` ya no
  pide el campo `tipo_revision` (un campo menos en la proyección liviana). El botón "Eliminar"
  de cada fila pasó a mostrar solo "×" (con `title="Eliminar proyecto"` para accesibilidad) —
  mismo `confirm()` de siempre, solo cambia el texto visible.
  **Separado de "Abrir" (jul-2026):** al quedar tan angosto, el botón "×" terminó muy pegado a
  "Abrir" — fácil de apretar por error. Se le agregó `margin-left:1.5rem` al form que lo
  contiene para separarlo con claridad.
  **Columna "Consultor" agregada (jul-2026):** a pedido del usuario, entre Postulante y Estado.
  `dashboard()` agrega `"resumen"` a la proyección liviana (`db.get_proyectos_ligero`) — se pide
  COMPLETO (no campo por campo) porque es chico (~25 campos cortos, tope 500 caracteres c/u,
  nada comparable al texto de los documentos que esa función existe para evitar cargar) — y
  calcula `p["consultor"] = (p.get("resumen") or {}).get("consultor", "").strip()` por cada
  proyecto antes de pasarlo a la plantilla (mismo dato que ya usa `_consultor_de_proyecto()` en
  el resto de la app). Muestra "—" si el campo está vacío o el proyecto es legado sin `resumen`.
  **Columna "N°" — numeración por antigüedad (jul-2026):** a pedido del usuario, primera columna
  de la tabla. NO cambia el orden de las filas (se consultó explícitamente y el usuario prefirió
  mantener los proyectos más recientes arriba, el orden de siempre) — solo numera cada proyecto
  según su antigüedad relativa (el más antiguo = 1), como referencia estable independiente del
  orden visual. `dashboard()` ordena una copia de `proyectos` por `fecha_creacion` ascendente
  para asignar el número (`numero_por_id`), y lo aplica sobre la lista real (que sigue en su
  orden descendente de siempre) — el número más alto queda arriba, junto al proyecto más
  reciente. Un proyecto legado sin `fecha_creacion` (cadena vacía) ordena como el más antiguo,
  sin romper.
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
- **Estado del proyecto:** se agregó **"Aprobado Técnicamente"** a los estados válidos
  (`cambiar_estado_proyecto`) y al menú/badge de estado en `proyecto.html` (verde). El botón
  guardado de la página Respuestas es el camino previsto; el menú de estado sigue permitiendo
  fijarlo a mano (el revisor es la autoridad). Ver la lista completa de los 5 estados vigentes
  y sus colores en "Estados del proyecto", más arriba.
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

## Auditoría general (ago-2026) — rendimiento, código muerto y costo de API

Segunda revisión completa a pedido del usuario ("elimina código muerto, optimiza procesos, y
busca cualquier tipo de mejora en velocidad o ahorro en llamadas a la API"). Lo aplicado:

**1. Bug de bloqueo del event loop — `_restaurar_archivos_necesarios` congelaba la app entera.**
Es una función SINCRÓNICA que puede hacer varias lecturas de `bytea` de varios MB desde Postgres
más la escritura de esos PDF al disco, y se llamaba **directo** (sin `asyncio.to_thread`) desde
`_analizar_item_fondo`, que es `async`. Mientras corría, el event loop quedaba bloqueado: ninguna
página respondía para NINGÚN usuario, no solo el que analizaba. Es exactamente el mismo patrón de
bug ya corregido dos veces en este proyecto (llamadas a Anthropic/PyMuPDF en la 1ª auditoría,
`bcrypt` en `login()` en la 2ª) — este punto se había quedado afuera de ambas. Se nota sobre todo
**tras un redeploy de Railway** (frecuentes acá), que es justo cuando esta restauración tiene
trabajo real que hacer. Arreglado con `await asyncio.to_thread(...)`.

**2. Consecuencia del anterior: `database.py` necesitaba ser thread-safe de verdad.** Hasta ahora
TODO el código que tocaba la única conexión psycopg2 compartida corría en el mismo hilo, así que
no hacía falta sincronizar nada — la 2ª auditoría ya había identificado esto como el requisito
previo para cualquier `to_thread` sobre la base, y lo dejó pendiente. Con el fix anterior hay un
segundo hilo, así que se cerró: `_pg_lock` (`threading.RLock`) dentro de `_reintenta_si_cae`.
- **Por qué ahí y no en cada función:** las 12 funciones que tocan Postgres pasan SIN EXCEPCIÓN
  por ese decorador (verificado con un barrido AST de `database.py`) — un solo punto, no 12.
- **Qué cubre exactamente:** psycopg2 declara `threadsafety = 2` ("threads may share the module
  and connections") y cada función de acá abre su PROPIO cursor (`with conn.cursor()`), que es la
  condición que esa garantía exige. Lo que NO cubre es el camino de reconexión del decorador, que
  cierra y reemplaza la global `_pg_conn` mientras otro hilo podría estar usando la vieja — esa
  es la ventana que cierra el lock.
- **`RLock` y no `Lock`** por prudencia: si alguna vez una función decorada llama a otra, un
  `Lock` simple se trabaría solo. No cuesta rendimiento — el acceso a la base YA estaba
  serializado de hecho (un solo hilo); esto solo lo hace explícito y seguro ahora que hay dos.

**3. Latencia — dos extracciones de Haiku que corrían una después de la otra.** En
`analizar_item()`, el ítem `diseno_hidraulico` (el ÚNICO con dos extracciones) hacía
`await _extraer_datos_hidraulicos(...)` y recién después `await _extraer_datos_agronomicos(...)`,
pese a ser completamente independientes (distinto conjunto de documentos, distinto prompt, sin
estado compartido) — pagaba la SUMA de ambas llamadas en vez del máximo. Ahora van con
`asyncio.gather`. Además, `revisar_invalidacion_cruzada` (que no depende del bloque de
verificación, solo de `docs_grupo`) se lanza con `asyncio.create_task` al INICIO de la función en
vez de recién en el `gather` final, así corre en paralelo también con las extracciones.
- **No cambia ni una llamada a la API** — mismas llamadas, mismos prompts, mismo resultado; solo
  cuándo arrancan. El costo es idéntico, baja la latencia.
- Verificado con las funciones reales de `analyzer.py` (extracciones simuladas con
  `asyncio.sleep`, sin mocks de HTTP): las 3 tareas arrancan en t≈0 y el total pasa de la suma
  (0,5+0,5+0,4 = 1,4 s) al máximo (0,9 s). Más las 4 regresiones: datos ya validados por el
  revisor siguen sin gastar ninguna llamada a Haiku, sin observaciones pendientes no se lanza la
  invalidación, los demás ítems quedan igual, y una excepción en la extracción se sigue tragando
  sin dejar la tarea de invalidación colgada (probado con `warnings.simplefilter("error")`).

**4. Reuso de la extracción del Chequeo de Cálculos — ya NO exige el tilde "validado"
(ago-2026).** Hasta ahora, al revisar "Diseño y cálculos hidráulicos" la app solo reusaba los
datos del Chequeo si estaban marcados "Ya revisé estos datos"; si no, los volvía a extraer con
Haiku desde cero. En la auditoría lo dejé así con dos argumentos, y **el usuario corrigió que
ambos eran falsos** para cómo usa realmente la app:
- *"Los documentos pueden haber cambiado entre extraer y revisar"* — **no pasa**: nunca se sube
  un documento nuevo entre una cosa y la otra.
- *"Sin el tilde, nadie revisó esos datos"* — **falso**: el revisor SIEMPRE revisa lo extraído en
  el Chequeo. No tilda "validado" por un motivo distinto y deliberado: los números de la app y
  los del consultor a veces no cuadran, y **la referencia de la revisión son siempre los datos
  del consultor**, no los recalculados por la app (esos son solo para comparar y, si la
  diferencia es grande, observarla). O sea que el tilde no significa "esto está revisado" sino
  otra cosa, y no correspondía usarlo como condición para reusar.
- **Argumento adicional del usuario, y es el más fuerte:** si una extracción ya encontró ciertos
  datos, una segunda extracción sobre los MISMOS documentos con el MISMO prompt debería devolver
  lo mismo — pero "debería", no "garantiza". Al re-extraer, el análisis puede terminar usando
  números levemente distintos a los que el revisor tiene a la vista en la página Chequeo. Reusar
  elimina esa inconsistencia: lo que se analiza es exactamente lo que el revisor vio.
- **Implementado:** `_datos_guardados()` + `_tiene_datos()` (main.py) reemplazan al `_validado()`
  anterior en `_analizar_item_fondo`, para los 3 grupos (hidráulico, agronómico, energético). La
  condición pasó de "está validado" a "hay algún dato real guardado". El tilde "Ya revisé estos
  datos" **se mantiene** y se sigue mostrando con fecha/autor — simplemente ya no decide esto.
- **La guarda que sí hace falta:** un formulario guardado EN BLANCO deja la clave existiendo pero
  vacía (`{"sistemas": [{"tramos": [], "amt_declarada_m": None, ...}]}`). Reusar eso habría
  matado la verificación numérica en silencio, que es peor que pagar la extracción. `_tiene_datos`
  recorre la estructura completa ignorando la metadata de validación y solo devuelve `True` si hay
  al menos un valor real — si está en blanco, el análisis extrae por su cuenta, como antes.
- Verificado con `_analizar_item_fondo()` real (mocks de `db.*` y de `analizar_item`, sin mocks de
  HTTP), interceptando qué recibe `analizar_item`: extraído-sin-tildar ahora se reusa; validado se
  reusa igual que antes; formulario en blanco NO se reusa y deja extraer; sin Chequeo previo
  extrae como siempre. Más `_tiene_datos` contra los shapes reales de los 3 grupos.

**5. Código muerto eliminado:** `calculos_riego.factor_christiansen()` (nunca se llamó desde
Python — solo existe una fórmula homónima dentro del HTML del Diseñador de Riego, que es una app
aparte) y el import sin uso de `hash_password` en `main.py`. Barrido AST de símbolos definidos vs.
usados sobre los 8 módulos + los templates: no quedó nada más.

**6. `_log_uso` cableado a las 8 llamadas de Haiku (ago-2026).** Hasta ahora solo registraban
costo las llamadas a Sonnet 5; las de Haiku (extracción hidráulica, agronómica, FV, partidas de
presupuesto, autocompletar Resumen, documentos obligatorios y las dos consolidaciones de
aprendizaje) no aparecían en el log, así que **una parte del gasto de cada proyecto era
literalmente invisible** al intentar explicar por qué costó lo que costó. Ahora todas pasan por
`_log_uso(..., MODELO_HAIKU)` — con el precio de Haiku, no el de Sonnet.

**7. Contador de costo POR PROYECTO, visible en la app (ago-2026).** Al explicarle el punto
anterior al usuario, la pregunta obvia: *"¿dónde se ven los costos? Yo solo lo verifico en la
página de la API de Claude, viendo el antes y el después de una revisión"* — y tenía razón: hasta
acá `_log_uso` solo imprimía en el log de Railway, que él no mira. Pidió *"un contador de costo,
visible en revisión y en cada paso que use API, es decir en resumen, chequeo y revisión, algo
discreto"*. Implementado:
- **`analyzer.iniciar_costo()` + el ContextVar `_costo_acumulado`.** La operación en curso abre un
  acumulador y todo `_log_uso` posterior suma ahí, además de seguir imprimiendo en el log igual
  que siempre. Es un ContextVar y no una global porque puede haber varias operaciones en vuelo a
  la vez (un análisis en segundo plano mientras el revisor consulta desde otra pestaña) y cada una
  debe sumar en el suyo. **El truco que lo hace no invasivo:** `asyncio.create_task` y
  `asyncio.to_thread` COPIAN el contexto pero comparten el mismo objeto dict — así las llamadas
  anidadas (las extracciones de Haiku, la invalidación cruzada, que corren como subtareas) suman
  solas, sin tocar ni una firma de `analyzer.py`.
- **`main._registrar_costo(proyecto, paso, acc, detalle)`** suma al proyecto:
  `proyecto["costo_api"] = {total_usd, llamadas, pasos:{paso:{usd,llamadas}}, items:{item_key:usd},
  actualizado}`. Muta en memoria y NO guarda — el llamador ya hace `db.save_proyecto()` con el
  resto del resultado, así que se suma a ese guardado en vez de pagar un round-trip extra. Si la
  operación no hizo ninguna llamada (datos reusados del Chequeo, error antes de llegar a la IA) no
  escribe nada: un paso con 0 llamadas no debe ensuciar el desglose.
- **Cableado en los 9 puntos del proyecto:** revisar ítem (con `detalle=item_key`, de ahí el
  desglose por ítem), chat, las 3 extracciones del Chequeo, metodología del consultor,
  autocompletar Resumen, consulta libre y evaluar respuesta de subsanación. **NO** se cargan las
  llamadas de administración (documentos obligatorios de un concurso, consolidar aprendizaje,
  perfil de consultor): no son de un proyecto puntual y cargarlas a uno cualquiera falsearía su
  costo.
- **Caso especial — evaluar respuesta de subsanación.** Es la única de las 9 que NO modifica el
  proyecto (devuelve la recomendación por AJAX y nada más), así que hubo que agregarle un
  guardado. Relee el proyecto FRESCO antes de guardar: la evaluación tarda decenas de segundos y
  en ese lapso un análisis en segundo plano pudo haber escrito sus observaciones — guardar la
  copia vieja las habría borrado.
- **UI (`templates/_costo_api.html`, incluido en proyecto.html / calculos.html / respuestas.html;
  CSS `.costo-api*` en base.html).** Discreto por el punto 8 de las instrucciones del usuario: un
  `US$ 3,32` gris en la fila de badges del encabezado; al hacer clic se abre un panel FLOTANTE
  (`position:absolute`, igual que el menú de estado) con el desglose por paso, el desglose por
  ítem ordenado de mayor a menor, y el total de llamadas. Flotante y no inline a propósito: un
  `<details>` que expandiera en el flujo empujaría toda la fila de badges hacia abajo al abrirse
  (verificado con Playwright que el botón de estado no se mueve). Si el proyecto no gastó nada,
  `_costo_para_vista()` devuelve `None` y no se muestra NADA — un "US$ 0,00" no aporta.
- **Bug pisado en el camino, el mismo de siempre:** la clave de la lista por ítem NO puede
  llamarse `items` — en Jinja `costo_api.items` resuelve al método `dict.items()` y el render
  revienta en runtime. Se llama `por_item`. Es la tercera vez que este proyecto tropieza con eso
  (ver la nota de `grupo.items` en "Criterio de análisis"); **nunca usar `items` como clave de un
  dict que se lea desde una plantilla.**
- **Lo que el contador NO es:** una factura. Son los precios de lista aplicados al `usage` que
  devuelve cada respuesta — sirve para comparar proyectos entre sí y detectar uno anómalo, no para
  cuadrar al centavo contra la consola de Anthropic. Y solo cuenta desde que se desplegó: los
  proyectos ya revisados arrancan sin `costo_api` y no muestran nada (no hay dato histórico que
  reconstruir, el log de Railway rota).
- Verificado con las funciones reales (sin mocks de HTTP): acumulación correcta sumando una
  subtarea de `create_task` y una llamada dentro de `to_thread`; dos operaciones en paralelo no se
  mezclan; sin acumulador activo `_log_uso` no falla; el registro ignora los pasos con 0 llamadas
  y ordena el desglose de mayor a menor; render de las 5 páginas (Resumen/Documentos/Ítems/
  Chequeo/Respuestas) con y sin costo; y captura de pantalla del panel abierto.

**Cómo diagnosticar un proyecto que costó de más** (el usuario reportó uno de USD 4,48 contra los
~3 habituales, sin saber por qué). Con el contador del punto 7 el desglose por ítem ya se ve en la
propia app; para la causa, los dos sospechosos, en orden de magnitud, ambos visibles en el log de
Railway:
- **Reintento por `max_tokens`** — el primer intento se paga COMPLETO y se descarta. En
  Presupuesto o Planos (`max_tokens` 24.000) eso son **USD 0,36 tirados por reintento**; en un
  ítem normal (16.000), USD 0,24. Tres o cuatro reintentos explican solo eso el salto. Se ve
  buscando en el log: `respuesta vacía por max_tokens — reintentando con más cupo`. Si un ítem lo
  hace SIEMPRE, la solución es subirle su entrada en `MAX_TOKENS_POR_ITEM` (arrancar en el cupo
  del reintento sale más barato que pagar dos intentos).
- **Caché reescrita en vez de leída** — el `SYSTEM_PROMPT` son 14.318 tokens: leerlo cuesta USD
  0,0043 y escribirlo USD 0,086, o sea **USD 0,082 de diferencia por ítem**. Si pasan más de 1 h
  entre un ítem y el siguiente, la caché expira y se reescribe: con los 19 ítems fallando son
  **+USD 1,55 en el proyecto**. Se ve en el log como `cache_creado` alto de forma repetida con
  `cache_leido` en 0. Es la palanca más grande que NO requiere tocar código: revisar de corrido
  (o con el botón de tanda) en vez de espaciado.

**Evaluado y NO cambiado (con el motivo, para no volver a revisarlo desde cero):**
- **El caché de prompt está bien montado, no había el bug que sospeché.** Se verificó contra la
  referencia oficial de la API: el prompt caching es **GA** y el `ttl: "1h"` NO requiere ningún
  header beta, así que el `anthropic-beta: prompt-caching-2024-07-31` que manda la app es un
  vestigio inofensivo (se dejó: quitarlo no gana nada medible y un error ahí se pagaría en costo
  real). El mínimo cacheable para Sonnet 5 es **1024 tokens** y el `SYSTEM_PROMPT` son ~14.300
  (57.275 caracteres), así que los 3 breakpoints de `_analizar_grupo` sí pegan — el mínimo aplica
  al prefijo ACUMULADO, no a cada bloque suelto.
- **Cachear el bloque de reglas de `revisar_invalidacion_cruzada`: descartado por medición.** Se
  midió su parte estática (las REGLAS ESTRICTAS + ejemplos negativos, idénticas en las ~18
  llamadas por proyecto): **745 tokens**, bajo el mínimo de 1024 — un breakpoint ahí NO se
  cachearía, y la API no avisa, simplemente `cache_creation_input_tokens: 0`. **Regla para el
  futuro: medir el bloque antes de agregar un `cache_control`; bajo 1024 tokens no hace nada.**
- **Cachear el bloque de reglas — revisar de nuevo SI se agregan más reglas fijas.** Los 745
  tokens son de la parte estática actual (TAREA + las 4 REGLAS ESTRICTAS + los 2 ejemplos
  negativos). Si a futuro se suma más texto fijo a ese mismo prompt (una regla 5 con su ejemplo,
  etc.) y el bloque cruza los 1024 tokens, ahí sí conviene cachearlo — medirlo de nuevo antes de
  decidir, no asumir que sigue quedando corto.
- **Envolver las ~127 llamadas `db.*` restantes en `to_thread`:** sigue descartado por el mismo
  motivo de la 2ª auditoría (no acelera la latencia de la propia acción del revisor), pero con el
  `_pg_lock` de arriba ya no está el impedimento técnico si alguna vez se quiere hacer.
- **Migraciones de startup** (`migrar_proyectos`, `migrar_textos_documentos`,
  `migrar_criterios_enfasis`): las 3 tienen guarda idempotente (marcador o blob vacío) y cuestan
  una query trivial por arranque. Se dejan — quitarlas arriesgaría el entorno JSON local del Mac
  si no hubiera arrancado desde jul-2026.

---

## Auditoría general (jul-2026) — hallazgos y correcciones

Revisión completa del código a pedido del usuario, buscando fallas, conflictos, código muerto y
cualquier cosa que amenace el funcionamiento o gaste de más. Lo aplicado:

**1. Regresión propia corregida — 2 tipos de documento quedaron INVISIBLES para la IA.** Al
excluir tipos del pool de Coherencia Global (ver esa entrada más arriba) se incluyeron
`antecedentes_legales` y `lista_beneficiarios` con la justificación de que "ya se revisan a fondo
en su propio ítem SEP" — **falso**: ninguno de los dos tiene ítem propio en `ITEMS_SEP`.
Coherencia era el ÚNICO lugar donde se leían, así que quedaron sin analizarse en ninguna parte de
la app. Agravante: el checklist de Coherencia depende de los antecedentes legales para verificar
que el caudal de diseño no exceda el derecho de agua y que la superficie respete el título de
dominio — justo el documento que se estaba excluyendo. Corregido: `TIPOS_EXCLUIDOS_COHERENCIA`
quedó solo con los 3 que sí tienen ítem propio (`cotizaciones_facturas`, `cotizaciones`,
`declaracion_iva`). **Blindaje para que no se repita:** al lado de la constante hay ahora una red
de seguridad que compara la lista contra la cobertura real de `ITEMS_SEP` y, si alguien agrega un
tipo sin ítem propio, lo reincorpora a Coherencia automáticamente avisando en el log, en vez de
dejarlo invisible en silencio.
- **Regla para el futuro:** antes de excluir un tipo de Coherencia, verificar que exista un ítem
  en `ITEMS_SEP` cuyo `tipo_docs` lo incluya. Hoy quedan 4 tipos sin ítem propio que dependen
  únicamente de Coherencia: `antecedentes_legales`, `lista_beneficiarios`, `evaluacion_social` y
  `otro` (los dos últimos nunca se excluyeron). Si alguna vez se quiere revisar Evaluación Social
  MIDESO a fondo, necesitaría su propio ítem — hoy solo la ve Coherencia.

**2. La app quedaba caída hasta reiniciarla si Postgres cortaba la conexión.** `_get_pg()`
reconectaba solo si `conn.closed`, pero psycopg2 marca eso únicamente cuando el CLIENTE cierra la
conexión — no cuando el servidor la corta por su cuenta (reinicio de Postgres en Railway, timeout
de inactividad, corte de red). En ese caso `_get_pg()` devolvía una conexión muerta y el error
recién saltaba al ejecutar la consulta, sin que nadie lo atrapara: **error 500 en todas las
páginas hasta reiniciar el proceso**. Corregido con el decorador `_reintenta_si_cae` (database.py)
aplicado a las 11 funciones que tocan Postgres: ante `OperationalError`/`InterfaceError` cierra la
conexión muerta, reconecta y reintenta una vez. El reintento es seguro porque todas las escrituras
del módulo son idempotentes (UPSERT `ON CONFLICT DO UPDATE`, o DELETE). Verificado simulando una
conexión que el servidor cortó (`closed == 0` pero la consulta falla): se recupera sola.

**3. Bug latente — el dashboard entero caía con 500 por un solo proyecto sin `fecha_creacion`.**
`get_proyectos_ligero` ordena por ese campo, pero la proyección de Postgres
(`jsonb_build_object`) devuelve los campos ausentes como **null, no ausentes** — así que
`.get("fecha_creacion", "")` daba `None` y `sorted()` reventaba mezclando `None` con `str`.
Corregido con `or ""` ahí y en la numeración por antigüedad del dashboard. **Esta diferencia
(null vs. ausente) es la trampa principal de las proyecciones** — cualquier lectura de un campo
proyectado debe usar `or {}` / `or ""`, nunca el default de `.get()`.

**4. Polling del análisis: traía el proyecto COMPLETO cada 4 segundos.** `estado_item` (el
endpoint que consulta la página mientras corre un análisis en segundo plano) usaba
`db.get_proyecto()`, cargando y deserializando todas las observaciones del proyecto en cada
vuelta solo para leer 3 campos de estado. Se agregó `db.get_proyecto_campos(proyecto_id, campos)`
(+ `_pg_load_campos`, con coincidencia EXACTA de clave, no `LIKE` con prefijo) y el endpoint
ahora pide solo `items_en_progreso`/`items_error`/`items_revisados`. Verificados los 5 casos
(sin campos, en progreso, error, listo con invalidadas, inexistente) en modo JSON y el SQL
generado en el camino PostgreSQL.

**5. Código muerto eliminado** (todo del flujo viejo de análisis documento-por-documento, ya
marcado como obsoleto en este documento): `seleccionar_modelo`, `DOCS_COMPLEJOS`,
`DOCS_FORZAR_HAIKU`, `DOCS_FORZAR_VISION`, `MAX_TOKENS_HAIKU`, `MAX_PAGINAS_ESCANEADO`,
`MAX_CHARS_POR_TIPO`, `MAX_CHARS_COMPLEJO_DEFAULT`, `MAX_CHARS_SIMPLE` (analyzer.py) y
`require_user` (main.py, además usaba `HTTPException(302)`, un patrón que no corresponde). Se
conservó `MAX_PAGINAS_POR_TIPO`, que SÍ sigue en uso (tope de páginas por documento en visión).
También se quitaron 3 imports sin uso en main.py (`timedelta`, `Depends`, `HTTPBearer`).

**6. Endpoint `/debug-env` eliminado (seguridad).** Estaba rotulado "Debug temporal" y era un
workaround de un problema de Railway V2 ya superado. Aunque exigía rol admin, devolvía los
**primeros 10 caracteres de `ANTHROPIC_API_KEY`** más la lista completa de nombres de variables
de entorno del contenedor — no hay razón para exponer eso desde la app. Se eliminó junto con su
helper `_leer_env_proc1()`.

---

## Normativa destilada — los 5 documentos grandes reescritos como criterios (jul-2026)

**El problema:** los 5 archivos más grandes de `normativa/` (DT-02, DT-06, DT-18, DT-24,
Manual_Supervision, todos de 51-72 KB) se cargaban truncados a los primeros 4.000 caracteres
(`MAX_CHARS_POR_NORMATIVA`) — apenas el 5-7 % de cada uno, y en 4 de los 5 esos primeros
caracteres eran **portada, índice con números de página o encabezado legal**. Eran ~20.000
caracteres viajando en el `SYSTEM_PROMPT` de CADA llamada sin aportar criterio.

**La solución (misma que ya usaban ITT-01 a 04 e `Invernaderos_Criterios`):** destilarlos a
extractos de CRITERIOS que caben completos, en vez de volcar el documento y truncarlo. Proceso:
propuesta en Artifact + archivo descargable → el usuario revisó y corrigió → recién ahí se
instalaron (mismo flujo que los checklists de los 18 ítems).

- **`normativa/fuentes/`** (nueva): las 5 fuentes originales sin destilar viven ahí, versionadas
  en el repo para poder re-destilarlas, pero **no se cargan** — `cargar_normativa()` usa
  `glob("*.txt")`, que NO es recursivo. Si se agregan fuentes nuevas, van a esa subcarpeta.
- **`MAX_CHARS_POR_NORMATIVA` subido de 4.000 a 5.000**: los destilados necesitan algo más de
  espacio para entrar enteros (el mayor, DT-06, quedó en 4.991). Solo alcanza a estos archivos —
  los otros 12 ya estaban bajo 4.000. **Regla: todo archivo de `normativa/` debe caber bajo el
  tope; si se pasa, se corta en silencio.** Verificar el tamaño al editar cualquiera.
- **DT-24 se dividió en dos** (`DT-24a_Balance_Hidrico`, y el de evaluación social que NO se
  instaló, ver abajo) — son dominios distintos que alimentan ítems distintos, mismo criterio con
  que los ITT están separados por tema.
- **Evaluación Social MIDESO: deliberadamente NO se instaló.** El usuario decidió excluirla —
  esos proyectos son obras más grandes que no se revisan en esta app. El extracto está hecho y
  quedó en el historial de la conversación; si algún día se necesita, se reinstala y ahí sí
  convendría darle ítem propio (hoy `evaluacion_social` no tiene ítem, solo lo ve Coherencia).
- **Manual de Supervisión — recorte fuerte a pedido del usuario** (4.518 → 3.288): regula la
  supervisión POSTERIOR a la adjudicación, que no es objeto de esta app. Quedaron solo 4 puntos
  verificables sobre el expediente al postular (plazos de construcción para el cronograma, regla
  de ITO según tamaño para el presupuesto, detalle exigible a las EETT para que los equipos sean
  acreditables después, e inicio anticipado de obras). El encabezado del extracto le dice
  explícitamente a la IA que NO observe nada de ejecución de obra. **Criterio general: nada de
  etapa de construcción entra a esta app.**
- **Hallazgo de la 2ª ronda:** el usuario notó que los extractos estaban "muy acotados" y tenía
  razón — en la 1ª versión solo se había mineado la sección 3 del DT-24 (evaluación social),
  saltándose toda la sección 2, que trae lo más aprovechable de los 5 documentos: la cadena
  completa de cálculo de la demanda hídrica y la tabla oficial de eficiencias. **Lección: al
  destilar un documento largo, recorrer su índice completo antes de decidir qué entra — no
  quedarse con la primera sección que parezca relevante.**
- **Costo:** 47.724 → 51.201 caracteres (~+870 tokens por llamada, ~USD 0,10/mes con el volumen
  actual, al ir en el bloque cacheado). Sube, a diferencia de lo estimado en la 1ª versión, y es
  un cambio favorable: entra criterio aplicable donde antes había índices.
- **DT-02 y DT-18 no crecieron a propósito:** el 95 % de ambos son tablas de consulta (caudales
  por estación, precios por partida) que no tiene sentido cargar — de DT-02 caben 3 estaciones de
  cientos, así que la IA nunca encontraría la que busca. Se destiló la metodología: en DT-02, la
  advertencia de que los caudales DGA NO descuentan extracciones aguas arriba; en DT-18, que cada
  partida tiene un RANGO y qué factores justifican moverse dentro de él (distancia al centro de
  abastecimiento, acceso, altura, zona extrema). **En DT-18 se decidió NO incluir precios**: se
  desactualizan y competirían con la tabla de precios referenciales de `/admin/precios`, que es
  la que la app usa para el contraste partida por partida.

**Verificación de la EFICIENCIA DE APLICACIÓN contra valores oficiales (implementado junto con
lo anterior):** salió de la Tabla 4 del DT-24 (Tendido 30 · Surcos 45 · Bordes 60 · Aspersión 75
· Cinta 90 · Goteo 90 %), que el usuario confirmó como "oficial y lo que debe considerar el
consultor para diseñar". Mismo mecanismo que la verificación de Kc contra DT-05:
- `EFICIENCIA_OFICIAL_POR_SISTEMA` + `_rango_eficiencia_oficial()` (analyzer.py) — se expresa
  como RANGO cruzando DT-24 (valor puntual) con DT-04 (rangos: aspersión 70-75, goteo/micro
  85-90), para no observar por un punto porcentual de diferencia.
- **Carrete queda deliberadamente FUERA**: ni DT-24 ni DT-04 le fijan eficiencia propia, y
  asignarle la de aspersión sería inventar — mismo criterio que `_buscar_rango_kc`, que devuelve
  None antes que adivinar. Mixto y "sin declarar" tampoco se validan.
- Asimetría a propósito en el mensaje: una eficiencia **sobre** la oficial reduce la demanda
  calculada (`TR = DHN / Ef`) y por lo tanto **infla la superficie que el proyecto dice poder
  regar** — ese es el error con consecuencia, y se instruye a observarlo. Una **bajo** el rango
  es conservadora: solo se advierte que puede ser un error o la eficiencia del método ACTUAL en
  vez del proyectado.
- Wiring: bloque en `_bloque_verificacion_agronomica_sistema` (independiente del resto de la
  cadena, solo necesita `sistema_riego` + `eficiencia_pct`), `_eficiencia_oficial_calculo()` en
  main.py para el preview, y fila nueva "Eficiencia vs. valor oficial (DT-24 / DT-04)" en
  `calculos.html`. **La tabla está duplicada en el `<script>` (`EF_OFICIAL`)** — misma regla de
  siempre: si se corrige en analyzer.py, replicar a mano en el template. Verificado con paridad
  automática (el test lee la tabla JS del propio template y la compara con la de Python) más 11
  casos de contraste.

---

## Mi cuenta — cambiar nombre (implementado, jul-2026)

El usuario notó que su perfil mostraba "Administrador CNR" (nombre por defecto del usuario admin
creado al iniciar la app) y preguntó si se podía cambiar el nombre — solo existía cambio de
contraseña. Se agregó `POST /mi-cuenta/nombre` (además del `GET/POST /mi-cuenta` ya existentes) —
mismo patrón que el cambio de contraseña, ambos en la misma página/tarjeta, cada uno con su
propio formulario y sus propias variables de error/ok (`ok_nombre`/`error_nombre` vs.
`ok_pass`/`error_pass` — antes el cambio de contraseña usaba las genéricas `ok`/`error`, se
renombraron para no colisionar entre los dos formularios de la misma página).
- `db.update_nombre(username, nuevo_nombre)` (database.py, mismo patrón que `update_password`).
- **El nombre viaja en el JWT de la sesión** (`create_token({"username", "nombre", "rol"})`,
  fijado al hacer login, 8 h de expiración) — sin reemitir la cookie, el cambio no se habría
  reflejado en la app (barra de navegación, "Mi cuenta", y cualquier registro nuevo que guarde
  `user["nombre"]` — ej. `validado_por` de Chequeo de Cálculos, `agregada_por` de una observación
  manual) hasta el próximo login. `cambiar_nombre()` reemite la cookie con el mismo patrón que
  `login()` (mismo `max_age=28800`) apenas guarda el cambio, y arma el `user` del contexto de
  render con el nombre ya actualizado — así la propia página, sin recargar, ya muestra el nombre
  nuevo en el campo y en la barra de navegación.
- **Registros ya guardados con el nombre anterior NO se migran** (mismo criterio que el resto de
  la app con cambios de nombre/etiqueta — ver por ejemplo el estado "Revisado" retirado sin
  migrar proyectos viejos) — es un registro histórico de quién hizo qué en su momento, no algo
  que deba reescribirse retroactivamente.
- **De paso, mismo bug de bcrypt bloqueante ya corregido en `login()` pero no en
  `cambiar_password()`:** `verify_password(...)` (bcrypt, deliberadamente lento, ~100-300 ms) se
  llamaba sincrónico dentro de la ruta `async def cambiar_password()`, bloqueando el event loop
  entero — mismo patrón de bug ya documentado y arreglado en `login()` (ver "Auditoría de
  rendimiento — 2ª ronda", punto 3) pero que no se había replicado acá. Corregido al tocar esta
  función: `await asyncio.to_thread(verify_password, ...)`.
- Verificado con pruebas funcionales sobre las rutas reales (`main.cambiar_nombre`, sin mocks de
  HTTP): actualiza la base, reemite la cookie con el nombre nuevo (confirmado decodificando el
  JWT resultante), el contexto de render ya trae el nombre actualizado, y un nombre vacío se
  rechaza sin tocar la base. Render completo de `mi_cuenta.html` (Jinja + captura de pantalla)
  confirmando los dos formularios uno debajo del otro, sin solaparse.

---

## Diseñador de Riego v114 + Fotovoltaico + Revisor Fotovoltaico (implementado, ago-2026)

Sesión larga en torno a fotovoltaico, con tres apps involucradas: **Diseñador de Riego** (la app
hermana donde el consultor diseña, `static/disenador_riego_v114.html`), **Revisor Fotovoltaico**
(app hermana nueva para chequear el dimensionamiento FV con otra metodología,
`static/fotovoltaico_riego_v9.html`) y Revisor CNR (esta app).

**1. Diseñador v112→v114 + Balance Anual FV (Manual CNR-Ministerio de Energía §5.1):**
- `calculos_riego.dimensionamiento_fv()` ganó `dias_riego`/`conexion`: Gen_anual = E_panel ×
  N_real × 365, Consumo_anual = P_bomba × H_bombeo × días_riego, Balance = Gen/Consumo × 100 %.
  `balance_ok` solo aplica si `conexion == "ongrid"` (Ley de Generación Distribuida); aislado no
  tiene el criterio de ≤100 %.
- `disenador_riego_v114.html`: `importProject()` ahora acepta también un ARRAY JSON (antes solo
  un objeto) — necesario para importar los 1-2 sistemas de un proyecto de una sola vez.
- Nuevo endpoint `GET /calculos/exportar-disenador` (sin `idx`) que exporta TODOS los sistemas
  del proyecto en un solo archivo (objeto si hay 1, array si hay 2) — reemplazó los botones de
  exportación individuales por sistema en `calculos.html` (ahora un solo botón arriba, junto a
  "Abrir Diseñador de Riego" y "Memoria de cálculo completa", los tres en la misma línea).

**2. Editor de tramos hidráulicos — agregar/eliminar filas:**
El usuario reportó que la IA a veces clasifica mal los tramos (mezcla goteo/aspersión). Se agregó
un botón "× eliminar" bajo el nombre de cada tramo con datos (vacía los inputs + oculta la fila,
`window.eliminarTramo` — **debe colgar de `window`**, el HTML usa `onclick` inline y el resto del
JS de la página vive en un IIFE `(function(){"use strict";...})()`, así que una función declarada
ahí NO es visible al scope global que `onclick` resuelve) y un botón "+ Agregar tramo" que revela
el siguiente slot oculto (máx. `N_TRAMOS_HIDRAULICOS = 6`, main.py). `initTramos(sp)` oculta al
cargar las filas sin nombre/Q/Ø — el backend (`calculos_guardar_hidraulico`) ya ignoraba esas
filas vacías desde antes, el cambio fue solo de UI.
- De paso, ajustes visuales pedidos: columna "Tramo" 200→180px, "V/Hf declarada" abreviadas a "V
  Dec."/"Hf Dec." con la unidad en una 2ª línea del header (55→72px, hasta 3 decimales), columna
  "Longitud" con "m" en 2ª línea. Los headers de `.calc-tbl` heredaban `text-transform:uppercase`
  del CSS global (`base.html th`) — se anuló con `text-transform:none` en `.calc-tbl th`, que
  también se puso en negrita y centrado.

**3. Revisor Fotovoltaico (`fotovoltaico_riego_v9.html`) — integración:**
App hermana independiente con OTRA metodología: usa el perfil solar HORARIO del predio
(importado desde el Explorador Solar CNR, `solar.minenergia.cl`) para calcular potencia
requerida, generación, cobertura anual y banco de baterías — cálculos que Revisor CNR NO puede
replicar porque esa matriz horaria vive solo dentro del Revisor Fotovoltaico. Se agregaron 3
botones en la sección FV de `calculos.html` (misma línea que "Extraer de los documentos"):
"Revisor Fotovoltaico" (abre la app), "Exportar al Revisor FV (.json)", "Explorador Solar".
- Formato de export: `{"formato": "riego-cnr-proyecto", "version": 1, "bombeo": {...},
  "fotovoltaico": {...}}` — mapeo de campos confirmado leyendo `construirProyectoJSON()` /
  `aplicarProyectoJSON()` del HTML fuente del Revisor FV, NO adivinado.
- **Bug corregido antes de pushear a producción:** el primer intento exportaba
  `fv_calc.n_paneles_real`/`kwp_total` — los valores CALCULADOS por Revisor CNR — sobrescribiendo
  el criterio del consultor. El usuario lo pescó de inmediato ("son los datos que ha declarado el
  consultor, no los que calcula la app"). Corregido: exporta `fv.declarado.n_paneles`/
  `kwp_total`/`banco_baterias_kwh` (los mismos campos que ya se usan para la comparación
  "declarado vs. calculado" del propio Chequeo de Cálculos).
- Campos nuevos capturados para alimentar el export, ninguno existía antes: **horas de riego
  mensuales** (12 inputs Ene-Dic en `calculos.html`, `fv.horas_mensuales`), **consumos
  adicionales %** (`fv.adic`), **banco de baterías declarado**
  (`fv.declarado.banco_baterias_kwh`), y tercera opción de conexión "Aislado con baterías"
  (`conexion == "aislado_bat"`, mapea a `offgridbat` del Revisor FV; el criterio de balance
  ≤100 % del punto 1 sigue aplicando solo a `ongrid`).
- Nuevo chequeo liviano en `calculos.html`/informe: consistencia interna de lo declarado (N°
  paneles × Wp panel vs. kWp total declarado) — mismo chequeo que hace el propio Revisor
  Fotovoltaico con sus datos, sin pedir ningún dato nuevo (reutiliza `decl_npaneles`/`wp`/
  `decl_kwp`, ya existentes).

**4. Memoria de Cálculo Completa — sección FV.4 (demanda mensual):**
`calculos_riego.demanda_fv_mensual(pkw, adic, horas_mensuales)` replica la fórmula de demanda del
Revisor Fotovoltaico: `Dem_día[mes] = Horas[mes] × P_bomba × (1+Adic%)`, `Dem_mes = Dem_día ×
Días_mes` (`DIAS_MES_FV`, constante copiada tal cual del Revisor FV, incluye feb=29 fijo),
`Dem_anual = Σ Dem_mes`. **Es la única parte de la metodología del Revisor FV que se puede
recalcular acá** — generación/cobertura/potencia requerida necesitan el perfil solar horario, que
no existe en Revisor CNR; el informe lo deja explícito y remite al botón "Revisor Fotovoltaico".
- **Bug encontrado por el usuario tras el primer despliegue:** la nueva sección FV.3 (declarado
  vs. calculado) había quedado anidada dentro del `{% if fv_calc %}` de FV.2, que exige los 6
  campos base del dimensionamiento completos (potencia bomba, horas bombeo, HSP, Wp, Vmp, Imp).
  Si faltaba uno, `fv_calc` quedaba vacío y FV.3 entera desaparecía — incluida la consistencia
  interna y el banco de baterías, que NO necesitan ese recálculo. El usuario preguntó si tenía que
  ver con el botón "Comparar con metodología del consultor" (no tenía relación — ese alimenta
  `mc_fv`, las cajas de comparación 2 columnas de FV.2). Corregido: FV.3 ahora es independiente de
  `fv_calc` (se mueve el `{% endif %}` de FV.2 antes de FV.3); las 3 filas que sí comparan contra
  el cálculo de la app quedan en un `{% if fv_calc %}` interno con una nota si falta, en vez de
  hacer desaparecer toda la sección.
- Verificado con render Jinja standalone (no solo `ast.parse`) en ambos escenarios — datos
  completos y datos declarados sin los 6 campos base — antes de pushear.

**5. Bug de extracción encontrado por el usuario — presupuesto de texto a medias:**
El usuario reportó que HSP, voltaje de sistema, horas de bombeo y sección de cable no se
extraían pese a estar en los documentos del ítem Diseño Fotovoltaico. Causa real, no adivinada:
`_extraer_datos_fv()` (el botón "Extraer de los documentos" del Chequeo de Cálculos) llamaba a
`_texto_grupo_para_extraccion()` **sin** `max_chars`, cayendo al default de 60.000 caracteres —
mientras que la revisión del ítem "Diseño Fotovoltaico" (mismo grupo de documentos) usa 120.000
vía `MAX_CHARS_POR_ITEM`. Con un Excel + memoria de cálculo típicos del ítem, el texto supera 60K
fácil y se trunca (75% inicio + 25% final) — datos de mitad de documento quedaban fuera. Corregido
para usar el mismo presupuesto de 120K. De paso se agregaron sinónimos al prompt para `vsis`
("voltaje bus DC" / "arreglo FV" / "entrada inversor") y sección de cable declarada ("calibre",
"conductor DC", puede estar en la lista de materiales del presupuesto eléctrico en vez de la
memoria de cálculo). **Pendiente de confirmar por el usuario en un proyecto real** (ver Estado
actual en CLAUDE.md).

También se agregó `horas_mensuales` al prompt de extracción (antes ni existía el campo en el
schema — no era que la IA "no detectara" el dato en el Excel, es que no tenía dónde reportarlo).

---

## Fix comparación FV + intento fallido de "Horas de riego mensual (Kc)" (ago-2026)

**1. Bug real: comparación FV con metodología del consultor siempre vacía.**
El usuario reportó que en FV.2 de la Memoria de Cálculo Completa, el botón "Comparar con
metodología del consultor" no mostraba las cajas de 2 columnas (App/Consultor) como en el resto
de las secciones. Causa encontrada por inspección directa del código, no adivinada:
`extraer_metodologia_completa_route()` (main.py) llamaba a
`_documentos_para_verificacion("diseno_fotovoltaico", documentos_con_texto)` — pero
`DOCS_VERIFICACION` (analyzer.py) solo tiene las claves `"hidraulico"`/`"agronomico"`/
`"energetico"`, NO `"diseno_fotovoltaico"`. `.get(grupo_key, [])` devolvía silenciosamente una
lista vacía, así que `extraer_metodologia_fv()` nunca recibía texto y siempre retornaba `{}` —
`mc_fv` quedaba `None` y `paso_mc()` caía siempre en la rama de una sola columna. Corregido a
`"energetico"` (la misma clave que usa el resto del chequeo FV, `calculos_extraer_fv`).
Después de probar el fix, el usuario reportó 8 de 9 ítems sin información — evaluado como
comportamiento esperado del prompt (deliberadamente estricto: "NUNCA reconstruyas ni inventes
una fórmula que el consultor no escribió"), no un bug nuevo. Queda como decisión pendiente del
usuario (ver Estado actual en CLAUDE.md): verificar contra el expediente real, o relajar el
criterio.

**2. "Horas de riego mensual (Kc)" — implementado, y luego revertido por completo.**
El usuario pidió una página secundaria para corroborar "Horas de riego promedio/día por mes"
(campo `fv.horas_mensuales` de la sesión anterior) reconstruyendo la demanda vía Kc mensual por
cultivo, con instrucción explícita de NO pushear hasta su aprobación ("con mi VB despliega, no
antes" — la única vez en el proyecto que se pidió retener el push; se hizo commit+push solo
después de su confirmación explícita).
- Se extrajo la tabla de Kc mensual (98 cultivos × 12 meses, MIDESO/CNR) del Excel que subió el
  usuario, sin retipeo manual (script Python leyendo el .xlsx directo a dict).
- **Primer diseño (incorrecto):** promediar el Kc de los cultivos ponderado por % de superficie y
  correr una sola cadena `cadena_agronomica()` para la "mezcla". El usuario subió el HTML fuente
  de otra app hermana, **Scall** (`scalldisenoV20.html` — una calculadora de captación de agua
  lluvia, no de riego como se asumió inicialmente), pidiendo revisar su pestaña "Demanda" para
  ver "formato y tipo de combinación" de cultivos — sin decir que había un error, solo pidiendo
  comparar metodologías antes de decidir el push.
- **Hallazgo al leer Scall:** su `calcDem()` NO promedia Kc entre cultivos — calcula la demanda de
  CADA cultivo por separado (con su Kc propio) y **suma los volúmenes** resultantes, cada uno
  multiplicado por SU PROPIA superficie (`S.dem[i] += bruta*c.sup`). Promediar Kc antes de
  calcular distorsiona el resultado cuando los cultivos tienen curvas muy distintas. Se rediseñó
  siguiendo ese criterio: demanda bruta diaria por cultivo (ETc/Ef, sin necesitar AD/Dn/Fr — el
  promedio diario da igual con o sin frecuencia de riego) × superficie propia → volumen → suma →
  horas, usando el CAUDAL DE BOMBEO declarado en Hidráulico (no el caudal de la fuente ni la
  pluviometría del emisor) para convertir volumen a horas.
- Verificado con render Jinja + `node --check` del JS extraído + un caso numérico realista
  (Python, con la tabla Kc real) antes de pedir el visto bueno — todo dio resultados sanos.
- **El usuario aprobó y se pusheó** ("Vamos con el Commit+push"). Inmediatamente después cayó en
  la cuenta de que todo el pedido era para la app de **Revisión Fotovoltaico** (`fotovoltaico_
  riego_v9.html`), no para Revisor CNR — el chequeo FV de esta app trabaja con un solo valor
  diario promedio, no con un motor agronómico multi-cultivo; ese tipo de verificación no
  corresponde acá. **Se revirtió por completo en el commit siguiente**: endpoint
  `/calculos/informe/kc-mensual`, `templates/informe_kc_mensual.html`, el botón en FV.2, y la
  tabla `KC_MENSUAL_MIDESO` de `calculos_riego.py` — sin dejar residuos (verificado con grep).
  Se le entregaron al usuario las instrucciones (metodología + fórmulas + ubicación del botón)
  para pedir la misma funcionalidad en el chat de la app de Revisión Fotovoltaico.
- **Lección:** cuando un pedido de funcionalidad no encaja naturalmente con el chequeo existente
  de la app (acá: pedir un motor agronómico completo dentro del chequeo FV, que normalmente solo
  usa un valor diario), vale la pena confirmar el alcance/la app correcta ANTES de construir,
  no solo después. La instrucción del usuario de retener el push en este caso fue justamente lo
  que evitó que el error llegara a producción.

---

## Revisor Fotovoltaico v15 + Diseñador v119 + capas de suelo + limpieza UI (ago-2026)

**1. Revisor Fotovoltaico actualizado a v15 (`fotovoltaico_riego_v9.html` se mantiene sin
borrar).** El usuario subió el JSON real que había exportado con la v9 vieja y notó que la v15
agrega dos campos nuevos al formato de intercambio: `bombeo.caudalDisenoLs` y
`bombeo.verificacionKc`.
- `caudalDisenoLs`: confirmado por lectura directa del HTML fuente (`aplicarProyectoJSON`/
  `construirProyectoJSON`) que corresponde 1:1 a `agro.declarado.caudal_diseno_ls` — un campo que
  YA existe en el Chequeo Agronómico (comparado ahí contra el caudal de operación calculado, no
  es nuevo). Se agregó a `exportar_para_revisor_fv()` en main.py. **Con 2 sistemas de riego se
  exporta el caudal MAYOR entre ambos** (pedido explícito del usuario en el mismo hilo: "usar
  siempre el Caudal mayor, porque es el que más exige" — la bomba única del proyecto debe cubrir
  el caso más exigente).
- `verificacionKc` (estación DGA + cultivos con trimestre/método/superficie): es el panel de
  verificación de horas de riego por Kc mensual que el Revisor FV agregó siguiendo las
  instrucciones que se le dieron la sesión anterior (ver sección de arriba, "Fix comparación FV +
  intento fallido...") — es estado propio de ESA app (el revisor lo tipea directo ahí), no un
  dato que Revisor CNR extraiga de documentos. Confirmado que NO corresponde exportarlo desde
  acá — coherente con la decisión de la sesión anterior de que ese tipo de verificación
  multi-cultivo es dominio del Revisor Fotovoltaico.

**2. Diseñador de Riego actualizado a v112→v119** (`disenador_riego_v114.html` se mantiene sin
borrar, mismo patrón). Referencias de versión actualizadas en `calculos.html`,
`exportar_disenador.py`, `main.py` (comentarios/docstrings).

**3. Desglose de Humedad Aprovechable por capas de suelo — Aspersión y Carrete.** El usuario pidió
"ver si se puede implementar" una funcionalidad nueva del Diseñador v119: en vez de un CC/PMP/Da/
Prof. radicular uniforme para todo el perfil de suelo, permite declarar varias capas (horizontes)
con su propia textura/CC/PMP/Da, y el AD total sale de sumar el aporte de cada capa. Confirmado
por diff línea a línea entre v114 y v119 que el feature es EXCLUSIVO de Aspersión y Carrete (no
Goteo, que ya no usa AD en absoluto desde antes; no Microaspersión, que no lo recibió).
- `calculos_riego.py`: `SUELO_DEFAULT_POR_TEXTURA` (5 texturas → CC/PMP/Da referenciales, mismos
  valores que la tabla `SDB` del Diseñador) y `ad_por_capas(capas)` — por capa, Altura[mm] =
  (Hasta−Desde)×10, Ha_capa = (CC−PMP)/100×Da×Altura; AD total = Σ Ha_capa. Capas con datos
  incompletos, Hasta≤Desde o CC≤PMP se descartan silenciosamente (mismo criterio del Diseñador:
  nunca calcula con una capa a medio llenar).
- `cadena_agronomica()` gana `ad_mm_override` — si se pasa, reemplaza el cálculo de AD de capa
  única sin tocar el resto de la cadena (Dn=AD×fa, Fr=Dn/ETc, etc., todas iguales).
- `main.py`: `_agronomico_calculo()` detecta `capas_suelo` válidas (solo si `sistema_riego` es
  Aspersión o Carrete) y relaja el requisito de CC/PMP/Da/Prof. radicular — mismo patrón que ya
  existía para Goteo (alta frecuencia). `calculos_guardar_agronomico()` persiste hasta
  `N_CAPAS_SUELO = 6` capas por sistema (mismo tope que `N_TRAMOS_HIDRAULICOS`).
- `calculos.html`: checkbox "Desglose de Humedad Aprovechable por capas de suelo" (mismo texto
  que el Diseñador) que revela filas agregar/eliminar por capa (Desde/Hasta/Textura/CC/PMP/Da),
  con la textura autocompletando CC/PMP/Da — mismo patrón de UI que los tramos hidráulicos
  (`agregarCapa`/`eliminarCapa`/`renderCapas`, con `name` attrs en los inputs generados por JS
  para que viajen con el submit normal del form, sin campos ocultos duplicados). El recálculo en
  vivo (`recalcAgroSistema`) usa `calcAdCapas(p)` para obtener el AD desde las capas cuando el
  checkbox está activo, y solo entonces relaja el `base` (lista de campos obligatorios) para no
  exigir CC/PMP/Da/Prof. Verificado con `node --check` sobre el bloque `<script>` completo y un
  render Jinja end-to-end (checkbox `checked`, caja `display:block`, JSON de hidratación) antes
  de pushear.
- **Nota para revisar en próxima sesión:** implementado y verificado con datos de prueba
  (aritmética + render), pero aún no probado por el usuario con un proyecto real.

**4. Limpieza de UI en `proyecto.html`** (pedido explícito, "son redundantes y no aportan"):
- Los badges "Tipo revisión: Técnica/Legal" y el badge de estado (`{{ proyecto.estado }}`) que
  aparecían antes del widget de costo se eliminaron — el badge de estado duplicaba al botón de
  estado (`● En revisión ▾`) que ya está más a la derecha en la misma fila y además permite
  cambiarlo, así que no se perdió información. Reemplazados por un texto simple "Costo API:".
- La franja verde "Concurso xxx — bases cargadas (N caracteres)" se eliminó (esa info ya está en
  la pestaña de Concurso). Se mantuvo la franja naranja de advertencia cuando el concurso NO
  tiene bases cargadas — esa sí es información accionable (los análisis no podrán verificar
  cumplimiento de bases), no redundante.

**5. Ajuste visual de la fila de capas de suelo (mismo día, follow-up):** el usuario pidió que
cada capa quede en una sola línea sin comprimirse (`flex-wrap:nowrap` + `flex-shrink:0` en cada
campo, `overflow-x:auto` de respaldo en el contenedor), el botón de eliminar solo con el símbolo
"×" (antes "× eliminar"), el `<select>` de textura al ancho de su opción más larga ("Franco-
Arcilloso", 150→165px) y los campos CC/PMP/Da un 33% más angostos (75→50px, 75→50px, 80→53px,
con placeholders acortados a "CC %"/"PMP %"/"Da" para que no se corten).

---

