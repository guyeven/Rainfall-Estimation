#!/usr/bin/env python3
"""
batch_analyze_multi_v3.py

Multi-solver analyzer that:
1) Produces *per-solver* Excel sheets in the "old" format:
   - CoverageStats_GTvs<LABEL>
   - DistanceStats_GTvs<LABEL>

   Columns (same as your previous batch_analyze):
     patch_key, mask_type, coverage_bin/distance_bin_m, n_pixels,
     mean_signed, median_signed, mean_abs, std_abs, median_abs,
     p90_abs, p99_abs, linf_abs,
     l1_abs_sum

   Conventions:
   - Rainy pixels: signed_rel = (GT - PRED)/GT, abs_rel = |GT-PRED|/GT
   - Non-rainy pixels: signed_diff = (PRED - GT), abs_diff = |PRED-GT|
   l1_abs_sum uses the corresponding "abs" quantity in each case.

2) Adds per-solver link-based sheets:
   - LinkStats_GTvs<LABEL>
     patch_key, n_links_valid, attn_l1_all, J1_all, attn_l1_ge10km, J1_ge10km

   Where:
     attn_l1 = sum_{links} |A_hat - A_obs|
     J1      = sum_{links} ((A_hat - A_obs)/L_km)^2
   and the *_ge10km versions restrict to links with L_km >= 10.

3) Keeps the nice final plots (IQR of per-patch medians by distance bin) across all solvers.

Relative paths in the YAML are resolved relative to the YAML file location.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


# ----------------------------
# Config utilities
# ----------------------------

def load_config_file(path: str | Path) -> dict:
    path = Path(path)
    suf = path.suffix.lower()
    if suf in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except Exception as e:
            raise RuntimeError("YAML config requires PyYAML (pip install pyyaml).") from e
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return {} if cfg is None else cfg
    if suf == ".json":
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg is None:
            return {}
        if not isinstance(cfg, dict):
            raise ValueError("JSON config must parse to a dict at top level.")
        return cfg
    raise ValueError("Config must be .yaml/.yml or .json")


def deep_get(d: dict, path: str, default=None):
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def resolve_path(p: str | Path | None, *, base_dir: Path) -> Optional[Path]:
    if p is None:
        return None
    pp = Path(str(p))
    if pp.is_absolute():
        return pp
    return (base_dir / pp).resolve()


def normalize_solvers(obj: Any, *, path_for_err: str) -> List[dict]:
    """
    Accept either:
      solvers: [ {..}, {..} ]
    or
      solvers:
        keyA: {..}
        keyB: {..}
    Returns list of solver dicts.
    """
    if obj is None:
        raise SystemExit(f"Config missing {path_for_err}.")
    if isinstance(obj, list):
        if not obj:
            raise SystemExit(f"{path_for_err} must be a non-empty list.")
        if not all(isinstance(x, dict) for x in obj):
            raise SystemExit(f"{path_for_err} list elements must be dicts.")
        return obj
    if isinstance(obj, dict):
        vals = list(obj.values())
        if not vals:
            raise SystemExit(f"{path_for_err} must be a non-empty mapping.")
        if not all(isinstance(x, dict) for x in vals):
            raise SystemExit(f"{path_for_err} mapping values must be dicts.")
        return vals
    raise SystemExit(f"{path_for_err} must be a list or mapping.")


# ----------------------------
# IO utilities
# ----------------------------

def load_npz_first_key(path: Path, key_preference: Sequence[str]) -> np.ndarray:
    z = np.load(path, allow_pickle=True)
    for k in key_preference:
        if k in z:
            arr = z[k]
            return np.asarray(arr)
    # fallback: first ndarray-like key
    for k in z.files:
        if isinstance(z[k], np.ndarray):
            return np.asarray(z[k])
    raise KeyError(f"None of keys {list(key_preference)} found in {path.name}; keys={z.files}")


def list_npz(dirp: Path, prefix: str) -> List[Path]:
    return sorted(dirp.glob(f"{prefix}_*.npz"))


def list_json(dirp: Path, prefix: str) -> List[Path]:
    return sorted(dirp.glob(f"{prefix}_*.json"))


def patch_key_from_filename(name: str) -> str:
    # expected patterns: gt_..._patch001.npz OR est_input_..._patch001_solution.npz etc.
    stem = Path(name).stem
    # remove trailing _solution if present
    if stem.endswith("_solution"):
        stem = stem[: -len("_solution")]
    # remove leading gt_/est_input_ if present
    if stem.startswith("gt_"):
        stem = stem[len("gt_") :]
    if stem.startswith("est_input_"):
        stem = stem[len("est_input_") :]
    return stem


# ----------------------------
# Coverage + distance from est_input JSON
# ----------------------------

def load_est_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def compute_coverage_map(est: dict) -> Tuple[np.ndarray, int, int]:
    """
    coverage(p) = #distinct links that intersect pixel p
    Uses segments_by_link with pixel indices (i,j).
    """
    header = est["header"]
    H = int(header["H"])
    W = int(header["W"])
    P = H * W

    segs: Dict[str, list] = est.get("segments_by_link", {})
    pairs: List[Tuple[int, int]] = []
    for li_str, seg_list in segs.items():
        li = int(li_str)
        for s in seg_list:
            i = int(s["i"]); j = int(s["j"])
            p = i * W + j
            pairs.append((p, li))

    if not pairs:
        return np.zeros((H, W), dtype=np.int32), H, W

    arr = np.array(pairs, dtype=np.int64)
    # unique pixel-link pairs
    arr_u = np.unique(arr, axis=0)
    cov = np.bincount(arr_u[:, 0], minlength=P).astype(np.int32)
    return cov.reshape(H, W), H, W


def point_to_segment_dist(px: np.ndarray, py: np.ndarray,
                          x0: np.ndarray, y0: np.ndarray,
                          x1: np.ndarray, y1: np.ndarray) -> np.ndarray:
    """
    Vectorized distance from points (px,py) to segments (x0,y0)-(x1,y1), per-segment.
    px,py are scalars or arrays broadcastable to segment arrays.
    Returns distances in same units as inputs.
    """
    vx = x1 - x0
    vy = y1 - y0
    wx = px - x0
    wy = py - y0
    vv = vx * vx + vy * vy
    # avoid div0
    vv = np.where(vv <= 1e-12, 1e-12, vv)
    t = (wx * vx + wy * vy) / vv
    t = np.clip(t, 0.0, 1.0)
    projx = x0 + t * vx
    projy = y0 + t * vy
    dx = px - projx
    dy = py - projy
    return np.sqrt(dx * dx + dy * dy)



def compute_d3_map_sampled_points(
    est: dict,
    *,
    sample_spacing_m: float = 250.0,
    k_query_samples: int = 48,
    chunk_size: int = 8000,
    max_samples_per_link: int = 200,
) -> Tuple[np.ndarray, float]:
    """
    Compute d3(p) = distance in meters from pixel center to the 3rd closest link (point-to-segment).

    This method matches the *older* analyzer: it samples points along each segment at a fixed spacing,
    builds a KD-tree over those sampled points, then uses nearest sampled points to propose candidate
    links. Exact point-to-segment distances are computed for candidate links, and the 3rd smallest is taken.

    Returns (d3_map_m, pixel_size_m)
    """
    header = est["header"]
    links = est["links"]
    H = int(header["H"])
    W = int(header["W"])
    pix = float(header["pixel_size_m"])

    if not links:
        return np.full((H, W), np.inf, dtype=np.float64), pix
    if len(links) < 3:
        return np.full((H, W), np.inf, dtype=np.float64), pix

    try:
        from scipy.spatial import cKDTree  # type: ignore
    except Exception as e:
        raise RuntimeError("scipy is required for d3 computation (scipy.spatial.cKDTree).") from e

    x0 = np.array([float(L["x0_m"]) for L in links], dtype=np.float64)
    y0 = np.array([float(L["y0_m"]) for L in links], dtype=np.float64)
    x1 = np.array([float(L["x1_m"]) for L in links], dtype=np.float64)
    y1 = np.array([float(L["y1_m"]) for L in links], dtype=np.float64)

    dx = x1 - x0
    dy = y1 - y0
    lengths = np.sqrt(dx * dx + dy * dy)
    spacing = max(1.0, float(sample_spacing_m))

    sample_xy_list = []
    sample_to_link_list = []

    for li in range(len(links)):
        L = float(lengths[li])
        n = max(2, int(math.ceil(L / spacing)) + 1)
        n = min(n, int(max_samples_per_link))
        ts = np.linspace(0.0, 1.0, n, dtype=np.float64)
        xs = x0[li] + ts * dx[li]
        ys = y0[li] + ts * dy[li]
        sample_xy_list.append(np.stack([xs, ys], axis=1))
        sample_to_link_list.append(np.full((n,), li, dtype=np.int32))

    sample_xy = np.concatenate(sample_xy_list, axis=0).astype(np.float64)
    sample_to_link = np.concatenate(sample_to_link_list, axis=0)

    tree = cKDTree(sample_xy)

    # pixel centers in meters
    xs = (np.arange(W, dtype=np.float64) + 0.5) * pix
    ys = (np.arange(H, dtype=np.float64) + 0.5) * pix
    X, Y = np.meshgrid(xs, ys)
    pts = np.stack([X.ravel(), Y.ravel()], axis=1).astype(np.float64)

    d3 = np.full((H * W,), np.inf, dtype=np.float64)

    kq = int(k_query_samples)
    kq = max(kq, 12)
    # cap kq to number of samples
    kq = min(kq, int(sample_xy.shape[0]))

    for start in range(0, pts.shape[0], int(chunk_size)):
        end = min(pts.shape[0], start + int(chunk_size))
        q = pts[start:end]

        # query nearest sample points
        _, nn_idx = tree.query(q, k=kq, workers=-1)
        if nn_idx.ndim == 1:
            nn_idx = nn_idx[:, None]

        for bi in range(q.shape[0]):
            cand_links = np.unique(sample_to_link[nn_idx[bi]])

            # ensure at least 3 candidates (rare when kq is small or samples are very few)
            if cand_links.size < 3:
                kq2 = min(int(sample_xy.shape[0]), kq * 4)
                _, nn_idx2 = tree.query(q[bi], k=kq2, workers=-1)
                cand_links = np.unique(sample_to_link[np.atleast_1d(nn_idx2)])

            if cand_links.size == 0:
                continue

            # exact point-to-segment distances for candidate links
            px = q[bi, 0]
            py = q[bi, 1]
            ds = point_to_segment_dist(px, py, x0[cand_links], y0[cand_links], x1[cand_links], y1[cand_links])

            if ds.size < 3:
                d3[start + bi] = float(np.max(ds))
            else:
                d3[start + bi] = float(np.partition(ds, 2)[2])

    return d3.reshape(H, W), pix



def compute_d3_map(est: dict, *, bin_edges_m: Sequence[float], max_candidates: int) -> Tuple[np.ndarray, float]:
    """
    d3(p) = distance in meters from pixel-center to the 3rd closest link (point-to-segment),
            approximated by using KDTree over endpoints+midpoints to propose candidates.

    Returns (d3_map_m, pixel_size_m)
    """
    header = est["header"]
    links = est["links"]
    H = int(header["H"])
    W = int(header["W"])
    pix = float(header["pixel_size_m"])

    if not links:
        return np.full((H, W), np.inf, dtype=np.float64), pix

    x0 = np.array([float(L["x0_m"]) for L in links], dtype=np.float64)
    y0 = np.array([float(L["y0_m"]) for L in links], dtype=np.float64)
    x1 = np.array([float(L["x1_m"]) for L in links], dtype=np.float64)
    y1 = np.array([float(L["y1_m"]) for L in links], dtype=np.float64)
    mx = 0.5 * (x0 + x1)
    my = 0.5 * (y0 + y1)
    n_links = len(links)

    try:
        from scipy.spatial import cKDTree  # type: ignore
    except Exception as e:
        raise RuntimeError("scipy is required for d3 computation (scipy.spatial.cKDTree).") from e

    pts = np.vstack([
        np.stack([x0, y0], axis=1),
        np.stack([x1, y1], axis=1),
        np.stack([mx, my], axis=1),
    ])
    pt_to_link = np.concatenate([np.arange(n_links), np.arange(n_links), np.arange(n_links)])
    tree = cKDTree(pts)

    # pixel centers in meters; assume pixel (i,j) spans [j*pix,(j+1)*pix] etc.
    xs = (np.arange(W, dtype=np.float64) + 0.5) * pix
    ys = (np.arange(H, dtype=np.float64) + 0.5) * pix
    X, Y = np.meshgrid(xs, ys)

    # query K nearest proxy points
    K = int(max_candidates)
    K = max(3, min(K, pts.shape[0]))
    d_proxy, idx_proxy = tree.query(np.stack([X.ravel(), Y.ravel()], axis=1), k=K, workers=-1)
    # ensure 2d
    if K == 1:
        idx_proxy = idx_proxy[:, None]

    d3 = np.empty(H * W, dtype=np.float64)
    # compute per pixel
    for t in range(H * W):
        cand_links = np.unique(pt_to_link[idx_proxy[t]])
        # true segment distances for these links
        dist = point_to_segment_dist(X.ravel()[t], Y.ravel()[t], x0[cand_links], y0[cand_links], x1[cand_links], y1[cand_links])
        if dist.size < 3:
            # not enough links; define as inf
            d3[t] = np.inf
        else:
            # 3rd smallest
            # partial sort for speed
            kth = np.partition(dist, 2)[2]
            d3[t] = float(kth)
    return d3.reshape(H, W), pix


def parse_bins(edges: Sequence[float]) -> List[Tuple[Optional[float], Optional[float], str]]:
    """
    edges = [125,375,750,...]
    bins: <=e0, (e0,e1], ..., >elast
    """
    e = list(map(float, edges))
    out: List[Tuple[Optional[float], Optional[float], str]] = []
    if not e:
        out.append((None, None, "all"))
        return out
    out.append((None, e[0], f"≤{int(e[0])}"))
    for a, b in zip(e, e[1:]):
        out.append((a, b, f"({int(a)},{int(b)}]"))
    out.append((e[-1], None, f">{int(e[-1])}"))
    return out


def assign_bin_labels(values: np.ndarray, bins: List[Tuple[Optional[float], Optional[float], str]]) -> np.ndarray:
    lab = np.empty(values.shape, dtype=object)
    for lo, hi, name in bins:
        if lo is None:
            m = values <= hi
        elif hi is None:
            m = values > lo
        else:
            m = (values > lo) & (values <= hi)
        lab[m] = name
    return lab


def parse_coverage_bins(cfg_bins: Sequence[Any]) -> Tuple[List[int], Optional[int]]:
    exact: List[int] = []
    ge: Optional[int] = None
    for b in cfg_bins:
        if isinstance(b, int):
            exact.append(int(b))
        elif isinstance(b, str) and b.strip().endswith("+"):
            ge = int(b.strip()[:-1])
        else:
            raise ValueError(f"Invalid coverage bin {b!r}. Use ints or 'K+'.")
    exact = sorted(set(exact))
    return exact, ge


def coverage_bin_label(v: int, exact: List[int], ge: Optional[int]) -> Optional[str]:
    if v in exact:
        return str(v)
    if ge is not None and v >= ge:
        return f"{ge}+"
    return None


# ----------------------------
# Stats helpers
# ----------------------------

def stats_row(err_signed: np.ndarray, err_abs: np.ndarray, *, l1_abs_sum: float) -> Dict[str, Any]:
    if err_abs.size == 0:
        return dict(
            n_pixels=0,
            mean_signed=0.0, median_signed=0.0,
            mean_abs=0.0, std_abs=0.0,
            median_abs=0.0, p90_abs=0.0, p99_abs=0.0, linf_abs=0.0,
            l1_abs_sum=0.0,
        )
    mean_signed = float(np.mean(err_signed))
    median_signed = float(np.median(err_signed))
    mean_abs = float(np.mean(err_abs))
    std_abs = float(np.std(err_abs, ddof=0))
    median_abs = float(np.median(err_abs))
    p90 = float(np.percentile(err_abs, 90))
    p99 = float(np.percentile(err_abs, 99))
    linf = float(np.max(err_abs))
    return dict(
        n_pixels=int(err_abs.size),
        mean_signed=mean_signed,
        median_signed=median_signed,
        mean_abs=mean_abs,
        std_abs=std_abs,
        median_abs=median_abs,
        p90_abs=p90,
        p99_abs=p99,
        linf_abs=linf,
        l1_abs_sum=float(l1_abs_sum),
    )


def compute_pixel_errors(gt: np.ndarray, pred: np.ndarray, mask_rainy: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
      signed_rainy, abs_rainy, signed_nonrainy, abs_nonrainy
    """
    gt = gt.astype(np.float64)
    pred = pred.astype(np.float64)
    rainy = mask_rainy

    # rainy: relative
    gt_r = gt[rainy]
    pred_r = pred[rainy]
    denom = np.where(gt_r == 0.0, 1.0, gt_r)
    signed_r = (gt_r - pred_r) / denom
    abs_r = np.abs(signed_r)

    # nonrainy: absolute difference
    gt_n = gt[~rainy]
    pred_n = pred[~rainy]
    signed_n = (pred_n - gt_n)
    abs_n = np.abs(signed_n)

    return signed_r, abs_r, signed_n, abs_n


# ----------------------------
# Attenuation / J1 (link-based)
# ----------------------------

def compute_link_terms(est: dict, R_field: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns arrays (A_obs, A_hat, L_km, valid_mask, len_ge10_mask) aligned by link_index.
    """
    from solve_rain_lbfgsb import k_alpha  # type: ignore

    links = est["links"]
    segs: Dict[str, list] = est.get("segments_by_link", {})

    header = est["header"]
    H = int(header["H"]); W = int(header["W"])
    R = np.asarray(R_field, dtype=np.float64)
    if R.shape != (H, W):
        raise ValueError(f"R_field shape {R.shape} != (H,W)=({H},{W}) for attenuation computation.")

    L = len(links)
    A_obs = np.zeros(L, dtype=np.float64)
    A_hat = np.zeros(L, dtype=np.float64)
    L_km = np.zeros(L, dtype=np.float64)

    # gather per-link k, alpha
    k = np.zeros(L, dtype=np.float64)
    a = np.zeros(L, dtype=np.float64)

    # Polarization mapping: different ITU implementations expect different strings.
    # We try a small set of common aliases for horizontal/vertical.
    def pol_aliases(p: str) -> list:
        p = str(p).strip()
        pu = p.upper()
        if pu in ("H", "HOR", "HORIZ", "HORIZONTAL", "HH"):
            return ["H", "h", "horizontal", "HORIZONTAL", "HH"]
        if pu in ("V", "VER", "VERT", "VERTICAL", "VV"):
            return ["V", "v", "vertical", "VERTICAL", "VV"]
        return [p, pu]

    for rec in links:
        li = int(rec["link_index"])
        A_obs[li] = float(rec.get("A_db", rec.get("A", 0.0)))
        freq = float(rec["freq_ghz"])
        pol_raw = rec.get("pol", "")
        last_err = None
        for pol_try in pol_aliases(pol_raw):
            try:
                k_li, a_li = k_alpha(freq, pol_try)
                k[li] = float(k_li)
                a[li] = float(a_li)
                last_err = None
                break
            except Exception as e:
                last_err = e
                continue
        if last_err is not None:
            raise ValueError(f"Unknown polarization: {pol_raw}") from last_err

    # compute A_hat by summing over pixel segments
    for li in range(L):
        seg_list = segs.get(str(li), [])
        if not seg_list:
            continue
        for s in seg_list:
            i = int(s["i"]); j = int(s["j"])
            ds_km = float(s["ds_m"]) / 1000.0
            L_km[li] += ds_km
            r = max(float(R[i, j]), 0.0)
            A_hat[li] += ds_km * k[li] * (r ** a[li])

    valid = L_km > 0
    ge10 = (L_km >= 10.0) & valid
    return A_obs, A_hat, L_km, valid, ge10


def attn_l1_and_J1(A_obs: np.ndarray, A_hat: np.ndarray, L_km: np.ndarray, mask: np.ndarray) -> Tuple[float, float, int]:
    idx = np.where(mask)[0]
    if idx.size == 0:
        return 0.0, 0.0, 0
    diff = A_hat[idx] - A_obs[idx]
    attn_l1 = float(np.sum(np.abs(diff)))
    J1 = float(np.sum((diff / L_km[idx]) ** 2))
    return attn_l1, J1, int(idx.size)


# ----------------------------
# Excel writing
# ----------------------------

def safe_sheet_name(name: str) -> str:
    # Excel sheet max length 31; remove invalid chars
    bad = set(r'[]:*?/\\')
    s = "".join(ch for ch in name if ch not in bad).strip()
    if not s:
        s = "Sheet"
    return s[:31]


def write_workbook(path: Path, sheets: Dict[str, List[Dict[str, Any]]]):
    try:
        from openpyxl import Workbook  # type: ignore
    except Exception as e:
        raise RuntimeError("openpyxl required to write Excel (pip install openpyxl).") from e

    wb = Workbook()
    # remove default
    wb.remove(wb.active)

    for sheet_name, rows in sheets.items():
        ws = wb.create_sheet(title=safe_sheet_name(sheet_name))
        if not rows:
            continue
        # header
        cols = list(rows[0].keys())
        ws.append(cols)
        for r in rows:
            ws.append([r.get(c, "") for c in cols])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


# ----------------------------
# Plot: IQR of per-patch medians by distance bin
# ----------------------------

def compute_iqr_profile(per_patch_medians: Dict[str, Dict[str, List[float]]],
                        dist_labels: List[str]) -> Dict[str, Dict[str, Tuple[float,float,float]]]:
    """
    per_patch_medians[method][bin_label] = list of medians (one per patch that had pixels in that bin)
    returns summary[method][bin_label] = (p25, p50, p75)
    """
    out: Dict[str, Dict[str, Tuple[float,float,float]]] = {}
    for method, by_bin in per_patch_medians.items():
        out[method] = {}
        for lab in dist_labels:
            vals = np.array(by_bin.get(lab, []), dtype=np.float64)
            if vals.size == 0:
                out[method][lab] = (0.0, 0.0, 0.0)
            else:
                out[method][lab] = (
                    float(np.percentile(vals, 25)),
                    float(np.percentile(vals, 50)),
                    float(np.percentile(vals, 75)),
                )
    return out


def plot_iqr_bars(out_png: Path, title: str,
                  summary: Dict[str, Dict[str, Tuple[float,float,float]]],
                  dist_labels: List[str],
                  method_order: List[str],
                  *, y_max: Optional[float] = None, dpi: int = 150, bin_spacing: float = 1.0):
    import matplotlib.pyplot as plt  # type: ignore

    n_bins = len(dist_labels)
    n_methods = len(method_order)
    x = np.arange(n_bins) * float(bin_spacing)

    # offsets
    width = 0.8 / max(1, n_methods)
    offsets = (np.arange(n_methods) - (n_methods - 1) / 2.0) * width

    fig_w = max(6, n_bins * 1.2 * float(bin_spacing))
    fig, ax = plt.subplots(figsize=(fig_w, 4.5), dpi=dpi)

    for mi, m in enumerate(method_order):
        off = offsets[mi]
        p25 = [summary[m][lab][0] for lab in dist_labels]
        p50 = [summary[m][lab][1] for lab in dist_labels]
        p75 = [summary[m][lab][2] for lab in dist_labels]

        # vertical IQR bars
        for bi in range(n_bins):
            ax.vlines(x[bi] + off, p25[bi], p75[bi], linewidth=2)
            # dotted caps
            ax.hlines(p25[bi], x[bi] + off - width*0.25, x[bi] + off + width*0.25, linestyles="dotted", linewidth=1)
            ax.hlines(p75[bi], x[bi] + off - width*0.25, x[bi] + off + width*0.25, linestyles="dotted", linewidth=1)
        # medians as points (no connecting line)
        ax.plot(x + off, p50, marker="o", linestyle="None", label=m)

    ax.set_xticks(x)
    ax.set_xticklabels(dist_labels, rotation=0)
    ax.set_ylabel("IQR of per-patch median error")
    ax.set_title(title)
    ax.legend(loc="best")
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)

    if y_max is not None:
        ax.set_ylim(0, y_max)
    else:
        ax.set_ylim(bottom=0)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


# ----------------------------
# Main
# ----------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = load_config_file(cfg_path)
    base_dir = cfg_path.resolve().parent

    # inputs
    gt_dir = resolve_path(deep_get(cfg, "input.gt_dir"), base_dir=base_dir)
    est_input_dir = resolve_path(deep_get(cfg, "input.est_input_dir"), base_dir=base_dir)
    if gt_dir is None or est_input_dir is None:
        raise SystemExit("Config must provide input.gt_dir and input.est_input_dir")

    gt_prefix = str(deep_get(cfg, "input.gt_prefix", "gt"))
    gt_key_pref = list(deep_get(cfg, "data.gt_key_preference", ["R_gt", "rain", "gt"]))

    # solvers
    solvers_cfg = normalize_solvers(deep_get(cfg, "input.solvers"), path_for_err="input.solvers")
    # build solver list: (name,label,dir,prefix,key_pref)
    solvers: List[Tuple[str,str,Path,str,List[str]]] = []
    for s in solvers_cfg:
        name = str(s.get("name") or s.get("label") or "solver")
        label = str(s.get("label") or name)
        sol_dir = resolve_path(s.get("sol_dir"), base_dir=base_dir)
        if sol_dir is None:
            raise SystemExit(f"Solver {label}: missing sol_dir")
        sol_prefix = str(s.get("sol_prefix", "est"))
        sol_key_pref = list(s.get("sol_key_preference", ["R_hat"]))
        solvers.append((name, label, sol_dir, sol_prefix, sol_key_pref))

    # outputs
    out_dir = resolve_path(deep_get(cfg, "output.out_dir", "batch_analyze_output_multi"), base_dir=base_dir) or (base_dir / "batch_analyze_output_multi").resolve()
    images_subdir = str(deep_get(cfg, "output.images_subdir", "images"))
    excel_name = str(deep_get(cfg, "output.excel_filename", "coverage_stats_long_multi.xlsx"))
    img_dir = (out_dir / images_subdir)
    excel_path = out_dir / excel_name

    # params
    thr = float(deep_get(cfg, "rain.threshold_mmph", 1.0))
    cov_bins_cfg = list(deep_get(cfg, "coverage.bins", [0,1,2,3,4,"5+"]))
    cov_exact, cov_ge = parse_coverage_bins(cov_bins_cfg)

    bin_edges = list(deep_get(cfg, "distance.bin_edges_m", [125,375,750,1500,3125]))
    dist_bins = parse_bins(bin_edges)
    dist_labels = [b[2] for b in dist_bins]
    max_candidates = int(deep_get(cfg, "distance.max_candidates", 64))
    dist_method = str(deep_get(cfg, "distance.method", "sampled_points")).strip().lower()
    sample_spacing_m = float(deep_get(cfg, "distance.sample_spacing_m", 250.0))
    k_query_samples = int(deep_get(cfg, "distance.k_query_samples", 48))
    chunk_size = int(deep_get(cfg, "distance.chunk_size", 8000))
    max_samples_per_link = int(deep_get(cfg, "distance.max_samples_per_link", 200))

    # plot scaling
    auto_y = bool(deep_get(cfg, "plots.automatic_vertical_scaling", True))
    y_scale = deep_get(cfg, "plots.vertical_scale", None)
    if not auto_y:
        try:
            y_max = float(y_scale)
        except Exception:
            raise SystemExit("plots.automatic_vertical_scaling=false but plots.vertical_scale is not a valid number")
        if y_max < 0:
            raise SystemExit("plots.vertical_scale must be non-negative")
    else:
        y_max = None
    dpi = int(deep_get(cfg, "plots.dpi", 150))
    bin_spacing = float(deep_get(cfg, "plots.bin_spacing", 1.35))

    # load files
    gt_files = list_npz(gt_dir, gt_prefix)
    if not gt_files:
        raise SystemExit(f"No GT files found in {gt_dir} with prefix {gt_prefix}_*.npz")

    # index GT by patch key
    gt_by_key: Dict[str, Path] = {patch_key_from_filename(p.name): p for p in gt_files}

    # also need est_input json per patch key
    est_jsons = list_json(est_input_dir, "est_input")
    est_by_key: Dict[str, Path] = {patch_key_from_filename(p.name): p for p in est_jsons}

    # sheets data
    sheets: Dict[str, List[Dict[str, Any]]] = {}

    # For plots: per method -> per bin -> list of per-patch medians
    medians_rainy: Dict[str, Dict[str, List[float]]] = {}
    medians_nonrainy: Dict[str, Dict[str, List[float]]] = {}

    # iterate per solver
    for name, label, sol_dir, sol_prefix, sol_key_pref in solvers:
        sol_files = list_npz(sol_dir, sol_prefix)
        sol_by_key = {patch_key_from_filename(p.name): p for p in sol_files}

        cov_rows: List[Dict[str, Any]] = []
        dist_rows: List[Dict[str, Any]] = []
        link_rows: List[Dict[str, Any]] = []

        medians_rainy[label] = {lab: [] for lab in dist_labels}
        medians_nonrainy[label] = {lab: [] for lab in dist_labels}

        # match patches by keys present in both GT and solver
        keys = sorted(set(gt_by_key.keys()) & set(sol_by_key.keys()))
        if not keys:
            print(f"[{label}] No matching patches between GT and {sol_dir}")
            continue

        for key in keys:
            gt_path = gt_by_key[key]
            sol_path = sol_by_key[key]
            est_path = est_by_key.get(key, None)
            if est_path is None:
                raise SystemExit(f"Missing est_input JSON for patch {key} under {est_input_dir}")

            gt = load_npz_first_key(gt_path, gt_key_pref)
            pred = load_npz_first_key(sol_path, sol_key_pref)

            if gt.shape != pred.shape:
                raise SystemExit(f"Shape mismatch for {key}: GT {gt.shape} vs {label} {pred.shape}")

            gt = gt.astype(np.float64)
            pred = pred.astype(np.float64)

            rainy = gt >= thr

            # coverage map + bins
            est = load_est_payload(est_path)
            cov_map, Hc, Wc = compute_coverage_map(est)
            if cov_map.shape != gt.shape:
                # allow if transposed? for now strict
                raise SystemExit(f"Coverage map shape {cov_map.shape} != GT shape {gt.shape} for {key}")

            # distance map d3
            if dist_method in ("sampled_points", "sampled", "samples"):
                d3_map, pix_m = compute_d3_map_sampled_points(
                    est,
                    sample_spacing_m=sample_spacing_m,
                    k_query_samples=k_query_samples,
                    chunk_size=chunk_size,
                    max_samples_per_link=max_samples_per_link,
                )
            else:
                d3_map, pix_m = compute_d3_map(est, bin_edges_m=bin_edges, max_candidates=max_candidates)
            if d3_map.shape != gt.shape:
                raise SystemExit(f"d3 map shape {d3_map.shape} != GT shape {gt.shape} for {key}")

            # compute signed/abs arrays for whole field
            # rainy relative:
            signed_r, abs_r, signed_n, abs_n = compute_pixel_errors(gt, pred, rainy)

            # Precompute full-field error arrays aligned to pixels for bin masking
            signed_full = np.empty_like(gt, dtype=np.float64)
            abs_full = np.empty_like(gt, dtype=np.float64)
            # rainy
            denom = np.where(gt == 0.0, 1.0, gt)
            signed_full[rainy] = (gt[rainy] - pred[rainy]) / denom[rainy]
            abs_full[rainy] = np.abs(signed_full[rainy])
            # nonrainy
            signed_full[~rainy] = pred[~rainy] - gt[~rainy]
            abs_full[~rainy] = np.abs(signed_full[~rainy])

            # --- CoverageStats per mask + coverage bin ---
            for mask_name, mask in (("rainy", rainy), ("nonrainy", ~rainy)):
                cov_vals = cov_map[mask].ravel()
                # per requested bins: exact + ge
                for v in cov_exact + ([] if cov_ge is None else [cov_ge]):
                    if cov_ge is not None and v == cov_ge:
                        m = cov_vals >= cov_ge
                        bin_lab = f"{cov_ge}+"
                    else:
                        m = cov_vals == v
                        bin_lab = str(v)
                    if not np.any(m):
                        # still add row? previous analyzer did include zeros sometimes.
                        n_pix = 0
                        row = dict(
                            patch_key=key, mask_type=mask_name, coverage_bin=bin_lab,
                            n_pixels=0,
                            mean_signed=0.0, median_signed=0.0,
                            mean_abs=0.0, std_abs=0.0,
                            median_abs=0.0, p90_abs=0.0, p99_abs=0.0, linf_abs=0.0,
                            l1_abs_sum=0.0,
                        )
                        cov_rows.append(row)
                        continue
                    # pixel indices within this (mask & covbin)
                    # build boolean for full image: this mask & cov condition
                    if cov_ge is not None and bin_lab.endswith("+"):
                        gmask = mask & (cov_map >= cov_ge)
                    else:
                        gmask = mask & (cov_map == int(bin_lab))
                    e_signed = signed_full[gmask].ravel()
                    e_abs = abs_full[gmask].ravel()
                    # l1: sum of abs quantity in this bin
                    l1 = float(np.sum(e_abs))
                    s = stats_row(e_signed, e_abs, l1_abs_sum=l1)
                    cov_rows.append(dict(
                        patch_key=key, mask_type=mask_name, coverage_bin=bin_lab, **s
                    ))

            # --- DistanceStats per mask + distance bin ---
            d3_vals = d3_map.ravel()
            d3_labels = assign_bin_labels(d3_vals, dist_bins).reshape(gt.shape)

            for mask_name, mask in (("rainy", rainy), ("nonrainy", ~rainy)):
                for _, _, bin_lab in dist_bins:
                    gmask = mask & (d3_labels == bin_lab)
                    e_signed = signed_full[gmask].ravel()
                    e_abs = abs_full[gmask].ravel()
                    l1 = float(np.sum(e_abs))
                    s = stats_row(e_signed, e_abs, l1_abs_sum=l1)
                    dist_rows.append(dict(
                        patch_key=key, mask_type=mask_name, distance_bin_m=bin_lab, **s
                    ))

                    # For final IQR plot: per-patch median_abs per bin (rainy uses abs_rel, nonrainy uses abs_diff)
                    if mask_name == "rainy" and e_abs.size > 0:
                        medians_rainy[label][bin_lab].append(float(np.median(e_abs)))
                    if mask_name == "nonrainy" and e_abs.size > 0:
                        medians_nonrainy[label][bin_lab].append(float(np.median(e_abs)))

            # --- LinkStats per patch ---
            try:
                A_obs, A_hat, L_km, valid, ge10 = compute_link_terms(est, pred)
                attn_all, J1_all, n_valid = attn_l1_and_J1(A_obs, A_hat, L_km, valid)
                attn_10, J1_10, n_10 = attn_l1_and_J1(A_obs, A_hat, L_km, ge10)
            except Exception as e:
                raise SystemExit(f"Failed to compute link stats for {key} ({label}): {e}") from e

            link_rows.append(dict(
                patch_key=key,
                n_links_valid=n_valid,
                attn_l1_all=attn_all,
                J1_all=J1_all,
                n_links_ge10km=n_10,
                attn_l1_ge10km=attn_10,
                J1_ge10km=J1_10,
            ))

        # store sheets
        sheets[f"CoverageStats_GTvs{label}"] = cov_rows
        sheets[f"DistanceStats_GTvs{label}"] = dist_rows
        sheets[f"LinkStats_GTvs{label}"] = link_rows

    # write excel
    write_workbook(excel_path, sheets)
    print(f"Wrote Excel: {excel_path}")

    # plots across solvers (IQR of per-patch medians)
    method_order = [label for _, label, _, _, _ in solvers if label in medians_rainy]
    if method_order:
        summary_r = compute_iqr_profile(medians_rainy, dist_labels)
        summary_n = compute_iqr_profile(medians_nonrainy, dist_labels)

        plot_iqr_bars(
            img_dir / "distance_iqr_medians_rainy_multi.png",
            "Rainy pixels: IQR of per-patch median |(GT-PRED)/GT| by distance bin",
            summary_r, dist_labels, method_order,
            y_max=y_max, dpi=dpi, bin_spacing=bin_spacing,
        )
        plot_iqr_bars(
            img_dir / "distance_iqr_medians_nonrainy_multi.png",
            "Non-rainy pixels: IQR of per-patch median |GT-PRED| by distance bin",
            summary_n, dist_labels, method_order,
            y_max=y_max, dpi=dpi, bin_spacing=bin_spacing,
        )
        print(f"Wrote plots under: {img_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
