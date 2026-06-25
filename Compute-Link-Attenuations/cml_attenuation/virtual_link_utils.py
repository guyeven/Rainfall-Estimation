#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any, Dict, Tuple

import numpy as np

from cml_attenuation.itu_r_p_8383 import k_alpha, k_alpha_H, k_alpha_V
from cml_attenuation.solvers.solve_rain_lbfgsb import EstProblem, _pol_to_itu


def compute_link_rain_equivalent(prob: EstProblem) -> np.ndarray:
    """
    Per-link uniform rain-rate equivalent implied by the observed attenuation:
      R_l = ((A_l / L_l) / k_l)^(1/alpha_l)
    Returns zeros on invalid links.
    """
    R_link = np.zeros(prob.L, dtype=np.float64)
    valid = (
        prob.valid_links
        & np.isfinite(prob.A_obs)
        & np.isfinite(prob.L_km)
        & (prob.L_km > 0.0)
        & np.isfinite(prob.k)
        & (prob.k > 0.0)
        & np.isfinite(prob.alpha)
        & (prob.alpha > 0.0)
    )
    if np.any(valid):
        gamma = np.zeros(prob.L, dtype=np.float64)
        gamma[valid] = prob.A_obs[valid] / prob.L_km[valid]
        gamma = np.maximum(gamma, 0.0)
        R_link[valid] = np.power(gamma[valid] / prob.k[valid], 1.0 / prob.alpha[valid])
    return R_link


def compute_link_model_from_freqs(freq_ghz: np.ndarray, pol: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    k_arr = np.zeros_like(freq_ghz, dtype=np.float64)
    alpha_arr = np.zeros_like(freq_ghz, dtype=np.float64)
    for li in range(freq_ghz.size):
        k_li, a_li = k_alpha(float(freq_ghz[li]), _pol_to_itu(str(pol[li])))
        k_arr[li] = float(k_li)
        alpha_arr[li] = float(a_li)
    return k_arr, alpha_arr


def _alpha_minus_one(freq_ghz: float, pol_code: str) -> float:
    pol_code = str(pol_code).strip().upper()
    if pol_code == "H":
        return float(k_alpha_H(float(freq_ghz))[1] - 1.0)
    if pol_code == "V":
        return float(k_alpha_V(float(freq_ghz))[1] - 1.0)
    raise ValueError(f"Unsupported polarization {pol_code!r}")


@lru_cache(maxsize=None)
def exact_alpha_one_frequency_for_pol(pol_code: str) -> float:
    """
    Find the highest-frequency root of alpha(f, pol) - 1 = 0 in the local
    ITU-R P.838-3 implementation. The highest-frequency root is used so the
    virtual link stays in the microwave regime.
    """
    pol_code = str(pol_code).strip().upper()
    f_lo = 0.1
    f_hi = 100.0
    n_grid = 200000
    freqs = np.linspace(f_lo, f_hi, n_grid + 1, dtype=np.float64)
    vals = np.asarray([_alpha_minus_one(float(f), pol_code) for f in freqs], dtype=np.float64)
    brackets: list[tuple[float, float]] = []
    for i in range(n_grid):
        a = float(vals[i])
        b = float(vals[i + 1])
        if a == 0.0:
            brackets.append((float(freqs[i]), float(freqs[i])))
        elif a * b < 0.0:
            brackets.append((float(freqs[i]), float(freqs[i + 1])))
    if not brackets:
        raise RuntimeError(f"Could not find any alpha=1 frequency root for polarization {pol_code!r}")
    lo, hi = brackets[-1]
    if lo == hi:
        return float(lo)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        vm = _alpha_minus_one(mid, pol_code)
        vl = _alpha_minus_one(lo, pol_code)
        if vl * vm <= 0.0:
            hi = mid
        else:
            lo = mid
    return float(0.5 * (lo + hi))


def exact_alpha_one_frequency_array(pol: np.ndarray) -> np.ndarray:
    out = np.zeros(pol.shape, dtype=np.float64)
    for i in range(pol.size):
        out[i] = exact_alpha_one_frequency_for_pol(str(pol[i]))
    return out


def make_transformed_problem(
    prob_real: EstProblem,
    *,
    transformed_freq_ghz: np.ndarray,
    link_rain_equivalent: np.ndarray | None = None,
) -> Tuple[EstProblem, Dict[str, Any]]:
    transformed_freq_ghz = np.asarray(transformed_freq_ghz, dtype=np.float64)
    if transformed_freq_ghz.shape != prob_real.freq_ghz.shape:
        raise ValueError("transformed_freq_ghz must have shape (L,)")
    R_link = (
        compute_link_rain_equivalent(prob_real)
        if link_rain_equivalent is None
        else np.asarray(link_rain_equivalent, dtype=np.float64)
    )
    if R_link.shape != prob_real.A_obs.shape:
        raise ValueError("link_rain_equivalent must have shape (L,)")

    k_new, alpha_new = compute_link_model_from_freqs(transformed_freq_ghz, prob_real.pol)
    A_obs_new = np.zeros(prob_real.L, dtype=np.float64)
    valid = (
        prob_real.valid_links
        & np.isfinite(prob_real.L_km)
        & (prob_real.L_km > 0.0)
        & np.isfinite(k_new)
        & (k_new > 0.0)
        & np.isfinite(alpha_new)
        & (alpha_new > 0.0)
        & np.isfinite(R_link)
        & (R_link >= 0.0)
    )
    if np.any(valid):
        A_obs_new[valid] = prob_real.L_km[valid] * k_new[valid] * np.power(R_link[valid], alpha_new[valid])

    prob_new = replace(
        prob_real,
        A_obs=A_obs_new.astype(np.float64),
        freq_ghz=transformed_freq_ghz.astype(np.float64),
        k=k_new.astype(np.float64),
        alpha=alpha_new.astype(np.float64),
    )
    info = {
        "link_rain_equivalent": R_link.astype(np.float64),
        "freq_ghz_transformed": transformed_freq_ghz.astype(np.float64),
        "k_transformed": k_new.astype(np.float64),
        "alpha_transformed": alpha_new.astype(np.float64),
        "A_obs_transformed": A_obs_new.astype(np.float64),
    }
    return prob_new, info


def make_virtual_problem(
    prob_real: EstProblem,
    *,
    virtual_freq_ghz: float | None = None,
    link_rain_equivalent: np.ndarray | None = None,
) -> Tuple[EstProblem, Dict[str, Any]]:
    if virtual_freq_ghz is None:
        freq = exact_alpha_one_frequency_array(prob_real.pol)
        virtual_freq_meta = freq.astype(np.float64)
    else:
        freq = np.full(prob_real.L, float(virtual_freq_ghz), dtype=np.float64)
        virtual_freq_meta = float(virtual_freq_ghz)
    prob_virtual, info = make_transformed_problem(
        prob_real,
        transformed_freq_ghz=freq,
        link_rain_equivalent=link_rain_equivalent,
    )
    info["virtual_freq_ghz"] = virtual_freq_meta
    return prob_virtual, info


def make_beta_problem(
    prob_real: EstProblem,
    *,
    beta: float,
    virtual_freq_ghz: float | None = None,
    link_rain_equivalent: np.ndarray | None = None,
) -> Tuple[EstProblem, Dict[str, Any]]:
    beta = float(beta)
    if virtual_freq_ghz is None:
        f_virtual = exact_alpha_one_frequency_array(prob_real.pol)
        virtual_freq_meta = f_virtual.astype(np.float64)
    else:
        f_virtual = np.full(prob_real.L, float(virtual_freq_ghz), dtype=np.float64)
        virtual_freq_meta = float(virtual_freq_ghz)
    freq_beta = beta * prob_real.freq_ghz + (1.0 - beta) * f_virtual
    prob_beta, info = make_transformed_problem(
        prob_real,
        transformed_freq_ghz=freq_beta,
        link_rain_equivalent=link_rain_equivalent,
    )
    info["beta"] = float(beta)
    info["virtual_freq_ghz"] = virtual_freq_meta
    return prob_beta, info
