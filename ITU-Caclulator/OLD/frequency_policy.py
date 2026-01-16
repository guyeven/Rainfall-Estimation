"""
Frequency set F and “reliability rule”:

Given:
  - F = {f_min + i*f_step}
  - link length d
  - target rainfall R*
  - allowed path attenuation α*
Choose:
  max f in F such that γ(f,R*)·d ≤ α*.

This mirrors your chooseFreq() logic.
"""

from __future__ import annotations
from typing import List

from .attenuation import path_attenuation
from .itu_coeffs import PolType


def build_freq_set(f_min: float, f_max: float, f_step: float) -> List[float]:
    """
    Build discrete F = {f_min + i*f_step}, clamped like your JS:
      - f_min ≥ 10 GHz
      - f_max ≥ f_min
      - step ≥ 1 GHz
    """
    lo = max(10.0, min(f_min, f_max))
    hi = max(lo, f_max)
    st = max(1.0, f_step)

    vals: List[float] = []
    f = lo
    while f <= hi + 1e-9:
        vals.append(round(f, 3))
        f += st
    return vals


def choose_freq_for_link(
    d_km: float,
    F: List[float],
    R_star: float,
    alpha_star: float,
    pol: PolType,
    mode: str = "rule",
    uniform_freq: float | None = None,
) -> float:
    """
    If mode == "uniform":
      snap uniform_freq to closest element of F.
    If mode == "rule":
      choose max f in F such that path_atten(d, f, R*) <= alpha*.
      If none satisfy, return min(F).
    """
    if not F:
        raise ValueError("Frequency set F is empty")

    if mode == "uniform":
        if uniform_freq is None:
            return F[0]
        best = F[0]
        best_err = float("inf")
        for f in F:
            err = abs(f - uniform_freq)
            if err < best_err:
                best_err = err
                best = f
        return best

    # rule mode
    chosen = F[0]
    for f in F:
        att = path_attenuation(d_km, f, R_star, pol)
        if att <= alpha_star:
            chosen = f
        else:
            break
    return chosen

