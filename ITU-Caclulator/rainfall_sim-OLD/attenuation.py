"""
High-level attenuation functions built on itu_coeffs.

This mirrors:
  specificAtten(f,R)
  kAlpha(f)
  gamma vs frequency / rain arrays
from your React ITU Calculator view.
"""

from __future__ import annotations
from typing import List, Literal, Tuple

from .itu_coeffs import k_alpha, PolType


def specific_attenuation(
    f_ghz: float, R_mm_per_h: float, pol: PolType
) -> float:
    """
    γ(f,R) in dB/km.
    γ(f,R) = k(f) * R^α(f)
    """
    k, alpha = k_alpha(f_ghz, pol)
    return k * (R_mm_per_h ** alpha)


def path_attenuation(
    d_km: float, f_ghz: float, R_mm_per_h: float, pol: PolType
) -> float:
    """
    Path attenuation over length d_km [km], in dB.
    """
    return specific_attenuation(f_ghz, R_mm_per_h, pol) * d_km


def gamma_vs_frequency(
    R_mm_per_h: float,
    pol: PolType,
    f_min: float = 1.0,
    f_max: float = 100.0,
    n_points: int = 41,
):
    """
    Return list of {f, gamma} for f in [f_min..f_max] (inclusive).
    Same sampling as your JS (1–100 GHz, 41 points).
    """
    out = []
    for i in range(n_points):
        f = f_min + (f_max - f_min) * i / (n_points - 1)
        g = specific_attenuation(f, R_mm_per_h, pol)
        out.append({"f": f, "g": g})
    return out


def gamma_vs_rain(
    f_ghz: float,
    pol: PolType,
    R_min: float = 0.1,
    R_max: float = 100.0,
    n_points: int = 41,
):
    """
    Return list of {R, gamma} for R in [R_min..R_max].
    Same sampling as your JS (0.1–100 mm/h, 41 points).
    """
    out = []
    for i in range(n_points):
        R = R_min + (R_max - R_min) * i / (n_points - 1)
        g = specific_attenuation(f_ghz, R, pol)
        out.append({"R": R, "g": g})
    return out

