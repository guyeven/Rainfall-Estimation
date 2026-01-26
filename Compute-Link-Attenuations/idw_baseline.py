
"""
idw_baseline.py

Shared IDW baseline utilities used by:
- solve_rain_lbfgsb.py (for IDW-based initialization)
- batch_analyze*.py (for GT vs IDW and IDW vs SOL comparisons)

Implements:
1) ITU-R P.838-3 (03/2005) coefficients k and alpha for rain specific attenuation:
      gamma_R = k * R**alpha    [gamma_R in dB/km, R in mm/h]

   For terrestrial (horizontal) links, we use elevation angle el = 0 deg.
   Then:
     - Horizontal pol => tau = 0 deg  => k = KH, alpha = alphaH
     - Vertical pol   => tau = 90 deg => k = KV, alpha = alphaV

   Coefficient formula and constants are taken from the open-source ITU-Rpy
   implementation of ITU-R P.838-3 (MIT licensed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import json
import math
import numpy as np

try:
    from scipy.spatial import cKDTree  # type: ignore
except Exception:  # pragma: no cover
    cKDTree = None


# -----------------------------
# ITU-R P.838-3 coefficients
# -----------------------------
def _curve_fcn(f_ghz: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    # a * exp(-((log10(f)-b)/c)^2)
    return a * np.exp(-((np.log10(f_ghz) - b) / c) ** 2)


def itu838_k_alpha(f_ghz: Union[float, np.ndarray], pol: Union[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute (k, alpha) for rain specific attenuation gamma_R = k R^alpha.

    Parameters
    ----------
    f_ghz : float or array
        Frequency in GHz
    pol : str or array
        'H' or 'V' (case-insensitive). If array, must align with f_ghz.

    Returns
    -------
    k : ndarray
    alpha : ndarray
    """
    f = np.asarray(f_ghz, dtype=np.float64)
    if f.ndim == 0:
        f = f[None]

    # Broadcast pol
    if isinstance(pol, str):
        pol_arr = np.full(f.shape, pol, dtype="<U1")
    else:
        pol_arr = np.asarray(pol)
        if pol_arr.shape != f.shape:
            pol_arr = np.broadcast_to(pol_arr, f.shape)

    pol_arr = np.char.upper(pol_arr.astype("<U1"))

    # Constants (P.838-3)
    kh = {'aj': [-5.33980, -0.35351, -0.23789, -0.94158],
          'bj': [-0.10008, 1.2697, 0.86036, 0.64552],
          'cj': [1.13098, 0.454, 0.15354, 0.16817],
          'mk': -0.18961,
          'ck': 0.71147}
    kv = {'aj': [-3.80595, -3.44965, -0.39902, 0.50167],
          'bj': [0.56934, -0.22911, 0.73042, 1.07319],
          'cj': [0.81061, 0.51059, 0.11899, 0.27195],
          'mk': -0.16398,
          'ck': 0.63297}
    alphah = {'aj': [-0.14318, 0.29591, 0.32177, -5.37610, 16.1721],
              'bj': [1.82442, 0.77564, 0.63773, -0.96230, -3.29980],
              'cj': [-0.55187, 0.19822, 0.13164, 1.47828, 3.4399],
              'ma': 0.67849,
              'ca': -1.95537}
    alphav = {'aj': [-0.07771, 0.56727, -0.20238, -48.2991, 48.5833],
              'bj': [2.3384, 0.95545, 1.1452, 0.791669, 0.791459],
              'cj': [-0.76284, 0.54039, 0.26809, 0.116226, 0.116479],
              'ma': -0.053739,
              'ca': 0.83433}

    # Compute KH, KV
    KH = np.power(
        10.0,
        sum(_curve_fcn(f, kh['aj'][j], kh['bj'][j], kh['cj'][j]) for j in range(4))
        + kh['mk'] * np.log10(f)
        + kh['ck']
    )
    KV = np.power(
        10.0,
        sum(_curve_fcn(f, kv['aj'][j], kv['bj'][j], kv['cj'][j]) for j in range(4))
        + kv['mk'] * np.log10(f)
        + kv['ck']
    )

    alphaH = (
        sum(_curve_fcn(f, alphah['aj'][j], alphah['bj'][j], alphah['cj'][j]) for j in range(5))
        + alphah['ma'] * np.log10(f)
        + alphah['ca']
    )
    alphaV = (
        sum(_curve_fcn(f, alphav['aj'][j], alphav['bj'][j], alphav['cj'][j]) for j in range(5))
        + alphav['ma'] * np.log10(f)
        + alphav['ca']
    )

    # Terrestrial horizontal path: el = 0 deg => choose by pol:
    k = np.where(pol_arr == "V", KV, KH)
    alpha = np.where(pol_arr == "V", alphaV, alphaH)

    return k.astype(np.float64), alpha.astype(np.float64)


# -----------------------------
# Link utilities and IDW
# -----------------------------
def link_midpoints_xy(links: List[Dict]) -> np.ndarray:
    """
    Return link midpoints (n_links, 2) in *the same coordinate system used in est_input.json*.
    In your project, link coords are typically in local patch coordinates ("local_from_NW").
    """
    x0 = np.array([float(L["x0_m"]) for L in links], dtype=np.float64)
    y0 = np.array([float(L["y0_m"]) for L in links], dtype=np.float64)
    x1 = np.array([float(L["x1_m"]) for L in links], dtype=np.float64)
    y1 = np.array([float(L["y1_m"]) for L in links], dtype=np.float64)
    return np.stack([(x0 + x1) / 2.0, (y0 + y1) / 2.0], axis=1)


def link_lengths_km(links: List[Dict]) -> np.ndarray:
    x0 = np.array([float(L["x0_m"]) for L in links], dtype=np.float64)
    y0 = np.array([float(L["y0_m"]) for L in links], dtype=np.float64)
    x1 = np.array([float(L["x1_m"]) for L in links], dtype=np.float64)
    y1 = np.array([float(L["y1_m"]) for L in links], dtype=np.float64)
    L_m = np.hypot(x1 - x0, y1 - y0)
    return (L_m / 1000.0).astype(np.float64)


def link_rain_from_attenuation(
    A_db: np.ndarray,
    L_km: np.ndarray,
    k: np.ndarray,
    alpha: np.ndarray,
    *,
    invalid_to_zero: bool = True,
) -> np.ndarray:
    """
    Compute an "equivalent uniform rain" per link:
      gamma = A / L_km
      R = (gamma / k)^(1/alpha)

    A_db is assumed to be the rain-induced attenuation in dB across the link.
    """
    A = np.asarray(A_db, dtype=np.float64)
    L = np.asarray(L_km, dtype=np.float64)
    k = np.asarray(k, dtype=np.float64)
    a = np.asarray(alpha, dtype=np.float64)

    R = np.full_like(A, np.nan, dtype=np.float64)
    safe = (L > 0) & (k > 0) & (a > 0) & np.isfinite(A) & np.isfinite(L) & np.isfinite(k) & np.isfinite(a)

    gamma = np.zeros_like(A, dtype=np.float64)
    gamma[safe] = A[safe] / L[safe]

    pos = safe & (gamma > 0)
    R[pos] = (gamma[pos] / k[pos]) ** (1.0 / a[pos])

    if invalid_to_zero:
        R[~np.isfinite(R)] = 0.0
        R[R < 0] = 0.0
    return R


def pixel_centers_local_xy(header: Dict) -> np.ndarray:
    """
    Pixel centers in local patch coords ("local_from_NW"):
      x = (j+0.5)*pixel_size_m
      y = (i+0.5)*pixel_size_m
    """
    H = int(header["H"])
    W = int(header["W"])
    pix = float(header["pixel_size_m"])
    xs = (np.arange(W, dtype=np.float64) + 0.5) * pix
    ys = (np.arange(H, dtype=np.float64) + 0.5) * pix
    X, Y = np.meshgrid(xs, ys)
    return np.stack([X.ravel(), Y.ravel()], axis=1)


def idw_truncated(
    points_xy: np.ndarray,
    values: np.ndarray,
    query_xy: np.ndarray,
    *,
    r_max_m: float,
    power: float = 2.0,
    eps_m: float = 1.0,
    default_value: float = 0.0,
) -> np.ndarray:
    """
    Exact truncated IDW as you specified:

      If ||p - p_i|| > R_max => weight 0.
      If no neighbors within R_max => output = default_value (usually 0).
      Otherwise:
        w_i = d^{-power} / sum_j d^{-power}
        fhat(p) = sum_i w_i f(p_i)

    Notes
    -----
    - Uses a KD-tree radius query. Complexity depends on how many neighbors fall inside R_max.
    - If a query point lands exactly on a data point, we return that data value.
    """
    if cKDTree is None:
        raise RuntimeError("scipy is required for IDW (scipy.spatial.cKDTree). Please `pip install scipy`.")

    pts = np.asarray(points_xy, dtype=np.float64)
    vals = np.asarray(values, dtype=np.float64)
    qry = np.asarray(query_xy, dtype=np.float64)

    tree = cKDTree(pts)

    out = np.full((qry.shape[0],), float(default_value), dtype=np.float64)

    # Query neighbors within radius (returns list-of-lists)
    neigh = tree.query_ball_point(qry, r=float(r_max_m))

    for i, idxs in enumerate(neigh):
        if not idxs:
            continue
        p = qry[i]
        P = pts[idxs]
        d = np.hypot(P[:, 0] - p[0], P[:, 1] - p[1])

        # Exact hit
        j0 = np.where(d <= 0.0)[0]
        if j0.size > 0:
            out[i] = vals[idxs[int(j0[0])]]
            continue

        d = np.maximum(d, float(eps_m))
        w = 1.0 / (d ** float(power))
        sw = np.sum(w)
        if sw <= 0 or not np.isfinite(sw):
            continue
        w = w / sw
        out[i] = float(np.sum(w * vals[idxs]))

    return out


def idw_field_from_est_input(
    est_input_json: Union[str, Path],
    *,
    r_max_m: float,
    power: float = 2.0,
    eps_m: float = 1.0,
    default_value: float = 0.0,
    # If link_values is None, we compute per-link rain from attenuation A_db using ITU k/alpha.
    link_values: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute an IDW rainfall field on the patch grid using link midpoints.

    Returns (R_idw, R_link):
      - R_idw: (H,W) grid
      - R_link: (n_links,) per-link rain used as values at midpoints
    """
    p = Path(est_input_json)
    est = json.loads(p.read_text())
    header = est["header"]
    links = est["links"]

    mids = link_midpoints_xy(links)

    if link_values is None:
        A_db = np.array([float(L.get("A_db", 0.0)) for L in links], dtype=np.float64)
        L_km = link_lengths_km(links)
        f_ghz = np.array([float(L.get("freq_ghz")) for L in links], dtype=np.float64)
        pol = np.array([str(L.get("pol", "H")) for L in links], dtype="<U1")
        k, a = itu838_k_alpha(f_ghz, pol)
        link_values = link_rain_from_attenuation(A_db, L_km, k, a, invalid_to_zero=True)

    q = pixel_centers_local_xy(header)
    out = idw_truncated(mids, link_values, q, r_max_m=r_max_m, power=power, eps_m=eps_m, default_value=default_value)
    H = int(header["H"])
    W = int(header["W"])
    return out.reshape(H, W), np.asarray(link_values, dtype=np.float64)
