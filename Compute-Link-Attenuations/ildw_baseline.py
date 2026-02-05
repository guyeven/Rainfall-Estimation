
"""
ildw_baseline.py

ILDW (IDW_links) baseline: segment-distance truncated IDW with a special crossing-pixel rule.

- For a pixel p, let C(p) be the set of links that intersect p (from segments_by_link).
  If C(p) is non-empty, ILDW sets R_hat(p) to the mean of the crossing links' values.
- Otherwise, ILDW uses truncated inverse-distance weighting where distance is the exact
  Euclidean distance from the pixel center to the link *segment* (not to the midpoint).

This module is designed to plug into the same pipeline as idw_baseline.py.
It provides:
  - ildw_field_from_est_input(est_input_json, ...) -> (R_hat(H,W), R_link(n_links))
  - solve_and_save(est_input_json, out_npz, cfg)  [expected by batch_solve_multi.py for "custom" solvers]
  - alias: idw_field_from_est_input = ildw_field_from_est_input (so you can run it as type: "idw")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

try:
    from scipy.spatial import cKDTree
except Exception:  # pragma: no cover
    cKDTree = None

# Reuse ITU + basic geometry helpers from your existing baseline
from idw_baseline import (
    itu838_k_alpha,
    link_lengths_km,
    link_midpoints_xy,
    link_rain_from_attenuation,
    pixel_centers_local_xy,
)


def _link_endpoints_xy(links: List[dict]) -> Tuple[np.ndarray, np.ndarray]:
    """Return arrays A=(n,2), B=(n,2) of link endpoints in local meters."""
    a = np.array([(float(L["x0_m"]), float(L["y0_m"])) for L in links], dtype=np.float64)
    b = np.array([(float(L["x1_m"]), float(L["y1_m"])) for L in links], dtype=np.float64)
    return a, b


def _point_to_segments_distance(p_xy: np.ndarray, a_xy: np.ndarray, b_xy: np.ndarray) -> np.ndarray:
    """
    Exact Euclidean distance from a single point p to each segment [a_i, b_i].

    p_xy: (2,)
    a_xy, b_xy: (m,2)

    Returns: (m,) distances
    """
    p = np.asarray(p_xy, dtype=np.float64).reshape(1, 2)
    a = np.asarray(a_xy, dtype=np.float64)
    b = np.asarray(b_xy, dtype=np.float64)

    v = b - a  # (m,2)
    w = p - a  # broadcast to (m,2)

    vv = np.sum(v * v, axis=1)
    vv = np.maximum(vv, 1e-12)  # robustness for degenerate segments

    t = np.sum(w * v, axis=1) / vv
    t = np.clip(t, 0.0, 1.0)

    proj = a + (t[:, None] * v)
    d = np.hypot(proj[:, 0] - p[0, 0], proj[:, 1] - p[0, 1])
    return d


def _build_crossing_links_by_pixel(
    header: dict,
    segments_by_link: Dict[str, List[dict]],
    n_links: int,
) -> List[List[int]]:
    """
    Build flattened list (H*W) where entry idx=i*W+j holds list of link indices crossing pixel (i,j).
    """
    H = int(header["H"])
    W = int(header["W"])
    out: List[List[int]] = [[] for _ in range(H * W)]

    for k_str, segs in segments_by_link.items():
        try:
            k = int(k_str)
        except Exception:
            continue
        if k < 0 or k >= n_links:
            continue
        for s in segs:
            i = int(s["i"])
            j = int(s["j"])
            if 0 <= i < H and 0 <= j < W:
                out[i * W + j].append(k)
    return out


def ildw_field_from_est_input(
    est_input_json: Union[str, Path],
    *,
    r_max_m: float,
    power: float = 2.0,
    eps_m: float = 1.0,
    default_value: float = 0.0,
    link_values: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute ILDW / IDW_links rainfall field on the patch grid.

    Returns (R_hat, R_link):
      - R_hat: (H,W) grid
      - R_link: (n_links,) per-link rain used as link values
    """
    if cKDTree is None:
        raise RuntimeError("ILDW requires scipy (scipy.spatial.cKDTree). Please `pip install scipy`.")

    est_input_json = Path(est_input_json)
    est = json.loads(est_input_json.read_text())
    header = est["header"]
    links = est["links"]
    segs_by_link = est.get("segments_by_link", {})

    n_links = len(links)

    # ---- link values f(ℓ) ----
    if link_values is None:
        A_db = np.array([float(L.get("A_db", 0.0)) for L in links], dtype=np.float64)
        L_km = link_lengths_km(links)
        f_ghz = np.array([float(L.get("freq_ghz")) for L in links], dtype=np.float64)
        pol = np.array([str(L.get("pol", "H")) for L in links], dtype="<U1")
        k, a = itu838_k_alpha(f_ghz, pol)
        link_values = link_rain_from_attenuation(A_db, L_km, k, a, invalid_to_zero=True)
    else:
        link_values = np.asarray(link_values, dtype=np.float64)
        if link_values.shape[0] != n_links:
            raise ValueError(f"link_values has length {link_values.shape[0]} but expected {n_links}.")

    # ---- geometry ----
    mids = link_midpoints_xy(links)  # (n,2)
    a_xy, b_xy = _link_endpoints_xy(links)

    # Safe candidate retrieval:
    # If a segment is within r_max of point p, then its midpoint is within r_max + (segment_length/2) of p.
    half_len_m = 0.5 * np.hypot(b_xy[:, 0] - a_xy[:, 0], b_xy[:, 1] - a_xy[:, 1])
    r_search = float(r_max_m) + float(np.max(half_len_m)) if n_links > 0 else float(r_max_m)

    tree = cKDTree(np.asarray(mids, dtype=np.float64)) if n_links > 0 else None

    # ---- pixels ----
    q = pixel_centers_local_xy(header)  # (H*W,2)
    H = int(header["H"])
    W = int(header["W"])

    crossing = _build_crossing_links_by_pixel(header, segs_by_link, n_links)

    out = np.full((H * W,), float(default_value), dtype=np.float64)

    # Crossing rule: mean of crossing links
    for idx, lst in enumerate(crossing):
        if not lst:
            continue
        if len(lst) > 1:
            lst = list(set(lst))
        out[idx] = float(np.mean(link_values[lst]))

    # Remaining pixels: segment-distance truncated IDW
    if n_links > 0:
        neigh = tree.query_ball_point(q, r=r_search)  # candidates by midpoint
        r_max_m = float(r_max_m)
        power = float(power)
        eps_m = float(eps_m)

        for idx, cand in enumerate(neigh):
            if crossing[idx]:
                continue
            if not cand:
                continue

            pxy = q[idx]
            cand = np.asarray(cand, dtype=np.int64)

            d = _point_to_segments_distance(pxy, a_xy[cand], b_xy[cand])

            mask = d <= r_max_m
            if not np.any(mask):
                continue

            cand2 = cand[mask]
            d2 = d[mask]

            # Exact hit (rare)
            z = np.where(d2 <= 0.0)[0]
            if z.size > 0:
                out[idx] = float(link_values[int(cand2[int(z[0])])])
                continue

            d2 = np.maximum(d2, eps_m)
            w = 1.0 / (d2 ** power)
            sw = float(np.sum(w))
            if sw <= 0.0 or not np.isfinite(sw):
                continue
            w = w / sw
            out[idx] = float(np.sum(w * link_values[cand2]))

    return out.reshape(H, W), np.asarray(link_values, dtype=np.float64)


def solve_and_save(est_input_json: str | Path, out_npz: str | Path, cfg: dict) -> dict:
    """
    Entry point expected by batch_solve_multi.py for "custom" solvers.

    Reads parameters from cfg['idw'] (same shape as the IDW baseline block).
    Writes an NPZ compatible with your analysis pipeline (at least includes R_hat).
    """
    est_input_json = Path(est_input_json)
    out_npz = Path(out_npz)
    out_npz.parent.mkdir(parents=True, exist_ok=True)

    idw_cfg = dict(cfg.get("idw", {}))
    r_max_m = float(idw_cfg.get("r_max_m", 15000.0))
    power = float(idw_cfg.get("power", 2.0))
    eps_m = float(idw_cfg.get("eps_m", 1.0))
    default_value = float(idw_cfg.get("default_value", 0.0))

    R_hat, R_link = ildw_field_from_est_input(
        est_input_json,
        r_max_m=r_max_m,
        power=power,
        eps_m=eps_m,
        default_value=default_value,
    )

    np.savez(
        out_npz,
        R_hat=np.asarray(R_hat, dtype=np.float64),
        R_link=np.asarray(R_link, dtype=np.float64),
        # meta/provenance (minimal but consistent with other solvers)
        meta_success=True,
        meta_status=0,
        meta_message="ILDW baseline",
        meta_nit=-1,
        meta_fun=np.nan,
        meta_H=int(R_hat.shape[0]),
        meta_W=int(R_hat.shape[1]),
        meta_L=int(R_link.size),
        meta_est_input_json=str(est_input_json),
        meta_init_method="ildw",
        meta_idw_r_max_m=r_max_m,
        meta_idw_power=power,
        meta_idw_eps_m=eps_m,
        meta_idw_default_value=default_value,
    )

    return {"success": True, "npz_out": str(out_npz), "H": int(R_hat.shape[0]), "W": int(R_hat.shape[1])}


# Alias for compatibility with type: "idw" dispatchers
idw_field_from_est_input = ildw_field_from_est_input
