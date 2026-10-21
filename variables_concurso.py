"""Cálculo determinístico del "Cuadro de Variables de Concurso" para Modificaciones de Proyecto
(oct-2026) — compara costo/bonificación/superficie entre el proyecto ORIGINAL ya bonificado y el
MODIFICADO que se está solicitando.

Basado en el Excel oficial que presentan los consultores ("Cuadro_variables_de_concurso.xlsx"),
con UNA corrección deliberada sobre su fórmula literal: el Excel calcula la bonificación modificada
como `(1 - aporte%) × costo_modificado` con el mismo aporte% que el original SIEMPRE — lo que haría
SUBIR la bonificación si el costo modificado sube. Esa fórmula solo es correcta cuando el costo baja
o se mantiene. El usuario (revisor CNR) confirmó explícitamente (oct-2026) la regla real: la
bonificación NUNCA puede superar la original — si el costo sube, el 100% del aumento lo asume el
beneficiario (la bonificación queda congelada en el monto original, y el aporte% EFECTIVO del
modificado sube, no se mantiene); si el costo baja, la bonificación baja proporcional manteniendo
el mismo aporte% (ahí sí coincide con la fórmula del Excel). Esto es "para mantener las variables
que le dieron puntaje en el concurso original" (cita textual del usuario).

El indicador "variable_concurso" (OK/ERROR) replica el chequeo H14 del Excel oficial (costo por
hectárea no debe empeorar) — es un chequeo DISTINTO al de la bonificación, sobre la eficiencia de
costo que puntuó en el concurso original.
"""


def _div(a, b):
    return a / b if b else None


def calcular_variables_concurso(datos: dict) -> dict:
    """`datos`: {"original": {...}, "modificado": {...}}, cada uno con:
    superficie_ha, metodo, superficie_beneficiada_ha, costo_uf, n_beneficiarios, aporte_pct
    (0-1). `aporte_pct` del modificado es ignorado si viene — el aporte% original es el dato de
    entrada; el del modificado siempre se CALCULA acá (ver regla de congelamiento arriba).

    Devuelve {"original": {...calculado...}, "modificado": {...calculado...},
    "variable_concurso_ok": bool, "diferencia_costo_uf": float,
    "monto_asumido_beneficiario_uf": float, "diferencia_bonificacion_uf": float}."""
    o = datos.get("original", {})
    m = datos.get("modificado", {})

    costo_o = o.get("costo_uf") or 0.0
    sup_benef_o = o.get("superficie_beneficiada_ha") or 0.0
    aporte_o = o.get("aporte_pct")
    bonif_o = (1 - aporte_o) * costo_o if aporte_o is not None else None
    sup_ponderada_o = sup_benef_o  # igual a la beneficiada, mismo criterio que el Excel oficial
    costo_ha_o = _div(costo_o, sup_benef_o)
    s2_c_o = _div(sup_ponderada_o, costo_o)

    costo_m = m.get("costo_uf") or 0.0
    sup_benef_m = m.get("superficie_beneficiada_ha") or 0.0
    sup_ponderada_m = sup_benef_m
    costo_ha_m = _div(costo_m, sup_benef_m)
    s2_c_m = _div(sup_ponderada_m, costo_m)

    if aporte_o is None or bonif_o is None:
        bonif_m = None
        aporte_m = None
    elif costo_m <= costo_o:
        # Costo baja o se mantiene: mismo aporte%, bonificación baja (o se mantiene) proporcional.
        aporte_m = aporte_o
        bonif_m = (1 - aporte_o) * costo_m
    else:
        # Costo sube: bonificación queda CONGELADA en el monto original — el 100% del aumento lo
        # asume el beneficiario. El aporte% efectivo del modificado sube (no se mantiene).
        bonif_m = bonif_o
        aporte_m = 1 - _div(bonif_o, costo_m) if costo_m else None

    variable_concurso_ok = (costo_ha_m is not None and costo_ha_o is not None
                             and costo_ha_m <= costo_ha_o)

    diferencia_costo_uf = costo_m - costo_o
    diferencia_bonificacion_uf = (bonif_m - bonif_o) if (bonif_m is not None and bonif_o is not None) else None
    monto_asumido_beneficiario_uf = max(0.0, diferencia_costo_uf)

    return {
        "original": {
            "superficie_ha": o.get("superficie_ha"), "metodo": o.get("metodo"),
            "superficie_beneficiada_ha": sup_benef_o, "superficie_ponderada_ha": sup_ponderada_o,
            "costo_uf": costo_o, "n_beneficiarios": o.get("n_beneficiarios"),
            "aporte_pct": aporte_o, "bonificacion_uf": bonif_o,
            "costo_ha": costo_ha_o, "s2_c": s2_c_o,
        },
        "modificado": {
            "superficie_ha": m.get("superficie_ha"), "metodo": m.get("metodo"),
            "superficie_beneficiada_ha": sup_benef_m, "superficie_ponderada_ha": sup_ponderada_m,
            "costo_uf": costo_m, "n_beneficiarios": m.get("n_beneficiarios"),
            "aporte_pct": aporte_m, "bonificacion_uf": bonif_m,
            "costo_ha": costo_ha_m, "s2_c": s2_c_m,
        },
        "variable_concurso_ok": variable_concurso_ok,
        "diferencia_costo_uf": diferencia_costo_uf,
        "diferencia_bonificacion_uf": diferencia_bonificacion_uf,
        "monto_asumido_beneficiario_uf": monto_asumido_beneficiario_uf,
    }
