#!/usr/bin/env python3
"""
batch_analyze_multi.py

Multi-method evaluator + distance-profile plotter.

This script compares Ground Truth (GT) against *multiple* solver output folders
(precomputed, e.g. SOL_0.1, SOL_IDW, IDW baseline), and produces:

1) An Excel workbook with:
   - DistanceStats_long: per (patch, method, mask_type, distance_bin) -> per-patch median error
   - DistanceIQR_summary: per (method, mask_type, distance_bin) -> p25/median/p75 across patches

2) PNG plots (rainy + nonrainy) showing, for each distance bin, **vertical IQR bars**
   (p25..p75 across patches of per-patch medians), with the median marked.
   Methods are drawn side-by-side per bin (small x-offset), **without** connecting lines.

Notes:
- This analyzer does *not* run IDW internally. If you want GT vs IDW, generate IDW outputs
  as a solver and include it in input.solvers.
- Distance bins are based on **d3 = distance to the 3rd-closest link** (point-to-segment),
  using link geometry from est_input_*.json.

Relative paths in the YAML are resolved relative to the config file location.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# matplotlib is used for plots
import matplotlib.pyplot as plt

# openpyxl for Excel output
from openpyxl import Workbook
from openpyxl.utils import get_column_letter


# ---------------------------
# Config utilities
# ---------------------------
def _load_config(path: Path) -> dict:
    suf = path.suffix.lower()
    if suf in (".yaml", ".yml"):
        import yaml  # type: ignore
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return {} if cfg is None else cfg
    if suf == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError("Config must be .yaml/.yml or .json")


def deep_get(d: dict, path: str, default=None):
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def resolve_path(p: Optional[str], base: Path) -> Optional[Path]:
    if p is None:
        return None
    pp = Path(p)
    return pp if pp.is_absolute() else (base / pp).resolve()


# ---------------------------
# Filename matching
# ---------------------------
def base_id_from_filename(name: str) -> str:
    """
    Turn:
      gt_RAD_..._202301301000_patch000.npz -> RAD_..._202301301000_patch000
      est_input_RAD_..._202301301000_patch000_solution.npz -> RAD_..._202301301000_patch000
      est_input_RAD_..._202301301000_patch000.json -> RAD_..._202301301000_patch000
    """
    stem = Path(name).stem
    if stem.startswith("gt_"):
        stem = stem[len("gt_") :]
    if stem.startswith("est_input_"):
        stem = stem[len("est_input_") :]
    if stem.endswith("_solution"):
        stem = stem[: -len("_solution")]
    return stem


def patch_key_from_base_id(base_id: str) -> str:
    """
    Convert base_id like:
      RAD_..._202301301000_patch000
    into:
      patch000__202301301000

    If parsing fails, falls back to base_id.
    """
    m = re.search(r"_(\d{10,14})_patch(\d+)$", base_id)
    if not m:
        return base_id
    ts = m.group(1)
    pid = f"patch{int(m.group(2)):03d}"
    return f"{pid}__{ts}"


# ---------------------------
# NPZ field loading
# ---------------------------
def load_npz_field(npz_path: Path, key_preference: Sequence[str]) -> np.ndarray:
    with np.load(npz_path, allow_pickle=True) as z:
        keys = list(z.keys())
        for k in key_preference:
            if k in z:
                arr = z[k]
                return np.asarray(arr, dtype=np.float64)
        # fallback: common keys
        for k in ("R_hat", "R", "rain", "gt", "R_gt"):
            if k in z:
                return np.asarray(z[k], dtype=np.float64)
        raise KeyError(f"{npz_path.name}: none of preferred keys {list(key_preference)} found. Keys={keys}")


# ---------------------------
# Distance to 3rd-closest link
# ---------------------------
def point_to_segment_distance(px: np.ndarray, py: np.ndarray, x0: np.ndarray, y0: np.ndarray, x1: np.ndarray, y1: np.ndarray) -> np.ndarray:
    """
    Vectorized distance from points (px,py) to segments (x0,y0)-(x1,y1).
    px,py shape (N,), segment arrays shape (M,) broadcast to (N,M) by caller if needed.
    Here we assume caller passes arrays with compatible broadcasting.
    """
    vx = x1 - x0
    vy = y1 - y0
    wx = px - x0
    wy = py - y0
    vv = vx * vx + vy * vy
    # avoid /0 for degenerate segments
    vv = np.where(vv <= 1e-12, 1e-12, vv)
    t = (wx * vx + wy * vy) / vv
    t = np.clip(t, 0.0, 1.0)
    projx = x0 + t * vx
    projy = y0 + t * vy
    dx = px - projx
    dy = py - projy
    return np.sqrt(dx * dx + dy * dy)


def d3_map_from_est_input(est_json: Path, *, max_candidates: int = 64) -> Tuple[np.ndarray, float]:
    """
    Returns:
      d3_map (H,W): distance to 3rd closest link segment (meters)
      pixel_size_m
    Strategy:
      - build a KDTree over endpoints+midpoints of segments (3*n_links points)
      - for each pixel center, query K nearest points => candidate link ids
      - compute exact point-to-segment distances to candidate links only
      - take 3rd smallest as d3 (or +inf if <3 links)
    """
    est = json.loads(est_json.read_text())
    header = est["header"]
    links = est["links"]

    H = int(header["H"])
    W = int(header["W"])
    pix = float(header["pixel_size_m"])

    # segment endpoints in local coords
    x0 = np.array([float(L["x0_m"]) for L in links], dtype=np.float64)
    y0 = np.array([float(L["y0_m"]) for L in links], dtype=np.float64)
    x1 = np.array([float(L["x1_m"]) for L in links], dtype=np.float64)
    y1 = np.array([float(L["y1_m"]) for L in links], dtype=np.float64)
    mx = 0.5 * (x0 + x1)
    my = 0.5 * (y0 + y1)

    n_links = len(links)
    if n_links == 0:
        return np.full((H, W), np.inf, dtype=np.float64), pix

    # build KDTree on endpoints + midpoints
    try:
        from scipy.spatial import cKDTree  # type: ignore
    except Exception as e:
        raise RuntimeError("scipy is required for d3 computation (scipy.spatial.cKDTree).") from e

    pts = np.vstack([
        np.stack([x0, y0], axis=1),
        np.stack([x1, y1], axis=1),
        np.stack([mx, my], axis=1),
    ])
    link_ids = np.concatenate([np.arange(n_links), np.arange(n_links), np.arange(n_links)])
    tree = cKDTree(pts)

    # pixel centers
    xs = (np.arange(W, dtype=np.float64) + 0.5) * pix
    ys = (np.arange(H, dtype=np.float64) + 0.5) * pix
    X, Y = np.meshgrid(xs, ys)
    q = np.stack([X.ravel(), Y.ravel()], axis=1)

    K = int(max_candidates)
    K = max(3, min(K, pts.shape[0]))
    _, idx = tree.query(q, k=K, workers=-1)

    if idx.ndim == 1:
        idx = idx[:, None]

    # For each query, compute distance to candidate unique links
    d3 = np.full((q.shape[0],), np.inf, dtype=np.float64)
    for i in range(q.shape[0]):
        cand_links = np.unique(link_ids[idx[i]])
        if cand_links.size < 3:
            continue
        px, py = q[i]
        dd = point_to_segment_distance(
            np.full(cand_links.shape, px),
            np.full(cand_links.shape, py),
            x0[cand_links],
            y0[cand_links],
            x1[cand_links],
            y1[cand_links],
        )
        dd.sort()
        d3[i] = dd[2]  # 3rd smallest

    return d3.reshape(H, W), pix


# ---------------------------
# Binning + stats
# ---------------------------
def make_distance_bins(bin_edges_m: Sequence[float]) -> Tuple[List[str], List[Tuple[float, float]]]:
    """
    Edges: [125, 375, 750, 1500, 3125]
    Produces bins:
      <=125
      (125,375]
      (375,750]
      (750,1500]
      (1500,3125]
      >3125
    Returns (labels, intervals) where intervals are (lo, hi) with lo exclusive except first, hi inclusive, and last is (lo, +inf).
    """
    edges = [float(x) for x in bin_edges_m]
    labels: List[str] = []
    intervals: List[Tuple[float, float]] = []

    labels.append(f"≤{int(edges[0])}")
    intervals.append((-np.inf, edges[0]))

    for a, b in zip(edges[:-1], edges[1:]):
        labels.append(f"({int(a)},{int(b)}]")
        intervals.append((a, b))

    labels.append(f">{int(edges[-1])}")
    intervals.append((edges[-1], np.inf))

    return labels, intervals


def bin_mask(d: np.ndarray, interval: Tuple[float, float], first: bool, last: bool) -> np.ndarray:
    lo, hi = interval
    if first:
        return d <= hi
    if last:
        return d > lo
    return (d > lo) & (d <= hi)


def percentile_safe(x: np.ndarray, q: float) -> float:
    if x.size == 0:
        return float("nan")
    return float(np.nanpercentile(x, q))


# ---------------------------
# Excel helpers
# ---------------------------
def autosize(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                val = "" if cell.value is None else str(cell.value)
            except Exception:
                val = ""
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = min(60, max(10, max_len + 2))


# ---------------------------
# Plotting
# ---------------------------
def plot_iqr_bars(
    out_png: Path,
    title: str,
    x_labels: List[str],
    series: List[Tuple[str, List[float], List[float], List[float]]],
    *,
    automatic_vertical_scaling: bool,
    vertical_scale: Optional[float],
):
    """
    series: list of (label, medians, p25s, p75s) aligned to x_labels
    """
    n_bins = len(x_labels)
    n_methods = len(series)
    x = np.arange(n_bins, dtype=np.float64)

    fig, ax = plt.subplots(figsize=(10.5, 4.6), dpi=150)
    ax.set_title(title)
    ax.set_xlabel("Distance bin to 3rd closest link (m)")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.grid(True, axis="y", linestyle=":", alpha=0.5)

    # offsets so methods appear side-by-side per bin
    delta = 0.18 if n_methods <= 3 else 0.14
    offsets = [(i - (n_methods - 1) / 2.0) * delta for i in range(n_methods)]

    for mi, (lab, meds, p25s, p75s) in enumerate(series):
        xo = x + offsets[mi]
        meds = np.asarray(meds, dtype=np.float64)
        p25s = np.asarray(p25s, dtype=np.float64)
        p75s = np.asarray(p75s, dtype=np.float64)

        # marker only (no connecting line)
        ax.scatter(xo, meds, label=lab, s=45)

        # vertical IQR bars
        for j in range(n_bins):
            if not np.isfinite(meds[j]) or not np.isfinite(p25s[j]) or not np.isfinite(p75s[j]):
                continue
            ax.vlines(xo[j], p25s[j], p75s[j], linewidth=2)
            # little horizontal dotted caps
            cap = 0.08
            ax.hlines(p25s[j], xo[j] - cap, xo[j] + cap, linestyles=":", linewidth=2)
            ax.hlines(p75s[j], xo[j] - cap, xo[j] + cap, linestyles=":", linewidth=2)

    ax.legend(loc="best")

    if automatic_vertical_scaling:
        ax.set_ylim(bottom=0.0)
    else:
        if vertical_scale is None or (not isinstance(vertical_scale, (int, float))) or vertical_scale < 0:
            raise ValueError("plots.vertical_scale must be a real non-negative number when automatic_vertical_scaling=false")
        ax.set_ylim(0.0, float(vertical_scale))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


# ---------------------------
# Main
# ---------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg_path = Path(args.config).resolve()
    base = cfg_path.parent
    cfg = _load_config(cfg_path)

    gt_dir = resolve_path(deep_get(cfg, "input.gt_dir", None), base)
    est_input_dir = resolve_path(deep_get(cfg, "input.est_input_dir", None), base)
    solvers = deep_get(cfg, "input.solvers", None)

    # Accept solvers as either a list (YAML '-') or a dict/mapping (no dashes).
    # Dict style lets you write: solvers: { my_solver: { ... }, ... }
    if isinstance(solvers, dict):
        solvers = list(solvers.values())

    if gt_dir is None or est_input_dir is None:
        raise SystemExit("Config must include input.gt_dir and input.est_input_dir")
    if not isinstance(solvers, list) or not solvers:
        raise SystemExit("Config must include input.solvers: [ ... ] (non-empty list)")

    gt_pref = deep_get(cfg, "data.gt_key_preference", ["R_gt", "rain", "gt"])
    allow_shape_mismatch = bool(deep_get(cfg, "data.allow_shape_mismatch", False))

    thr = float(deep_get(cfg, "rain.threshold_mmph", 0.6))

    edges = deep_get(cfg, "distance.bin_edges_m", [125, 375, 750, 1500, 3125])
    dist_labels, dist_intervals = make_distance_bins(edges)
    max_candidates = int(deep_get(cfg, "distance.max_candidates", 64))

    out_dir = resolve_path(deep_get(cfg, "output.out_dir", "batch_analyze_output_multi"), base) or (base / "batch_analyze_output_multi")
    images_subdir = str(deep_get(cfg, "output.images_subdir", "images"))
    excel_filename = str(deep_get(cfg, "output.excel_filename", "distance_stats_multi.xlsx"))

    plot_cfg = deep_get(cfg, "plots", {}) or {}
    auto_scale = bool(plot_cfg.get("automatic_vertical_scaling", True))
    vscale = plot_cfg.get("vertical_scale", None)

    img_dir = (out_dir / images_subdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    # Collect GT files
    gt_files = sorted(gt_dir.glob("*.npz"))
    gt_map: Dict[str, Path] = {}
    for p in gt_files:
        bid = base_id_from_filename(p.name)
        gt_map[bid] = p

    # Collect est_input files
    est_files = sorted(est_input_dir.glob("est_input_*.json"))
    est_map: Dict[str, Path] = {}
    for p in est_files:
        bid = base_id_from_filename(p.name)
        est_map[bid] = p

    # Collect solver solution maps
    solver_specs: List[Tuple[str, str, Dict[str, Any], Dict[str, Path]]] = []
    for s in solvers:
        if not isinstance(s, dict):
            raise SystemExit("Each input.solvers[] entry must be a dict.")
        name = str(s.get("name", "solver"))
        label = str(s.get("label", name))
        sol_dir = resolve_path(str(s.get("sol_dir")), base)
        if sol_dir is None:
            raise SystemExit(f"Solver '{label}' missing sol_dir")
        sol_pref = s.get("sol_key_preference", ["R_hat"])
        sol_files = sorted(sol_dir.glob("*_solution.npz"))
        sol_map: Dict[str, Path] = {}
        for p in sol_files:
            bid = base_id_from_filename(p.name)
            sol_map[bid] = p
        solver_specs.append((name, label, {"sol_key_preference": sol_pref}, sol_map))

    # Match base_ids
    base_ids = sorted(set(gt_map.keys()) & set(est_map.keys()))
    for _, _, _, sm in solver_specs:
        base_ids = sorted(set(base_ids) & set(sm.keys()))

    if not base_ids:
        raise SystemExit("No matched (gt, est_input, solutions) triples found across all methods.")

    print(f"Matched patches across all methods: {len(base_ids)}")

    # Long records: one per (patch, method, mask_type, bin)
    long_rows: List[Dict[str, Any]] = []

    # For summary: collect per-bin medians per method + mask
    per_method_mask_bin: Dict[Tuple[str, str, str], List[float]] = {}

    for bid in base_ids:
        patch_key = patch_key_from_base_id(bid)
        gt_path = gt_map[bid]
        est_path = est_map[bid]

        # compute d3 map once per patch
        d3_map, pix = d3_map_from_est_input(est_path, max_candidates=max_candidates)

        GT = load_npz_field(gt_path, gt_pref)
        if GT.ndim != 2:
            raise ValueError(f"{gt_path.name}: expected 2D rainfall field, got shape {GT.shape}")

        rainy_mask = GT >= thr
        nonrainy_mask = ~rainy_mask

        # precompute bin masks
        bin_masks = []
        for bi, interval in enumerate(dist_intervals):
            bm = bin_mask(d3_map, interval, first=(bi == 0), last=(bi == len(dist_intervals) - 1))
            bin_masks.append(bm)

        for (_, label, meta, sol_map) in solver_specs:
            sol_path = sol_map[bid]
            sol_pref = meta["sol_key_preference"]
            SOL = load_npz_field(sol_path, sol_pref)

            if SOL.shape != GT.shape:
                if not allow_shape_mismatch:
                    raise ValueError(f"Shape mismatch {patch_key} {label}: GT {GT.shape} vs SOL {SOL.shape}")
                # best-effort crop to min shape
                H = min(GT.shape[0], SOL.shape[0])
                W = min(GT.shape[1], SOL.shape[1])
                GT2 = GT[:H, :W]
                SOL2 = SOL[:H, :W]
                rainy = rainy_mask[:H, :W]
                nonrainy = nonrainy_mask[:H, :W]
                d3 = d3_map[:H, :W]
                masks = [bm[:H, :W] for bm in bin_masks]
            else:
                GT2, SOL2, rainy, nonrainy, d3, masks = GT, SOL, rainy_mask, nonrainy_mask, d3_map, bin_masks

            # errors
            # rainy metric: relative abs error |(GT-SOL)/GT|
            gt_safe = np.where(GT2 == 0.0, np.nan, GT2)
            rel_abs = np.abs((GT2 - SOL2) / gt_safe)

            # nonrainy metric: abs diff |GT-SOL|
            abs_diff = np.abs(GT2 - SOL2)

            for bi, lab in enumerate(dist_labels):
                m_bin = masks[bi]

                # rainy
                mr = m_bin & rainy & np.isfinite(rel_abs)
                vals_r = rel_abs[mr]
                med_r = float(np.nanmedian(vals_r)) if vals_r.size else float("nan")

                long_rows.append({
                    "patch_key": patch_key,
                    "method_label": label,
                    "mask_type": "rainy",
                    "distance_bin_m": lab,
                    "n_pixels": int(vals_r.size),
                    "median_error": med_r,
                    "gt_file": gt_path.name,
                    "sol_file": sol_path.name,
                    "est_input_file": est_path.name,
                    "d_metric": "d3(point-to-segment)",
                })
                per_method_mask_bin.setdefault((label, "rainy", lab), []).append(med_r)

                # nonrainy
                mn = m_bin & nonrainy & np.isfinite(abs_diff)
                vals_n = abs_diff[mn]
                med_n = float(np.nanmedian(vals_n)) if vals_n.size else float("nan")

                long_rows.append({
                    "patch_key": patch_key,
                    "method_label": label,
                    "mask_type": "nonrainy",
                    "distance_bin_m": lab,
                    "n_pixels": int(vals_n.size),
                    "median_error": med_n,
                    "gt_file": gt_path.name,
                    "sol_file": sol_path.name,
                    "est_input_file": est_path.name,
                    "d_metric": "d3(point-to-segment)",
                })
                per_method_mask_bin.setdefault((label, "nonrainy", lab), []).append(med_n)

    # Build summary
    summary_rows: List[Dict[str, Any]] = []
    for (label, mask, binlab), arr in per_method_mask_bin.items():
        a = np.asarray(arr, dtype=np.float64)
        a = a[np.isfinite(a)]
        summary_rows.append({
            "method_label": label,
            "mask_type": mask,
            "distance_bin_m": binlab,
            "n_patches": int(a.size),
            "p25": percentile_safe(a, 25),
            "median": percentile_safe(a, 50),
            "p75": percentile_safe(a, 75),
        })

    # Excel output
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "DistanceStats_long"

    cols1 = ["patch_key", "method_label", "mask_type", "distance_bin_m", "n_pixels", "median_error",
             "gt_file", "sol_file", "est_input_file", "d_metric"]
    ws1.append(cols1)
    for r in long_rows:
        ws1.append([r.get(c) for c in cols1])
    autosize(ws1)

    ws2 = wb.create_sheet("DistanceIQR_summary")
    cols2 = ["method_label", "mask_type", "distance_bin_m", "n_patches", "p25", "median", "p75"]
    ws2.append(cols2)
    # sort summary in a nice order
    order_bin = {lab: i for i, lab in enumerate(dist_labels)}
    summary_rows_sorted = sorted(summary_rows, key=lambda x: (x["mask_type"], x["method_label"], order_bin.get(x["distance_bin_m"], 999)))
    for r in summary_rows_sorted:
        ws2.append([r.get(c) for c in cols2])
    autosize(ws2)

    out_xlsx = out_dir / excel_filename
    wb.save(out_xlsx)
    print(f"Wrote: {out_xlsx}")

    # Plots
    def build_series(mask: str) -> List[Tuple[str, List[float], List[float], List[float]]]:
        series = []
        # preserve solver order as given in config
        for (_, label, _, _) in solver_specs:
            meds, p25s, p75s = [], [], []
            for binlab in dist_labels:
                # find summary row
                rows = [r for r in summary_rows_sorted if r["mask_type"] == mask and r["method_label"] == label and r["distance_bin_m"] == binlab]
                if rows:
                    meds.append(rows[0]["median"])
                    p25s.append(rows[0]["p25"])
                    p75s.append(rows[0]["p75"])
                else:
                    meds.append(float("nan"))
                    p25s.append(float("nan"))
                    p75s.append(float("nan"))
            series.append((label, meds, p25s, p75s))
        return series

    # rainy plot: relative abs error
    plot_iqr_bars(
        img_dir / "distance_iqr_medians_rainy_multi.png",
        "Rainy pixels: IQR across patches of per-patch median error |(GT - X)/GT|",
        dist_labels,
        build_series("rainy"),
        automatic_vertical_scaling=auto_scale,
        vertical_scale=vscale,
    )

    # nonrainy plot: abs diff
    plot_iqr_bars(
        img_dir / "distance_iqr_medians_nonrainy_multi.png",
        "Non-rainy pixels: IQR across patches of per-patch median |GT - X|",
        dist_labels,
        build_series("nonrainy"),
        automatic_vertical_scaling=auto_scale,
        vertical_scale=vscale,
    )

    print(f"Wrote plots to: {img_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())