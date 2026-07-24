"""Exporta los datos del Chequeo de Cálculos al formato de archivo del Diseñador de Riego
(la app hermana del mismo usuario, `disenador_riego_v101.html`), para poder abrirlo ahí y seguir
evaluando aspectos que no cubre Revisor CNR — sin recargar Revisor con esos cálculos.

REGLA: solo se exportan los datos que Revisor efectivamente tiene (extraídos/validados en el
Chequeo de Cálculos + el Resumen). NUNCA se inventan valores: las claves sin dato simplemente NO
se incluyen, así el Diseñador conserva sus propios valores por defecto al cargar el archivo.

El Diseñador guarda un JSON por SISTEMA de riego, con un prefijo de campo distinto según el
sistema (g-/m-/a-/c-) y un código `__sys` (got/mic/asp/car). Los campos que mapean 1:1 (mismo
significado, mismo dato) son los que porté a `calculos_riego.py` en su momento, más los del
Resumen y el dimensionamiento fotovoltaico. La red hidráulica detallada por tramos solo tiene un
formato genérico (`__tramos`, lista l/q) en Aspersión y Carrete; Goteo/Microaspersión usan en el
Diseñador un modelo matriz/terciaria/lateral que NO mapea desde nuestra tabla de tramos plana sin
adivinar cuál tramo es cuál — por eso ahí no se exportan los tramos (quedan para el Diseñador)."""

# Sistema de riego declarado en Revisor → (prefijo de campo, código __sys del Diseñador).
SISTEMA_A_DR = {
    "Goteo": ("g", "got"),
    "Microaspersión": ("m", "mic"),
    "Aspersión": ("a", "asp"),
    "Carrete": ("c", "car"),
}

# Sistemas que usan la lista genérica de tramos de impulsión `__tramos` (l/q). Goteo y
# Microaspersión NO — su red se describe con campos matriz/terciaria/lateral que no mapean.
_SYS_CON_TRAMOS = {"asp", "car"}


def _s(v):
    """Valor a string tal como lo espera el Diseñador (todos sus campos son strings), o None si
    no hay dato (para omitir la clave). Un float entero se emite sin decimales (60.0 → "60")."""
    if v is None or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


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

    # VIB (Velocidad de Infiltración Básica) — el Diseñador la tiene en Aspersión y
    # Microaspersión (Goteo/Carrete no la exponen).
    if sys_code in ("asp", "mic"):
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
