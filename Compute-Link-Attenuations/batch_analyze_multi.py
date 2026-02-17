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
     l1_rae_sum, l1_abs_mmph_sum, l1_abs_mmph_sum_norm_hw

   Conventions:
   - Rainy pixels: signed_rel = (GT - PRED)/GT, abs_rel = |GT-PRED|/GT
   - Non-rainy pixels: signed_diff = (PRED - GT), abs_diff = |PRED-GT|
   l1_rae_sum = sum(|GT-PRED|/GT), using denom=1 when GT=0.
   l1_abs_mmph_sum = sum(|GT-PRED|).
   l1_abs_mmph_sum_norm_hw = l1_abs_mmph_sum / (H*W) for the patch.

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


def load_npz_meta_scalars(path: Path) -> Dict[str, float]:
    """
    Read scalar meta_* fields from solver npz, if present.
    """
    out: Dict[str, float] = {}
    z = np.load(path, allow_pickle=True)
    for k in z.files:
        if not str(k).startswith("meta_"):
            continue
        try:
            v = z[k]
            if np.isscalar(v):
                out[str(k)] = float(v)
            elif isinstance(v, np.ndarray) and v.size == 1:
                out[str(k)] = float(v.reshape(-1)[0])
        except Exception:
            continue
    return out


def build_neighbor_triplets(H: int, W: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    a_idx: List[int] = []
    b_idx: List[int] = []
    c_idx: List[int] = []
    for i in range(H):
        for j in range(W):
            b = i * W + j
            neigh: List[int] = []
            if i > 0:
                neigh.append((i - 1) * W + j)
            if i + 1 < H:
                neigh.append((i + 1) * W + j)
            if j > 0:
                neigh.append(i * W + (j - 1))
            if j + 1 < W:
                neigh.append(i * W + (j + 1))
            for a in neigh:
                for c in neigh:
                    if a == c:
                        continue
                    a_idx.append(a)
                    b_idx.append(b)
                    c_idx.append(c)
    if not a_idx:
        z = np.zeros(0, dtype=np.int64)
        return z, z, z
    return (
        np.asarray(a_idx, dtype=np.int64),
        np.asarray(b_idx, dtype=np.int64),
        np.asarray(c_idx, dtype=np.int64),
    )


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

def stats_row(
    err_signed: np.ndarray,
    err_abs: np.ndarray,
    *,
    l1_rae_sum: float,
    l1_abs_mmph_sum: float,
) -> Dict[str, Any]:
    if err_abs.size == 0:
        return dict(
            n_pixels=0,
            mean_signed=0.0, median_signed=0.0,
            mean_abs=0.0, std_abs=0.0,
            median_abs=0.0, p90_abs=0.0, p99_abs=0.0, linf_abs=0.0,
            l1_rae_sum=0.0,
            l1_abs_mmph_sum=0.0,
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
        l1_rae_sum=float(l1_rae_sum),
        l1_abs_mmph_sum=float(l1_abs_mmph_sum),
    )


def append_average_rows(
    rows: List[Dict[str, Any]],
    *,
    group_keys: List[str],
    patch_key_field: str = "patch_key",
    average_label: str = "AVERAGE",
) -> List[Dict[str, Any]]:
    """
    Append average rows over patches, grouped by group_keys.
    """
    if not rows:
        return rows

    def _is_number(v: Any) -> bool:
        return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)

    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for r in rows:
        if r.get(patch_key_field) == average_label:
            continue
        g = tuple(r.get(k, None) for k in group_keys)
        grouped.setdefault(g, []).append(r)

    avg_rows: List[Dict[str, Any]] = []
    for g, grp_rows in grouped.items():
        if not grp_rows:
            continue
        out: Dict[str, Any] = {patch_key_field: average_label}
        for i, k in enumerate(group_keys):
            out[k] = g[i]

        keys = set()
        for rr in grp_rows:
            keys.update(rr.keys())
        keys.discard(patch_key_field)
        for k in group_keys:
            keys.discard(k)

        for k in sorted(keys):
            vals = [rr.get(k, None) for rr in grp_rows]
            nums = [float(v) for v in vals if _is_number(v)]
            if nums:
                out[k] = float(np.mean(nums))
            else:
                out[k] = ""
        avg_rows.append(out)

    return rows + avg_rows


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
    R_field: np.ndarray,
    *,
    lam: float,
    mu: float,
    eps: float,
    eta: float = 0.0,
) -> Dict[str, float]:
    if R_field.shape != (prob.H, prob.W):
        raise ValueError(f"R_field shape {R_field.shape} != (H,W)=({prob.H},{prob.W})")
    R = np.asarray(R_field, dtype=np.float64).ravel()

    # --- J1 data term ---
    pix = prob.pix_idx
    li = prob.link_idx
    ds = prob.ds_km
    A_obs = prob.A_obs
    L_km = prob.L_km
    valid = prob.valid_links
    k = prob.k
    a = prob.alpha

    Rp = R[pix]
    pow_a = np.power(Rp, a[li], where=(Rp > 0), out=np.zeros_like(Rp))
    contrib = ds * k[li] * pow_a
    A_hat = np.bincount(li, weights=contrib, minlength=prob.L).astype(np.float64)

    r = np.zeros(prob.L, dtype=np.float64)
    r[valid] = (A_hat[valid] - A_obs[valid]) / L_km[valid]
    J1 = float(np.dot(r[valid], r[valid]))

    # --- J2 smoothness term ---
    R_eps = R + eps
    u = np.log(R_eps)
    du = u[prob.n_u] - u[prob.n_v]
    J2 = float(np.dot(du, du))

    # --- J3 shrinkage term ---
    J3 = float(np.dot(R, R))

    # --- J4 triplet term: sum((f(b)-f(a))-(f(c)-f(b))) ---
    t_a, t_b, t_c = build_neighbor_triplets(prob.H, prob.W)
    if t_a.size > 0:
        J4 = float(np.sum((R[t_b] - R[t_a]) - (R[t_c] - R[t_b])))
    else:
        J4 = 0.0

    lamJ2 = float(lam * J2)
    muJ3 = float(mu * J3)
    etaJ4 = float(eta * J4)
    J = J1 + lamJ2 + muJ3 + etaJ4
    return dict(
        J=float(J),
        J1=float(J1),
        J2=float(J2),
        J3=float(J3),
        J4=float(J4),
        wJ1=float(J1),
        wJ2=lamJ2,
        wJ3=muJ3,
        wJ4=etaJ4,
        etaJ4=etaJ4,
        eta=float(eta),
    )


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


def compute_p90_profile(per_patch_p90s: Dict[str, Dict[str, List[float]]],
                        dist_labels: List[str]) -> Dict[str, Dict[str, Tuple[float,float,float]]]:
    """
    per_patch_p90s[method][bin_label] = list of p90s (one per patch that had pixels in that bin)
    returns summary[method][bin_label] = (p25, p50, p90)
    """
    out: Dict[str, Dict[str, Tuple[float,float,float]]] = {}
    for method, by_bin in per_patch_p90s.items():
        out[method] = {}
        for lab in dist_labels:
            vals = np.array(by_bin.get(lab, []), dtype=np.float64)
            if vals.size == 0:
                out[method][lab] = (0.0, 0.0, 0.0)
            else:
                out[method][lab] = (
                    float(np.percentile(vals, 25)),
                    float(np.percentile(vals, 50)),
                    float(np.percentile(vals, 90)),
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
                  tick_labels: Optional[List[str]] = None,
                  y_label: Optional[str] = None):
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
    ax.set_ylabel(y_label or "IQR of per-patch median error")
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


def plot_ratio_iqr(
    out_png: Path,
    *,
    title: str,
    entries: List[Tuple[str, str, List[float]]],
    dpi: int = 150,
) -> None:
    """
    entries: list of (solver_label, x_label, values_per_patch)
    """
    import matplotlib.pyplot as plt  # type: ignore

    if not entries:
        return

    x = np.arange(len(entries))
    fig_w = max(8, len(entries) * 0.8)
    fig, ax = plt.subplots(figsize=(fig_w, 4.5), dpi=dpi)

    # color by solver
    solver_labels = []
    for solver, _, _ in entries:
        if solver not in solver_labels:
            solver_labels.append(solver)
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors = {s: color_cycle[i % max(1, len(color_cycle))] for i, s in enumerate(solver_labels)}

    p25s = []
    p50s = []
    p75s = []
    for _, _, vals in entries:
        if vals:
            arr = np.array(vals, dtype=np.float64)
            p25s.append(float(np.percentile(arr, 25)))
            p50s.append(float(np.percentile(arr, 50)))
            p75s.append(float(np.percentile(arr, 75)))
        else:
            p25s.append(0.0)
            p50s.append(0.0)
            p75s.append(0.0)

    # plot
    for i, (solver, _, _) in enumerate(entries):
        c = colors.get(solver, None)
        ax.vlines(x[i], p25s[i], p75s[i], linewidth=2, color=c)
        ax.hlines(p25s[i], x[i] - 0.15, x[i] + 0.15, linestyles="dotted", linewidth=1, color=c)
        ax.hlines(p75s[i], x[i] - 0.15, x[i] + 0.15, linestyles="dotted", linewidth=1, color=c)
        ax.plot(x[i], p50s[i], marker="o", linestyle="None", color=c)

    ax.set_xticks(x)
    ax.set_xticklabels([lab for _, lab, _ in entries], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Median of per-patch ratios (IQR)")
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)

    # legend
    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[s], label=s) for s in solver_labels]
    ax.legend(handles=handles, loc="best")

    fig.text(
        0.5,
        0.01,
        "E = sum(A_obs - A_hat) / sum(|L_km|); E2 = sum((A_obs - A_hat)^2) / sum(|L_km|) over all links",
        ha="center",
        fontsize=8,
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_png)
    plt.close(fig)


def plot_fp_fn_summary(
    out_png: Path,
    *,
    title: str,
    rows: List[Dict[str, Any]],
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    if not rows:
        return

    solvers = [r["solver"] for r in rows]
    fp_mean = [float(r["fp_rate_mean"]) for r in rows]
    fp_std = [float(r["fp_rate_std"]) for r in rows]
    fn_mean = [float(r["fn_rate_mean"]) for r in rows]
    fn_std = [float(r["fn_rate_std"]) for r in rows]

    x = np.arange(len(solvers))
    width = 0.35

    fig_w = max(8, len(solvers) * 0.8)
    fig, ax = plt.subplots(figsize=(fig_w, 4.5), dpi=dpi)

    ax.errorbar(x - width/2, fp_mean, yerr=fp_std, fmt="o", capsize=4, label="Wet FP rate")
    ax.errorbar(x + width/2, fn_mean, yerr=fn_std, fmt="o", capsize=4, label="Wet FN rate")

    ax.set_xticks(x)
    ax.set_xticklabels(solvers, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Mean rate across patches (±1 std)")
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)
    ax.legend(loc="best")

    fig.text(
        0.5,
        0.01,
        "Positive = wet (gt >= threshold). FP: pred wet & GT dry. FN: pred dry & GT wet.",
        ha="center",
        fontsize=8,
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
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


def build_rain_gt_bin_edges(*, max_upper: float = 128.0) -> List[float]:
    edges: List[float] = [0.0, 1.0]
    cur = 1.0
    while cur < float(max_upper):
        cur *= 2.0
        edges.append(float(cur))
    return edges


def format_interval_label(lo: float, hi: float) -> str:
    lo_s = str(int(lo)) if float(lo).is_integer() else f"{lo:g}"
    hi_s = str(int(hi)) if float(hi).is_integer() else f"{hi:g}"
    return f"[{lo_s},{hi_s})"


def plot_gt_binned_patchavg_error(
    out_png: Path,
    *,
    title: str,
    bin_labels: List[str],
    solver_order: List[str],
    mean_by_solver: Dict[str, List[float]],
    std_by_solver: Dict[str, List[float]],
    y_label: str,
    dpi: int = 150,
):
    import matplotlib.pyplot as plt  # type: ignore

    if not bin_labels or not solver_order:
        return
    x = np.arange(len(bin_labels), dtype=np.float64)
    nsol = max(1, len(solver_order))
    width = 0.8 / nsol
    fig_w = max(10.0, len(bin_labels) * 1.3)
    fig, ax = plt.subplots(figsize=(fig_w, 5.8), dpi=dpi)
    color_cycle = ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F"]

    for s_idx, solver in enumerate(solver_order):
        m = np.array(mean_by_solver.get(solver, []), dtype=np.float64)
        sd = np.array(std_by_solver.get(solver, []), dtype=np.float64)
        if m.size == 0:
            continue
        offset = (s_idx - (nsol - 1) / 2.0) * width
        xpos = x + offset
        ax.bar(
            xpos,
            m,
            width=width,
            color=color_cycle[s_idx % len(color_cycle)],
            alpha=0.85,
            label=solver,
            yerr=sd,
            error_kw={"elinewidth": 1.0, "capsize": 2.0},
        )

    ax.set_xticks(x)
    ax.set_xticklabels(bin_labels, rotation=35, ha="right")
    ax.set_ylabel(y_label)
    ax.set_xlabel("GT rain interval (mm/h)")
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
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
    obj_pairs: List[Tuple[float, float, float]] = []
    for item in obj_pairs_raw:
        if isinstance(item, dict):
            lam = item.get("w_smooth", item.get("lambda", item.get("lam", None)))
            mu = item.get("w_shrink", item.get("mu", None))
            eta = item.get("w_second_der", item.get("eta", 0.0))
            if lam is None or mu is None:
                continue
            obj_pairs.append((float(lam), float(mu), float(eta)))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            obj_pairs.append((float(item[0]), float(item[1]), 0.0))
        elif isinstance(item, (list, tuple)) and len(item) == 3:
            obj_pairs.append((float(item[0]), float(item[1]), float(item[2])))
    if not obj_pairs:
        obj_pairs = []

    rae_cfg = deep_get(cfg, "rae_hist", {}) or {}
    rae_enabled = bool(rae_cfg.get("enabled", False))
    rae_bins = int(rae_cfg.get("bins", 50))
    rae_max_patches = rae_cfg.get("max_patches", None)
    rae_out_subdir = str(rae_cfg.get("out_dir", "images/RAE_histograms"))

    rainy_bin_cfg = deep_get(cfg, "rainy_error_bins", {}) or {}
    rainy_bins_enabled = bool(rainy_bin_cfg.get("enabled", True))
    rainy_bins_max_upper = float(rainy_bin_cfg.get("max_upper", 128.0))
    rainy_bins_zero_frac = float(rainy_bin_cfg.get("prune_zero_frac", 0.5))
    rainy_edges = build_rain_gt_bin_edges(max_upper=rainy_bins_max_upper)
    rainy_intervals: List[Tuple[float, float, str]] = []
    for i in range(len(rainy_edges) - 1):
        lo = float(rainy_edges[i])
        hi = float(rainy_edges[i + 1])
        rainy_intervals.append((lo, hi, format_interval_label(lo, hi)))

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
    sheet_order: List[str] = []

    # For plots: per k -> per method -> per bin -> list of per-patch medians / p90s
    medians_rainy: Dict[int, Dict[str, Dict[str, List[float]]]] = {k: {} for k in k_values}
    medians_nonrainy: Dict[int, Dict[str, Dict[str, List[float]]]] = {k: {} for k in k_values}
    p90s_rainy: Dict[int, Dict[str, Dict[str, List[float]]]] = {k: {} for k in k_values}
    p90s_nonrainy: Dict[int, Dict[str, Dict[str, List[float]]]] = {k: {} for k in k_values}
    bin_counts: Dict[int, Dict[str, Dict[str, List[int]]]] = {
        k: {"rainy": {lab: [] for lab in dist_labels}, "nonrainy": {lab: [] for lab in dist_labels}}
        for k in k_values
    }
    bin_counts_seen: set = set()
    dry_metrics: Dict[str, Dict[str, List[float]]] = {}

    objective_rows: List[Dict[str, Any]] = []
    objective_gt_done: set = set()
    objective_vals: Dict[Tuple[float, float, float], Dict[str, Dict[str, float]]] = {}
    link_metrics: Dict[str, Dict[str, Dict[str, float]]] = {}
    stop_rows: List[Dict[str, Any]] = []
    gtbin_counts_global: Dict[str, Dict[str, int]] = {lab: {} for _, _, lab in rainy_intervals}
    gtbin_rel_patch_means: Dict[str, Dict[str, List[float]]] = {}
    gtbin_abs_patch_means: Dict[str, Dict[str, List[float]]] = {}

    obj_enabled = len(obj_pairs) > 0
    if obj_enabled:
        from solve_rain_lbfgsb import load_est_input_json as load_est_for_obj  # type: ignore
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
        link_metrics[label] = {}
        dry_metrics[label] = {"fp_rates": [], "fn_rates": []}
        gtbin_rel_patch_means[label] = {lab: [] for _, _, lab in rainy_intervals}
        gtbin_abs_patch_means[label] = {lab: [] for _, _, lab in rainy_intervals}

        for k in k_values:
            medians_rainy[k][label] = {lab: [] for lab in dist_labels}
            medians_nonrainy[k][label] = {lab: [] for lab in dist_labels}
            p90s_rainy[k][label] = {lab: [] for lab in dist_labels}
            p90s_nonrainy[k][label] = {lab: [] for lab in dist_labels}

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
            # dry classification metrics (dry = pred < thr)
            gt_wet = gt >= thr
            pred_wet = pred >= thr
            fp = np.logical_and(pred_wet, ~gt_wet)  # predicted wet but GT dry
            fn = np.logical_and(~pred_wet, gt_wet)  # predicted dry but GT wet
            total_pixels = gt.size
            if total_pixels > 0:
                dry_metrics[label]["fp_rates"].append(float(np.sum(fp)) / float(total_pixels))
                dry_metrics[label]["fn_rates"].append(float(np.sum(fn)) / float(total_pixels))

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
            abs_rae_full = np.empty_like(gt, dtype=np.float64)
            abs_mmph_full = np.abs(gt - pred)
            # rainy
            denom = np.where(gt == 0.0, 1.0, gt)
            signed_full[rainy] = (gt[rainy] - pred[rainy]) / denom[rainy]
            abs_full[rainy] = np.abs(signed_full[rainy])
            abs_rae_full[rainy] = abs_full[rainy]
            # nonrainy
            signed_full[~rainy] = pred[~rainy] - gt[~rainy]
            abs_full[~rainy] = np.abs(signed_full[~rainy])
            abs_rae_full[~rainy] = abs_mmph_full[~rainy] / denom[~rainy]

            # --- GT-binned all-pixels error (powers of 2 buckets) ---
            if rainy_bins_enabled:
                for lo, hi, bin_lab in rainy_intervals:
                    gmask_bin = (gt >= lo) & (gt < hi)
                    n_bin = int(np.sum(gmask_bin))
                    if key not in gtbin_counts_global[bin_lab]:
                        gtbin_counts_global[bin_lab][key] = n_bin
                    if n_bin == 0:
                        continue
                    abs_vals = abs_mmph_full[gmask_bin]
                    # Per request, the [0,1) bucket uses absolute error also in the "relative" plot.
                    if lo < 1.0:
                        rel_vals = abs_vals
                    else:
                        den_bin = np.where(gt[gmask_bin] == 0.0, 1.0, gt[gmask_bin])
                        rel_vals = abs_vals / den_bin
                    gtbin_rel_patch_means[label][bin_lab].append(float(np.mean(rel_vals)))
                    gtbin_abs_patch_means[label][bin_lab].append(float(np.mean(abs_vals)))

            # --- Objective values (GT + solver) ---
            if obj_enabled:
                est_key = str(est_path)
                prob = prob_cache.get(est_key)
                if prob is None:
                    prob = load_est_for_obj(est_path, warn=False)
                    prob_cache[est_key] = prob
                for lam, mu, eta in obj_pairs:
                    gt_tag = (key, lam, mu, eta)
                    if gt_tag not in objective_gt_done:
                        j_gt = evaluate_objective_values(
                            prob, gt,
                            lam=lam, mu=mu, eps=obj_eps, eta=eta,
                        )
                        objective_vals.setdefault((float(lam), float(mu), float(eta)), {}).setdefault(key, {})["GT"] = j_gt
                        objective_gt_done.add(gt_tag)

                    j_sol = evaluate_objective_values(
                        prob, pred,
                        lam=lam, mu=mu, eps=obj_eps, eta=eta,
                    )
                    objective_vals.setdefault((float(lam), float(mu), float(eta)), {}).setdefault(key, {})[label] = j_sol

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
                            l1_rae_sum=0.0,
                            l1_abs_mmph_sum=0.0,
                            l1_abs_mmph_sum_norm_hw=0.0,
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
                    l1_rae = float(np.sum(abs_rae_full[gmask]))
                    l1_abs_mmph = float(np.sum(abs_mmph_full[gmask]))
                    s = stats_row(e_signed, e_abs, l1_rae_sum=l1_rae, l1_abs_mmph_sum=l1_abs_mmph)
                    cov_rows.append(dict(
                        patch_key=key,
                        mask_type=mask_name,
                        coverage_bin=bin_lab,
                        l1_abs_mmph_sum_norm_hw=(l1_abs_mmph / float(gt.size)),
                        **s,
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
                        l1_rae = float(np.sum(abs_rae_full[gmask]))
                        l1_abs_mmph = float(np.sum(abs_mmph_full[gmask]))
                        s = stats_row(e_signed, e_abs, l1_rae_sum=l1_rae, l1_abs_mmph_sum=l1_abs_mmph)
                        dist_rows_by_k[k].append(dict(
                            patch_key=key,
                            mask_type=mask_name,
                            distance_bin_m=bin_lab,
                            l1_abs_mmph_sum_norm_hw=(l1_abs_mmph / float(gt.size)),
                            **s,
                        ))

                        # For final IQR plot: per-patch median_abs per bin (rainy uses abs_rel, nonrainy uses abs_diff)
                        if mask_name == "rainy" and e_abs.size > 0:
                            medians_rainy[k][label][bin_lab].append(float(np.median(e_abs)))
                            p90s_rainy[k][label][bin_lab].append(float(np.percentile(e_abs, 90)))
                        if mask_name == "nonrainy" and e_abs.size > 0:
                            medians_nonrainy[k][label][bin_lab].append(float(np.median(e_abs)))
                            p90s_nonrainy[k][label][bin_lab].append(float(np.percentile(e_abs, 90)))

                        # RAE histogram data (rainy only, optional)
                        if rae_hist_data is not None and key in hist_keys and mask_name == "rainy" and e_abs.size > 0:
                            rae_hist_data[k][bin_lab].extend(e_abs.tolist())

            # --- LinkStats per patch ---
            try:
                A_obs, A_hat, L_km, valid, ge10 = compute_link_terms(est, pred)
                attn_all, J1_all, n_valid = attn_l1_and_J1(A_obs, A_hat, L_km, valid)
                attn_10, J1_10, n_10 = attn_l1_and_J1(A_obs, A_hat, L_km, ge10)
                denom_L = float(np.sum(np.abs(L_km[valid])))
                if denom_L > 0:
                    E_all = float(np.sum(A_obs[valid] - A_hat[valid]) / denom_L)
                else:
                    E_all = 0.0
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
                E_all=E_all,
                E2_all=(float(np.sum((A_obs[valid] - A_hat[valid]) ** 2) / denom_L) if denom_L > 0 else 0.0),
            ))
            link_metrics[label][key] = dict(
                L1=attn_all,
                J1=J1_all,
                E=E_all,
                E2=(float(np.sum((A_obs[valid] - A_hat[valid]) ** 2) / denom_L) if denom_L > 0 else 0.0),
            )

        # store sheets (order: LinkStats, DistanceStats, CoverageStats)
        link_rows = append_average_rows(link_rows, group_keys=[])
        cov_rows = append_average_rows(cov_rows, group_keys=["mask_type", "coverage_bin"])
        for k in k_values:
            dist_rows_by_k[k] = append_average_rows(
                dist_rows_by_k[k],
                group_keys=["mask_type", "distance_bin_m"],
            )

        sheet_name = f"LinkStats_GTvs{label}"
        sheets[sheet_name] = link_rows
        sheet_order.append(sheet_name)
        k_values_for_sheets = sorted(k_values, key=lambda kv: (0 if kv == 3 else (1 if kv == 2 else 2), kv))
        for k in k_values_for_sheets:
            if k == 3:
                sheet_name = f"DistanceStats_GTvs{label}"
            else:
                sheet_name = f"DistanceStatsK{k}_GTvs{label}"
            sheets[sheet_name] = dist_rows_by_k[k]
            sheet_order.append(sheet_name)
        sheet_name = f"CoverageStats_GTvs{label}"
        sheets[sheet_name] = cov_rows
        sheet_order.append(sheet_name)

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
    if obj_enabled and objective_vals:
        solver_labels = [label for _, label, _, _, _ in solvers]
        # ensure GT first
        cols = ["GT"] + [lab for lab in solver_labels if lab != "GT"]
        metric_suffixes = ["J", "J1", "J2", "J3", "J4", "wJ1", "wJ2", "wJ3", "wJ4"]
        wide_rows: List[Dict[str, Any]] = []
        for (lam, mu, eta), by_patch in objective_vals.items():
            for key in sorted(by_patch.keys()):
                row: Dict[str, Any] = dict(
                    patch_key=key,
                    lambda_val=float(lam),
                    mu_val=float(mu),
                    eta_val=float(eta),
                    eps=float(obj_eps),
                )
                vals = by_patch[key]
                for col in cols:
                    v = vals.get(col, {})
                    for suf in metric_suffixes:
                        row[f"{col}_{suf}"] = float(v.get(suf, 0.0))
                wide_rows.append(row)

            # averages
            avg_row: Dict[str, Any] = dict(
                patch_key="AVERAGE",
                lambda_val=float(lam),
                mu_val=float(mu),
                eta_val=float(eta),
                eps=float(obj_eps),
            )
            for col in cols:
                for suf in metric_suffixes:
                    col_vals = [by_patch[k].get(col, {}).get(suf, None) for k in by_patch.keys()]
                    col_vals = [v for v in col_vals if v is not None]
                    avg_row[f"{col}_{suf}"] = float(np.mean(col_vals)) if col_vals else 0.0
            wide_rows.append(avg_row)

        sheets["Objective_J"] = wide_rows
        sheet_order.append("Objective_J")

    # dry classification summary
    if dry_metrics:
        dry_rows: List[Dict[str, Any]] = []
        for label, vals in dry_metrics.items():
            fp = np.array(vals.get("fp_rates", []), dtype=np.float64)
            fn = np.array(vals.get("fn_rates", []), dtype=np.float64)
            fp_mean = float(np.mean(fp)) if fp.size else 0.0
            fp_std = float(np.std(fp, ddof=0)) if fp.size else 0.0
            fn_mean = float(np.mean(fn)) if fn.size else 0.0
            fn_std = float(np.std(fn, ddof=0)) if fn.size else 0.0
            dry_rows.append(dict(
                solver=label,
                dry_threshold_mmph=float(thr),
                positive_definition="wet (gt >= threshold)",
                fp_definition="pred wet & GT dry",
                fn_definition="pred dry & GT wet",
                fp_rate_mean=fp_mean,
                fp_rate_std=fp_std,
                fp_rate_range=f"[{fp_mean - fp_std:.6f},{fp_mean + fp_std:.6f}]",
                fn_rate_mean=fn_mean,
                fn_rate_std=fn_std,
                fn_rate_range=f"[{fn_mean - fn_std:.6f},{fn_mean + fn_std:.6f}]",
            ))
        sheets["DryConfusionSummary"] = dry_rows
        sheet_order.append("DryConfusionSummary")

        plot_fp_fn_summary(
            img_dir / "dry_fp_fn_summary.png",
            title="Dry-classification FP/FN rates (mean ± std across patches)",
            rows=dry_rows,
            dpi=dpi,
        )

    # write excel (ordered)
    ordered_sheets: Dict[str, List[Dict[str, Any]]] = {}
    # enforce global ordering: all LinkStats, then DistanceStats, then CoverageStats
    for prefix in ("LinkStats_", "DistanceStats", "CoverageStats"):
        for name in sheet_order:
            if name.startswith(prefix) and name not in ordered_sheets:
                ordered_sheets[name] = sheets[name]
    # add remaining sheets in original order
    for name in sheet_order:
        if name not in ordered_sheets:
            ordered_sheets[name] = sheets[name]
    # add any leftover (shouldn't happen)
    for name in sheets:
        if name not in ordered_sheets:
            ordered_sheets[name] = sheets[name]

    write_workbook(excel_path, ordered_sheets)
    print(f"Wrote Excel: {excel_path}")

    # ratio plot vs IDW for link metrics
    if "IDW" in link_metrics:
        entries: List[Tuple[str, str, List[float]]] = []
        metrics = ["L1", "J1", "E", "E2"]
        for solver_label in [label for _, label, _, _, _ in solvers if label in link_metrics]:
            per_patch = link_metrics.get(solver_label, {})
            per_patch_idw = link_metrics.get("IDW", {})
            keys = sorted(set(per_patch.keys()) & set(per_patch_idw.keys()))
            if not keys:
                continue
            ratio_vals: Dict[str, List[float]] = {m: [] for m in metrics}
            for k in keys:
                v = per_patch[k]
                v_idw = per_patch_idw[k]
                # L1 ratio
                if v_idw["L1"] != 0:
                    ratio_vals["L1"].append(v["L1"] / v_idw["L1"])
                # J1 ratio
                if v_idw["J1"] != 0:
                    ratio_vals["J1"].append(v["J1"] / v_idw["J1"])
                # E ratio
                if v_idw["E"] != 0:
                    ratio_vals["E"].append(v["E"] / v_idw["E"])
                # E2 ratio
                if v_idw["E2"] != 0:
                    ratio_vals["E2"].append(v["E2"] / v_idw["E2"])

            entries.append((solver_label, f"L1({solver_label})/L1(IDW)", ratio_vals["L1"]))
            entries.append((solver_label, f"J1({solver_label})/J1(IDW)", ratio_vals["J1"]))
            entries.append((solver_label, f"E({solver_label})/E(IDW)", ratio_vals["E"]))
            entries.append((solver_label, f"E2({solver_label})/E2(IDW)", ratio_vals["E2"]))

        if entries:
            plot_ratio_iqr(
                img_dir / "link_ratio_summary.png",
                title="Link-metric ratios vs IDW (median and IQR across patches)",
                entries=entries,
                dpi=dpi,
            )

    # GT-binned all-pixels plots (powers-of-2 bins)
    if rainy_bins_enabled and gtbin_rel_patch_means and gtbin_abs_patch_means:
        ordered_labels = [lab for _, _, lab in rainy_intervals]
        labels_to_plot = list(ordered_labels)
        # Tail-only pruning by zero fraction across patches.
        while labels_to_plot:
            tail = labels_to_plot[-1]
            counts = list(gtbin_counts_global.get(tail, {}).values())
            if not counts:
                labels_to_plot.pop()
                continue
            zfrac = float(sum(1 for c in counts if c == 0)) / float(len(counts))
            if zfrac >= rainy_bins_zero_frac:
                labels_to_plot.pop()
            else:
                break

        solver_order = [label for _, label, _, _, _ in solvers if label in gtbin_rel_patch_means]
        if labels_to_plot and solver_order:
            rel_mean: Dict[str, List[float]] = {}
            rel_std: Dict[str, List[float]] = {}
            abs_mean: Dict[str, List[float]] = {}
            abs_std: Dict[str, List[float]] = {}
            for solver_label in solver_order:
                rel_mean[solver_label] = []
                rel_std[solver_label] = []
                abs_mean[solver_label] = []
                abs_std[solver_label] = []
                for bin_lab in labels_to_plot:
                    rv = np.array(gtbin_rel_patch_means.get(solver_label, {}).get(bin_lab, []), dtype=np.float64)
                    av = np.array(gtbin_abs_patch_means.get(solver_label, {}).get(bin_lab, []), dtype=np.float64)
                    rel_mean[solver_label].append(float(np.mean(rv)) if rv.size else 0.0)
                    rel_std[solver_label].append(float(np.std(rv, ddof=0)) if rv.size else 0.0)
                    abs_mean[solver_label].append(float(np.mean(av)) if av.size else 0.0)
                    abs_std[solver_label].append(float(np.std(av, ddof=0)) if av.size else 0.0)

            plot_gt_binned_patchavg_error(
                img_dir / "gt_binned_patchavg_relative_abs_error_all_pixels.png",
                title="GT-binned all-pixels error (avg of patch-averaged error ± std)",
                bin_labels=labels_to_plot,
                solver_order=solver_order,
                mean_by_solver=rel_mean,
                std_by_solver=rel_std,
                y_label="Avg patch error (|GT-PRED|/GT; [0,1) uses |GT-PRED|)",
                dpi=dpi,
            )
            plot_gt_binned_patchavg_error(
                img_dir / "gt_binned_patchavg_absolute_error_all_pixels.png",
                title="GT-binned all-pixels absolute error (avg of patch means ± std)",
                bin_labels=labels_to_plot,
                solver_order=solver_order,
                mean_by_solver=abs_mean,
                std_by_solver=abs_std,
                y_label="Avg patch absolute error |GT-PRED| (mm/h)",
                dpi=dpi,
            )

    # plots across solvers (IQR of per-patch medians)
    method_order = [label for _, label, _, _, _ in solvers if label in medians_rainy[k_values[0]]]
    if method_order:
        for k in k_values:
            summary_r = compute_iqr_profile(medians_rainy[k], dist_labels)
            summary_n = compute_iqr_profile(medians_nonrainy[k], dist_labels)
            summary_p90_r = compute_p90_profile(p90s_rainy[k], dist_labels)
            summary_p90_n = compute_p90_profile(p90s_nonrainy[k], dist_labels)
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
                rainy_p90_name = "distance_iqr_p90s_rainy_multi.png"
                nonrainy_p90_name = "distance_iqr_p90s_nonrainy_multi.png"
                rainy_p90_title = "Rainy pixels: per-patch p90 |(GT-PRED)/GT| by distance bin (median, p25-p90)"
                nonrainy_p90_title = "Non-rainy pixels: per-patch p90 |GT-PRED| by distance bin (median, p25-p90)"
            else:
                rainy_name = f"distance_iqr_medians_rainy_multi_k{k}.png"
                nonrainy_name = f"distance_iqr_medians_nonrainy_multi_k{k}.png"
                rainy_title = f"Rainy pixels: IQR of per-patch median |(GT-PRED)/GT| by distance bin (k={k})"
                nonrainy_title = f"Non-rainy pixels: IQR of per-patch median |GT-PRED| by distance bin (k={k})"
                rainy_p90_name = f"distance_iqr_p90s_rainy_multi_k{k}.png"
                nonrainy_p90_name = f"distance_iqr_p90s_nonrainy_multi_k{k}.png"
                rainy_p90_title = f"Rainy pixels: per-patch p90 |(GT-PRED)/GT| by distance bin (median, p25-p90; k={k})"
                nonrainy_p90_title = f"Non-rainy pixels: per-patch p90 |GT-PRED| by distance bin (median, p25-p90; k={k})"

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

            # median-of-p90s plots (p25/p90 across per-patch p90s)
            plot_iqr_bars(
                img_dir / rainy_p90_name,
                rainy_p90_title,
                summary_p90_r, labels_r, method_order,
                y_max=y_max, dpi=dpi, bin_spacing=bin_spacing,
                tick_labels=tick_labels_r,
                y_label="Per-patch p90 error (median, p25-p90)",
            )
            plot_iqr_bars(
                img_dir / nonrainy_p90_name,
                nonrainy_p90_title,
                summary_p90_n, labels_n, method_order,
                y_max=y_max, dpi=dpi, bin_spacing=bin_spacing,
                tick_labels=tick_labels_n,
                y_label="Per-patch p90 error (median, p25-p90)",
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
