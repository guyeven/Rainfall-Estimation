"""
ITU-R P.838-3 coefficient tables and low-level helpers.

This mirrors the kH, kV, aH, aV + sumExp + k_from_params + alpha_from_params
+ combineLinear + k_alpha logic from your React canvas code.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Literal, Tuple

# Standard parameters for k_H, k_V, a_H, a_V as functions of f (GHz)
# with x = log10(f). These match your React code.

kH = {
    "a": [-5.3398, -0.35351, -0.23789, -0.94158],
    "b": [-0.10008, 1.2697, 0.86036, 0.64552],
    "c": [1.13098, 0.454, 0.15354, 0.16817],
    "m": -0.18961,
    "c0": 0.71147,
}
kV = {
    "a": [-3.80595, -3.44965, -0.39902, 0.50167],
    "b": [0.56934, -0.22911, 0.73042, 1.07319],
    "c": [0.81061, 0.51059, 0.11899, 0.27195],
    "m": -0.16398,
    "c0": 0.63297,
}
aH = {
    "a": [-0.14318, 0.29591, 0.32177, -5.3761, 16.1721],
    "b": [1.82442, 0.77564, 0.63773, -0.9623, -3.2998],
    "c": [-0.55187, 0.19822, 0.13164, 1.47828, 3.4399],
    "m": 0.67849,
    "c0": -1.95537,
}
aV = {
    "a": [-0.07771, 0.56727, -0.20238, -48.2991, 48.5833],
    "b": [2.3384, 0.95545, 1.1452, 0.791669, 0.791459],
    "c": [-0.76284, 0.54039, 0.26809, 0.116226, 0.116479],
    "m": -0.053739,
    "c0": 0.83433,
}


def sum_exp(x: float, A, B, C) -> float:
    """sum_j A_j * exp( - ((x - B_j)/C_j)^2 )."""
    s = 0.0
    for aj, bj, cj in zip(A, B, C):
        t = (x - bj) / cj
        s += aj * math.exp(-(t * t))
    return s


def k_from_params(f_ghz: float, P: dict) -> float:
    """
    k(f) in linear units (not dB).
    f_ghz: frequency in GHz.
    """
    x = math.log10(f_ghz)
    log10k = sum_exp(x, P["a"], P["b"], P["c"]) + P["m"] * x + P["c0"]
    return 10 ** log10k


def alpha_from_params(f_ghz: float, P: dict) -> float:
    """alpha(f): power-law exponent."""
    x = math.log10(f_ghz)
    return sum_exp(x, P["a"], P["b"], P["c"]) + P["m"] * x + P["c0"]


PolType = Literal["H", "V", "Circular"]


def combine_linear(
    kH_val: float,
    kV_val: float,
    aH_val: float,
    aV_val: float,
    theta_deg: float,
    tau_deg: float,
) -> Tuple[float, float]:
    """
    Combine H and V to arbitrary linear polarization.

    This is the same formula used in your JS:
      c = cos^2(theta) * cos(2*tau)
      k = (kH + kV + (kH - kV)*c)/2
      alpha = (kH*aH + kV*aV + (kH*aH - kV*aV)*c) / (2*k)
    """
    th = math.radians(theta_deg)
    tau = math.radians(tau_deg)
    c = math.cos(th) ** 2 * math.cos(2 * tau)
    k = (kH_val + kV_val + (kH_val - kV_val) * c) / 2.0
    alpha = (
        kH_val * aH_val
        + kV_val * aV_val
        + (kH_val * aH_val - kV_val * aV_val) * c
    ) / (2.0 * k)
    return k, alpha


def k_alpha(f_ghz: float, pol: PolType) -> Tuple[float, float]:
    """
    Return (k, alpha) for given f and polarization.
    'Circular' uses theta=0°, tau=45° exactly as in the React code.
    """
    kH_val = k_from_params(f_ghz, kH)
    kV_val = k_from_params(f_ghz, kV)
    aH_val = alpha_from_params(f_ghz, aH)
    aV_val = alpha_from_params(f_ghz, aV)

    if pol == "H":
        return kH_val, aH_val
    if pol == "V":
        return kV_val, aV_val
    # Circular
    return combine_linear(kH_val, kV_val, aH_val, aV_val, 0.0, 45.0)

