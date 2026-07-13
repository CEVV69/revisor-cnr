"""
Conversión de coordenadas UTM (WGS84) a latitud/longitud, para ubicar en Google Maps el
punto que el consultor declara en el Resumen del proyecto (Coordenada E, Coordenada N, Huso).
Fórmula estándar de Snyder (USGS Professional Paper 1395) sobre el elipsoide WGS84 — la misma
que usan las librerías de conversión UTM habituales. Función pura, sin dependencias externas.

Se asume datum WGS84/SIRGAS-Chile (prácticamente coincidentes para este uso) y hemisferio sur
(todo Chile continental) — suficiente precisión para ubicar un pin en un mapa, no para deslinde.
"""
import math

_A = 6378137.0          # semieje mayor, elipsoide WGS84 (m)
_E2 = 0.00669438         # excentricidad al cuadrado, WGS84
_K0 = 0.9996              # factor de escala UTM
_EP2 = _E2 / (1 - _E2)

_SQRT_E = math.sqrt(1 - _E2)
_E1 = (1 - _SQRT_E) / (1 + _SQRT_E)

_M1 = 1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256
_P2 = 3.0 / 2 * _E1 - 27.0 / 32 * _E1 ** 3 + 269.0 / 512 * _E1 ** 5
_P3 = 21.0 / 16 * _E1 ** 2 - 55.0 / 32 * _E1 ** 4
_P4 = 151.0 / 96 * _E1 ** 3 - 417.0 / 128 * _E1 ** 5
_P5 = 1097.0 / 512 * _E1 ** 4


def utm_a_latlon(este: float, norte: float, huso: int, hemisferio_sur: bool = True):
    """Convierte coordenadas UTM (este, norte, huso) a (latitud, longitud) en grados
    decimales WGS84. `hemisferio_sur=True` por defecto (todo Chile continental)."""
    x = este - 500000.0
    y = norte - 10000000.0 if hemisferio_sur else norte

    m = y / _K0
    mu = m / (_A * _M1)

    p_rad = (mu + _P2 * math.sin(2 * mu) + _P3 * math.sin(4 * mu)
             + _P4 * math.sin(6 * mu) + _P5 * math.sin(8 * mu))
    p_sin, p_cos = math.sin(p_rad), math.cos(p_rad)
    p_tan = p_sin / p_cos
    p_tan2, p_tan4 = p_tan ** 2, p_tan ** 4

    ep_sin2 = 1 - _E2 * p_sin ** 2
    n = _A / math.sqrt(ep_sin2)
    r = (1 - _E2) / ep_sin2

    c = _EP2 * p_cos ** 2
    c2 = c * c

    d = x / (n * _K0)
    d2, d3, d4, d5, d6 = d ** 2, d ** 3, d ** 4, d ** 5, d ** 6

    lat_rad = (p_rad - (p_tan / r) * (
        d2 / 2 - d4 / 24 * (5 + 3 * p_tan2 + 10 * c - 4 * c2 - 9 * _EP2))
        + d6 / 720 * (61 + 90 * p_tan2 + 298 * c + 45 * p_tan4 - 252 * _EP2 - 3 * c2))

    lon_rad = (d - d3 / 6 * (1 + 2 * p_tan2 + c)
               + d5 / 120 * (5 - 2 * c + 28 * p_tan2 - 3 * c2 + 8 * _EP2 + 24 * p_tan4)) / p_cos

    lon_central = (huso - 1) * 6 - 180 + 3
    longitud = math.degrees(lon_rad) + lon_central
    latitud = math.degrees(lat_rad)
    return latitud, longitud
