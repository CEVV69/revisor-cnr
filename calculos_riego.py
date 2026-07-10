"""
Fórmulas de ingeniería de riego (hidráulica y agronómica), portadas del Diseñador de Riego
(misma fuente normativa: Manuales e Instructivos CNR en Drive — Hazen-Williams, cadena de
demanda agronómica ETo→ETc→AD→Dn→Fr→Db).

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
