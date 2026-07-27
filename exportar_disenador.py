"""Exporta los datos del Chequeo de Cálculos al formato de archivo del Diseñador de Riego
(la app hermana del mismo usuario, `disenador_riego_v108.html`), para poder abrirlo ahí y seguir
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
  posición ni por diámetro. Si el nombre no calza con ningún alias, o si calzan dos o más tramos
  con el MISMO nivel (ambiguo), ese nivel simplemente no se exporta — el revisor corrige el
  campo `nombre` si quiere que se reconozca, o completa el dato a mano en el Diseñador."""
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
    campo `nombre` de cada tramo de `tramos` (la tabla de tramos hidráulicos de Revisor). Un
    nivel queda en None (no se exporta) si NINGÚN tramo calza con sus alias, o si calzan DOS O
    MÁS tramos con el mismo nivel — la clasificación nunca adivina, solo reconoce coincidencias
    inequívocas."""
    candidatos = {"matriz": [], "terciaria": [], "lateral": []}
    for t in (tramos or []):
        nombre_norm = _normalizar_nombre_tramo(t.get("nombre"))
        if not nombre_norm:
            continue
        for nivel, alias in _ALIAS_TRAMO_JERARQUICO.items():
            if any(a in nombre_norm for a in alias):
                candidatos[nivel].append(t)
                break   # un tramo se clasifica en un solo nivel (el primero que calce)
    return {nivel: (lista[0] if len(lista) == 1 else None) for nivel, lista in candidatos.items()}


def construir(sistema_agro: dict, tramos_hid: list, fv: dict, resumen: dict,
              proyecto: dict, nombre_sistema: str, fecha_str: str) -> dict:
    """Arma el dict del archivo del Diseñador para UN sistema de riego, o None si el sistema no
    es uno de los cuatro exportables (Goteo/Microaspersión/Aspersión/Carrete)."""
    par = SISTEMA_A_DR.get(nombre_sistema)
    if not par:
        return None
    p, sys_code = par
    sistema_agro = sistema_agro or {}
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

    # Horas de riego disponibles al día — Carrete no tiene ese campo en el Diseñador.
    if sys_code in ("got", "mic", "asp"):
        put("hrs", sistema_agro.get("horas_disponibles_dia"))

    # Criterio de riego (% de agotamiento) — solo Aspersión y Carrete lo exponen.
    if sys_code in ("asp", "car"):
        put("crit", sistema_agro.get("factor_agotamiento_pct"))

    # VIB (Velocidad de Infiltración Básica) — el Diseñador la tiene en Aspersión, Microaspersión
    # y Carrete (v108, campo c-vib — corregido jul-2026; antes se creía que Carrete no la
    # exponía, pero sí la tiene y la usa en su verificación INIA-Carillanca). Goteo no la expone.
    if sys_code in ("asp", "mic", "car"):
        put("vib", sistema_agro.get("vib_mmhr"))

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
        # código fuente del Diseñador v108 (`calcCarP`, campos c-desc/c-margq/c-radio/c-vv/c-lf/
        # c-va). `c-fv` ("Factor Esp. Viento") existe en la UI del Diseñador pero NO se lee en
        # `calcCarP` (el % real sale de una tabla fija según `c-vv`) — no se exporta, es vestigial.
        put("desc", sistema_agro.get("caudal_canon_m3h"))
        put("margq", sistema_agro.get("margen_sobredimensionamiento_pct"))
        put("radio", sistema_agro.get("radio_alcance_m"))
        put("vv", sistema_agro.get("velocidad_viento_ms"))
        put("lf", sistema_agro.get("longitud_franja_m"))
        put("va", sistema_agro.get("velocidad_avance_mh"))

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
    for suf in ("pkw", "hbom", "hsp", "fp", "wp", "vmp", "imp", "ct", "temp", "einv", "vsis"):
        put(f"fv-{suf}", fv.get(suf))

    # ── Tramos de impulsión (solo Aspersión/Carrete usan la lista genérica l/q) ──
    if sys_code in _SYS_CON_TRAMOS:
        tramos = []
        for t in (tramos_hid or []):
            l = _s(t.get("longitud_m"))
            q = _s(t.get("caudal_ls"))
            if l is None and q is None:
                continue
            # `t` (¿nº de tramos iguales?) y `z` (desnivel) no existen en Revisor — se dejan
            # vacíos para que el revisor los complete en el Diseñador (no se inventan).
            tramos.append({"l": l or "", "q": q or "", "t": "", "z": ""})
        if tramos:
            fields["__tramos"] = tramos

    codigo = proyecto.get("codigo_sep", "") or ""
    nombre = f"{nombre_sistema} {codigo}".strip()
    return {"__sys": sys_code, "__name": nombre, "__date": fecha_str, "fields": fields}
