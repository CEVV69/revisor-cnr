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


def factor_christiansen(n_salidas: int) -> float:
    """Factor de corrección de Christiansen para tuberías con salidas múltiples
    equiespaciadas (típico en laterales/terciarias de goteo). m=1,852 (Hazen-Williams)."""
    if not n_salidas or n_salidas <= 1:
        return 1.0
    m = 1.852
    return 1 / (m + 1) + 1 / (2 * n_salidas) + math.sqrt(m + 1) / (6 * n_salidas ** 2)


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


# ── Agronómico: cadena ETo → ETc → AD → Dn → Fr → Db ────────────────────────

def cadena_agronomica(cc_pct: float, pmp_pct: float, da: float, prof_cm: float,
                      kc: float, eto_dia_mm: float, factor_agotamiento_pct: float,
                      eficiencia_pct: float, alta_frecuencia: bool = False) -> dict:
    """Recalcula la demanda agronómica con la misma cadena que usa el Diseñador de Riego.

    ETc = ETo × Kc, siempre. Después hay DOS modelos según el sistema de riego:

    · Aspersión / Carrete / Microaspersión (por turnos, con agotamiento — `alta_frecuencia=False`):
        AD     = (CC − PMP)/100 × Da × Prof(m) × 1000   [mm — agua disponible del suelo]
        Dn     = AD × fa                                 [mm — lámina neta de riego]
        Fr     = Dn / ETc  →  Fr_adj = floor(Fr) (mín. 1) [días — frecuencia de riego]
        Dn_adj = ETc × Fr_adj
        Db     = Dn_adj / Ef                             [mm — demanda bruta]

    · Goteo (riego localizado de ALTA FRECUENCIA — `alta_frecuencia=True`): se riega a diario
        reponiendo la ETc del día, así que la demanda bruta sale DIRECTO de la ETc, sin pasar
        por el factor de agotamiento (Fr = 1). Es el modelo `calcGA` del Diseñador de Riego —
        por eso goteo no tiene campo "criterio de riego":
        Db = ETc / Ef,  Fr_adj = 1,  Dn = Dn_adj = ETc

    `factor_agotamiento_pct` se ignora cuando `alta_frecuencia=True` (puede venir None). AD se
    calcula igual (dato informativo) si están CC/PMP/Da/Prof; si falta alguno, queda None.
    """
    etc = eto_dia_mm * kc
    if None not in (cc_pct, pmp_pct, da, prof_cm):
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
        fr_adj = max(1, math.floor(fr)) if fr else 1
        dn_adj = etc * fr_adj
    db = dn_adj / (eficiencia_pct / 100) if eficiencia_pct else 0
    return {
        "etc_mm_dia": round(etc, 3), "ad_mm": round(ad, 2) if ad is not None else None,
        "dn_mm": round(dn, 3), "fr_dias": round(fr, 2), "fr_adj_dias": fr_adj,
        "dn_adj_mm": round(dn_adj, 3), "db_mm": round(db, 3),
    }


def verificacion_diseno_riego(db_mm_dia: float, superficie_ha: float = None,
                              caudal_disponible_ls: float = None,
                              precipitacion_mmhr: float = None,
                              horas_disponibles_dia: float = None,
                              volumen_acumulador_m3: float = None) -> dict:
    """Recalcula los resultados base del diseño de riego a partir de la demanda bruta (Db) —
    misma relación que usan los sistemas localizados (goteo/microaspersión) del Diseñador de
    Riego. Aspersión/carrete usan ahí un modelo de "posturas" más elaborado (caudal y tiempo
    por postura, N° de posturas por superficie) que no se replica acá a propósito — esto es
    una verificación general de la relación demanda↔caudal↔tiempo↔sectores↔volumen, no un
    diseño completo por tipo de sistema:

    Demanda[l/s/ha]         = Db / 8,64                    (1 mm/día/ha = 1/8,64 l/s/ha)
    Superficie riego segura = Caudal de la FUENTE / Demanda[l/s/ha]
    Tiempo de riego         = Db / Precipitación del sistema declarada   [hr/día — por sector,
                              independiente del área total]

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

    (El Diseñador calcula `Q_requerido` a partir del N° de emisores real; acá se deriva de
    Precipitación×Superficie, matemáticamente equivalente — ver CLAUDE.md para la derivación —
    y evita depender de datos de marco/emisores que no siempre se pueden extraer con
    confianza del expediente.)

    Cada resultado solo se calcula si están los datos que necesita — es aditivo, no todo o
    nada. `caudal_disponible_ls` habilita la superficie segura; `precipitacion_mmhr` habilita
    el tiempo de riego; el N° de sectores y el resto de las verificaciones necesitan
    precipitación + superficie; `horas_disponibles_dia` habilita la verificación de si el N° de
    sectores calculado cabe en el día."""
    r = {}
    if not db_mm_dia:
        return r
    demanda_ls_ha = db_mm_dia / 8.64
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

        r["caudal_operacion_ls"] = round(q_requerido_total_ls / n_sectores, 3)

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

    return r


def verificacion_vib(vib_mmhr: float, precipitacion_mmhr: float) -> dict:
    """Verifica que la Velocidad de Infiltración Básica (VIB) del suelo supere la precipitación
    (velocidad de aplicación) del sistema de riego — si no, hay riesgo de escorrentía. Aplica
    solo a Aspersión (Goteo no la usa — aplica agua directo al bulbo húmedo, no en área). Mismo
    criterio del Diseñador de Riego ("VIB > VA" en aspersión, "Pls ≤ VIB" en microaspersión)."""
    if not vib_mmhr or not precipitacion_mmhr:
        return {}
    return {"vib_ok": vib_mmhr > precipitacion_mmhr}


def caudal_postura_aspersion(n_aspersores: float, caudal_aspersor_m3h: float) -> dict:
    """Caudal de trabajo de una postura de aspersión — mismo criterio del Diseñador de Riego
    (`calcAspP`): el caudal que exige simultáneamente una postura es la suma de todos los
    aspersores abiertos a la vez, convertido de m³/hr a l/s:
        Q_postura[l/s] = N° aspersores × Q_aspersor[m³/hr] / 3,6
    Solo aplica a Aspersión (Carrete usa un único cañón regador, no "aspersores por postura")."""
    if not n_aspersores or not caudal_aspersor_m3h:
        return {}
    return {"caudal_postura_ls": round(n_aspersores * caudal_aspersor_m3h / 3.6, 3)}


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
                        vsis: float, l_cable_m: float = 50) -> dict:
    """Recalcula el dimensionamiento fotovoltaico con la misma cadena que usa el Diseñador
    de Riego:

    E_día      = P_bomba[kW] × H_bombeo[hr]                       [kWh/día requeridos]
    PR         = Fp × η_inv                                        [performance ratio]
    Derating   = 1 + (Ct/100) × (T_max − 25)                       [corrección por temperatura]
    Wp_efectivo= Wp_panel × Derating
    E_panel    = (Wp_ef/1000) × HSP × PR                           [kWh/panel/día]
    N_paneles  = ⌈E_día / E_panel⌉                                  [mínimo necesario]
    Serie      = ⌊V_sistema / Vmp⌋ · Paralelo = ⌈N_paneles/Serie⌉   [configuración real]
    kWp_total  = N_real × Wp / 1000
    Cable DC   = ρ_Cu × L × I_campo / (2% × V_campo)               [sección mm², normalizada]

    `pkw`: potencia de la bomba en kW. `hbom`: horas de bombeo/día. `hsp`: horas sol pico
    del sitio. `fp`: factor de pérdidas del sistema (0-1, típico 0,80). `wp`: potencia
    nominal del panel (Wp). `vmp`/`imp`: voltaje/corriente en el punto de máxima potencia
    del panel. `ct`: coeficiente de temperatura del panel (%/°C, típico negativo, ej. -0,35).
    `temp`: temperatura máxima del sitio (°C). `einv`: eficiencia del inversor (0-1, típico
    0,95). `vsis`: voltaje nominal del sistema/inversor (V).
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
    return {
        "e_dia_kwh": round(e_dia, 3), "pr": round(pr, 3), "derating": round(derating, 4),
        "wp_efectivo": round(wp_efectivo, 1), "e_panel_kwh": round(e_panel, 4),
        "n_paneles_minimo": n_paneles, "paneles_serie": pan_serie,
        "strings_paralelo": pan_paralelo, "n_paneles_real": n_real,
        "kwp_total": round(kwp_total, 2), "i_campo_a": round(i_campo, 2),
        "v_campo_v": round(v_campo, 0),
        "seccion_cable_mm2": seccion_cable_normalizada(seccion_calc) if seccion_calc else None,
    }
