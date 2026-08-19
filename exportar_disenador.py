"""Exporta los datos del Chequeo de Cálculos al formato de archivo del Diseñador de Riego
(la app hermana del mismo usuario, `disenador_riego_v123.html`), para poder abrirlo ahí y seguir
evaluando aspectos que no cubre Revisor CNR — sin recargar Revisor con esos cálculos.

REGLA: solo se exportan los datos que Revisor efectivamente tiene (extraídos/validados en el
Chequeo de Cálculos + el Resumen). NUNCA se inventan valores: las claves sin dato simplemente NO
se incluyen, así el Diseñador conserva sus propios valores por defecto al cargar el archivo.

El Diseñador guarda un JSON por SISTEMA de riego, con un prefijo de campo distinto según el
sistema (g-/m-/a-/c-) y un código `__sys` (got/mic/asp/car). Los campos que mapean 1:1 (mismo
significado, mismo dato) son los que porté a `calculos_riego.py` en su momento, más los del
Resumen y el dimensionamiento fotovoltaico. La red hidráulica detallada por tramos tiene DOS
formatos según el sistema, confirmados leyendo el HTML fuente del Diseñador v108 (no adivinados):
- Aspersión y Carrete: lista GENÉRICA `__tramos` (l/q), misma tabla dinámica en ambos (`#a-trs`/
  `#c-trs`) — ver `_SYS_CON_TRAMOS`.
- Goteo y Microaspersión: modelo FIJO de 3 niveles — Matriz → Terciaria → Lateral, cada uno con
  Longitud [m] + Diámetro interior [mm] + Material (C de Hazen-Williams) — ver
  `_ALIAS_TRAMO_JERARQUICO`/`_clasificar_tramos_jerarquico`. Se identifica CUÁL de los tramos de
  Revisor es cada nivel por el campo `nombre` (texto libre, editable por el revisor) — nunca por
  posición ni por diámetro. Si el nombre no calza con ningún alias, ese nivel simplemente no se
  exporta — el revisor corrige el campo `nombre` si quiere que se reconozca, o completa el dato a
  mano en el Diseñador. Matriz/Terciaria además exigen que el alias calce con un ÚNICO tramo (dos
  o más es ambiguo → no se exporta); Lateral es la excepción porque es normal declarar varios
  (uno por sector) — con 2+ laterales se exporta el "lateral crítico" (mayor `longitud_m`).

El Desglose de Humedad Aprovechable por capas de suelo (checkbox "reemplaza CC/PMP/Da", solo
Aspersión/Carrete — desde v120 es la ÚNICA vía de entrada de esos datos ahí, ver más abajo) se
exporta como `__capasA`/`__capasC` — mismo formato que usa el propio Diseñador para guardar/
exportar sus proyectos, confirmado contra un archivo real exportado desde el Diseñador v121 (no
adivinado). El truncamiento de cada capa a la profundidad radicular (`{p}-pr`) lo hace el propio
Diseñador al recalcular — acá se exportan las capas tal cual las declaró el consultor.

DATOS QUE REVISOR TIENE PERO NO SE EXPORTAN, y por qué (para no volver a intentarlo cada vez):
- `caudal_emisor_lhr` (Goteo/Microaspersión): el Diseñador NO tiene un campo numérico para el
  caudal del gotero — lo saca del emisor elegido en su propio catálogo (`g-tipe`/`m-tipe`, select
  con botón "⚙ Gestionar"). Escribirlo exigiría inventar una entrada de catálogo.
- `eto_dia_mm`: el campo del Diseñador es "ETo Mes Crítico [mm/MES]" (`-etom`) y el de Revisor es
  del día crítico [mm/día]. Convertir exige asumir los días del mes, que Revisor no sabe.
- `amt_declarada_m` / `caudal_bombeo_ls`: los campos `-bomb-h`/`-bomb-q` del Diseñador son
  "H Nominal"/"Q Nominal" — la placa de la bomba elegida, no la AMT que exige el diseño."""
import unicodedata

import calculos_riego

# Sistema de riego declarado en Revisor → (prefijo de campo, código __sys del Diseñador).
SISTEMA_A_DR = {
    "Goteo": ("g", "got"),
    "Microaspersión": ("m", "mic"),
    "Aspersión": ("a", "asp"),
    "Carrete": ("c", "car"),
}

# Sistemas que usan la lista genérica de tramos de impulsión `__tramos` (l/q). Goteo y
# Microaspersión NO — su red se describe con el modelo jerárquico Matriz/Terciaria/Lateral,
# ver `_clasificar_tramos_jerarquico`.
_SYS_CON_TRAMOS = {"asp", "car"}

# Alias por los que se reconoce el `nombre` de un tramo como uno de los 3 niveles fijos que
# usa el Diseñador para Goteo/Microaspersión. Coincidencia por SUBSTRING (no exacta) sobre el
# nombre normalizado, para tolerar variantes razonables como "Tubería matriz" o "Línea
# terciaria PVC" — deliberadamente conservador: si el nombre no menciona ninguno de estos
# términos, no se clasifica (mejor no exportar que adivinar mal).
_ALIAS_TRAMO_JERARQUICO = {
    "matriz": {"matriz", "principal"},
    "terciaria": {"terciaria", "secundaria", "submatriz"},
    "lateral": {"lateral", "portagotero", "portaemisor", "regante"},
}

# Sufijos de campo por nivel (longitud, diámetro, material/C) — confirmados en el HTML del
# Diseñador: Goteo y Microaspersión usan EXACTAMENTE los mismos sufijos para los 3 niveles.
_SUFIJOS_NIVEL_HIDRAULICO = {
    "matriz": ("lm", "dm", "cm"),
    "terciaria": ("lt", "dt", "ct"),
    "lateral": ("ll", "dl", "cl"),
}


def _s(v):
    """Valor a string tal como lo espera el Diseñador (todos sus campos son strings), o None si
    no hay dato (para omitir la clave). Un float entero se emite sin decimales (60.0 → "60")."""
    if v is None or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _normalizar_nombre_tramo(nombre: str) -> str:
    """minúsculas, sin tildes, para comparar contra los alias de `_ALIAS_TRAMO_JERARQUICO`."""
    n = unicodedata.normalize("NFKD", (nombre or "").strip().lower())
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


def _clasificar_tramos_jerarquico(tramos: list) -> dict:
    """Devuelve {"matriz": tramo|None, "terciaria": tramo|None, "lateral": tramo|None} según el
    campo `nombre` de cada tramo de `tramos` (la tabla de tramos hidráulicos de Revisor).

    Matriz y Terciaria: un nivel queda en None (no se exporta) si NINGÚN tramo calza con sus
    alias, o si calzan DOS O MÁS — la clasificación nunca adivina entre varios candidatos.

    Lateral: es el único nivel donde es normal y esperable declarar VARIOS tramos (uno por
    sector/hilera), a diferencia de Matriz/Terciaria que son troncales únicos. Con 2+ candidatos
    a "lateral" se exporta el "lateral crítico" — el de mayor `longitud_m` (criterio del usuario:
    a mayor longitud, mayor pérdida de carga, así que es el más exigente para el dimensionamiento
    del Diseñador). Si ninguno de los candidatos múltiples tiene longitud declarada, no se puede
    determinar cuál es el crítico y el nivel queda en None (mismo criterio de no adivinar)."""
    candidatos = {"matriz": [], "terciaria": [], "lateral": []}
    for t in (tramos or []):
        nombre_norm = _normalizar_nombre_tramo(t.get("nombre"))
        if not nombre_norm:
            continue
        for nivel, alias in _ALIAS_TRAMO_JERARQUICO.items():
            if any(a in nombre_norm for a in alias):
                candidatos[nivel].append(t)
                break   # un tramo se clasifica en un solo nivel (el primero que calce)

    resultado = {
        nivel: (lista[0] if len(lista) == 1 else None)
        for nivel, lista in candidatos.items() if nivel != "lateral"
    }
    laterales = candidatos["lateral"]
    if len(laterales) == 1:
        resultado["lateral"] = laterales[0]
    elif len(laterales) > 1:
        con_longitud = [t for t in laterales if t.get("longitud_m") is not None]
        resultado["lateral"] = max(con_longitud, key=lambda t: t["longitud_m"]) if con_longitud else None
    else:
        resultado["lateral"] = None
    return resultado


def construir(sistema_agro: dict, tramos_hid: list, fv: dict, resumen: dict,
              proyecto: dict, nombre_sistema: str, fecha_str: str,
              hid_sistema: dict = None) -> dict:
    """Arma el dict del archivo del Diseñador para UN sistema de riego, o None si el sistema no
    es uno de los cuatro exportables (Goteo/Microaspersión/Aspersión/Carrete).

    `hid_sistema`: el bloque hidráulico del sistema (`verificacion_calculos.hidraulico.sistemas[i]`)
    — de ahí salen desnivel y pérdida de cabezal, que NO viven en `sistema_agro`."""
    par = SISTEMA_A_DR.get(nombre_sistema)
    if not par:
        return None
    p, sys_code = par
    sistema_agro = sistema_agro or {}
    hid_sistema = hid_sistema or {}
    fv = fv or {}
    resumen = resumen or {}

    fields = {}

    def put(sufijo, valor):
        s = _s(valor)
        if s is not None:
            fields[f"{p}-{sufijo}"] = s

    # ── Identificación (desde el Resumen del proyecto) ──
    put("consultor", resumen.get("consultor"))
    put("nombre-proy", resumen.get("nombre_proyecto") or proyecto.get("nombre"))
    put("prop", resumen.get("postulante") or proyecto.get("postulante"))
    put("rol", resumen.get("rol"))
    put("com", resumen.get("comuna"))
    put("huso", resumen.get("coord_h"))
    put("utmn", resumen.get("coord_n"))
    put("utme", resumen.get("coord_e"))

    # ── Cadena agronómica (Chequeo de Cálculos) ──
    put("cult", sistema_agro.get("cultivo"))
    put("ef", sistema_agro.get("eficiencia_pct"))
    # CC/PMP/Da: el Diseñador NO los tiene en Goteo (no existen `g-cc`/`g-pmp`/`g-da` en su HTML)
    # — misma razón por la que Revisor los oculta ahí: en alta frecuencia la demanda bruta sale
    # directo de ETc/Ef, sin pasar por el agotamiento del suelo. Aspersión y Carrete TAMPOCO los
    # tienen desde v120 (eliminados junto con `a-tex`/`c-tex`: la textura/CC/PMP/Da de esos dos
    # sistemas ahora entra SOLO por `__capasA`/`__capasC`, ver más abajo) — Microaspersión es el
    # ÚNICO que conserva el modelo de capa única (confirmado contra el HTML fuente del Diseñador
    # v121, no adivinado). Emitirlos para asp/car/got metía claves muertas en el archivo. Prof.
    # radicular (`{p}-pr`) SÍ existe en los 4 — sigue siendo el z que trunca las capas.
    if sys_code == "mic":
        put("cc", sistema_agro.get("cc_pct"))
        put("pmp", sistema_agro.get("pmp_pct"))
        put("da", sistema_agro.get("da"))
    put("pr", sistema_agro.get("prof_radicular_cm"))
    put("kc", sistema_agro.get("kc"))
    put("q", sistema_agro.get("caudal_disponible_ls"))

    # Acumulador (estanque/tranque regulador) — mismo campo -acum-vol en los 4 sistemas del
    # Diseñador (v98+). El checkbox -acum-chk no se exporta: es un <input type="checkbox"> y el
    # Diseñador lo restaura con `el.value = ...`, que no marca `.checked` — el revisor debe
    # tildarlo a mano en el Diseñador para que se muestre el volumen ya cargado.
    put("acum-vol", sistema_agro.get("volumen_acumulador_m3"))

    # Superficie a regar — el nombre del campo cambia según el sistema.
    superficie = sistema_agro.get("superficie_riego_ha")
    if sys_code in ("got", "mic"):
        put("sup", superficie)
    elif sys_code == "asp":
        put("strie", superficie)
    elif sys_code == "car":
        put("supr", superficie)

    # Horas de riego disponibles al día — Carrete SÍ tiene el campo desde v121 (`c-hrs`, antes
    # no existía).
    put("hrs", sistema_agro.get("horas_disponibles_dia"))

    # Tiempo de cambio de postura / traslado (Carrete: `c-tras`, desde v121). Aspersión también
    # tiene `a-tras` en el Diseñador, pero Revisor no lo captura como dato editable para ese
    # sistema (usa un valor fijo interno, ver `calculos_riego.postura_aspersion`) — no hay nada
    # que exportar ahí.
    if sys_code == "car":
        put("tras", sistema_agro.get("tiempo_cambio_postura_hr"))

    # Criterio de riego (% de agotamiento) — solo Aspersión y Carrete lo exponen.
    if sys_code in ("asp", "car"):
        put("crit", sistema_agro.get("factor_agotamiento_pct"))

    # VIB (Velocidad de Infiltración Básica) — el Diseñador la tiene en Aspersión, Microaspersión
    # y Carrete (v108, campo c-vib — corregido jul-2026; antes se creía que Carrete no la
    # exponía, pero sí la tiene y la usa en su verificación INIA-Carillanca). Goteo no la expone.
    if sys_code in ("asp", "mic", "car"):
        put("vib", sistema_agro.get("vib_mmhr"))

    # Presión de operación del emisor (mca) — mismo dato en los 4 sistemas del Diseñador, pero
    # con sufijo de campo distinto según sistema. Aspersión: -pres ("a-pres"). Goteo/
    # Microaspersión: -pem ("g-pem"/"m-pem"). Carrete: -pb ("c-pb") — su campo "c-pres" se
    # eliminó en v120/121 y se fusionó en "c-pb" ("Presión en el Cañón"), que antes NO se
    # exportaba (confirmado contra el HTML fuente del Diseñador v121, no adivinado).
    presion_emisor = sistema_agro.get("presion_emisor_mca")
    if sys_code == "asp":
        put("pres", presion_emisor)
    elif sys_code == "car":
        put("pb", presion_emisor)
    elif sys_code in ("got", "mic"):
        put("pem", presion_emisor)

    # Desnivel del área de riego → "ΔZ [m]" (`-dz`), presente en los 4 sistemas del Diseñador
    # ("Dif. de Cota ΔZ [m]" en Aspersión). Mismo dato que Revisor suma en la AMT calculada.
    put("dz", hid_sistema.get("desnivel_m"))

    # Pérdidas de carga del cabezal de control → "Pérdidas Cabezal [mca]" (`-pcab`). SOLO existe
    # en Goteo y Microaspersión: en Aspersión/Carrete el Diseñador no tiene un campo equivalente
    # (`a-pb` es "Presión Mín. Aspersor" y `c-pb` la presión en la boquilla del cañón — otro dato,
    # no la pérdida del cabezal), así que ahí simplemente no se exporta.
    if sys_code in ("got", "mic"):
        put("pcab", hid_sistema.get("perdida_cabezal_m"))

    # Marco de plantación / espaciamiento — los IDs del Diseñador difieren por sistema:
    #   Goteo: DEH (dist. entre hileras), DSH (dist. sobre hilera / entre plantas), N° líneas de
    #          emisor, Esp. entre goteros.
    #   Microaspersión: DL (dist. entre laterales = entre hileras), DE (dist. entre emisores).
    #   Aspersión: Esp. entre aspersores, Esp. entre laterales.
    #   Carrete: no tiene marco de plantación en el Diseñador.
    dist_hileras = sistema_agro.get("distancia_hileras_m")
    dist_plantas = sistema_agro.get("distancia_plantas_m")
    esp_emisores = sistema_agro.get("espaciamiento_emisores_m")
    if sys_code == "got":
        put("deh", dist_hileras)
        put("dsh", dist_plantas)
        put("nlin", sistema_agro.get("n_lineas_emisor"))
        put("espm", esp_emisores)
    elif sys_code == "mic":
        put("dl", dist_hileras)
        put("de", esp_emisores)
    elif sys_code == "asp":
        put("easp", sistema_agro.get("espaciamiento_aspersores_m"))
        put("elat", sistema_agro.get("espaciamiento_laterales_m"))
        put("nasp", sistema_agro.get("n_aspersores_postura"))
        put("qasp", sistema_agro.get("caudal_aspersor_m3h"))
    elif sys_code == "car":
        # Datos distintivos del carrete (metodología INIA-Carillanca) — IDs confirmados en el
        # código fuente del Diseñador (`calcCarP`, campos c-desc/c-margq/c-radio/c-vv/c-lf/c-va).
        # `c-fv` ("Factor Esp. Viento", % editable desde v121) no se exporta: Revisor no captura
        # un dato de consultor distinto de `velocidad_viento_ms` para ese %, y el propio
        # Diseñador se autocompleta con el mismo valor sugerido por tabla INIA cuando llega
        # vacío — exportarlo sería repetir un cálculo que el Diseñador ya hace solo.
        put("desc", sistema_agro.get("caudal_canon_m3h"))
        put("margq", sistema_agro.get("margen_sobredimensionamiento_pct"))
        put("radio", sistema_agro.get("radio_alcance_m"))
        put("vv", sistema_agro.get("velocidad_viento_ms"))
        put("lf", sistema_agro.get("longitud_franja_m"))
        put("va", sistema_agro.get("velocidad_avance_mh"))
        # Ángulo de sector (α) — campo `c-alfa` agregado en el Diseñador v123 (antes fijo en
        # 210° en su código, sin campo editable; ID confirmado contra el HTML fuente v123, no
        # adivinado). Si no se declara/calcula en Revisor, no se manda — el Diseñador cae a su
        # propio default (210°, mismo valor value="210" del input) al importar sin esta clave.
        put("alfa", sistema_agro.get("angulo_sector_deg"))

    # ── Desglose de Humedad Aprovechable por capas de suelo (solo Aspersión/Carrete — mismo
    # checkbox "reemplaza CC/PMP/Da" del Chequeo Agronómico). Mismas claves de textura
    # (franco_arenoso/franco/franco_limoso/franco_arcilloso/arcilloso) en ambas apps — confirmado
    # contra el HTML del Diseñador v121, no adivinado.
    if sys_code in ("asp", "car"):
        capas_suelo = sistema_agro.get("capas_suelo") or []
        if capas_suelo:
            fields["__capas" + ("A" if sys_code == "asp" else "C")] = {
                "on": True,
                "capas": [
                    {
                        "desde": _s(c.get("desde_cm")) or "",
                        "hasta": _s(c.get("hasta_cm")) or "",
                        "tex": c.get("textura") or "",
                        "cc": _s(c.get("cc_pct")) or "",
                        "pmp": _s(c.get("pmp_pct")) or "",
                        "da": _s(c.get("da")) or "",
                    }
                    for c in capas_suelo
                ],
            }

    # ── Red hidráulica jerárquica Matriz/Terciaria/Lateral (solo Goteo/Microaspersión) ──
    # Ver `_clasificar_tramos_jerarquico` — cada nivel se exporta solo si se identificó sin
    # ambigüedad; el material (string libre "pvc"/"pe"/"aluminio" en Revisor) se traduce al
    # coeficiente C de Hazen-Williams, que es literalmente el `value` que usa el <select> del
    # Diseñador para ese campo (confirmado en su HTML: PVC=150, Aluminio=140, PE=120).
    if sys_code in ("got", "mic"):
        niveles = _clasificar_tramos_jerarquico(tramos_hid)
        for nivel, (suf_l, suf_d, suf_c) in _SUFIJOS_NIVEL_HIDRAULICO.items():
            tramo = niveles.get(nivel)
            if not tramo:
                continue
            put(suf_l, tramo.get("longitud_m"))
            put(suf_d, tramo.get("diametro_mm"))
            c_val = calculos_riego.C_HAZEN_WILLIAMS.get((tramo.get("material") or "").strip().lower())
            if c_val is not None:
                put(suf_c, c_val)

    # ── Dimensionamiento fotovoltaico (mismos sufijos en ambas apps) ──
    for suf in ("pkw", "hbom", "hsp", "fp", "wp", "vmp", "imp", "ct", "temp", "einv", "vsis",
                "diasriego", "conexion"):
        # dias_riego en Revisor → diasriego en el Diseñador (sin guión bajo)
        fv_key = "dias_riego" if suf == "diasriego" else suf
        put(f"fv-{suf}", fv.get(fv_key))

    # ── Tramos de impulsión (solo Aspersión/Carrete usan la lista genérica l/q) ──
    if sys_code in _SYS_CON_TRAMOS:
        tramos = []
        for t in (tramos_hid or []):
            l = _s(t.get("longitud_m"))
            q = _s(t.get("caudal_ls"))
            if l is None and q is None:
                continue
            # `t` (¿nº de tramos iguales?) y `z` no existen en Revisor a nivel de TRAMO — se dejan
            # vacíos para que el revisor los complete en el Diseñador (no se inventan). Ojo: el
            # desnivel que sí tiene Revisor es del sistema completo, no por tramo, y va al campo
            # `-dz` de arriba; repartirlo entre los tramos sería inventar.
            tramos.append({"l": l or "", "q": q or "", "t": "", "z": ""})
        if tramos:
            fields["__tramos"] = tramos

    codigo = proyecto.get("codigo_sep", "") or ""
    nombre = f"{nombre_sistema} {codigo}".strip()
    return {"__sys": sys_code, "__name": nombre, "__date": fecha_str, "fields": fields}
