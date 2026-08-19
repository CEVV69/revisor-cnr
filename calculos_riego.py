"""
Fórmulas de ingeniería de riego (hidráulica, agronómica y fotovoltaica), portadas del
Diseñador de Riego (misma fuente normativa: Manuales e Instructivos CNR en Drive —
Hazen-Williams, cadena de demanda agronómica ETo→ETc→AD→Dn→Fr→Db, dimensionamiento FV).

Se usan para RECALCULAR de forma determinística lo que el consultor declaró en el expediente,
y comparar — en vez de que la IA intente hacer la matemática de memoria a partir de texto
libre. Funciones puras, sin dependencias externas.
"""
import math


# ── Hidráulica: Hazen-Williams ──────────────────────────────────────────────

# Coeficiente C de Hazen-Williams por material (mismo criterio del Diseñador de Riego)
C_HAZEN_WILLIAMS = {
    "aluminio": 140,
    "pvc": 150,
    "pe": 120,
    "pead": 120,
    "polietileno": 120,
}

VELOCIDAD_MIN_RECOMENDADA = 0.5   # m/s — bajo esto, riesgo de sedimentación
VELOCIDAD_MAX_RECOMENDADA = 2.0   # m/s — sobre esto, golpe de ariete / pérdidas excesivas

# Catálogo de tuberías comerciales — MISMOS datos que usa el Diseñador de Riego (array `TUBOS`
# por defecto en static/disenador_riego_v123.html), portado tal cual para que el Chequeo
# Hidráulico use el diámetro INTERIOR real en Hazen-Williams en vez del diámetro comercial/
# exterior que suele venir en la memoria. El espesor de pared NO es un único valor por
# diámetro+material — depende también de la clase de presión (PN/SDR), por eso esto es un
# catálogo de productos (el revisor elige el que corresponda), no una resta genérica que
# asumiera una clase por defecto.
#
# PVC 32/40/50mm (ago-2026, pedido por el usuario — no estaban ni en este catálogo ni en el del
# Diseñador): dint = dext − 2×e_mín, con e_mín de la Ficha Técnica "Tubería Hidráulica de PVC"
# de Tigre Chile (Tabla 2, norma NCh 399/2011) — 32mm: PN6 e=1,5mm, PN10 e=1,9mm; 40mm: PN6
# e=1,5mm, PN10 e=1,9mm; 50mm: PN6 e=1,6mm, PN10 e=2,4mm. No inventado: dato de fabricante real.
TUBOS_CATALOGO = [
    {"nombre": 'Aluminio 2"',  "dext": 50,    "dint": 48,    "c": 140, "material": "aluminio"},
    {"nombre": 'Aluminio 3"',  "dext": 76.2,  "dint": 74.2,  "c": 140, "material": "aluminio"},
    {"nombre": 'Aluminio 4"',  "dext": 101.6, "dint": 99.6,  "c": 140, "material": "aluminio"},
    {"nombre": 'Aluminio 6"',  "dext": 152.4, "dint": 150.4, "c": 140, "material": "aluminio"},
    {"nombre": "PVC 32mm PN6",   "dext": 32,  "dint": 29.0,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 32mm PN10",  "dext": 32,  "dint": 28.2,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 40mm PN6",   "dext": 40,  "dint": 37.0,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 40mm PN10",  "dext": 40,  "dint": 36.2,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 50mm PN6",   "dext": 50,  "dint": 46.8,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 50mm PN10",  "dext": 50,  "dint": 45.2,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 63mm PN6",   "dext": 63,  "dint": 59.2,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 63mm PN10",  "dext": 63,  "dint": 57,    "c": 150, "material": "pvc"},
    {"nombre": "PVC 90mm PN6",   "dext": 90,  "dint": 84.6,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 90mm PN10",  "dext": 90,  "dint": 81.4,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 110mm PN6",  "dext": 110, "dint": 103.6, "c": 150, "material": "pvc"},
    {"nombre": "PVC 110mm PN10", "dext": 110, "dint": 99.4,  "c": 150, "material": "pvc"},
    {"nombre": "PVC 160mm PN6",  "dext": 160, "dint": 150.6, "c": 150, "material": "pvc"},
    {"nombre": "PVC 160mm PN10", "dext": 160, "dint": 144.6, "c": 150, "material": "pvc"},
    {"nombre": "PE 32mm SDR13.6 PN10",         "dext": 32, "dint": 27.2, "c": 120, "material": "pe"},
    {"nombre": "PE 40mm SDR13.6 PN10 (Ø36.4)", "dext": 40, "dint": 36.4, "c": 120, "material": "pe"},
    {"nombre": "PE 50mm SDR13.6 PN10 (Ø46.4)", "dext": 50, "dint": 46.4, "c": 120, "material": "pe"},
    {"nombre": "PE 63mm SDR13.6 PN10 (Ø57)",   "dext": 63, "dint": 57,   "c": 120, "material": "pe"},
    {"nombre": "PE 63mm SDR7.4 PN16 (Ø52.4)",  "dext": 63, "dint": 52.4, "c": 120, "material": "pe"},
    {"nombre": "PE 90mm SDR13.6 PN10 (Ø81.4)", "dext": 90, "dint": 81.4, "c": 120, "material": "pe"},
    {"nombre": "Polietileno 16mm lat.", "dext": 16, "dint": 14, "c": 120, "material": "pe"},
]


def hazen_williams(q_ls: float, d_mm: float, l_m: float, c: float) -> float:
    """Pérdida de carga (Hf, en mca) por tramo de tubería. Q en l/s, D en mm, L en m."""
    if not q_ls or not d_mm or not l_m or not c:
        return 0.0
    q_m3s = q_ls / 1000
    d_m = d_mm / 1000
    return 10.67 * l_m * (q_m3s ** 1.852) / ((c ** 1.852) * (d_m ** 4.87))


def velocidad_tuberia(q_ls: float, d_mm: float) -> float:
    """Velocidad del flujo (m/s). Q en l/s, D en mm."""
    if not q_ls or not d_mm:
        return 0.0
    area_m2 = (math.pi / 4) * (d_mm / 1000) ** 2
    return (q_ls / 1000) / area_m2


def diametro_sugerido_mm(q_ls: float) -> float:
    """Diámetro mínimo sugerido (mm) para que V ≤ 1,5 m/s. Q en l/s."""
    if not q_ls:
        return 0.0
    return math.sqrt(849.6 * q_ls)


def evaluar_tramo(q_ls: float, d_mm: float, l_m: float = None, c: float = None) -> dict:
    """Evalúa un tramo de tubería: velocidad, diámetro sugerido, pérdida de carga (si hay
    longitud y material) y si la velocidad queda fuera del rango recomendado."""
    vel = velocidad_tuberia(q_ls, d_mm)
    d_sug = diametro_sugerido_mm(q_ls)
    hf = hazen_williams(q_ls, d_mm, l_m, c) if (l_m and c) else None
    alerta = None
    if vel > VELOCIDAD_MAX_RECOMENDADA:
        alerta = f"velocidad {vel:.2f} m/s supera el máximo recomendado (2,0 m/s)"
    elif 0 < vel < VELOCIDAD_MIN_RECOMENDADA:
        alerta = f"velocidad {vel:.2f} m/s bajo el mínimo recomendado (0,5 m/s) — riesgo de sedimentación"
    return {
        "velocidad_ms": round(vel, 2) if vel else None,
        "diametro_sugerido_mm": round(d_sug, 1) if d_sug else None,
        "hf_mca": round(hf, 3) if hf is not None else None,
        "alerta": alerta,
    }


def amt_calculada_m(tramos: list, desnivel_m: float = None, perdida_cabezal_m: float = None, presion_emisor_mca: float = None) -> float:
    """AMT/CDT calculada = Σ Hf de los tramos declarados (Hazen-Williams, mismo criterio de
    `evaluar_tramo`) + desnivel del área de riego + pérdidas de carga en el cabezal de control
    + presión de operación del emisor (goteros/aspersores/cañón según el sistema).

    NO es la cadena CDT completa (le falta succión y margen de seguridad si el consultor no los
    incluyó como un tramo más de la tabla) — es la suma de lo que Revisor efectivamente puede
    calcular o el revisor declaró a mano. None si no hay NINGÚN dato para sumar (ni un Hf de
    tramo, ni desnivel, ni pérdida de cabezal, ni presión del emisor) — evita mostrar "0" como si
    fuera un resultado real cuando en verdad no hay nada calculado."""
    total = 0.0
    hubo_dato = False
    for t in (tramos or []):
        c = C_HAZEN_WILLIAMS.get((t.get("material") or "").strip().lower())
        hf = hazen_williams(t.get("caudal_ls"), t.get("diametro_mm"), t.get("longitud_m"), c)
        if hf:
            total += hf
            hubo_dato = True
    if desnivel_m is not None:
        total += desnivel_m
        hubo_dato = True
    if perdida_cabezal_m is not None:
        total += perdida_cabezal_m
        hubo_dato = True
    if presion_emisor_mca is not None:
        total += presion_emisor_mca
        hubo_dato = True
    return round(total, 2) if hubo_dato else None


# ── Agronómico: cadena ETo → ETc → AD → Dn → Fr → Db ────────────────────────

# Suelo por defecto (CC/PMP/Da) según textura — mismo criterio del Diseñador de Riego (v119,
# desglose de Humedad Aprovechable por capas): valores referenciales para autocompletar una
# capa al elegir su textura. El revisor puede sobrescribirlos si el expediente trae análisis
# de suelo propio.
SUELO_DEFAULT_POR_TEXTURA = {
    "franco_arenoso":   {"cc": 14, "pmp": 6,  "da": 1.50},
    "franco":           {"cc": 22, "pmp": 10, "da": 1.40},
    "franco_limoso":    {"cc": 20, "pmp": 10, "da": 1.30},
    "franco_arcilloso": {"cc": 27, "pmp": 13, "da": 1.35},
    "arcilloso":        {"cc": 35, "pmp": 17, "da": 1.25},
}


def ad_por_capas(capas: list, prof_radicular_cm: float = None) -> dict:
    """Agua Disponible (AD) total del suelo a partir de un desglose por capas — mismo criterio
    que el Diseñador de Riego (checkbox "Desglose de Humedad Aprovechable por capas de suelo",
    disponible en Aspersión y Carrete). Reemplaza el cálculo de capa única (CC/PMP/Da/Prof.
    radicular uniforme) cuando el consultor declara horizontes de suelo distintos.

    Por capa: Alt.ef[mm] = MAX(0, MIN(Hasta, z) − Desde)[cm] × 10
              Ha_capa[mm] = (CC − PMP)/100 × Da × Alt.ef
    AD total = Σ Ha_capa

    `prof_radicular_cm` (z, ago-2026 — Diseñador de Riego v121): cada capa se trunca a la
    profundidad radicular del cultivo. Una capa íntegramente bajo z no aporta nada (Alt.ef=0,
    Ha_capa=0, pero SIGUE siendo una capa válida — no se descarta); una capa que cruza z se corta
    justo ahí. Sin z (None, compatibilidad con datos guardados antes de este cambio), no trunca —
    se comporta como el modelo anterior (Alt.ef = espesor completo declarado).

    `capas`: lista de {"desde_cm", "hasta_cm", "cc_pct", "pmp_pct", "da"}. Una capa con datos
    incompletos, Hasta≤Desde o CC≤PMP se descarta silenciosamente (mismo criterio de validación
    que el Diseñador — nunca calcula con una capa a medio llenar; esto es independiente del
    truncamiento por z). Devuelve {} si no queda ninguna capa válida."""
    validas = []
    ad_total = 0.0
    prof_total = 0.0
    max_hasta = 0.0
    for c in (capas or []):
        desde, hasta = c.get("desde_cm"), c.get("hasta_cm")
        cc, pmp, da = c.get("cc_pct"), c.get("pmp_pct"), c.get("da")
        if None in (desde, hasta, cc, pmp, da) or hasta <= desde or cc <= pmp:
            continue
        if hasta > max_hasta:
            max_hasta = hasta
        if prof_radicular_cm is not None:
            altura_ef = max(0.0, min(hasta, prof_radicular_cm) - desde) * 10
        else:
            altura_ef = (hasta - desde) * 10
        ha_capa = (cc - pmp) / 100 * da * altura_ef if altura_ef > 0 else 0.0
        validas.append({**c, "altura_mm": round(altura_ef, 1), "ha_capa_mm": round(ha_capa, 2)})
        ad_total += ha_capa
        prof_total += altura_ef / 10
    if not validas:
        return {}
    r = {"capas": validas, "ad_total_mm": round(ad_total, 2), "prof_total_cm": round(prof_total, 1)}
    if prof_radicular_cm is not None:
        r["prof_radicular_cm"] = prof_radicular_cm
        r["capas_no_alcanzan_prof_radicular"] = max_hasta < prof_radicular_cm
    return r


def _redondear_fr(fr: float) -> int:
    """Redondeo al entero más próximo (no truncamiento hacia abajo) — mismo criterio que usan los
    consultores al declarar la frecuencia de riego (Fr), confirmado por el usuario (ago-2026):
    antes esta app y el Diseñador de Riego truncaban Fr con `floor`, lo que sistemáticamente subía
    la frecuencia de riego declarable y arrastraba una diferencia a toda la cadena aguas abajo
    (Dn_adj, Db, superficie de riego segura, N° de sectores/posturas).

    Se implementa como `floor(fr + 0.5)` en vez de usar `round()` de Python a propósito: `round()`
    usa redondeo bancario (`round(2.5) == 2`, `round(3.5) == 4`) — no es el redondeo aritmético
    clásico que espera un consultor ni el que aplica `Math.round` en JavaScript (que SIEMPRE
    redondea 0,5 hacia arriba). Con `floor(fr + 0.5)` el comportamiento es idéntico al de
    `Math.round` del Diseñador de Riego y del propio Chequeo (`recalcAgroSistema` en
    calculos.html), evitando que el mismo Fr redondee distinto en Python y en JS."""
    return int(math.floor(fr + 0.5))


def cadena_agronomica(cc_pct: float, pmp_pct: float, da: float, prof_cm: float,
                      kc: float, eto_dia_mm: float, factor_agotamiento_pct: float,
                      eficiencia_pct: float, alta_frecuencia: bool = False,
                      ad_mm_override: float = None) -> dict:
    """Recalcula la demanda agronómica con la misma cadena que usa el Diseñador de Riego.

    ETc = ETo × Kc, siempre. Después hay DOS modelos según el sistema de riego:

    · Aspersión / Carrete / Microaspersión (por turnos, con agotamiento — `alta_frecuencia=False`):
        AD     = (CC − PMP)/100 × Da × Prof(m) × 1000   [mm — agua disponible del suelo]
        Dn     = AD × fa                                 [mm — lámina neta de riego]
        Fr     = Dn / ETc  →  Fr_adj = redondeo al entero más cercano (mín. 1) [días — frecuencia
                 de riego. Ago-2026: antes se truncaba hacia abajo (floor) — el usuario advirtió
                 que los consultores redondean al entero más próximo, no al piso, y que ese truncar
                 arrastraba una diferencia a TODA la cadena aguas abajo (Dn_adj, Db, superficie
                 segura, N° de sectores/posturas...). Mismo criterio aplicado en el Diseñador de
                 Riego (`calcAA`/`calcCA`/`calcMA`) — ver docstring de `_redondear_fr`]
        Dn_adj = ETc × Fr_adj
        Db     = Dn_adj / Ef                             [mm — demanda bruta]

    · Goteo (riego localizado de ALTA FRECUENCIA — `alta_frecuencia=True`): se riega a diario
        reponiendo la ETc del día, así que la demanda bruta sale DIRECTO de la ETc, sin pasar
        por el factor de agotamiento (Fr = 1). Es el modelo `calcGA` del Diseñador de Riego —
        por eso goteo no tiene campo "criterio de riego":
        Db = ETc / Ef,  Fr_adj = 1,  Dn = Dn_adj = ETc

    `factor_agotamiento_pct` se ignora cuando `alta_frecuencia=True` (puede venir None). AD se
    calcula igual (dato informativo) si están CC/PMP/Da/Prof; si falta alguno, queda None.

    `ad_mm_override`: si se pasa (típicamente el `ad_total_mm` de `ad_por_capas()`), reemplaza
    el cálculo de AD de capa única — Aspersión/Carrete con desglose de suelo por capas (v119
    del Diseñador). CC/PMP/Da/Prof dejan de ser necesarios en ese caso.
    """
    etc = eto_dia_mm * kc
    if ad_mm_override is not None:
        ad = ad_mm_override
    elif None not in (cc_pct, pmp_pct, da, prof_cm):
        ad = (cc_pct - pmp_pct) / 100 * da * (prof_cm / 100) * 1000
    else:
        ad = None

    if alta_frecuencia:
        fr = 1.0
        fr_adj = 1
        dn = etc
        dn_adj = etc
    else:
        dn = ad * (factor_agotamiento_pct / 100) if ad is not None else 0
        fr = dn / etc if etc else 0
        fr_adj = max(1, _redondear_fr(fr)) if fr else 1
        dn_adj = etc * fr_adj
    db = dn_adj / (eficiencia_pct / 100) if eficiencia_pct else 0
    # Db "diario" (ETc/Ef, SIN pasar por Fr) — el propio Diseñador de Riego lo calcula aparte
    # (`dbDiario`/`dbDiarioC` en `calcAA`/`calcCA`) para usarlo SOLO en "Superficie de Riego
    # Segura" (ITT-03 §1): esa verificación pregunta "¿alcanza el caudal para regar TODO en un
    # día?", una pregunta de balance diario — usar el Db de Fr días ahí subestimaría la demanda
    # real de agua por unidad de superficie. Aplica igual en alta frecuencia (donde db_mm YA es
    # ETc/Ef, así que db_diario_mm resulta idéntico a db_mm).
    db_diario = etc / (eficiencia_pct / 100) if eficiencia_pct else 0
    return {
        "etc_mm_dia": round(etc, 3), "ad_mm": round(ad, 2) if ad is not None else None,
        "dn_mm": round(dn, 3), "fr_dias": round(fr, 2), "fr_adj_dias": fr_adj,
        "dn_adj_mm": round(dn_adj, 3), "db_mm": round(db, 3),
        "db_diario_mm": round(db_diario, 3),
    }


def verificacion_diseno_riego(db_mm_dia: float, superficie_ha: float = None,
                              caudal_disponible_ls: float = None,
                              precipitacion_mmhr: float = None,
                              horas_disponibles_dia: float = None,
                              volumen_acumulador_m3: float = None,
                              db_diario_mm_dia: float = None,
                              n_posturas_ext: int = None) -> dict:
    """Recalcula los resultados base del diseño de riego a partir de la demanda bruta (Db) —
    misma relación que usan los sistemas localizados (goteo/microaspersión) del Diseñador de
    Riego. Aspersión/carrete usan ahí un modelo de "posturas" más elaborado (caudal y tiempo
    por postura, N° de posturas por superficie) que no se replica acá a propósito — esto es
    una verificación general de la relación demanda↔caudal↔tiempo↔sectores↔volumen, no un
    diseño completo por tipo de sistema:

    Demanda[l/s/ha]         = Db_diario / 8,64              (1 mm/día/ha = 1/8,64 l/s/ha)
    Superficie riego segura = Caudal de la FUENTE / Demanda[l/s/ha]
    Tiempo de riego         = Db / Precipitación del sistema declarada   [hr/día — por sector,
                              independiente del área total]

    **Db_diario vs. Db (jul-2026, Diseñador v108):** "Superficie de Riego Segura" usa el Db
    "diario" (`db_diario_mm_dia`, = ETc/Ef, SIN pasar por Fr) — la misma distinción que hace el
    propio Diseñador de Riego (`calcAA`/`calcCA`, comentario explícito "SIEMPRE con demanda
    DIARIA, no con Db de Fr días") porque esa pregunta es de balance diario ("¿alcanza el caudal
    de la fuente para regar TODO en 24 horas?"), no de ciclo de riego. El resto de este bloque
    (Tiempo de riego, N° de sectores, balance/volumen del estanque) sigue usando `db_mm_dia` (el
    Db ajustado por Fr) como siempre — esas verificaciones sí son sobre el ciclo de riego. Si no
    se pasa `db_diario_mm_dia`, cae a `db_mm_dia` (compatible con el comportamiento anterior a
    este cambio, y exacto en alta frecuencia/Goteo donde ambos valores ya coinciden).

    N° de sectores (fórmula v104 del Diseñador de Riego, `calcGE`/`calcME`, FORMA CERRADA sin
    iterar). El criterio es de CAUDAL: si el caudal que exige regar TODA la superficie a la vez,
    al ritmo de precipitación del sistema, supera lo que puede entregar la fuente (más lo que
    aporte el acumulador durante el riego de un sector), hay que dividir en sectores:
        Q_requerido[l/s] = Precipitación del sistema[mm/hr] × Superficie[ha] × 10.000 / 3.600
        Q_estanque[l/s]  = Volumen acumulador[m³]×1000 / (Tiempo de riego×3600)  (0 si no declara)
        N° de sectores    = ⌈(Q_requerido − Q_estanque) / Caudal de la fuente⌉, mínimo 1
    Derivación (evita iterar: el requisito por sector es Q_requerido/n ≤ Q_fuente +
    Q_estanque_total/n, que multiplicado por n despeja directo la fórmula de arriba). El
    acumulador reparte su volumen ENTRE los sectores del día — por eso Q_estanque se resta UNA
    vez del Q_requerido total, no una vez por sector.

    **A diferencia de versiones anteriores del Diseñador (v101/v102), el acumulador YA NO se
    suma al caudal de la fuente para la Superficie de riego segura** — esa sigue calculándose
    solo con el caudal de la fuente. El rol del acumulador quedó acotado, con más precisión, a
    reducir el N° de sectores y a las dos verificaciones de volumen de abajo.

    Con el N° de sectores determinado, además:
    - Caudal de operación (`caudal_operacion_ls`) = Q_requerido / N° de sectores — el caudal que
      circula por la red mientras opera UN sector (el que el consultor debería haber usado para
      dimensionar diámetros/pérdidas de carga, distinto del caudal de la fuente).
    - Verificación de tiempo: N° sectores × Tiempo de riego vs. horas disponibles declaradas
      (`cabe_en_horas_disponibles`) — a diferencia del modelo viejo, ahora SÍ puede no caber.
    - Verificación de BALANCE DIARIO de volumen (NO depende del N° de sectores, es la condición
      de fondo): V_requerido/día = Q_requerido × Tiempo de riego × 3.600 vs. V_fuente/día =
      Caudal de la fuente × 86.400. Si la fuente no repone el volumen diario que exige el
      diseño, NINGÚN acumulador lo resuelve (hay que reducir superficie o aumentar el derecho
      de agua) — `balance_diario_ok`.
    - Si hay acumulador declarado: volumen MÍNIMO que debe tener = V_requerido − Caudal de la
      fuente × (N° sectores × Tiempo de riego) × 3.600 — compara contra el volumen declarado
      (`volumen_minimo_estanque_l`, `acumulador_ok`).
    - Datos INFORMATIVOS del aporte del estanque (Diseñador v106, `evalAcum` — mismo chequeo de
      volumen mínimo de arriba, expresado en unidades de tiempo, más intuitivo para el revisor):
        ΔQ que aporta el estanque = Caudal de operación − Caudal de la fuente (si es ≤ 0, la
          fuente sola alcanza y el estanque no necesita aportar nada) — `delta_q_estanque_ls`.
        Autonomía = Volumen del estanque / ΔQ — horas que el volumen sostiene ese déficit antes
          de vaciarse (solo si ΔQ > 0) — `autonomia_estanque_hr`.
        Tiempo de llenado = Volumen del estanque / Caudal de la fuente — horas que tarda en
          llenarse desde vacío usando solo la fuente — `tiempo_llenado_estanque_hr`.

    (El Diseñador calcula `Q_requerido` a partir del N° de emisores real; acá se deriva de
    Precipitación×Superficie, matemáticamente equivalente — ver CLAUDE.md para la derivación —
    y evita depender de datos de marco/emisores que no siempre se pueden extraer con
    confianza del expediente.)

    Cada resultado solo se calcula si están los datos que necesita — es aditivo, no todo o
    nada. `caudal_disponible_ls` habilita la superficie segura; `precipitacion_mmhr` habilita
    el tiempo de riego; el N° de sectores y el resto de las verificaciones necesitan
    precipitación + superficie; `horas_disponibles_dia` habilita la verificación de si el N° de
    sectores calculado cabe en el día.

    **`n_posturas_ext` (jul-2026) — Aspersión/Carrete usan POSTURAS, no sectores.** En esos dos
    sistemas el N° que declara el consultor no es de origen caudal (no se obtiene dividiendo el
    caudal requerido entre el disponible) — es GEOMÉTRICO/de equipo: cuántas veces hay que
    reposicionar un grupo fijo de aspersores, o el cañón, para cubrir el predio (ver
    `postura_aspersion()`/`diseno_carrete()`). Si se pasa `n_posturas_ext` (ese N° ya calculado
    con el modelo real del sistema), la función lo usa DIRECTO como `n_sectores` — NO recalcula
    por caudal ni lo reduce con el acumulador (`caudal_estanque_ls` no se calcula en este caso: el
    N° de posturas es fijo, no depende del acumulador). El resto del bloque (Caudal de operación,
    Tiempo total del día, Balance diario, Volumen mínimo/ΔQ/Autonomía/T. llenado) usa exactamente
    las MISMAS fórmulas de siempre, solo que con este N en vez del N° de sectores por caudal — por
    eso los resultados de esos cálculos cambian para Aspersión/Carrete respecto a antes de este
    parámetro. Sin `n_posturas_ext` (Goteo/Microaspersión, comportamiento de siempre), N° de
    sectores se sigue calculando por caudal, con la reducción por acumulador incluida."""
    r = {}
    if not db_mm_dia:
        return r
    db_diario = db_diario_mm_dia if db_diario_mm_dia else db_mm_dia
    demanda_ls_ha = db_diario / 8.64
    r["demanda_ls_ha"] = round(demanda_ls_ha, 4)

    # Superficie de riego segura: SOLO el caudal de la fuente (v104 — el acumulador ya no se
    # suma acá, ver docstring).
    if caudal_disponible_ls and demanda_ls_ha:
        r["superficie_segura_ha"] = round(caudal_disponible_ls / demanda_ls_ha, 4)

    tiempo_riego = None
    if precipitacion_mmhr:
        tiempo_riego = db_mm_dia / precipitacion_mmhr
        r["tiempo_riego_hr"] = round(tiempo_riego, 2)

    if tiempo_riego and superficie_ha:
        q_requerido_total_ls = precipitacion_mmhr * superficie_ha * 10000 / 3600
        r["q_requerido_total_ls"] = round(q_requerido_total_ls, 4)

        vol_litros = (volumen_acumulador_m3 or 0) * 1000
        q_estanque_ls = (vol_litros / (tiempo_riego * 3600)) if vol_litros else 0.0

        if n_posturas_ext is not None:
            # Aspersión/Carrete: N° de posturas (geométrico/de equipo), fijo — no se recalcula
            # por caudal ni se reduce con el acumulador.
            n_sectores = max(1, int(n_posturas_ext))
        else:
            if vol_litros:
                r["caudal_estanque_ls"] = round(q_estanque_ls, 3)
            if caudal_disponible_ls:
                n_sectores = max(1, math.ceil((q_requerido_total_ls - q_estanque_ls) / caudal_disponible_ls))
            else:
                n_sectores = 1
        r["n_sectores"] = n_sectores
        tiempo_total_dia = n_sectores * tiempo_riego
        r["tiempo_total_dia_hr"] = round(tiempo_total_dia, 2)
        if horas_disponibles_dia:
            r["cabe_en_horas_disponibles"] = tiempo_total_dia <= horas_disponibles_dia

        caudal_operacion_ls = q_requerido_total_ls / n_sectores
        r["caudal_operacion_ls"] = round(caudal_operacion_ls, 3)

        # Balance diario de volumen — NO depende del N° de sectores (Q_sector×T_total =
        # Q_requerido×Tiempo_riego siempre, ver docstring).
        v_dia_l = q_requerido_total_ls * tiempo_riego * 3600
        r["v_requerido_dia_l"] = round(v_dia_l, 0)
        if caudal_disponible_ls:
            v_fuente_dia_l = caudal_disponible_ls * 24 * 3600
            r["v_fuente_dia_l"] = round(v_fuente_dia_l, 0)
            r["balance_diario_ok"] = v_dia_l <= v_fuente_dia_l

            if vol_litros:
                v_min_l = max(0.0, v_dia_l - caudal_disponible_ls * tiempo_total_dia * 3600)
                r["volumen_minimo_estanque_l"] = round(v_min_l, 0)
                r["acumulador_ok"] = vol_litros >= v_min_l

                # Datos informativos del aporte del estanque (Diseñador v106, `evalAcum`) — el
                # mismo chequeo de volumen mínimo de arriba, expresado en unidades de tiempo (más
                # intuitivo para el revisor: "cuántas horas aguanta" en vez de solo litros).
                # Equivalencia algebraica exacta: autonomía ≥ Tiempo total ⟺ Vol ≥ Volumen mínimo
                # (ambas expresan la misma desigualdad, solo reordenada).
                delta_q_ls = caudal_operacion_ls - caudal_disponible_ls
                r["delta_q_estanque_ls"] = round(max(delta_q_ls, 0.0), 3)
                if delta_q_ls > 0:
                    r["autonomia_estanque_hr"] = round(vol_litros / (delta_q_ls * 3600), 2)
                r["tiempo_llenado_estanque_hr"] = round(vol_litros / (caudal_disponible_ls * 3600), 2)

    return r


def verificacion_vib(vib_mmhr: float, precipitacion_mmhr: float) -> dict:
    """Verifica que la Velocidad de Infiltración Básica (VIB) del suelo supere la precipitación
    (velocidad de aplicación) del sistema de riego — si no, hay riesgo de escorrentía. Aplica
    solo a Aspersión (Goteo no la usa — aplica agua directo al bulbo húmedo, no en área). Mismo
    criterio del Diseñador de Riego ("VIB > VA" en aspersión, "Pls ≤ VIB" en microaspersión)."""
    if not vib_mmhr or not precipitacion_mmhr:
        return {}
    return {"vib_ok": vib_mmhr > precipitacion_mmhr}


def postura_aspersion(caudal_aspersor_m3h: float, espaciamiento_aspersores_m: float,
                      espaciamiento_laterales_m: float, n_aspersores: float,
                      superficie_ha: float, vib_mmhr: float = None,
                      db_mm: float = None, horas_disponibles_dia: float = None,
                      tiempo_traslado_hr: float = 0.5) -> dict:
    """Recalcula la distribución por POSTURAS de un sistema de Aspersión — mismo criterio del
    Diseñador de Riego (`calcAspP`). Aspersión NO riega por "sectores" (concepto de
    `verificacion_diseno_riego`, que reparte el caudal requerido entre el caudal disponible —
    pensado para Goteo/Microaspersión): mueve un grupo FIJO de aspersores (`n_aspersores`, con su
    marco de espaciamiento) de una posición a otra, y cada posición es una "postura". El N° de
    posturas es geométrico (superficie total / superficie que cubre una postura), no depende del
    caudal disponible — por eso puede no coincider con el "N° de sectores" genérico, y es el que
    corresponde comparar contra lo que declara el consultor (el propio Diseñador anota
    "N_posturas = ⌈A_total/A_pos⌉ (= Fr)" — una vuelta completa de posturas equivale al ciclo de
    riego).

    VA[mm/hr]        = Q_aspersor[l/hr] / Marco[m²] = (Q_aspersor×1.000) / (Esp.asp×Esp.lat)
    A_postura[ha]    = Esp.asp × Esp.lat × N° aspersores / 10.000
    Q_postura[l/s]   = N° aspersores × Q_aspersor / 3,6           (caudal simultáneo de la postura)
    N_posturas       = ⌈Superficie del proyecto / A_postura⌉
    T_postura[hr]    = Db / VA           (tiempo para aplicar la demanda bruta a esa velocidad —
                       necesita Db, la cadena agronómica completa)
    Posturas/día     = ⌊Horas disponibles / (T_postura + T_traslado)⌋   (T_traslado entre
                       posturas: 0,5 hr por defecto, mismo valor del Diseñador)
    Días necesarios  = ⌈N_posturas / Posturas_día⌉  (ago-2026, Diseñador v121 — cuántos días
                       toma completar el ciclo de riego con las posturas/día que rinden las
                       horas disponibles)

    VA, A_postura, Q_postura y N_posturas son independientes del resto de la cadena agronómica
    (no necesitan AD/Dn/Fr/Db) — todos los argumentos salvo `vib_mmhr`/`db_mm`/
    `horas_disponibles_dia` son obligatorios. T_postura y Posturas/día solo se calculan si se
    pasa `db_mm` (y, además, `horas_disponibles_dia` para Posturas/día); Días_necesarios solo si
    Posturas/día resulta mayor que 0 (con menos horas que un traslado+postura, no se puede regar
    ni una postura al día — no hay ciclo posible que reportar)."""
    if not all([caudal_aspersor_m3h, espaciamiento_aspersores_m, espaciamiento_laterales_m,
                n_aspersores, superficie_ha]):
        return {}
    va_mmhr = (caudal_aspersor_m3h * 1000) / (espaciamiento_aspersores_m * espaciamiento_laterales_m)
    sup_postura_ha = (espaciamiento_aspersores_m * espaciamiento_laterales_m * n_aspersores) / 10000
    q_postura_ls = n_aspersores * caudal_aspersor_m3h / 3.6
    n_posturas = math.ceil(superficie_ha / sup_postura_ha) if sup_postura_ha else 0
    r = {
        "va_mmhr": round(va_mmhr, 2),
        "superficie_postura_ha": round(sup_postura_ha, 3),
        "caudal_postura_ls": round(q_postura_ls, 3),
        "n_posturas": n_posturas,
    }
    if vib_mmhr:
        r["vib_ok"] = vib_mmhr > va_mmhr
    if db_mm and va_mmhr:
        tiempo_postura_hr = db_mm / va_mmhr
        r["tiempo_postura_hr"] = round(tiempo_postura_hr, 2)
        if horas_disponibles_dia:
            t_trasl = tiempo_traslado_hr if tiempo_traslado_hr is not None else 0.5
            posturas_dia = math.floor(horas_disponibles_dia / (tiempo_postura_hr + t_trasl))
            r["posturas_dia"] = posturas_dia
            if posturas_dia > 0:
                r["dias_necesarios"] = math.ceil(n_posturas / posturas_dia)
    return r


# ── Carrete de riego (cañón viajero): modelo INIA-Carillanca 2001 (Simpfendörfer) ───────────

ANGULO_SECTOR_CARRETE_DEG = 210    # ángulo de sector INIA por DEFECTO (usado solo si el
                                    # expediente no lo declara — rango recomendado 200-220°)
ANGULO_SECTOR_CARRETE_MIN = 200    # rango recomendado INIA — fuera de este rango, advertir
ANGULO_SECTOR_CARRETE_MAX = 220
VIB_MINIMA_CARRETE_MMHR = 7.5      # INIA-Carillanca: mínimo exigido para que el suelo sea apto


def _pct_espaciamiento_viento(vv_ms: float) -> float:
    """Porcentaje del diámetro mojado usado como espaciamiento entre franjas del cañón, según
    la velocidad del viento — tabla INIA-Carillanca (Cuadro 1), igual que el Diseñador de Riego."""
    if vv_ms <= 1:
        return 0.80
    if vv_ms <= 2.5:
        return 0.75
    if vv_ms <= 5:
        return 0.625
    return 0.525


def diseno_carrete(caudal_catalogo_m3h: float, margen_sobredim_pct: float, radio_alcance_m: float,
                   velocidad_viento_ms: float, longitud_franja_m: float, velocidad_avance_mh: float,
                   superficie_ha: float, vib_mmhr: float = None, horas_disponibles_dia: float = None,
                   tiempo_cambio_postura_hr: float = None, angulo_sector_deg: float = None) -> dict:
    """Recalcula los parámetros de operación de un carrete de riego (cañón viajero) con el
    modelo INIA-Carillanca 2001 (Simpfendörfer) — la misma fórmula que usa el Diseñador de Riego
    (`calcCarP`, leída directo de su código fuente). A diferencia de goteo/microaspersión/
    aspersión (turnos con agotamiento AD→Dn→Fr→Db), el carrete no se diseña por "sectores de
    riego" sino por POSTURAS del cañón — posiciones sucesivas donde se detiene a regar una
    franja de terreno.

    Q_diseño[m³/hr]  = Q_catálogo × (1 + margen/100)      — sobredimensionado 15-20% (INIA:
                       cubre viento fuerte, mayor demanda del cultivo o averías)
    D_mojado[m]      = 2 × Radio de alcance
    %viento          = 80% (viento≤1 m/s) · 75% (≤2,5) · 62,5% (≤5) · 52,5% (>5)  — INIA Cuadro 1
    E_franjas[m]     = D_mojado × %viento                 — espaciamiento entre pasadas del cañón
    PP[mm/hr]        = Q_diseño / (π×(0,9×Radio)²) × (α/360) × 1000   — pluviometría media,
                       α=`angulo_sector_deg` si el expediente lo declara; si no, 210° por
                       defecto INIA (rango recomendado 200-220°; ago-2026 — antes α estaba fijo
                       en 210° sin extraerlo, y el ángulo mueve la PP hasta ±5% entre los
                       extremos del rango — relevante porque PP se compara contra la VIB y
                       contra el mínimo INIA de 7,5 mm/hr)
    A_postura[ha]    = (Longitud de franja × E_franjas) / 10.000
    N_posturas       = ⌈Superficie del proyecto / A_postura⌉
    L_manguera[m]    = máx(Longitud de franja/2 − 2/3×Radio, 10)
    Ti[hr]           = (2/3×Radio / V_avance) × (α/360)
    Tfe[hr]          = (2/3×Radio / V_avance) × (1 − α/360)
    T_postura[hr]    = L_manguera/V_avance + Ti + máx(Tfe, 0)
    Posturas/día     = ⌊Horas disponibles / (T_postura + T_cambio_postura)⌋   (ago-2026,
                       Diseñador v121 — T_cambio_postura: 1,5 hr por defecto si no se declara,
                       INIA-Carillanca: ≈1 hr cambio de posición + ≈0,5 hr puesta en posición)
    Días necesarios  = ⌈N_posturas / Posturas_día⌉

    Verificación VIB — DISTINTA de la de Aspersión (`verificacion_vib`, que compara contra la
    Precipitación del sistema declarada libremente por el consultor): acá el umbral es FIJO en
    7,5 mm/hr (INIA-Carillanca exige ese mínimo para que el suelo sea apto para carrete, sin
    importar el cañón elegido), y además se compara la VIB contra la Pluviometría (PP) recién
    calculada, no contra un dato declarado aparte.

    ADITIVO, no todo-o-nada (ago-2026): antes exigía los 6 datos base a la vez y devolvía {} si
    faltaba cualquiera. El usuario advirtió que, en la práctica, lo único que casi nunca se logra
    extraer del expediente es la velocidad del viento de diseño (y la VIB) — y esos dos datos NO
    son necesarios para Q_diseño, D_mojado, PP ni T_postura. Ahora cada resultado se calcula si
    están los datos que necesita — mismo criterio que el resto de `calculos_riego.py`
    (`verificacion_diseno_riego`, `cadena_agronomica`). Dependencias reales de cada salida:
      Q_diseño          → caudal_catalogo_m3h
      D_mojado          → radio_alcance_m
      PP                → caudal_catalogo_m3h, radio_alcance_m (NO necesita viento)
      E_franjas         → radio_alcance_m, velocidad_viento_ms
      A_postura         → longitud_franja_m, E_franjas (⇒ además radio y viento)
      N_posturas        → A_postura, superficie_ha
      T_postura         → radio_alcance_m, velocidad_avance_mh, longitud_franja_m (NO necesita
                          viento ni superficie)
      Posturas/día      → T_postura, horas_disponibles_dia (NO necesita viento ni N_posturas)
      Días necesarios   → Posturas/día, N_posturas (⇒ sí necesita viento, indirectamente)
    A diferencia de una verificación silenciosa, esta app NUNCA asume un viento medio por sector o
    suelo (a diferencia del Diseñador de Riego, que si el campo llega vacío completa un valor
    sugerido según su tabla INIA — ver `c-fv` en `exportar_disenador.py`): sin el dato declarado,
    los resultados que dependen de él simplemente no se calculan."""
    r = {}
    margen = margen_sobredim_pct if margen_sobredim_pct is not None else 15
    alfa = angulo_sector_deg if angulo_sector_deg is not None else ANGULO_SECTOR_CARRETE_DEG

    q_diseno_m3h = None
    if caudal_catalogo_m3h:
        q_diseno_m3h = caudal_catalogo_m3h * (1 + margen / 100)
        r["q_diseno_m3h"] = round(q_diseno_m3h, 1)
        r["q_diseno_ls"] = round(q_diseno_m3h / 3.6, 2)

    d_mojado = 2 * radio_alcance_m if radio_alcance_m else None
    if d_mojado is not None:
        r["d_mojado_m"] = round(d_mojado, 1)

    pp_mmhr = None
    if q_diseno_m3h and radio_alcance_m:
        pp_mmhr = q_diseno_m3h / (math.pi * (0.9 * radio_alcance_m) ** 2) * (alfa / 360) * 1000
        r["pluviometria_mmhr"] = round(pp_mmhr, 1)
        if vib_mmhr:
            r["vib_supera_pp"] = vib_mmhr > pp_mmhr
            r["vib_cumple_minimo_inia"] = vib_mmhr >= VIB_MINIMA_CARRETE_MMHR

    esp_franja = None
    if d_mojado is not None and velocidad_viento_ms is not None:
        esp_franja = d_mojado * _pct_espaciamiento_viento(velocidad_viento_ms)
        r["espaciamiento_franjas_m"] = round(esp_franja, 1)

    sup_postura_ha = None
    if longitud_franja_m and esp_franja is not None:
        sup_postura_ha = (longitud_franja_m * esp_franja) / 10000
        r["superficie_postura_ha"] = round(sup_postura_ha, 3)

    n_posturas = None
    if sup_postura_ha and superficie_ha:
        n_posturas = math.ceil(superficie_ha / sup_postura_ha)
        r["n_posturas"] = n_posturas

    t_postura_hr = None
    if radio_alcance_m and velocidad_avance_mh and longitud_franja_m:
        l_manguera = max(longitud_franja_m / 2 - (2 / 3) * radio_alcance_m, 10)
        ti = (2 / 3 * radio_alcance_m / velocidad_avance_mh) * (alfa / 360)
        tfe = (2 / 3 * radio_alcance_m / velocidad_avance_mh) * (1 - alfa / 360)
        t_postura_hr = l_manguera / velocidad_avance_mh + ti + max(tfe, 0)
        r["tiempo_postura_hr"] = round(t_postura_hr, 2)

    if t_postura_hr is not None and horas_disponibles_dia:
        t_cambio = tiempo_cambio_postura_hr if tiempo_cambio_postura_hr is not None else 1.5
        posturas_dia = max(0, math.floor(horas_disponibles_dia / (t_postura_hr + t_cambio)))
        r["posturas_dia"] = posturas_dia
        if posturas_dia > 0 and n_posturas is not None:
            r["dias_necesarios"] = math.ceil(n_posturas / posturas_dia)

    if pp_mmhr is not None or t_postura_hr is not None:
        r["angulo_sector_deg"] = alfa
        r["angulo_sector_declarado"] = angulo_sector_deg is not None
        if angulo_sector_deg is not None and not (ANGULO_SECTOR_CARRETE_MIN <= angulo_sector_deg <= ANGULO_SECTOR_CARRETE_MAX):
            r["angulo_sector_fuera_rango"] = True
    return r


# ── Fotovoltaico: energía requerida → N° paneles → configuración → cable DC ─

# Secciones normalizadas de cable de cobre (mm²), mismo criterio del Diseñador de Riego
SECCIONES_CABLE_MM2 = [4, 6, 10, 16, 25, 35, 50, 70]
RHO_CU = 1 / 58   # Ω·mm²/m — resistividad del cobre


def seccion_cable_normalizada(seccion_calculada_mm2: float) -> float:
    """Redondea hacia arriba a la sección comercial normalizada más cercana."""
    for s in SECCIONES_CABLE_MM2:
        if seccion_calculada_mm2 <= s:
            return s
    return SECCIONES_CABLE_MM2[-1]


def dimensionamiento_fv(pkw: float, hbom: float, hsp: float, fp: float, wp: float,
                        vmp: float, imp: float, ct: float, temp: float, einv: float,
                        vsis: float, l_cable_m: float = 50,
                        dias_riego: int = None, conexion: str = None) -> dict:
    """Recalcula el dimensionamiento fotovoltaico con la misma cadena que usa el Diseñador
    de Riego (v114):

    E_día      = P_bomba[kW] × H_bombeo[hr]                       [kWh/día requeridos]
    PR         = Fp × η_inv                                        [performance ratio]
    Derating   = 1 + (Ct/100) × (T_max − 25)                       [corrección por temperatura]
    Wp_efectivo= Wp_panel × Derating
    E_panel    = (Wp_ef/1000) × HSP × PR                           [kWh/panel/día]
    N_paneles  = ⌈E_día / E_panel⌉                                  [mínimo necesario]
    Serie      = ⌊V_sistema / Vmp⌋ · Paralelo = ⌈N_paneles/Serie⌉   [configuración real]
    kWp_total  = N_real × Wp / 1000
    Cable DC   = ρ_Cu × L × I_campo / (2% × V_campo)               [sección mm², normalizada]

    Balance Anual Energético (Manual CNR-Ministerio de Energía §5.1):
    Gen_día_real  = E_panel × N_real                               [kWh/día del campo completo]
    Gen_anual     = Gen_día_real × 365                             [el parque genera 365 días/año]
    Consumo_anual = P_bomba × H_bombeo × días_riego                [bomba solo consume días riego]
    Balance       = Gen_anual / Consumo_anual × 100 %
    balance_ok    = True si aislado (criterio no aplica); si on-grid, balance ≤ 100 %

    `pkw`: potencia de la bomba en kW. `hbom`: horas de bombeo/día. `hsp`: horas sol pico
    del sitio. `fp`: factor de pérdidas del sistema (0-1, típico 0,80). `wp`: potencia
    nominal del panel (Wp). `vmp`/`imp`: voltaje/corriente en el punto de máxima potencia
    del panel. `ct`: coeficiente de temperatura del panel (%/°C, típico negativo, ej. -0,35).
    `temp`: temperatura máxima del sitio (°C). `einv`: eficiencia del inversor (0-1, típico
    0,95). `vsis`: voltaje nominal del sistema/inversor (V).
    `dias_riego`: días efectivos de operación del sistema de riego al año (para balance anual).
    `conexion`: 'aislado' (default) o 'ongrid' — determina si aplica el criterio de 100%.
    """
    if not pkw or not hbom or not hsp or not wp or not vmp or not imp:
        return {}
    e_dia = pkw * hbom
    pr = (fp or 0.80) * (einv or 0.95)
    derating = 1 + ((ct or 0) / 100) * (temp - 25) if temp else 1.0
    wp_efectivo = wp * derating
    e_panel = (wp_efectivo / 1000) * hsp * pr
    n_paneles = math.ceil(e_dia / e_panel) if e_panel else 0
    pan_serie = max(1, math.floor((vsis or 0) / vmp)) if vsis else 1
    pan_paralelo = math.ceil(n_paneles / pan_serie) if pan_serie else n_paneles
    n_real = pan_serie * pan_paralelo
    kwp_total = n_real * wp / 1000
    i_campo = pan_paralelo * imp
    v_campo = pan_serie * vmp
    dv_max = v_campo * 0.02
    seccion_calc = (RHO_CU * l_cable_m * i_campo) / dv_max if dv_max else 0
    r = {
        "e_dia_kwh": round(e_dia, 3), "pr": round(pr, 3), "derating": round(derating, 4),
        "wp_efectivo": round(wp_efectivo, 1), "e_panel_kwh": round(e_panel, 4),
        "n_paneles_minimo": n_paneles, "paneles_serie": pan_serie,
        "strings_paralelo": pan_paralelo, "n_paneles_real": n_real,
        "kwp_total": round(kwp_total, 2), "i_campo_a": round(i_campo, 2),
        "v_campo_v": round(v_campo, 0),
        "seccion_cable_mm2": seccion_cable_normalizada(seccion_calc) if seccion_calc else None,
    }
    # Balance Anual Energético — solo si se ingresa días de riego
    if dias_riego:
        gen_dia_real = e_panel * n_real
        gen_anual = gen_dia_real * 365
        consumo_anual = pkw * hbom * dias_riego
        balance_anual = (gen_anual / consumo_anual * 100) if consumo_anual else 0
        es_ongrid = (conexion or "aislado") == "ongrid"
        r["gen_dia_real_kwh"] = round(gen_dia_real, 3)
        r["gen_anual_kwh"] = round(gen_anual, 1)
        r["consumo_anual_kwh"] = round(consumo_anual, 1)
        r["balance_anual_pct"] = round(balance_anual, 1)
        r["balance_ok"] = (balance_anual <= 100) if es_ongrid else None
    return r


MESES_3 = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
# Días por mes que usa el Revisor Fotovoltaico (fotovoltaico_riego_v15.html, const DIAS) —
# incluye feb=29 fijo (no depende del año del proyecto).
DIAS_MES_FV = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def demanda_fv_mensual(pkw: float, adic: float, horas_mensuales: list) -> dict:
    """Demanda energética mensual de la bomba con la MISMA fórmula que usa el Revisor
    Fotovoltaico (fotovoltaico_riego_v15.html, función calc()):

    Dem_día[mes] = Horas_riego[mes] × P_bomba × (1 + Adicionales%/100)   [kWh/día]
    Dem_mes[mes] = Dem_día[mes] × Días_del_mes                          [kWh/mes]
    Dem_anual    = Σ Dem_mes[mes]                                       [kWh/año]

    Es la única parte de la metodología del Revisor Fotovoltaico que Revisor CNR puede
    recalcular de forma determinística: la generación, cobertura y potencia requerida
    dependen del perfil solar horario del predio (Explorador Solar), que solo se importa
    dentro del propio Revisor Fotovoltaico — no se replica acá.

    `pkw`: potencia de la bomba (kW). `adic`: consumos adicionales declarados (%, ej. 5).
    `horas_mensuales`: lista de 12 valores (horas de riego promedio/día por mes, Ene→Dic;
    None o 0 en meses sin riego). Devuelve {} si falta la potencia de la bomba o no hay
    ningún mes con horas declaradas."""
    if not pkw or not horas_mensuales or not any(h for h in horas_mensuales if h):
        return {}
    adic_pct = adic if adic is not None else 0
    meses = []
    dem_anual = 0.0
    horas_excedidas = []
    for i in range(12):
        h = horas_mensuales[i] if i < len(horas_mensuales) and horas_mensuales[i] is not None else 0
        if h > 24:
            horas_excedidas.append(MESES_3[i])
        dem_dia = h * pkw * (1 + adic_pct / 100)
        dem_mes = dem_dia * DIAS_MES_FV[i]
        dem_anual += dem_mes
        meses.append({"mes": MESES_3[i], "horas": h,
                      "dem_dia_kwh": round(dem_dia, 3), "dem_mes_kwh": round(dem_mes, 1)})
    return {"meses": meses, "dem_anual_kwh": round(dem_anual, 1),
            "horas_excedidas": horas_excedidas}
