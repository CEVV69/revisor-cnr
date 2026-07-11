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
                      eficiencia_pct: float) -> dict:
    """Recalcula la demanda agronómica con la misma cadena que usa el Diseñador de Riego:

    ETc    = ETo × Kc
    AD     = (CC − PMP)/100 × Da × Prof(m) × 1000     [mm — agua disponible del suelo]
    Dn     = AD × fa                                   [mm — lámina neta de riego]
    Fr     = Dn / ETc  →  Fr_adj = floor(Fr) (mín. 1)   [días — frecuencia de riego]
    Dn_adj = ETc × Fr_adj
    Db     = Dn_adj / Ef                                [mm — demanda bruta]
    """
    etc = eto_dia_mm * kc
    ad = (cc_pct - pmp_pct) / 100 * da * (prof_cm / 100) * 1000
    dn = ad * (factor_agotamiento_pct / 100)
    fr = dn / etc if etc else 0
    fr_adj = max(1, math.floor(fr)) if fr else 1
    dn_adj = etc * fr_adj
    db = dn_adj / (eficiencia_pct / 100) if eficiencia_pct else 0
    return {
        "etc_mm_dia": round(etc, 3), "ad_mm": round(ad, 2), "dn_mm": round(dn, 3),
        "fr_dias": round(fr, 2), "fr_adj_dias": fr_adj, "dn_adj_mm": round(dn_adj, 3),
        "db_mm": round(db, 3),
    }


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
