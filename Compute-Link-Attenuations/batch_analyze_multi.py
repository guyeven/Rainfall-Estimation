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
import sys
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


def progress_iter(items: Iterable[Any], *, total: Optional[int] = None, desc: str = "") -> Iterable[Any]:
    try:
        from tqdm import tqdm  # type: ignore
        return tqdm(items, total=total, desc=desc)
    except Exception:
        def gen():
            count = 0
            for count, item in enumerate(items, 1):
                if total is not None:
                    msg = f"{desc} {count}/{total}"
                else:
                    msg = f"{desc} {count}"
                if count == 1 or count % 5 == 0 or (total is not None and count == total):
                    sys.stdout.write("\r" + msg)
                    sys.stdout.flush()
                yield item
            if count > 0:
                sys.stdout.write("\r" + msg + "\n")
                sys.stdout.flush()
        return gen()


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



def compute_dk_maps_sampled_points(
    est: dict,
    k_values: Sequence[int],
    *,
    sample_spacing_m: float = 250.0,
    k_query_samples: int = 48,
    chunk_size: int = 8000,
    max_samples_per_link: int = 200,
    warn_shortfall: bool = True,
    warn_threshold_frac: float = 0.01,
    debug_label: Optional[str] = None,
) -> Tuple[Dict[int, np.ndarray], float]:
    """
    Compute dk(p) = distance in meters from pixel center to the k-th closest link (point-to-segment),
    for each k in k_values.

    This method matches the *older* analyzer: it samples points along each segment at a fixed spacing,
    builds a KD-tree over those sampled points, then uses nearest sampled points to propose candidate
    links. Exact point-to-segment distances are computed for candidate links, and the k-th smallest is taken.

    Returns (dict k -> dk_map_m, pixel_size_m)
    """
    header = est["header"]
    links = est["links"]
    H = int(header["H"])
    W = int(header["W"])
    pix = float(header["pixel_size_m"])

    k_values = sorted({int(k) for k in k_values if int(k) >= 1})
    if not k_values:
        return {}, pix
    k_max = max(k_values)

    if not links or len(links) < k_max:
        return {k: np.full((H, W), np.inf, dtype=np.float64) for k in k_values}, pix

    try:
        from scipy.spatial import cKDTree  # type: ignore
    except Exception as e:
        raise RuntimeError("scipy is required for dk computation (scipy.spatial.cKDTree).") from e

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

    out = {k: np.full((H * W,), np.inf, dtype=np.float64) for k in k_values}

    kq = int(k_query_samples)
    kq = max(kq, 12)
    # cap kq to number of samples
    kq = min(kq, int(sample_xy.shape[0]))

    total_queries = 0
    shortfall_queries = 0

    for start in range(0, pts.shape[0], int(chunk_size)):
        end = min(pts.shape[0], start + int(chunk_size))
        q = pts[start:end]

        # query nearest sample points
        _, nn_idx = tree.query(q, k=kq, workers=-1)
        if nn_idx.ndim == 1:
            nn_idx = nn_idx[:, None]

        for bi in range(q.shape[0]):
            cand_links = np.unique(sample_to_link[nn_idx[bi]])

            # ensure enough candidates
            if cand_links.size < k_max:
                shortfall_queries += 1
                kq2 = min(int(sample_xy.shape[0]), kq * 4)
                _, nn_idx2 = tree.query(q[bi], k=kq2, workers=-1)
                cand_links = np.unique(sample_to_link[np.atleast_1d(nn_idx2)])

            if cand_links.size == 0:
                continue

            # exact point-to-segment distances for candidate links
            px = q[bi, 0]
            py = q[bi, 1]
            ds = point_to_segment_dist(px, py, x0[cand_links], y0[cand_links], x1[cand_links], y1[cand_links])

            if ds.size == 0:
                continue

            for k in k_values:
                if ds.size < k:
                    out[k][start + bi] = np.inf
                else:
                    out[k][start + bi] = float(np.partition(ds, k - 1)[k - 1])

            total_queries += 1

    if warn_shortfall and total_queries > 0:
        frac = float(shortfall_queries) / float(total_queries)
        if frac >= float(warn_threshold_frac):
            lab = f" ({debug_label})" if debug_label else ""
            print(
                f"[dist] Candidate shortfall{lab}: {shortfall_queries}/{total_queries} "
                f"pixels had <{k_max} candidate links "
                f"(k_query_samples={k_query_samples}, frac={frac:.3f})"
            )

    return {k: v.reshape(H, W) for k, v in out.items()}, pix


def compute_dk_maps(est: dict, k_values: Sequence[int], *, max_candidates: int) -> Tuple[Dict[int, np.ndarray], float]:
    """
    dk(p) = distance in meters from pixel-center to the k-th closest link (point-to-segment),
            approximated by using KDTree over endpoints+midpoints to propose candidates.

    Returns (dict k -> dk_map_m, pixel_size_m)
    """
    header = est["header"]
    links = est["links"]
    H = int(header["H"])
    W = int(header["W"])
    pix = float(header["pixel_size_m"])

    k_values = sorted({int(k) for k in k_values if int(k) >= 1})
    if not k_values:
        return {}, pix
    k_max = max(k_values)

    if not links or len(links) < k_max:
        return {k: np.full((H, W), np.inf, dtype=np.float64) for k in k_values}, pix

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
        raise RuntimeError("scipy is required for dk computation (scipy.spatial.cKDTree).") from e

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
    K = max(k_max, min(K, pts.shape[0]))
    _, idx_proxy = tree.query(np.stack([X.ravel(), Y.ravel()], axis=1), k=K, workers=-1)
    # ensure 2d
    if K == 1:
        idx_proxy = idx_proxy[:, None]

    out = {k: np.empty(H * W, dtype=np.float64) for k in k_values}
    # compute per pixel
    for t in range(H * W):
        cand_links = np.unique(pt_to_link[idx_proxy[t]])
        # true segment distances for these links
        dist = point_to_segment_dist(X.ravel()[t], Y.ravel()[t], x0[cand_links], y0[cand_links], x1[cand_links], y1[cand_links])
        for k in k_values:
            if dist.size < k:
                out[k][t] = np.inf
            else:
                out[k][t] = float(np.partition(dist, k - 1)[k - 1])
    return {k: v.reshape(H, W) for k, v in out.items()}, pix


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


def evaluate_objective_values(
    prob,
    make_objective_fn,
    R_field: np.ndarray,
    *,
    lam: float,
    mu: float,
    eps: float,
) -> float:
    if R_field.shape != (prob.H, prob.W):
        raise ValueError(f"R_field shape {R_field.shape} != (H,W)=({prob.H},{prob.W})")
    fun, _ = make_objective_fn(prob, lam=lam, mu=mu, eps=eps)
    return float(fun(R_field.reshape(prob.P)))


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


def compute_relative_iqr_profile(
    summary: Dict[str, Dict[str, Tuple[float, float, float]]],
    *,
    idw_label: str,
    dist_labels: List[str],
) -> Dict[str, Dict[str, Tuple[float, float, float]]]:
    """
    Divide each method's (p25,p50,p75) by IDW's p50 (median-of-medians) per bin.
    """
    if idw_label not in summary:
        return {}
    out: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
    for method, by_bin in summary.items():
        out[method] = {}
        for lab in dist_labels:
            p25, p50, p75 = by_bin.get(lab, (0.0, 0.0, 0.0))
            idw_med = summary[idw_label].get(lab, (0.0, 0.0, 0.0))[1]
            if idw_med == 0.0:
                out[method][lab] = (0.0, 0.0, 0.0)
            else:
                out[method][lab] = (p25 / idw_med, p50 / idw_med, p75 / idw_med)
    return out


def plot_iqr_bars(out_png: Path, title: str,
                  summary: Dict[str, Dict[str, Tuple[float,float,float]]],
                  dist_labels: List[str],
                  method_order: List[str],
                  *, y_max: Optional[float] = None, dpi: int = 150, bin_spacing: float = 1.0,
                  tick_labels: Optional[List[str]] = None):
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
    if tick_labels is None:
        tick_labels = dist_labels
    has_multiline = any("\n" in str(lab) for lab in tick_labels)
    if has_multiline:
        ax.set_xticklabels(tick_labels, rotation=20, ha="right", fontsize=8)
        fig.subplots_adjust(bottom=0.28)
        ax.set_xlabel("Distance bin (m)\nSecond line: avg pixels [avg-std, avg+std]")
    else:
        ax.set_xticklabels(tick_labels, rotation=0)
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


def build_bin_tick_labels(dist_labels: List[str], counts_by_bin: Dict[str, List[int]]) -> List[str]:
    out: List[str] = []
    for lab in dist_labels:
        vals = np.array(counts_by_bin.get(lab, []), dtype=np.float64)
        if vals.size == 0:
            out.append(f"{lab}\npx avg=0 [0,0]")
            continue
        avg = float(np.mean(vals))
        std = float(np.std(vals, ddof=0))
        lo = max(0.0, avg - std)
        hi = max(0.0, avg + std)
        out.append(f"{lab}\npx avg={avg:.0f} [{lo:.0f},{hi:.0f}]")
    return out


def filter_bins_by_zero_fraction(
    dist_labels: List[str],
    counts_by_bin: Dict[str, List[int]],
    *,
    zero_frac_threshold: float,
) -> List[str]:
    out: List[str] = []
    for lab in dist_labels:
        vals = counts_by_bin.get(lab, [])
        if not vals:
            continue
        zeros = sum(1 for v in vals if v == 0)
        frac = float(zeros) / float(len(vals))
        if frac < zero_frac_threshold:
            out.append(lab)
    return out


def plot_rae_histograms(
    out_png: Path,
    *,
    title: str,
    dist_labels: List[str],
    data_by_bin: Dict[str, List[float]],
    bins: int = 50,
    dpi: int = 150,
):
    import matplotlib.pyplot as plt  # type: ignore

    n_bins = len(dist_labels)
    ncols = min(4, max(1, n_bins))
    nrows = int(math.ceil(n_bins / ncols))

    fig_w = max(8, ncols * 3.2)
    fig_h = max(3.0, nrows * 2.6)
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(fig_w, fig_h), dpi=dpi)
    if nrows == 1 and ncols == 1:
        axes = np.array([[axes]])
    elif nrows == 1:
        axes = np.array([axes])
    elif ncols == 1:
        axes = axes[:, None]

    for i, lab in enumerate(dist_labels):
        r = i // ncols
        c = i % ncols
        ax = axes[r][c]
        vals = np.array(data_by_bin.get(lab, []), dtype=np.float64)
        if vals.size > 0:
            ax.hist(vals, bins=bins, color="#4C78A8", alpha=0.85)
        ax.set_title(lab)
        ax.set_xlabel("RAE = |GT-PRED|/GT")
        ax.set_ylabel("count")
        ax.grid(True, axis="y", linestyle=":", linewidth=0.6)

    # hide unused subplots
    for i in range(n_bins, nrows * ncols):
        r = i // ncols
        c = i % ncols
        axes[r][c].axis("off")

    fig.suptitle(title)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_png.parent.mkdir(parents=True, exist_ok=True)
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

    k_values = list(deep_get(cfg, "distance.k_values", [3]))
    k_values = sorted({int(k) for k in k_values if int(k) >= 1})
    if not k_values:
        k_values = [3]

    bin_edges = list(deep_get(cfg, "distance.bin_edges_m", [125,375,750,1500,3125]))
    dist_bins = parse_bins(bin_edges)
    dist_labels = [b[2] for b in dist_bins]
    max_candidates = int(deep_get(cfg, "distance.max_candidates", 64))
    dist_method = str(deep_get(cfg, "distance.method", "sampled_points")).strip().lower()
    sample_spacing_m = float(deep_get(cfg, "distance.sample_spacing_m", 250.0))
    k_query_samples = int(deep_get(cfg, "distance.k_query_samples", 48))
    chunk_size = int(deep_get(cfg, "distance.chunk_size", 8000))
    max_samples_per_link = int(deep_get(cfg, "distance.max_samples_per_link", 200))

    obj_cfg = deep_get(cfg, "objective", {}) or {}
    obj_eps = float(obj_cfg.get("eps", 0.01))
    obj_pairs_raw = obj_cfg.get("pairs", []) or []
    obj_pairs: List[Tuple[float, float]] = []
    for item in obj_pairs_raw:
        if isinstance(item, dict):
            lam = item.get("lambda", item.get("lam", None))
            mu = item.get("mu", None)
            if lam is None or mu is None:
                continue
            obj_pairs.append((float(lam), float(mu)))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            obj_pairs.append((float(item[0]), float(item[1])))
    if not obj_pairs:
        obj_pairs = []

    rae_cfg = deep_get(cfg, "rae_hist", {}) or {}
    rae_enabled = bool(rae_cfg.get("enabled", False))
    rae_bins = int(rae_cfg.get("bins", 50))
    rae_max_patches = rae_cfg.get("max_patches", None)
    rae_out_subdir = str(rae_cfg.get("out_dir", "images/RAE_histograms"))

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
    prune_bins_enabled = bool(deep_get(cfg, "plots.prune_bins_enabled", False))
    prune_bins_zero_frac = float(deep_get(cfg, "plots.prune_bins_zero_frac", 0.5))

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

    # For plots: per k -> per method -> per bin -> list of per-patch medians
    medians_rainy: Dict[int, Dict[str, Dict[str, List[float]]]] = {k: {} for k in k_values}
    medians_nonrainy: Dict[int, Dict[str, Dict[str, List[float]]]] = {k: {} for k in k_values}
    bin_counts: Dict[int, Dict[str, Dict[str, List[int]]]] = {
        k: {"rainy": {lab: [] for lab in dist_labels}, "nonrainy": {lab: [] for lab in dist_labels}}
        for k in k_values
    }
    bin_counts_seen: set = set()

    objective_rows: List[Dict[str, Any]] = []
    objective_gt_done: set = set()

    obj_enabled = len(obj_pairs) > 0
    if obj_enabled:
        from solve_rain_lbfgsb import load_est_input_json as load_est_for_obj  # type: ignore
        from solve_rain_lbfgsb import make_objective as make_objective_fn  # type: ignore
        prob_cache: Dict[str, Any] = {}

    # iterate per solver
    for name, label, sol_dir, sol_prefix, sol_key_pref in progress_iter(
        solvers, total=len(solvers), desc="Solvers"
    ):
        sol_files = list_npz(sol_dir, sol_prefix)
        sol_by_key = {patch_key_from_filename(p.name): p for p in sol_files}

        cov_rows: List[Dict[str, Any]] = []
        dist_rows_by_k: Dict[int, List[Dict[str, Any]]] = {k: [] for k in k_values}
        link_rows: List[Dict[str, Any]] = []

        for k in k_values:
            medians_rainy[k][label] = {lab: [] for lab in dist_labels}
            medians_nonrainy[k][label] = {lab: [] for lab in dist_labels}

        rae_hist_data: Optional[Dict[int, Dict[str, List[float]]]] = None
        if rae_enabled:
            rae_hist_data = {k: {lab: [] for lab in dist_labels} for k in k_values}

        # match patches by keys present in both GT and solver
        keys = sorted(set(gt_by_key.keys()) & set(sol_by_key.keys()))
        if not keys:
            print(f"[{label}] No matching patches between GT and {sol_dir}")
            continue

        hist_keys = keys
        if rae_enabled and rae_max_patches is not None:
            try:
                kmax = int(rae_max_patches)
                if kmax > 0:
                    hist_keys = keys[:kmax]
            except Exception:
                pass

        for key in progress_iter(keys, total=len(keys), desc=f"{label} patches"):
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

            # distance maps d_k
            if dist_method in ("sampled_points", "sampled", "samples"):
                dk_maps, pix_m = compute_dk_maps_sampled_points(
                    est,
                    k_values,
                    sample_spacing_m=sample_spacing_m,
                    k_query_samples=k_query_samples,
                    chunk_size=chunk_size,
                    max_samples_per_link=max_samples_per_link,
                )
            else:
                dk_maps, pix_m = compute_dk_maps(est, k_values, max_candidates=max_candidates)
            for k in k_values:
                d_map = dk_maps.get(k)
                if d_map is None:
                    raise SystemExit(f"Missing d{k} map for {key}")
                if d_map.shape != gt.shape:
                    raise SystemExit(f"d{k} map shape {d_map.shape} != GT shape {gt.shape} for {key}")

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

            # --- Objective values (GT + solver) ---
            if obj_enabled:
                est_key = str(est_path)
                prob = prob_cache.get(est_key)
                if prob is None:
                    prob = load_est_for_obj(est_path, warn=False)
                    prob_cache[est_key] = prob
                for lam, mu in obj_pairs:
                    gt_tag = (key, lam, mu)
                    if gt_tag not in objective_gt_done:
                        j_gt = evaluate_objective_values(
                            prob, make_objective_fn, gt,
                            lam=lam, mu=mu, eps=obj_eps,
                        )
                        objective_rows.append(dict(
                            patch_key=key,
                            target="GT",
                            lambda_val=float(lam),
                            mu_val=float(mu),
                            eps=float(obj_eps),
                            J=float(j_gt),
                        ))
                        objective_gt_done.add(gt_tag)

                    j_sol = evaluate_objective_values(
                        prob, make_objective_fn, pred,
                        lam=lam, mu=mu, eps=obj_eps,
                    )
                    objective_rows.append(dict(
                        patch_key=key,
                        target=label,
                        lambda_val=float(lam),
                        mu_val=float(mu),
                        eps=float(obj_eps),
                        J=float(j_sol),
                    ))

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

            # --- DistanceStats per mask + distance bin (per k) ---
            for k in k_values:
                d_map = dk_maps[k]
                d_vals = d_map.ravel()
                d_labels = assign_bin_labels(d_vals, dist_bins).reshape(gt.shape)

                for mask_name, mask in (("rainy", rainy), ("nonrainy", ~rainy)):
                    for _, _, bin_lab in dist_bins:
                        gmask = mask & (d_labels == bin_lab)
                        count_key = (k, mask_name, bin_lab, key)
                        if count_key not in bin_counts_seen:
                            bin_counts[k][mask_name][bin_lab].append(int(np.sum(gmask)))
                            bin_counts_seen.add(count_key)
                        e_signed = signed_full[gmask].ravel()
                        e_abs = abs_full[gmask].ravel()
                        l1 = float(np.sum(e_abs))
                        s = stats_row(e_signed, e_abs, l1_abs_sum=l1)
                        dist_rows_by_k[k].append(dict(
                            patch_key=key, mask_type=mask_name, distance_bin_m=bin_lab, **s
                        ))

                        # For final IQR plot: per-patch median_abs per bin (rainy uses abs_rel, nonrainy uses abs_diff)
                        if mask_name == "rainy" and e_abs.size > 0:
                            medians_rainy[k][label][bin_lab].append(float(np.median(e_abs)))
                        if mask_name == "nonrainy" and e_abs.size > 0:
                            medians_nonrainy[k][label][bin_lab].append(float(np.median(e_abs)))

                        # RAE histogram data (rainy only, optional)
                        if rae_hist_data is not None and key in hist_keys and mask_name == "rainy" and e_abs.size > 0:
                            rae_hist_data[k][bin_lab].extend(e_abs.tolist())

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
        for k in k_values:
            if k == 3:
                sheets[f"DistanceStats_GTvs{label}"] = dist_rows_by_k[k]
            else:
                sheets[f"DistanceStatsK{k}_GTvs{label}"] = dist_rows_by_k[k]
        sheets[f"LinkStats_GTvs{label}"] = link_rows

        # RAE histograms (rainy only)
        if rae_hist_data is not None:
            rae_dir = out_dir / rae_out_subdir
            for k in k_values:
                out_png = rae_dir / f"rae_hist_k{k}_{label}.png"
                plot_rae_histograms(
                    out_png,
                    title=f"RAE histograms (rainy) | k={k} | {label}",
                    dist_labels=dist_labels,
                    data_by_bin=rae_hist_data[k],
                    bins=rae_bins,
                    dpi=dpi,
                )

    # optional objective sheet
    if objective_rows:
        sheets["Objective_J"] = objective_rows

    # write excel
    write_workbook(excel_path, sheets)
    print(f"Wrote Excel: {excel_path}")

    # plots across solvers (IQR of per-patch medians)
    method_order = [label for _, label, _, _, _ in solvers if label in medians_rainy[k_values[0]]]
    if method_order:
        for k in k_values:
            summary_r = compute_iqr_profile(medians_rainy[k], dist_labels)
            summary_n = compute_iqr_profile(medians_nonrainy[k], dist_labels)
            labels_r = dist_labels
            labels_n = dist_labels
            if prune_bins_enabled:
                labels_r = filter_bins_by_zero_fraction(
                    dist_labels, bin_counts[k]["rainy"],
                    zero_frac_threshold=prune_bins_zero_frac,
                )
                labels_n = filter_bins_by_zero_fraction(
                    dist_labels, bin_counts[k]["nonrainy"],
                    zero_frac_threshold=prune_bins_zero_frac,
                )
            tick_labels_r = build_bin_tick_labels(labels_r, bin_counts[k]["rainy"])
            tick_labels_n = build_bin_tick_labels(labels_n, bin_counts[k]["nonrainy"])

            if len(k_values) == 1 and k == 3:
                rainy_name = "distance_iqr_medians_rainy_multi.png"
                nonrainy_name = "distance_iqr_medians_nonrainy_multi.png"
                rainy_title = "Rainy pixels: IQR of per-patch median |(GT-PRED)/GT| by distance bin"
                nonrainy_title = "Non-rainy pixels: IQR of per-patch median |GT-PRED| by distance bin"
            else:
                rainy_name = f"distance_iqr_medians_rainy_multi_k{k}.png"
                nonrainy_name = f"distance_iqr_medians_nonrainy_multi_k{k}.png"
                rainy_title = f"Rainy pixels: IQR of per-patch median |(GT-PRED)/GT| by distance bin (k={k})"
                nonrainy_title = f"Non-rainy pixels: IQR of per-patch median |GT-PRED| by distance bin (k={k})"

            plot_iqr_bars(
                img_dir / rainy_name,
                rainy_title,
                summary_r, labels_r, method_order,
                y_max=y_max, dpi=dpi, bin_spacing=bin_spacing,
                tick_labels=tick_labels_r,
            )
            plot_iqr_bars(
                img_dir / nonrainy_name,
                nonrainy_title,
                summary_n, labels_n, method_order,
                y_max=y_max, dpi=dpi, bin_spacing=bin_spacing,
                tick_labels=tick_labels_n,
            )

            # relative plots vs IDW (median-of-medians)
            if "IDW" in summary_r:
                summary_r_rel = compute_relative_iqr_profile(summary_r, idw_label="IDW", dist_labels=dist_labels)
                summary_n_rel = compute_relative_iqr_profile(summary_n, idw_label="IDW", dist_labels=dist_labels)

                plot_iqr_bars(
                    img_dir / rainy_name.replace(".png", "_rel.png"),
                    f"{rainy_title} (relative to IDW medians)",
                    summary_r_rel, labels_r, method_order,
                    y_max=None, dpi=dpi, bin_spacing=bin_spacing,
                    tick_labels=tick_labels_r,
                )
                plot_iqr_bars(
                    img_dir / nonrainy_name.replace(".png", "_rel.png"),
                    f"{nonrainy_title} (relative to IDW medians)",
                    summary_n_rel, labels_n, method_order,
                    y_max=None, dpi=dpi, bin_spacing=bin_spacing,
                    tick_labels=tick_labels_n,
                )
        print(f"Wrote plots under: {img_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
