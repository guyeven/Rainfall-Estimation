"""ITU-R P.838-3 specific rain attenuation model.

Implements:
    gamma_R(f, R) = k(f) * R**alpha(f)

using equations (1)–(5) and Tables 1–4 of Rec. ITU-R P.838-3
for horizontal, vertical and circular polarization.

This file is copied from the provided ITU code (lightly trimmed of comments).
"""

import math
from typing import Literal, Tuple

Pol = Literal["horizontal", "vertical", "circular"]

K_H_COEFFS = [
    (-5.33980, -0.10008, 1.13098),
    (-0.35351, 1.26970, 0.45400),
    (-0.23789, 0.86036, 0.15354),
    (-0.94158, 0.64552, 0.16817),
]
MK_H = -0.18961
CK_H = 0.71147

K_V_COEFFS = [
    (-3.80595, 0.56934, 0.81061),
    (-3.44965, -0.22911, 0.51059),
    (-0.39902, 0.73042, 0.11899),
    (0.50167, 1.07319, 0.27195),
]
MK_V = -0.16398
CK_V = 0.63297

ALPHA_H_COEFFS = [
    (-0.14318, 1.82442, -0.55187),
    (0.29591, 0.77564, 0.19822),
    (0.32177, 0.63773, 0.13164),
    (-5.37610, -0.96230, 1.47828),
    (16.17210, -3.29980, 3.43990),
]
MA_H = 0.67849
CA_H = -1.95537

ALPHA_V_COEFFS = [
    (-0.07771, 2.33840, -0.76284),
    (0.56727, 0.95545, 0.54039),
    (-0.20238, 1.14520, 0.26809),
    (-48.2991, 0.791669, 0.116226),
    (48.5833, 0.791459, 0.116479),
]
MA_V = -0.053739
CA_V = 0.83433


def _sum_gaussians(logf: float, coeffs, m: float, c: float) -> float:
    s = 0.0
    for a, b, cc in coeffs:
        s += a * math.exp(-((logf - b) / cc) ** 2)
    return s + m * logf + c


def k_alpha_H(f_ghz: float) -> Tuple[float, float]:
    logf = math.log10(f_ghz)
    log10_k = _sum_gaussians(logf, K_H_COEFFS, MK_H, CK_H)
    k = 10 ** log10_k
    alpha = _sum_gaussians(logf, ALPHA_H_COEFFS, MA_H, CA_H)
    return k, alpha


def k_alpha_V(f_ghz: float) -> Tuple[float, float]:
    logf = math.log10(f_ghz)
    log10_k = _sum_gaussians(logf, K_V_COEFFS, MK_V, CK_V)
    k = 10 ** log10_k
    alpha = _sum_gaussians(logf, ALPHA_V_COEFFS, MA_V, CA_V)
    return k, alpha


def k_alpha(f_ghz: float, pol: Pol, elevation_deg: float = 0.0) -> Tuple[float, float]:
    kH, aH = k_alpha_H(f_ghz)
    kV, aV = k_alpha_V(f_ghz)

    if pol == "horizontal":
        tau_deg = 0.0
    elif pol == "vertical":
        tau_deg = 90.0
    elif pol == "circular":
        tau_deg = 45.0
    else:
        raise ValueError(f"Unknown polarization: {pol}")

    theta = math.radians(elevation_deg)
    tau = math.radians(tau_deg)

    cos_theta_sq = math.cos(theta) ** 2
    cos_2tau = math.cos(2 * tau)

    k = 0.5 * (kH + kV + (kH - kV) * cos_theta_sq * cos_2tau)

    num = kH * aH + kV * aV + (kH * aH - kV * aV) * cos_theta_sq * cos_2tau
    alpha = num / (2 * k)

    return k, alpha


def gamma_specific(f_ghz: float, R_mm_per_h: float, pol: Pol) -> float:
    if R_mm_per_h <= 0:
        return 0.0
    k, alpha = k_alpha(f_ghz, pol)
    return k * (R_mm_per_h ** alpha)
