#!/usr/bin/env python3
"""
Per-link ILDW/IDW diagnostics report for attenuation error analysis.

Outputs:
- Excel workbook (ranked links + crowding bins + prefix diagnostics + synthetic controls)
- Plots:
  * Pareto curve (top-k% links vs cumulative % of J)
  * Crowding-vs-error (overlap fraction and n_neighbors threshold bins)
  * ILDW vs IDW per-link comparison (scatter + ratio histogram)
  * Map with top-K labels by e_l (default K=20)
  * Optional synthetic-controls bar chart with 95% CI

This script uses the same attenuation mapping as the existing project:
  A_hat[l] = sum_{segments in link l} ds_km * k_l * R(pixel)^alpha_l
and
  e_l = (A_obs[l] - A_hat[l])^2 / |l|_km
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook

from idw_baseline import itu838_k_alpha


@dataclass
class LinkGeom:
    idx: int
    x0: float
    y0: float
    x1: float
    y1: float


E_NOTE = r"Per-link error: $e_\ell = (A_\ell-\hat{A}_\ell)^2/|\ell|$"


def _key_from_est_path(p: Path) -> str:
    name = p.stem
    if name.startswith("est_input_"):
        return name[len("est_input_") :]
    return name


def _find_est_inputs(est_dir: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for p in sorted(est_dir.glob("est_input_*.json")):
        out[_key_from_est_path(p)] = p
    return out


def _find_solution_npz(sol_dir: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for p in sorted(sol_dir.glob("est_input_*_solution.npz")):
        key = p.stem
        key = key[len("est_input_") :] if key.startswith("est_input_") else key
        key = key[: -len("_solution")] if key.endswith("_solution") else key
        out[key] = p
    return out


def _load_r_hat(npz_path: Path) -> np.ndarray:
    z = np.load(npz_path, allow_pickle=True)
    if "R_hat" not in z.files:
        raise ValueError(f"Missing R_hat in {npz_path}")
    r = np.asarray(z["R_hat"], dtype=np.float64)
    if r.ndim != 2:
        raise ValueError(f"R_hat must be 2D in {npz_path}, got shape {r.shape}")
    return r


def _load_segments_by_link(raw: object, n_links: int) -> List[List[Dict[str, float]]]:
    out: List[List[Dict[str, float]]] = [[] for _ in range(n_links)]
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = ((str(i), v) for i, v in enumerate(raw))
    else:
        raise ValueError(f"Unsupported segments_by_link type: {type(raw)}")

    for k, segs in items:
        try:
            idx = int(k)
        except Exception:
            continue
        if idx < 0 or idx >= n_links:
            continue
        if not isinstance(segs, list):
            continue
        out[idx] = segs
    return out


def _load_est(est_json: Path):
    est = json.loads(est_json.read_text())
    links = est["links"]
    n_links = len(links)
    segs_by_link = _load_segments_by_link(est.get("segments_by_link", {}), n_links)
    header = est["header"]

    x0 = np.array([float(l["x0_m"]) for l in links], dtype=np.float64)
    y0 = np.array([float(l["y0_m"]) for l in links], dtype=np.float64)
    x1 = np.array([float(l["x1_m"]) for l in links], dtype=np.float64)
    y1 = np.array([float(l["y1_m"]) for l in links], dtype=np.float64)
    L_km = np.hypot(x1 - x0, y1 - y0) / 1000.0

    A_obs = np.array([float(l.get("A_db", np.nan)) for l in links], dtype=np.float64)
    f_ghz = np.array([float(l.get("freq_ghz", np.nan)) for l in links], dtype=np.float64)
    pol = np.array([str(l.get("pol", "H")) for l in links], dtype="<U1")
    k, alpha = itu838_k_alpha(f_ghz, pol)

    link_idx = np.array([
        int(l.get("link_index", i)) if str(l.get("link_index", i)).isdigit() else i
        for i, l in enumerate(links)
    ], dtype=np.int64)

    geoms = [LinkGeom(i, float(x0[i]), float(y0[i]), float(x1[i]), float(y1[i])) for i in range(n_links)]

    return {
        "header": header,
        "links": links,
        "segs_by_link": segs_by_link,
        "link_idx": link_idx,
        "A_obs": A_obs,
        "L_km": L_km,
        "k": k,
        "alpha": alpha,
        "geoms": geoms,
    }


def _compute_a_hat_from_field(
    R_hat: np.ndarray,
    segs_by_link: Sequence[Sequence[Dict[str, float]]],
    k: np.ndarray,
    alpha: np.ndarray,
) -> np.ndarray:
    H, W = R_hat.shape
    L = len(segs_by_link)
    out = np.zeros(L, dtype=np.float64)
    for li, segs in enumerate(segs_by_link):
        if not segs:
            continue
        kval = float(k[li])
        aval = float(alpha[li])
        if not (np.isfinite(kval) and np.isfinite(aval) and kval > 0.0 and aval > 0.0):
            continue
        acc = 0.0
        for s in segs:
            i = int(s["i"])
            j = int(s["j"])
            if i < 0 or i >= H or j < 0 or j >= W:
                continue
            ds_km = float(s["ds_m"]) / 1000.0
            r = float(R_hat[i, j])
            if r <= 0.0 or (not np.isfinite(r)):
                continue
            acc += ds_km * kval * (r ** aval)
        out[li] = acc
    return out


def _valid_mask(A_obs: np.ndarray, L_km: np.ndarray, k: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    return (
        np.isfinite(A_obs)
        & np.isfinite(L_km)
        & np.isfinite(k)
        & np.isfinite(alpha)
        & (L_km > 0.0)
        & (k > 0.0)
        & (alpha > 0.0)
    )


def _compute_e(A_obs: np.ndarray, A_hat: np.ndarray, L_km: np.ndarray, valid: np.ndarray) -> np.ndarray:
    e = np.full(A_obs.shape, np.nan, dtype=np.float64)
    idx = np.where(valid)[0]
    d = A_obs[idx] - A_hat[idx]
    e[idx] = (d * d) / L_km[idx]
    return e


def _pixel_overlap_stats(segs_by_link: Sequence[Sequence[Dict[str, float]]]) -> Tuple[np.ndarray, np.ndarray]:
    # Unique pixel participation per link
    pixel_to_count: Dict[Tuple[int, int], int] = {}
    link_pixels: List[List[Tuple[int, int]]] = []

    for segs in segs_by_link:
        pix = sorted({(int(s["i"]), int(s["j"])) for s in segs})
        link_pixels.append(pix)
        for p in pix:
            pixel_to_count[p] = pixel_to_count.get(p, 0) + 1

    pixels_crossed = np.array([len(pix) for pix in link_pixels], dtype=np.int64)
    pixels_with_overlap = np.array([
        sum(1 for p in pix if pixel_to_count.get(p, 0) >= 2) for pix in link_pixels
    ], dtype=np.int64)
    return pixels_crossed, pixels_with_overlap


def _cross2(ax: np.ndarray, ay: np.ndarray, bx: np.ndarray, by: np.ndarray) -> np.ndarray:
    return ax * by - ay * bx


def _orient(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    return _cross2(b[:, 0] - a[:, 0], b[:, 1] - a[:, 1], c[:, 0] - a[:, 0], c[:, 1] - a[:, 1])


def _on_segment(a: np.ndarray, b: np.ndarray, c: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    # c on bbox(a,b) with collinearity checked separately
    return (
        (np.minimum(a[:, 0], b[:, 0]) - eps <= c[:, 0])
        & (c[:, 0] <= np.maximum(a[:, 0], b[:, 0]) + eps)
        & (np.minimum(a[:, 1], b[:, 1]) - eps <= c[:, 1])
        & (c[:, 1] <= np.maximum(a[:, 1], b[:, 1]) + eps)
    )


def _segments_intersect_many(p1: np.ndarray, p2: np.ndarray, q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    n = q1.shape[0]
    a = np.repeat(p1.reshape(1, 2), n, axis=0)
    b = np.repeat(p2.reshape(1, 2), n, axis=0)

    o1 = _orient(a, b, q1)
    o2 = _orient(a, b, q2)
    o3 = _orient(q1, q2, a)
    o4 = _orient(q1, q2, b)

    eps = 1e-9
    proper = ((o1 > eps) & (o2 < -eps) | (o1 < -eps) & (o2 > eps)) & (
        ((o3 > eps) & (o4 < -eps)) | ((o3 < -eps) & (o4 > eps))
    )

    col1 = (np.abs(o1) <= eps) & _on_segment(a, b, q1)
    col2 = (np.abs(o2) <= eps) & _on_segment(a, b, q2)
    col3 = (np.abs(o3) <= eps) & _on_segment(q1, q2, a)
    col4 = (np.abs(o4) <= eps) & _on_segment(q1, q2, b)

    return proper | col1 | col2 | col3 | col4


def _point_to_segments_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    v = b - a
    w = p.reshape(1, 2) - a
    vv = np.sum(v * v, axis=1)
    vv = np.maximum(vv, 1e-12)
    t = np.sum(w * v, axis=1) / vv
    t = np.clip(t, 0.0, 1.0)
    proj = a + t[:, None] * v
    return np.hypot(proj[:, 0] - p[0], proj[:, 1] - p[1])


def _segment_distance_one_to_many(g: LinkGeom, others: Sequence[LinkGeom]) -> np.ndarray:
    if not others:
        return np.zeros(0, dtype=np.float64)
    p1 = np.array([g.x0, g.y0], dtype=np.float64)
    p2 = np.array([g.x1, g.y1], dtype=np.float64)

    q1 = np.array([[o.x0, o.y0] for o in others], dtype=np.float64)
    q2 = np.array([[o.x1, o.y1] for o in others], dtype=np.float64)

    inter = _segments_intersect_many(p1, p2, q1, q2)

    # Distances from p endpoints to each q-segment
    d1 = _point_to_segments_distance(p1, q1, q2)
    d2 = _point_to_segments_distance(p2, q1, q2)
    # Distances from q endpoints to the p-segment
    a = np.repeat(p1.reshape(1, 2), q1.shape[0], axis=0)
    b = np.repeat(p2.reshape(1, 2), q1.shape[0], axis=0)
    dq1 = _point_to_segments_distance_many_points(q1, a, b)
    dq2 = _point_to_segments_distance_many_points(q2, a, b)

    d = np.minimum(np.minimum(d1, d2), np.minimum(dq1, dq2))
    d[inter] = 0.0
    return d


def _point_to_segments_distance_many_points(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # p, a, b are (n,2): distance point p_i to segment [a_i,b_i]
    v = b - a
    w = p - a
    vv = np.sum(v * v, axis=1)
    vv = np.maximum(vv, 1e-12)
    t = np.sum(w * v, axis=1) / vv
    t = np.clip(t, 0.0, 1.0)
    proj = a + t[:, None] * v
    return np.hypot(proj[:, 0] - p[:, 0], proj[:, 1] - p[:, 1])


def _neighbor_counts_within_threshold(geoms: Sequence[LinkGeom], threshold_m: float) -> np.ndarray:
    n = len(geoms)
    out = np.zeros(n, dtype=np.int64)
    for i in range(n):
        d = _segment_distance_one_to_many(geoms[i], geoms[i + 1 :])
        hit = d <= threshold_m
        c = int(np.sum(hit))
        out[i] += c
        if c > 0:
            idxs = np.where(hit)[0] + (i + 1)
            out[idxs] += 1
    return out


def _bin_overlap_fraction(v: np.ndarray) -> np.ndarray:
    labels = np.full(v.shape, "nan", dtype=object)
    labels[np.isfinite(v) & (v == 0)] = "0"
    labels[np.isfinite(v) & (v > 0) & (v <= 0.25)] = "(0,0.25]"
    labels[np.isfinite(v) & (v > 0.25) & (v <= 0.50)] = "(0.25,0.50]"
    labels[np.isfinite(v) & (v > 0.50) & (v <= 0.75)] = "(0.50,0.75]"
    labels[np.isfinite(v) & (v > 0.75)] = "(0.75,1.00]"
    return labels


def _bin_neighbors(v: np.ndarray) -> np.ndarray:
    labels = np.full(v.shape, "nan", dtype=object)
    labels[v == 0] = "0"
    labels[(v >= 1) & (v <= 2)] = "1-2"
    labels[(v >= 3) & (v <= 5)] = "3-5"
    labels[(v >= 6) & (v <= 10)] = "6-10"
    labels[v >= 11] = "11+"
    return labels


def _group_mean_count(values: np.ndarray, bins: np.ndarray, order: Sequence[str]) -> List[Tuple[str, int, float, float]]:
    out: List[Tuple[str, int, float, float]] = []
    for b in order:
        m = bins == b
        n = int(np.sum(m))
        if n == 0:
            out.append((b, 0, np.nan, np.nan))
            continue
        vv = values[m]
        out.append((b, n, float(np.nanmean(vv)), float(np.nanmedian(vv))))
    return out


def _make_pareto_plot(e: np.ndarray, valid: np.ndarray, out_png: Path) -> None:
    vals = e[valid]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return
    vals = np.sort(vals)[::-1]
    cum = np.cumsum(vals)
    x = (np.arange(vals.size) + 1) / vals.size * 100.0
    y = cum / max(float(cum[-1]), 1e-30) * 100.0

    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150)
    ax.plot(x, y, color="#145DA0", linewidth=2.0)
    ax.set_xlabel("Top links (% of links, sorted by e_l)")
    ax.set_ylabel("Cumulative contribution to J_atten (%)")
    ax.set_title("Pareto: per-link ILDW error contribution")
    ax.grid(alpha=0.25)
    fig.text(0.01, 0.01, E_NOTE, ha="left", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def _make_crowding_plot(overlap_stats, neighbor_stats, out_png: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), dpi=150)

    o_labels = [x[0] for x in overlap_stats]
    o_mean = [x[2] for x in overlap_stats]
    axes[0].plot(o_labels, o_mean, marker="o", color="#1A7F37")
    axes[0].set_yscale("log")
    axes[0].set_title("Mean e_l by overlap fraction bin")
    axes[0].set_ylabel("Mean e_l (log scale)")
    axes[0].grid(alpha=0.25)

    n_labels = [x[0] for x in neighbor_stats]
    n_mean = [x[2] for x in neighbor_stats]
    axes[1].plot(n_labels, n_mean, marker="o", color="#B54708")
    axes[1].set_yscale("log")
    axes[1].set_title("Mean e_l by n_neighbors<=threshold")
    axes[1].set_ylabel("Mean e_l (log scale)")
    axes[1].grid(alpha=0.25)

    fig.text(0.01, 0.01, E_NOTE, ha="left", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def _make_ildw_vs_idw_plot(e_ildw: np.ndarray, e_idw: np.ndarray, valid: np.ndarray, out_png: Path) -> None:
    m = valid & np.isfinite(e_ildw) & np.isfinite(e_idw)
    if not np.any(m):
        return

    x = e_idw[m]
    y = e_ildw[m]
    eps = 1e-18

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=150)

    axes[0].scatter(x + eps, y + eps, s=14, alpha=0.6, color="#0A84FF", edgecolors="none")
    lo = float(max(min(np.min(x), np.min(y)), eps))
    hi = float(max(np.max(x), np.max(y), lo * 10))
    axes[0].plot([lo, hi], [lo, hi], "--", color="black", linewidth=1.1)
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("e_l (IDW)")
    axes[0].set_ylabel("e_l (ILDW)")
    axes[0].set_title("Per-link ILDW vs IDW error")
    axes[0].grid(alpha=0.25)

    ratio = y / np.maximum(x, eps)
    ratio = ratio[np.isfinite(ratio) & (ratio > 0.0)]
    if ratio.size == 0:
        return

    # Use fine-grained logarithmic bins so dense bars are easier to inspect.
    rmin = float(max(np.min(ratio), 1e-6))
    rmax = float(max(np.max(ratio), rmin * 10.0))
    n_bins = 120
    log_bins = np.logspace(np.log10(rmin), np.log10(rmax), num=n_bins)
    counts, edges, _ = axes[1].hist(ratio, bins=log_bins, color="#6F42C1", alpha=0.85)
    axes[1].set_xscale("log")
    axes[1].set_xlim(rmin, rmax)
    # Explicit major ticks on powers of 10 for clearer bin-range reading.
    p0 = int(np.floor(np.log10(rmin)))
    p1 = int(np.ceil(np.log10(rmax)))
    xt = [10.0 ** p for p in range(p0, p1 + 1)]
    axes[1].set_xticks(xt)
    axes[1].set_xticklabels([f"1e{p}" for p in range(p0, p1 + 1)])
    axes[1].set_xlabel("e_l(ILDW) / e_l(IDW)")
    axes[1].set_ylabel("# links")
    axes[1].set_title("Ratio histogram")
    axes[1].grid(alpha=0.25)

    # Annotate the tallest bar with its bin range.
    if counts.size > 0:
        k = int(np.argmax(counts))
        left = edges[k]
        right = edges[k + 1]
        axes[1].annotate(
            f"max bin: [{left:.2e}, {right:.2e})\\ncount={int(counts[k])}",
            xy=((left * right) ** 0.5, counts[k]),
            xytext=(0.03, 0.97),
            textcoords="axes fraction",
            ha="left",
            va="top",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#6F42C1", lw=0.8, alpha=0.9),
        )

    fig.text(0.01, 0.01, E_NOTE, ha="left", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def _make_map_with_topk(
    R_hat: np.ndarray,
    geoms: Sequence[LinkGeom],
    e_ildw: np.ndarray,
    valid: np.ndarray,
    header: Dict,
    out_png: Path,
    top_k: int,
) -> None:
    H, W = R_hat.shape
    pix = float(header.get("pixel_size_m", 125.0))
    width_m = W * pix
    height_m = H * pix

    fig, ax = plt.subplots(figsize=(13, 8), dpi=150)
    ax.imshow(
        R_hat,
        cmap="YlGnBu",
        origin="upper",
        extent=[0.0, width_m, height_m, 0.0],
        alpha=0.78,
    )

    # Base layer: all links
    for g in geoms:
        ax.plot([g.x0, g.x1], [g.y0, g.y1], color="#2A5CAA", linewidth=0.75, alpha=0.55)

    idx = np.where(valid & np.isfinite(e_ildw))[0]
    if idx.size > 0:
        rank_idx = idx[np.argsort(e_ildw[idx])[::-1]]
        top = rank_idx[: max(0, int(top_k))]
        rank_by_li = {int(li): n for n, li in enumerate(top, start=1)}

        # Highlight top links on the map.
        top_midpoints: List[Tuple[int, float, float]] = []
        for li in top:
            g = geoms[int(li)]
            xm = 0.5 * (g.x0 + g.x1)
            ym = 0.5 * (g.y0 + g.y1)
            ax.plot([g.x0, g.x1], [g.y0, g.y1], color="#C1121F", linewidth=2.0, alpha=0.95)
            top_midpoints.append((int(li), float(xm), float(ym)))

        # Non-overlapping labels: place all ranks on a right-side rail with leader lines.
        rail_margin = 0.22 * width_m
        x_anchor = width_m + 0.03 * width_m
        x_text = width_m + 0.10 * width_m
        ax.set_xlim(0.0, width_m + rail_margin)
        ax.axvspan(width_m, width_m + rail_margin, color="#F8F9FB", alpha=0.95, zorder=0)

        by_y = sorted(top_midpoints, key=lambda t: t[2])
        y_slots = np.linspace(0.05 * height_m, 0.95 * height_m, num=len(by_y))
        for (li, xm, ym), y_slot in zip(by_y, y_slots):
            n = rank_by_li[int(li)]
            ax.plot([xm, x_anchor], [ym, y_slot], color="#C1121F", linewidth=0.9, alpha=0.9)
            ax.text(
                x_text,
                float(y_slot),
                f"{n}",
                fontsize=9,
                va="center",
                ha="left",
                color="black",
                bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#C1121F", lw=0.9, alpha=0.95),
            )

    ax.set_title(f"ILDW rainfall map with top-{top_k} links labeled by e_l rank")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m, local-from-NW)")
    fig.text(0.01, 0.01, E_NOTE, ha="left", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def _ci95(vals: np.ndarray) -> Tuple[float, float, float]:
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return np.nan, np.nan, np.nan
    mean = float(np.mean(vals))
    if vals.size == 1:
        return mean, mean, mean
    se = float(np.std(vals, ddof=1) / np.sqrt(vals.size))
    d = 1.96 * se
    return mean, mean - d, mean + d


def _write_sheet(wb: Workbook, name: str, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    ws = wb.create_sheet(title=name)
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))


def _dataset_rows(
    label: str,
    est_json: Path,
    ildw_npz: Path,
    idw_npz: Path,
    neighbor_threshold_m: float,
):
    est = _load_est(est_json)
    R_ildw = _load_r_hat(ildw_npz)
    R_idw = _load_r_hat(idw_npz)

    if R_ildw.shape != R_idw.shape:
        raise ValueError(f"Shape mismatch ILDW vs IDW: {R_ildw.shape} vs {R_idw.shape} for {est_json}")

    A_obs = est["A_obs"]
    L_km = est["L_km"]
    k = est["k"]
    alpha = est["alpha"]

    A_hat_ildw = _compute_a_hat_from_field(R_ildw, est["segs_by_link"], k, alpha)
    A_hat_idw = _compute_a_hat_from_field(R_idw, est["segs_by_link"], k, alpha)

    valid = _valid_mask(A_obs, L_km, k, alpha)
    e_ildw = _compute_e(A_obs, A_hat_ildw, L_km, valid)
    e_idw = _compute_e(A_obs, A_hat_idw, L_km, valid)

    pixels_crossed, pixels_with_overlap = _pixel_overlap_stats(est["segs_by_link"])
    overlap_fraction = np.divide(
        pixels_with_overlap,
        np.maximum(pixels_crossed, 1),
        dtype=np.float64,
    )

    neighbors = _neighbor_counts_within_threshold(est["geoms"], neighbor_threshold_m)

    n_total = int(valid.size)
    n_valid = int(np.sum(valid))
    J_ildw = float(np.nanmean(e_ildw[valid])) if n_valid > 0 else np.nan
    J_idw = float(np.nanmean(e_idw[valid])) if n_valid > 0 else np.nan

    contrib_ildw = np.zeros_like(e_ildw)
    contrib_idw = np.zeros_like(e_idw)
    if n_total > 0:
        contrib_ildw[np.isfinite(e_ildw)] = e_ildw[np.isfinite(e_ildw)] / float(n_total)
        contrib_idw[np.isfinite(e_idw)] = e_idw[np.isfinite(e_idw)] / float(n_total)

    idx = np.where(valid & np.isfinite(e_ildw))[0]
    order = idx[np.argsort(e_ildw[idx])[::-1]] if idx.size > 0 else np.array([], dtype=np.int64)

    cumulative = np.zeros(e_ildw.shape[0], dtype=np.float64)
    if order.size > 0:
        csum = np.cumsum(e_ildw[order])
        denom = float(csum[-1]) if csum[-1] > 0 else 1.0
        cumulative[order] = csum / denom * 100.0

    rows = []
    csum_i = np.cumsum(e_ildw[order]) if order.size > 0 else np.zeros(0, dtype=np.float64)
    csum_d = np.cumsum(e_idw[order]) if order.size > 0 else np.zeros(0, dtype=np.float64)
    for rank, li in enumerate(order, start=1):
        prefix_j_i = float(csum_i[rank - 1] / rank)
        prefix_j_d = float(csum_d[rank - 1] / rank)
        prefix_ratio_pct = float(100.0 * prefix_j_i / prefix_j_d) if prefix_j_d > 0.0 else np.nan
        rows.append(
            (
                label,
                rank,
                int(est["link_idx"][li]),
                int(li),
                float(e_ildw[li]),
                float(contrib_ildw[li]),
                float(cumulative[li]),
                float(e_idw[li]) if np.isfinite(e_idw[li]) else np.nan,
                float(contrib_idw[li]),
                (float(e_ildw[li] / max(e_idw[li], 1e-18)) if np.isfinite(e_idw[li]) else np.nan),
                prefix_j_i,
                prefix_j_d,
                prefix_ratio_pct,
                float(A_obs[li]),
                float(A_hat_ildw[li]),
                float(A_hat_idw[li]),
                float(L_km[li]),
                int(pixels_crossed[li]),
                int(pixels_with_overlap[li]),
                float(overlap_fraction[li]),
                int(neighbors[li]),
            )
        )

    overlap_mask = valid & np.isfinite(e_ildw) & np.isfinite(e_idw)
    overlap_bins = _bin_overlap_fraction(overlap_fraction[overlap_mask])
    overlap_vals_ildw = e_ildw[overlap_mask]
    overlap_vals_idw = e_idw[overlap_mask]
    overlap_order = ["0", "(0,0.25]", "(0.25,0.50]", "(0.50,0.75]", "(0.75,1.00]"]
    overlap_stats_ildw = _group_mean_count(overlap_vals_ildw, overlap_bins, overlap_order)
    overlap_stats_idw = _group_mean_count(overlap_vals_idw, overlap_bins, overlap_order)
    overlap_stats = []
    for (b, n, mean_i, med_i), (_, _, mean_d, med_d) in zip(overlap_stats_ildw, overlap_stats_idw):
        ratio_means = float(mean_i / mean_d) if (np.isfinite(mean_i) and np.isfinite(mean_d) and mean_d > 0.0) else np.nan
        overlap_stats.append((b, n, mean_i, med_i, mean_d, med_d, ratio_means))

    neigh_mask = valid & np.isfinite(e_ildw) & np.isfinite(e_idw)
    neigh_vals = neighbors[neigh_mask]
    neigh_bins = _bin_neighbors(neigh_vals)
    neigh_order = ["0", "1-2", "3-5", "6-10", "11+"]
    neigh_stats_ildw = _group_mean_count(e_ildw[neigh_mask], neigh_bins, neigh_order)
    neigh_stats_idw = _group_mean_count(e_idw[neigh_mask], neigh_bins, neigh_order)
    neigh_stats = []
    for (b, n, mean_i, med_i), (_, _, mean_d, med_d) in zip(neigh_stats_ildw, neigh_stats_idw):
        ratio_means_pct = float(100.0 * mean_i / mean_d) if (np.isfinite(mean_i) and np.isfinite(mean_d) and mean_d > 0.0) else np.nan
        neigh_stats.append((b, n, mean_i, med_i, mean_d, med_d, ratio_means_pct))

    return {
        "label": label,
        "est_json": est_json,
        "R_ildw": R_ildw,
        "header": est["header"],
        "geoms": est["geoms"],
        "valid": valid,
        "e_ildw": e_ildw,
        "e_idw": e_idw,
        "rows": rows,
        "link_idx": est["link_idx"],
        "overlap_fraction": overlap_fraction,
        "overlap_stats": overlap_stats,
        "neighbor_stats": neigh_stats,
        "summary": {
            "label": label,
            "n_links_total": n_total,
            "n_links_valid": n_valid,
            "J_atten_ildw": J_ildw,
            "J_atten_idw": J_idw,
            "ratio_ildw_over_idw": (J_ildw / J_idw) if (np.isfinite(J_ildw) and np.isfinite(J_idw) and J_idw > 0) else np.nan,
        },
    }


def _collect_pairs(est_dir: Path, ildw_dir: Path, idw_dir: Path) -> List[Tuple[str, Path, Path, Path]]:
    est_map = _find_est_inputs(est_dir)
    ildw_map = _find_solution_npz(ildw_dir)
    idw_map = _find_solution_npz(idw_dir)

    keys = sorted(set(est_map.keys()) & set(ildw_map.keys()) & set(idw_map.keys()))
    return [(k, est_map[k], ildw_map[k], idw_map[k]) for k in keys]


def _make_synth_plot(rows: List[Tuple[str, float, float, float]], out_png: Path):
    if not rows:
        return
    labels = [r[0] for r in rows]
    means = np.array([r[1] for r in rows], dtype=np.float64)
    los = np.array([r[2] for r in rows], dtype=np.float64)
    his = np.array([r[3] for r in rows], dtype=np.float64)

    yerr = np.vstack([means - los, his - means])

    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=150)
    ax.bar(labels, means, yerr=yerr, capsize=6, color=["#2563EB", "#D97706"][: len(labels)], alpha=0.85)
    ax.set_ylabel("J_atten(ILDW)")
    ax.set_title("Synthetic controls: mean J_atten(ILDW) with 95% CI")
    ax.grid(alpha=0.25, axis="y")
    fig.text(0.01, 0.01, E_NOTE, ha="left", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)



def _prefix_rows_for_dataset(label: str, e_ildw: np.ndarray, e_idw: np.ndarray, valid: np.ndarray):
    idx = np.where(valid & np.isfinite(e_ildw) & np.isfinite(e_idw))[0]
    if idx.size == 0:
        return []
    order = idx[np.argsort(e_ildw[idx])[::-1]]
    e_i = e_ildw[order]
    e_d = e_idw[order]
    c_i = np.cumsum(e_i)
    c_d = np.cumsum(e_d)
    rows = []
    for x in range(1, order.size + 1):
        j_i = float(c_i[x - 1] / x)
        j_d = float(c_d[x - 1] / x)
        ratio_pct = float(100.0 * j_i / j_d) if j_d > 0 else np.nan
        rows.append((label, x, j_i, j_d, ratio_pct))
    return rows


def _overlap_prefix_rows_for_dataset(
    label: str,
    link_idx: np.ndarray,
    overlap_fraction: np.ndarray,
    e_ildw: np.ndarray,
    e_idw: np.ndarray,
    valid: np.ndarray,
):
    m = valid & np.isfinite(overlap_fraction) & np.isfinite(e_ildw) & np.isfinite(e_idw)
    idx = np.where(m)[0]
    if idx.size == 0:
        return []

    # Sort by overlap_fraction ascending; tie-break by e_ildw descending.
    order_local = np.lexsort((-e_ildw[idx], overlap_fraction[idx]))
    order = idx[order_local]

    c_i = np.cumsum(e_ildw[order])
    c_d = np.cumsum(e_idw[order])

    rows = []
    for x, li in enumerate(order, start=1):
        j_i = float(c_i[x - 1] / x)
        j_d = float(c_d[x - 1] / x)
        ratio_pct = float(100.0 * j_i / j_d) if j_d > 0 else np.nan
        rows.append((
            label,
            x,
            int(link_idx[li]),
            int(li),
            float(overlap_fraction[li]),
            float(e_ildw[li]),
            float(e_idw[li]),
            j_i,
            j_d,
            ratio_pct,
        ))
    return rows


def _make_prefix_ratio_plot(prefix_rows: List[Tuple[str, int, float, float, float]], out_png: Path) -> None:
    if not prefix_rows:
        return
    xs = np.array([r[1] for r in prefix_rows], dtype=np.int64)
    yi = np.array([r[2] for r in prefix_rows], dtype=np.float64)
    yd = np.array([r[3] for r in prefix_rows], dtype=np.float64)
    yr = np.array([r[4] for r in prefix_rows], dtype=np.float64)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=150)

    axes[0].plot(xs, yi, color="#C1121F", linewidth=1.8, label="Prefix J_atten(ILDW)")
    axes[0].plot(xs, yd, color="#0A84FF", linewidth=1.8, label="Prefix J_atten(IDW)")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Top X links (sorted by e_l desc)")
    axes[0].set_ylabel("Prefix J_atten")
    axes[0].set_title("Prefix J_atten by top-X links")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="best")

    axes[1].plot(xs, yr, color="#6F42C1", linewidth=1.8)
    axes[1].set_xlabel("Top X links (sorted by e_l desc)")
    axes[1].set_ylabel("Prefix ratio (%)")
    axes[1].set_title("100 * Prefix J_atten(ILDW) / Prefix J_atten(IDW)")
    axes[1].grid(alpha=0.25)

    fig.text(0.01, 0.01, E_NOTE, ha="left", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)

def main() -> None:
    ap = argparse.ArgumentParser(description="Per-link diagnostics for ILDW vs IDW attenuation mismatch")
    ap.add_argument("--est-json", type=Path, help="Single est_input JSON path")
    ap.add_argument("--ildw-npz", type=Path, help="Single ILDW solution NPZ path (must contain R_hat)")
    ap.add_argument("--idw-npz", type=Path, help="Single IDW solution NPZ path (must contain R_hat)")
    ap.add_argument("--label", type=str, default="native", help="Label for single-run mode")

    ap.add_argument("--native-est-dir", type=Path, help="Directory with native est_input_*.json")
    ap.add_argument("--native-ildw-dir", type=Path, help="Directory with native ILDW est_input_*_solution.npz")
    ap.add_argument("--native-idw-dir", type=Path, help="Directory with native IDW est_input_*_solution.npz")

    ap.add_argument("--synthetic-est-dir", type=Path, help="Directory with synthetic est_input_*.json")
    ap.add_argument("--synthetic-ildw-dir", type=Path, help="Directory with synthetic ILDW est_input_*_solution.npz")
    ap.add_argument("--synthetic-idw-dir", type=Path, help="Directory with synthetic IDW est_input_*_solution.npz")

    ap.add_argument("--neighbor-threshold-m", type=float, default=177.0)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    datasets: List[dict] = []

    if args.est_json and args.ildw_npz and args.idw_npz:
        datasets.append(
            _dataset_rows(
                args.label,
                args.est_json,
                args.ildw_npz,
                args.idw_npz,
                args.neighbor_threshold_m,
            )
        )

    if args.native_est_dir and args.native_ildw_dir and args.native_idw_dir:
        for key, est_p, ildw_p, idw_p in _collect_pairs(args.native_est_dir, args.native_ildw_dir, args.native_idw_dir):
            datasets.append(_dataset_rows(f"native::{key}", est_p, ildw_p, idw_p, args.neighbor_threshold_m))

    if args.synthetic_est_dir and args.synthetic_ildw_dir and args.synthetic_idw_dir:
        for key, est_p, ildw_p, idw_p in _collect_pairs(args.synthetic_est_dir, args.synthetic_ildw_dir, args.synthetic_idw_dir):
            datasets.append(_dataset_rows(f"synthetic::{key}", est_p, ildw_p, idw_p, args.neighbor_threshold_m))

    if not datasets:
        raise SystemExit("No dataset configured. Provide single-run args or native/synthetic directories.")

    # Aggregate workbook rows
    ranked_rows = []
    overlap_prefix_rows = []
    crowd_overlap_rows = []
    crowd_neighbor_rows = []
    summary_rows = []

    for ds in datasets:
        ranked_rows.extend(ds["rows"])
        overlap_prefix_rows.extend(
            _overlap_prefix_rows_for_dataset(
                ds["label"],
                ds["link_idx"],
                ds["overlap_fraction"],
                ds["e_ildw"],
                ds["e_idw"],
                ds["valid"],
            )
        )
        for (b, n, mean_e_ildw, med_e_ildw, mean_e_idw, med_e_idw, ratio_means) in ds["overlap_stats"]:
            crowd_overlap_rows.append((ds["label"], b, n, mean_e_ildw, med_e_ildw, mean_e_idw, med_e_idw, ratio_means))
        for (b, n, mean_e_ildw, med_e_ildw, mean_e_idw, med_e_idw, ratio_means_pct) in ds["neighbor_stats"]:
            crowd_neighbor_rows.append((ds["label"], b, n, mean_e_ildw, med_e_ildw, mean_e_idw, med_e_idw, ratio_means_pct))
        s = ds["summary"]
        summary_rows.append((s["label"], s["n_links_total"], s["n_links_valid"], s["J_atten_ildw"], s["J_atten_idw"], s["ratio_ildw_over_idw"]))

    wb = Workbook()
    wb.remove(wb.active)

    _write_sheet(
        wb,
        "Links_Ranked",
        [
            "dataset",
            "rank_by_e_ildw",
            "link_id",
            "link_idx_internal",
            "e_ildw",
            "contrib_to_J_ildw_per_all_links",
            "cum_contrib_pct_ildw",
            "e_idw",
            "contrib_to_J_idw_per_all_links",
            "ratio_e_ildw_over_idw",
            "prefix_J_atten_ildw",
            "prefix_J_atten_idw",
            "prefix_ratio_pct",
            "A_obs",
            "A_hat_ildw",
            "A_hat_idw",
            "L_km",
            "pixels_crossed",
            "pixels_with_overlap",
            "overlap_fraction",
            "n_neighbors_within_threshold",
        ],
        ranked_rows,
    )

    _write_sheet(
        wb,
        "Overlap_Prefix_J",
        [
            "dataset",
            "rank_by_overlap_asc",
            "link_id",
            "link_idx_internal",
            "overlap_fraction",
            "e_ildw",
            "e_idw",
            "prefix_J_atten_ildw",
            "prefix_J_atten_idw",
            "prefix_ratio_pct",
        ],
        overlap_prefix_rows,
    )

    _write_sheet(
        wb,
        "Crowding_Overlap",
        [
            "dataset",
            "overlap_fraction_bin",
            "n_links",
            "mean_e_ildw",
            "median_e_ildw",
            "mean_e_idw",
            "median_e_idw",
            "ratio_means_e_ildw_idw",
        ],
        crowd_overlap_rows,
    )

    _write_sheet(
        wb,
        "Crowding_Neighbors",
        [
            "dataset",
            "neighbors_bin",
            "n_links",
            "mean_e_ildw",
            "median_e_ildw",
            "mean_e_idw",
            "median_e_idw",
            "ratio_means_e_ildw_idw_pct",
        ],
        crowd_neighbor_rows,
    )

    _write_sheet(
        wb,
        "Summary",
        ["dataset", "n_links_total", "n_links_valid", "J_atten_ildw", "J_atten_idw", "ratio_ildw_over_idw"],
        summary_rows,
    )

    # Synthetic controls (native vs synthetic CI), if both groups exist
    synth_rows = []
    native_vals = np.array([s[3] for s in summary_rows if str(s[0]).startswith("native::")], dtype=np.float64)
    synth_vals = np.array([s[3] for s in summary_rows if str(s[0]).startswith("synthetic::")], dtype=np.float64)
    if native_vals.size > 0 and synth_vals.size > 0:
        n_mean, n_lo, n_hi = _ci95(native_vals)
        s_mean, s_lo, s_hi = _ci95(synth_vals)
        synth_rows = [
            ("native", int(native_vals.size), n_mean, n_lo, n_hi),
            ("synthetic", int(synth_vals.size), s_mean, s_lo, s_hi),
        ]
        _write_sheet(
            wb,
            "SyntheticControls",
            ["group", "n_patches", "mean_J_atten_ildw", "ci95_low", "ci95_high"],
            synth_rows,
        )

    xlsx_path = out_dir / "link_diagnostics_report.xlsx"
    wb.save(xlsx_path)

    # Per-request plots for the first dataset as main visual package
    ds0 = datasets[0]
    _make_pareto_plot(ds0["e_ildw"], ds0["valid"], images_dir / "pareto_topk_cumulative_J.png")
    _make_crowding_plot(ds0["overlap_stats"], ds0["neighbor_stats"], images_dir / "crowding_vs_error.png")
    _make_ildw_vs_idw_plot(ds0["e_ildw"], ds0["e_idw"], ds0["valid"], images_dir / "ildw_vs_idw_per_link.png")
    _make_prefix_ratio_plot(
        _prefix_rows_for_dataset(ds0["label"], ds0["e_ildw"], ds0["e_idw"], ds0["valid"]),
        images_dir / "prefix_j_ratio_topx.png",
    )
    _make_map_with_topk(
        ds0["R_ildw"],
        ds0["geoms"],
        ds0["e_ildw"],
        ds0["valid"],
        ds0["header"],
        images_dir / f"ildw_map_top{int(args.top_k)}_labels.png",
        top_k=int(args.top_k),
    )

    if synth_rows:
        _make_synth_plot([(r[0], r[2], r[3], r[4]) for r in synth_rows], images_dir / "synthetic_controls_ci95.png")

    print(f"Wrote: {xlsx_path}")
    print(f"Images dir: {images_dir}")
    print(f"Output dir: {out_dir}")


if __name__ == "__main__":
    main()
