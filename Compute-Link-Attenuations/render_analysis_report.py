#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from batch_analyze_multi import (
    load_config_file,
    load_npz_first_key,
    mask_to_nan,
    objective_header_comments_map,
    parse_bins,
    read_report_cache,
    reorder_report_sheets,
    safe_path_token,
    save_png_2x2,
    write_workbook,
)


def render_bool(cfg: Dict[str, Any], path: str, default: bool) -> bool:
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return bool(cur)


def render_value(cfg: Dict[str, Any], path: str, default: Any) -> Any:
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def resolve_render_config_path(
    cache: Dict[str, Any],
    explicit_path: Optional[str],
) -> Optional[Path]:
    if explicit_path:
        path = Path(explicit_path).resolve()
        return path if path.exists() else None
    cfg_path = cache.get("config_path", None)
    if cfg_path:
        candidate = Path(str(cfg_path)).resolve().with_name("render_report.yaml")
        if candidate.exists():
            return candidate
    return None


def compute_relative_distribution_profile(
    per_patch_values: Dict[str, Dict[str, List[float]]],
    *,
    baseline_label: str,
    dist_labels: List[str],
) -> Dict[str, Dict[str, List[float]]]:
    if baseline_label not in per_patch_values:
        return {}
    out: Dict[str, Dict[str, List[float]]] = {}
    baseline_bins = per_patch_values[baseline_label]
    for method, by_bin in per_patch_values.items():
        out[method] = {}
        for lab in dist_labels:
            baseline_vals = np.asarray(baseline_bins.get(lab, []), dtype=np.float64)
            if baseline_vals.size == 0:
                out[method][lab] = []
                continue
            baseline_med = float(np.percentile(baseline_vals, 50))
            if baseline_med == 0.0:
                out[method][lab] = []
                continue
            vals = np.asarray(by_bin.get(lab, []), dtype=np.float64)
            vals = vals[np.isfinite(vals)]
            out[method][lab] = [float(v / baseline_med) for v in vals]
    return out


def plot_box_whisker(
    out_png: Path,
    title: str,
    per_patch_values: Dict[str, Dict[str, List[float]]],
    dist_labels: List[str],
    method_order: List[str],
    *,
    y_max: Optional[float] = None,
    dpi: int = 150,
    bin_spacing: float = 1.0,
    tick_labels: Optional[List[str]] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    footnote: Optional[str] = None,
    show_boxes: bool = True,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    n_bins = len(dist_labels)
    n_methods = len(method_order)
    x = np.arange(n_bins) * float(bin_spacing)
    width = 0.8 / max(1, n_methods)
    offsets = (np.arange(n_methods) - (n_methods - 1) / 2.0) * width

    fig_w = max(6, n_bins * 1.2 * float(bin_spacing))
    fig, ax = plt.subplots(figsize=(fig_w, 4.5), dpi=dpi)
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors = {m: color_cycle[i % max(1, len(color_cycle))] for i, m in enumerate(method_order)}

    for mi, method in enumerate(method_order):
        off = offsets[mi]
        color = colors.get(method, None)
        medians: List[float] = []
        for bi, lab in enumerate(dist_labels):
            vals = np.asarray(per_patch_values.get(method, {}).get(lab, []), dtype=np.float64)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                medians.append(0.0)
                continue
            medians.append(float(np.percentile(vals, 50)))
            if show_boxes:
                ax.boxplot(
                    [vals],
                    positions=[x[bi] + off],
                    widths=width * 0.8,
                    patch_artist=True,
                    showfliers=False,
                    whis=(0, 100),
                    manage_ticks=False,
                    boxprops={"facecolor": color, "alpha": 0.25, "edgecolor": color, "linewidth": 1.2},
                    whiskerprops={"color": color, "linewidth": 1.2},
                    capprops={"color": color, "linewidth": 1.2},
                    medianprops={"color": color, "linewidth": 1.4},
                )
        ax.plot(x + off, medians, marker="o", linestyle="None", color=color, label=method)

    ax.set_xticks(x)
    tick_labels = tick_labels or dist_labels
    has_multiline = any("\n" in str(lab) for lab in tick_labels)
    if has_multiline:
        ax.set_xticklabels(tick_labels, rotation=20, ha="right", fontsize=8)
        fig.subplots_adjust(bottom=0.28)
        ax.set_xlabel(x_label or "Distance bin (m)\nSecond line: avg pixels [avg-std, avg+std]")
    else:
        ax.set_xticklabels(tick_labels, rotation=0)
    ax.set_ylabel(y_label or "Per-patch median error")
    ax.set_title(title)
    ax.legend(loc="best")
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)

    if y_max is not None:
        ax.set_ylim(0, y_max)
    else:
        ax.set_ylim(bottom=0)

    if footnote:
        fig.text(0.5, 0.01, str(footnote), ha="center", fontsize=8)
        fig.tight_layout(rect=(0, 0.05, 1, 1))
    else:
        fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def render_patch_error_maps_from_job(
    job: Dict[str, Any],
    *,
    img_dir: Path,
    render_cfg: Dict[str, Any],
) -> None:
    gt = load_npz_first_key(Path(str(job["gt_path"])), list(job["gt_key_pref"])).astype(np.float64)
    pred = load_npz_first_key(Path(str(job["sol_path"])), list(job["sol_key_pref"])).astype(np.float64)
    if gt.shape != pred.shape:
        raise ValueError(f"Shape mismatch for patch plot {job['patch_key']}: GT {gt.shape} vs SOL {pred.shape}")

    key = str(job["patch_key"])
    solver_label = str(job["solver_label"])
    thr = float(render_cfg["threshold_mmph"])
    plot_dpi = int(render_cfg["dpi"])
    cmap_gt = str(render_cfg["cmap_gt"])
    cmap_sol = str(render_cfg["cmap_sol"])
    cmap_diff = str(render_cfg["cmap_diff"])
    cmap_abs = str(render_cfg["cmap_abs_diff"])
    cmap_rel = str(render_cfg["cmap_rel"])
    cmap_abs_rel = str(render_cfg["cmap_abs_rel"])

    rainy = gt >= thr
    rel_full = np.full_like(gt, np.nan, dtype=np.float64)
    if np.any(rainy):
        rel_full[rainy] = (gt[rainy] - pred[rainy]) / np.where(gt[rainy] == 0.0, 1.0, gt[rainy])
    abs_rel_full = np.abs(rel_full)
    diff_full = pred - gt
    abs_diff_full = np.abs(diff_full)

    finite_gt_sol = np.concatenate([gt[np.isfinite(gt)], pred[np.isfinite(pred)]])
    rmax = float(np.max(finite_gt_sol)) if finite_gt_sol.size > 0 else 1.0
    rmax = max(rmax, 1e-9)
    rel_max = float(np.nanmax(np.abs(rel_full))) if np.any(np.isfinite(rel_full)) else 1.0
    rel_abs_max = float(np.nanmax(abs_rel_full)) if np.any(np.isfinite(abs_rel_full)) else 1.0
    dmax = float(np.nanmax(np.abs(diff_full[~rainy]))) if np.any(~rainy) else 1.0
    rel_max = max(rel_max, 1e-9)
    rel_abs_max = max(rel_abs_max, 1e-9)
    dmax = max(dmax, 1e-9)

    patch_plot_dir = img_dir / "patch_error_maps" / safe_path_token(solver_label)
    save_png_2x2(
        patch_plot_dir / f"{safe_path_token(key)}_rainy.png",
        mask_to_nan(gt, rainy),
        mask_to_nan(pred, rainy),
        mask_to_nan(rel_full, rainy),
        mask_to_nan(abs_rel_full, rainy),
        titles=("GT (rainy)", "SOL (rainy)", "(GT-SOL)/GT", "|GT-SOL|/GT"),
        suptitle=f"{key} | rainy: GT>= {thr} mm/h",
        cmaps=(cmap_gt, cmap_sol, cmap_rel, cmap_abs_rel),
        vlims=((0.0, rmax), (0.0, rmax), (-rel_max, rel_max), (0.0, rel_abs_max)),
        dpi=plot_dpi,
        show=False,
    )
    save_png_2x2(
        patch_plot_dir / f"{safe_path_token(key)}_nonrainy.png",
        mask_to_nan(gt, ~rainy),
        mask_to_nan(pred, ~rainy),
        mask_to_nan(diff_full, ~rainy),
        mask_to_nan(abs_diff_full, ~rainy),
        titles=("GT (non-rainy)", "SOL (non-rainy)", "SOL-GT", "|SOL-GT|"),
        suptitle=f"{key} | non-rainy: GT< {thr} mm/h",
        cmaps=(cmap_gt, cmap_sol, cmap_diff, cmap_abs),
        vlims=((0.0, rmax), (0.0, rmax), (-dmax, dmax), (0.0, rmax)),
        dpi=plot_dpi,
        show=False,
    )


def plot_ratio_box_whisker(
    out_png: Path,
    *,
    title: str,
    entries: List[Tuple[str, str, List[float]]],
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    if not entries:
        return

    x = np.arange(len(entries))
    fig_w = max(8, len(entries) * 0.8)
    fig, ax = plt.subplots(figsize=(fig_w, 4.5), dpi=dpi)

    solver_labels: List[str] = []
    for solver, _, _ in entries:
        if solver not in solver_labels:
            solver_labels.append(solver)
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors = {s: color_cycle[i % max(1, len(color_cycle))] for i, s in enumerate(solver_labels)}

    medians: List[float] = []
    for _, _, vals in entries:
        arr = np.asarray(vals, dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        medians.append(float(np.percentile(arr, 50)) if arr.size else 0.0)

    for i, (solver, _, vals) in enumerate(entries):
        color = colors.get(solver, None)
        arr = np.asarray(vals, dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        if arr.size > 0:
            ax.boxplot(
                [arr],
                positions=[x[i]],
                widths=0.5,
                patch_artist=True,
                showfliers=False,
                whis=(0, 100),
                manage_ticks=False,
                boxprops={"facecolor": color, "alpha": 0.25, "edgecolor": color, "linewidth": 1.2},
                whiskerprops={"color": color, "linewidth": 1.2},
                capprops={"color": color, "linewidth": 1.2},
                medianprops={"color": color, "linewidth": 1.4},
            )
        ax.plot(x[i], medians[i], marker="o", linestyle="None", color=color)

    ax.set_xticks(x)
    ax.set_xticklabels([lab for _, lab, _ in entries], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Per-patch ratio")
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)
    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[s], label=s) for s in solver_labels]
    ax.legend(handles=handles, loc="best")

    fig.text(
        0.5,
        0.01,
        "L1 = sum(|A_hat-A_obs|); J1 ratio uses J1_len1 = sum((A_hat-A_obs)^2/L_km); "
        "E = sum(A_obs-A_hat)/sum(|L_km|); E2 = sum((A_obs-A_hat)^2)/sum(|L_km|) over all links",
        ha="center",
        fontsize=8,
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_png)
    plt.close(fig)


def plot_fp_fn_vs_threshold(
    out_png: Path,
    *,
    title: str,
    rows: List[Dict[str, Any]],
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore
    from matplotlib.ticker import FormatStrFormatter, MultipleLocator  # type: ignore

    if not rows:
        return

    by_solver: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_solver.setdefault(str(row["solver"]), []).append(row)

    fig, ax = plt.subplots(figsize=(9.8, 5.2), dpi=dpi)
    for solver, vals in sorted(by_solver.items()):
        vals_sorted = sorted(vals, key=lambda x: float(x.get("threshold_mmph", 0.0)))
        xs = np.array([float(v["threshold_mmph"]) for v in vals_sorted], dtype=np.float64)
        fp = np.array([float(v.get("fp_rate_dry_mean", 0.0)) for v in vals_sorted], dtype=np.float64)
        fn = np.array([float(v.get("fn_rate_wet_mean", 0.0)) for v in vals_sorted], dtype=np.float64)
        fp_std = np.array([float(v.get("fp_rate_dry_std", 0.0)) for v in vals_sorted], dtype=np.float64)
        fn_std = np.array([float(v.get("fn_rate_wet_std", 0.0)) for v in vals_sorted], dtype=np.float64)
        marker = "o" if xs.size == 1 else None
        plot_kwargs = dict(linewidth=1.8, marker=marker, markersize=6, markeredgewidth=1.0, zorder=3, clip_on=False)
        (l_fp,) = ax.plot(xs, fp, linestyle="-", label=f"{solver} FPR", **plot_kwargs)
        (l_fn,) = ax.plot(xs, fn, linestyle="--", label=f"{solver} FNR", **plot_kwargs)
        ax.fill_between(xs, np.clip(fp - fp_std, 0.0, 1.0), np.clip(fp + fp_std, 0.0, 1.0), color=l_fp.get_color(), alpha=0.12, linewidth=0.0)
        ax.fill_between(xs, np.clip(fn - fn_std, 0.0, 1.0), np.clip(fn + fn_std, 0.0, 1.0), color=l_fn.get_color(), alpha=0.08, linewidth=0.0)

    ax.set_xlabel("Threshold (mm/h)")
    ax.set_ylabel("Rate")
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)
    ax.set_ylim(bottom=-0.02)
    ax.xaxis.set_major_locator(MultipleLocator(0.1))
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.tick_params(axis="x", labelrotation=90, labelsize=7)
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="best", fontsize=8)
    fig.suptitle(title)
    fig.text(
        0.5,
        0.01,
        "Wet is the positive class. Solid=FPR=FP/GT_dry_count; dashed=FNR=FN/GT_wet_count. Shaded band shows mean±std across patches.",
        ha="center",
        fontsize=8,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(out_png)
    plt.close(fig)


def plot_j_behavior(
    out_png: Path,
    *,
    title: str,
    iterations: Sequence[Dict[str, Any]],
    dpi: int = 150,
) -> None:
    if not iterations:
        return
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return

    xs = [int(it.get("iter", i + 1)) for i, it in enumerate(iterations)]

    def series(key: str) -> List[float]:
        out: List[float] = []
        for it in iterations:
            v = it.get(key, None)
            try:
                out.append(float(v) if v is not None else float("nan"))
            except Exception:
                out.append(float("nan"))
        return out

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=dpi)
    ax.plot(xs, series("J_native_total"), marker="o", markersize=2.0, linewidth=1.0, label="J_weighted_sum (J_native_total)")
    ax.plot(xs, series("J_atten"), marker="o", markersize=2.0, linewidth=0.9, label="J_atten")
    ax.plot(xs, series("J_1d"), marker="o", markersize=2.0, linewidth=0.9, label="J_1d")
    ax.plot(xs, series("J_total"), marker="o", markersize=2.0, linewidth=0.9, label="J_total")
    ax.plot(xs, series("J_2d"), marker="o", markersize=2.0, linewidth=0.9, label="J_2d")
    ax.set_title(title)
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Value")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi)
    plt.close(fig)


def build_bin_tick_labels(
    dist_labels: List[str],
    counts_by_bin: Dict[str, List[int]],
    *,
    count_label: str = "px",
) -> List[str]:
    out: List[str] = []
    for lab in dist_labels:
        vals = np.array(counts_by_bin.get(lab, []), dtype=np.float64)
        if vals.size == 0:
            out.append(f"{lab}\n{count_label} avg=0 [0,0]")
            continue
        avg = float(np.mean(vals))
        std = float(np.std(vals, ddof=0))
        out.append(f"{lab}\n{count_label} avg={avg:.0f} [{max(0.0, avg - std):.0f},{max(0.0, avg + std):.0f}]")
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
        if vals and (sum(1 for v in vals if v == 0) / float(len(vals))) < zero_frac_threshold:
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
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    n_bins = len(dist_labels)
    ncols = min(4, max(1, n_bins))
    nrows = int(math.ceil(n_bins / ncols))
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(max(8, ncols * 3.2), max(3.0, nrows * 2.6)), dpi=dpi)
    if nrows == 1 and ncols == 1:
        axes = np.array([[axes]])
    elif nrows == 1:
        axes = np.array([axes])
    elif ncols == 1:
        axes = axes[:, None]

    for i, lab in enumerate(dist_labels):
        ax = axes[i // ncols][i % ncols]
        vals = np.array(data_by_bin.get(lab, []), dtype=np.float64)
        if vals.size > 0:
            ax.hist(vals, bins=bins, color="#4C78A8", alpha=0.85)
        ax.set_title(lab)
        ax.set_xlabel("RAE = |GT-PRED|/GT")
        ax.set_ylabel("count")
        ax.grid(True, axis="y", linestyle=":", linewidth=0.6)

    for i in range(n_bins, nrows * ncols):
        axes[i // ncols][i % ncols].axis("off")

    fig.suptitle(title)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def plot_gt_binned_patchavg_error(
    out_png: Path,
    *,
    title: str,
    bin_labels: List[str],
    bin_count_stats: Optional[Dict[str, Tuple[float, float]]] = None,
    solver_order: List[str],
    mean_by_solver: Dict[str, List[float]],
    std_by_solver: Dict[str, List[float]],
    y_label: str,
    footnote: Optional[str] = None,
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    if not bin_labels or not solver_order:
        return
    x = np.arange(len(bin_labels), dtype=np.float64)
    nsol = max(1, len(solver_order))
    width = 0.8 / nsol
    fig, ax = plt.subplots(figsize=(max(10.0, len(bin_labels) * 1.3), 5.8), dpi=dpi)
    color_cycle = ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F"]

    for s_idx, solver in enumerate(solver_order):
        mean_vals = np.array(mean_by_solver.get(solver, []), dtype=np.float64)
        std_vals = np.array(std_by_solver.get(solver, []), dtype=np.float64)
        if mean_vals.size == 0:
            continue
        xpos = x + (s_idx - (nsol - 1) / 2.0) * width
        ax.bar(
            xpos,
            mean_vals,
            width=width,
            color=color_cycle[s_idx % len(color_cycle)],
            alpha=0.85,
            label=solver,
            yerr=std_vals,
            error_kw={"elinewidth": 1.0, "capsize": 2.0},
        )

    tick_labels = list(bin_labels)
    if bin_count_stats:
        tick_labels = []
        for lab in bin_labels:
            stats = bin_count_stats.get(lab, None)
            if stats is None:
                tick_labels.append(f"{lab}\nN_avg=NA\n[N_avg-std,N_avg+std]=NA")
                continue
            mean_count, std_count = float(stats[0]), float(stats[1])
            tick_labels.append(f"{lab}\nN_avg={mean_count:.1f}\n[{mean_count - std_count:.1f},{mean_count + std_count:.1f}]")

    ax.set_xticks(x)
    ax.set_xticklabels(tick_labels, rotation=35, ha="right")
    ax.set_ylabel(y_label)
    ax.set_xlabel("GT rain interval (mm/h)\nPer-bin patch-pixel stats: N_avg = average #pixels per patch in bin; [N_avg-std, N_avg+std] = mean ± std interval.")
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)
    ax.legend(loc="best", fontsize=8)
    if footnote:
        fig.text(0.01, 0.01, footnote, ha="left", va="bottom", fontsize=8)
        fig.tight_layout(rect=[0, 0.04, 1, 1])
    else:
        fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def render_largest_patch_distance_bin_maps(
    payload: Dict[str, Any],
    *,
    out_dir: Path,
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore
    from matplotlib.colors import ListedColormap  # type: ignore

    if not payload:
        return

    patch_key = str(payload["patch_key"])
    H = int(payload["H"])
    W = int(payload["W"])
    pix = float(payload["pixel_size_m"])
    area_km2 = float(payload["area_km2"])
    bins = parse_bins([float(v) for v in payload.get("bin_edges_m", [])])
    labels = [b[2] for b in bins]
    n_bins = len(labels)
    cmap = ListedColormap(plt.cm.plasma(np.linspace(0.08, 0.95, max(1, n_bins))))
    cmap.set_bad(color="#d9d9d9")

    links = payload.get("links", []) or []
    x0 = np.asarray([float(L["x0_m"]) for L in links], dtype=np.float64) if links else np.zeros(0, dtype=np.float64)
    y0 = np.asarray([float(L["y0_m"]) for L in links], dtype=np.float64) if links else np.zeros(0, dtype=np.float64)
    x1 = np.asarray([float(L["x1_m"]) for L in links], dtype=np.float64) if links else np.zeros(0, dtype=np.float64)
    y1 = np.asarray([float(L["y1_m"]) for L in links], dtype=np.float64) if links else np.zeros(0, dtype=np.float64)

    out_dir.mkdir(parents=True, exist_ok=True)
    edges = np.asarray([float(v) for v in payload.get("bin_edges_m", [])], dtype=np.float64)
    if edges.size > 0:
        edges = np.unique(edges[np.isfinite(edges)])

    for k in [int(v) for v in payload.get("k_targets", [2, 3])]:
        d_map = np.asarray(payload.get("dk_maps", {}).get(str(k), []), dtype=np.float64).reshape(H, W)
        finite = np.isfinite(d_map)
        bin_idx = np.zeros_like(d_map, dtype=np.int32) if edges.size == 0 else np.digitize(d_map, edges, right=True).astype(np.int32)
        bin_plot = np.ma.masked_where(~finite, bin_idx)

        fig, ax = plt.subplots(figsize=(9.0, 7.2), dpi=dpi)
        im = ax.imshow(
            bin_plot,
            cmap=cmap,
            vmin=-0.5,
            vmax=max(0, n_bins - 1) + 0.5,
            origin="upper",
            extent=(0.0, float(W) * pix, float(H) * pix, 0.0),
            interpolation="nearest",
            aspect="equal",
        )
        if x0.size > 0:
            for i in range(x0.size):
                ax.plot([x0[i], x1[i]], [y0[i], y1[i]], color="black", linewidth=0.55, alpha=0.55)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_ticks(np.arange(n_bins))
        cbar.set_ticklabels(labels)
        cbar.ax.set_ylabel(f"d{k} distance bin (m)")
        ax.set_title(
            f"Largest patch distance bins (k={k}) with links\n"
            f"{patch_key} | size={(float(W) * pix) / 1000.0:.1f}x{(float(H) * pix) / 1000.0:.1f} km | area={area_km2:.1f} km^2 | links={x0.size}"
        )
        ax.set_xlabel("x_local (m)")
        ax.set_ylabel("y_local (m)")
        ax.grid(False)
        out_png = out_dir / f"largest_patch_distance_bins_k{k}.png"
        fig.tight_layout()
        fig.savefig(out_png, dpi=dpi)
        plt.close(fig)


def render_report_from_cache(
    cache: Dict[str, Any],
    *,
    output_dir: Optional[Path] = None,
    render_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Path]:
    render_config = render_config or {}
    out_dir = output_dir or Path(str(render_value(render_config, "output.out_dir", cache["output"]["out_dir"])))
    images_subdir = str(render_value(render_config, "output.images_subdir", cache["output"]["images_subdir"]))
    excel_name = str(render_value(render_config, "output.excel_filename", cache["output"]["excel_filename"]))
    img_dir = out_dir / images_subdir
    excel_path = out_dir / excel_name

    ordered_sheets = cache.get("ordered_sheets", {})
    if not isinstance(ordered_sheets, dict):
        raise ValueError("Cache missing ordered_sheets.")
    ordered_sheets = reorder_report_sheets(ordered_sheets)

    objective_sheet_comments: Dict[str, str] = {}
    obj_rows = ordered_sheets.get("Objective_J", [])
    if obj_rows:
        header_comments = objective_header_comments_map()
        for col_name in obj_rows[0].keys():
            if col_name in header_comments:
                objective_sheet_comments[col_name] = header_comments[col_name]

    if render_bool(render_config, "excel.enabled", True):
        write_workbook(excel_path, ordered_sheets, header_comments={"Objective_J": objective_sheet_comments})
        print(f"Wrote Excel: {excel_path}")

    dpi = int(render_value(render_config, "style.dpi", cache["render"]["dpi"]))
    bin_spacing = float(render_value(render_config, "style.bin_spacing", cache["render"]["bin_spacing"]))
    y_max_raw = render_value(render_config, "style.y_max", cache["render"].get("y_max", None))
    y_max = None if y_max_raw is None else float(y_max_raw)
    prune_bins_enabled = bool(render_value(render_config, "style.prune_bins_enabled", cache["render"]["prune_bins_enabled"]))
    prune_bins_zero_frac = float(render_value(render_config, "style.prune_bins_zero_frac", cache["render"]["prune_bins_zero_frac"]))
    rae_bins = int(render_value(render_config, "style.rae_bins", cache["render"]["rae_bins"]))

    labels = cache["labels"]
    k_values = [int(v) for v in labels["k_values"]]
    dist_labels = [str(v) for v in labels["dist_labels"]]
    jatten_k_values = [int(v) for v in labels["jatten_k_values"]]
    jatten_dist_labels = [str(v) for v in labels["jatten_dist_labels"]]

    solver_order = [str(v) for v in cache["solvers"]["order"]]

    largest_patch_payload = cache.get("largest_patch_plot_payload", None)
    if largest_patch_payload and render_bool(render_config, "plots.largest_patch_distance_bins", True):
        render_largest_patch_distance_bin_maps(
            largest_patch_payload,
            out_dir=img_dir / "largest_patch_distance_bins",
            dpi=dpi,
        )

    if render_bool(render_config, "plots.j_behavior", True):
        for plot_payload in cache.get("j_behavior_plots", []) or []:
            plot_j_behavior(
                img_dir / "j_behavior" / safe_path_token(str(plot_payload["solver_name"])) / f"{safe_path_token(str(plot_payload['patch_key']))}.png",
                title=f"J behavior: {plot_payload['solver_label']} | {plot_payload['patch_key']}",
                iterations=plot_payload.get("iterations", []) or [],
                dpi=dpi,
            )

    if render_bool(render_config, "plots.patch_error_maps", True):
        for patch_plot_job in cache.get("patch_plot_jobs", []) or []:
            render_patch_error_maps_from_job(patch_plot_job, img_dir=img_dir, render_cfg=cache["render"])

    if render_bool(render_config, "plots.rae_histograms", True):
        for payload in cache.get("rae_hist_plots", []) or []:
            plot_rae_histograms(
                img_dir / str(payload["out_relpath"]),
                title=str(payload["title"]),
                dist_labels=[str(v) for v in payload["dist_labels"]],
                data_by_bin={str(k): list(v) for k, v in payload["data_by_bin"].items()},
                bins=rae_bins,
                dpi=dpi,
            )

    fpfn_rows = ordered_sheets.get("FPFN_ByThreshold", [])
    if fpfn_rows and render_bool(render_config, "plots.fp_fn_vs_threshold", True):
        plot_fp_fn_vs_threshold(
            img_dir / "fp_fn_vs_threshold.png",
            title="Wet-class FP/FN rates vs threshold",
            rows=fpfn_rows,
            dpi=dpi,
        )

    plot_data = cache["plot_data"]
    medians_rainy = plot_data["medians_rainy"]
    medians_nonrainy = plot_data["medians_nonrainy"]
    p90s_rainy = plot_data["p90s_rainy"]
    p90s_nonrainy = plot_data["p90s_nonrainy"]
    jatten_medians = plot_data["jatten_medians"]
    bin_counts = plot_data["bin_counts"]
    jatten_link_bin_counts = plot_data["jatten_link_bin_counts"]

    enabled_k_values = [int(v) for v in render_value(render_config, "filters.k_values", k_values)]
    enabled_jatten_k_values = [int(v) for v in render_value(render_config, "filters.jatten_k_values", jatten_k_values)]
    method_order = [label for label in solver_order if label in medians_rainy.get(str(k_values[0]), {})]
    if method_order:
        for k in [v for v in k_values if v in enabled_k_values]:
            kstr = str(k)
            labels_r = list(dist_labels)
            labels_n = list(dist_labels)
            if prune_bins_enabled:
                labels_r = filter_bins_by_zero_fraction(dist_labels, {str(kb): list(v) for kb, v in bin_counts[kstr]["rainy"].items()}, zero_frac_threshold=prune_bins_zero_frac)
                labels_n = filter_bins_by_zero_fraction(dist_labels, {str(kb): list(v) for kb, v in bin_counts[kstr]["nonrainy"].items()}, zero_frac_threshold=prune_bins_zero_frac)
            tick_labels_r = build_bin_tick_labels(labels_r, {str(kb): list(v) for kb, v in bin_counts[kstr]["rainy"].items()})
            tick_labels_n = build_bin_tick_labels(labels_n, {str(kb): list(v) for kb, v in bin_counts[kstr]["nonrainy"].items()})

            if len(k_values) == 1 and k == 3:
                rainy_name = "distance_iqr_medians_rainy_multi.png"
                nonrainy_name = "distance_iqr_medians_nonrainy_multi.png"
                rainy_title = "Rainy pixels: per-patch median |(GT-PRED)/GT| by distance bin (box-and-whisker)"
                nonrainy_title = "Non-rainy pixels: per-patch median |GT-PRED| by distance bin (box-and-whisker)"
                rainy_p90_name = "distance_iqr_p90s_rainy_multi.png"
                nonrainy_p90_name = "distance_iqr_p90s_nonrainy_multi.png"
                rainy_p90_title = "Rainy pixels: per-patch p90 |(GT-PRED)/GT| by distance bin (box-and-whisker)"
                nonrainy_p90_title = "Non-rainy pixels: per-patch p90 |GT-PRED| by distance bin (box-and-whisker)"
            else:
                rainy_name = f"distance_iqr_medians_rainy_multi_k{k}.png"
                nonrainy_name = f"distance_iqr_medians_nonrainy_multi_k{k}.png"
                rainy_title = f"Rainy pixels: per-patch median |(GT-PRED)/GT| by distance bin (box-and-whisker, k={k})"
                nonrainy_title = f"Non-rainy pixels: per-patch median |GT-PRED| by distance bin (box-and-whisker, k={k})"
                rainy_p90_name = f"distance_iqr_p90s_rainy_multi_k{k}.png"
                nonrainy_p90_name = f"distance_iqr_p90s_nonrainy_multi_k{k}.png"
                rainy_p90_title = f"Rainy pixels: per-patch p90 |(GT-PRED)/GT| by distance bin (box-and-whisker, k={k})"
                nonrainy_p90_title = f"Non-rainy pixels: per-patch p90 |GT-PRED| by distance bin (box-and-whisker, k={k})"

            if render_bool(render_config, "plots.distance_profiles", True):
                plot_box_whisker(img_dir / rainy_name, rainy_title, medians_rainy[kstr], labels_r, method_order, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r)
                plot_box_whisker(img_dir / nonrainy_name, nonrainy_title, medians_nonrainy[kstr], labels_n, method_order, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n)
            if render_bool(render_config, "plots.p90_profiles", True):
                plot_box_whisker(img_dir / rainy_p90_name, rainy_p90_title, p90s_rainy[kstr], labels_r, method_order, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r, y_label="Per-patch p90 error")
                plot_box_whisker(img_dir / nonrainy_p90_name, nonrainy_p90_title, p90s_nonrainy[kstr], labels_n, method_order, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n, y_label="Per-patch p90 error")

            if "IDW" in medians_rainy[kstr] and render_bool(render_config, "plots.distance_profiles_relative", True):
                plot_box_whisker(
                    img_dir / rainy_name.replace(".png", "_rel.png"),
                    f"{rainy_title} (relative to IDW medians)",
                    compute_relative_distribution_profile(medians_rainy[kstr], baseline_label="IDW", dist_labels=dist_labels),
                    labels_r,
                    method_order,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_r,
                )
                plot_box_whisker(
                    img_dir / nonrainy_name.replace(".png", "_rel.png"),
                    f"{nonrainy_title} (relative to IDW medians)",
                    compute_relative_distribution_profile(medians_nonrainy[kstr], baseline_label="IDW", dist_labels=dist_labels),
                    labels_n,
                    method_order,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_n,
                )

        for k in [v for v in jatten_k_values if v in enabled_jatten_k_values]:
            kstr = str(k)
            labels_jatten = list(jatten_dist_labels)
            if prune_bins_enabled:
                labels_jatten = filter_bins_by_zero_fraction(jatten_dist_labels, {str(kb): list(v) for kb, v in jatten_link_bin_counts[kstr].items()}, zero_frac_threshold=prune_bins_zero_frac)
            tick_labels_jatten = build_bin_tick_labels(labels_jatten, {str(kb): list(v) for kb, v in jatten_link_bin_counts[kstr].items()}, count_label="links")
            jatten_img_dir = img_dir / "jatten_iqr_plots"
            if len(jatten_k_values) == 1 and k == 3:
                jatten_name = "distance_iqr_medians_jatten_multi.png"
                jatten_title = "Link-distance-binned J_atten: per-patch medians (box-and-whisker)"
            else:
                jatten_name = f"distance_iqr_medians_jatten_multi_k{k}.png"
                jatten_title = f"Link-distance-binned J_atten: per-patch medians (box-and-whisker, k={k})"

            if render_bool(render_config, "plots.jatten_profiles", True):
                plot_box_whisker(
                    jatten_img_dir / jatten_name,
                    jatten_title,
                    jatten_medians[kstr],
                    labels_jatten,
                    method_order,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label="J_atten link contribution (per-patch median across patches)",
                    footnote="Per-link contribution: ((A_hat - A_obs)^2 / L_km) / #valid_links. Links are binned by segment-to-segment distance to the k-th closest other link.",
                )
                plot_box_whisker(
                    jatten_img_dir / jatten_name.replace(".png", "_no_p25_p75.png"),
                    f"{jatten_title} (medians only)",
                    jatten_medians[kstr],
                    labels_jatten,
                    method_order,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label="J_atten link contribution (per-patch median across patches)",
                    footnote="Per-link contribution: ((A_hat - A_obs)^2 / L_km) / #valid_links. Links are binned by segment-to-segment distance to the k-th closest other link.",
                    show_boxes=False,
                )

            for baseline_label, tag in (("IDW", "idw"), ("ILDW", "ildw")):
                if not render_bool(render_config, "plots.jatten_profiles_relative", True):
                    continue
                if baseline_label not in jatten_medians[kstr]:
                    continue
                rel_profile = compute_relative_distribution_profile(jatten_medians[kstr], baseline_label=baseline_label, dist_labels=jatten_dist_labels)
                rel_name = f"distance_iqr_medians_jatten_multi_rel_{tag}.png" if len(jatten_k_values) == 1 and k == 3 else f"distance_iqr_medians_jatten_multi_k{k}_rel_{tag}.png"
                plot_box_whisker(
                    jatten_img_dir / rel_name,
                    f"Link-distance-binned J_atten: per-patch medians (relative to {baseline_label} median)",
                    rel_profile,
                    labels_jatten,
                    method_order,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label=f"J_atten link-contribution ratio (per-patch median; baseline={baseline_label} p50)",
                    footnote=f"For each distance bin, per-patch values are divided by {baseline_label}'s p50 in that bin.",
                )
                plot_box_whisker(
                    jatten_img_dir / rel_name.replace(".png", "_no_p25_p75.png"),
                    f"Link-distance-binned J_atten: per-patch medians (relative to {baseline_label} median, medians only)",
                    rel_profile,
                    labels_jatten,
                    method_order,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label=f"J_atten link-contribution ratio (per-patch median; baseline={baseline_label} p50)",
                    footnote=f"For each distance bin, medians are divided by {baseline_label}'s p50 in that bin.",
                    show_boxes=False,
                )

    link_ratio_entries = cache.get("link_ratio_entries", []) or []
    if link_ratio_entries and render_bool(render_config, "plots.link_ratio_summary", True):
        entries = [(str(r["solver"]), str(r["label"]), [float(v) for v in r.get("values", [])]) for r in link_ratio_entries]
        plot_ratio_box_whisker(img_dir / "link_ratio_summary.png", title="Link-metric ratios vs IDW (box-and-whisker across patches)", entries=entries, dpi=dpi)

    gtbin = cache.get("gtbin_plot_data", None)
    if gtbin and render_bool(render_config, "plots.gt_binned_patchavg", True):
        labels_to_plot = [str(v) for v in gtbin.get("labels_to_plot", [])]
        solver_plot_order = [label for label in solver_order if label in gtbin.get("rel_mean", {})]
        if labels_to_plot and solver_plot_order:
            bin_count_stats = {str(k): (float(v[0]), float(v[1])) for k, v in gtbin.get("bin_count_stats", {}).items()}
            plot_gt_binned_patchavg_error(
                img_dir / "gt_binned_patchavg_relative_abs_error_all_pixels.png",
                title="GT-binned all-pixels error (avg of patch-averaged error ± std)",
                bin_labels=labels_to_plot,
                bin_count_stats=bin_count_stats,
                solver_order=solver_plot_order,
                mean_by_solver={str(k): [float(x) for x in v] for k, v in gtbin.get("rel_mean", {}).items()},
                std_by_solver={str(k): [float(x) for x in v] for k, v in gtbin.get("rel_std", {}).items()},
                y_label="Avg patch error (|GT-PRED|/GT; [0,1) uses |GT-PRED|)",
                footnote="Note: For GT in [0,1) mm/h, the metric uses absolute error |GT-PRED| (not RAE).",
                dpi=dpi,
            )
            plot_gt_binned_patchavg_error(
                img_dir / "gt_binned_patchavg_absolute_error_all_pixels.png",
                title="GT-binned all-pixels absolute error (avg of patch means ± std)",
                bin_labels=labels_to_plot,
                bin_count_stats=bin_count_stats,
                solver_order=solver_plot_order,
                mean_by_solver={str(k): [float(x) for x in v] for k, v in gtbin.get("abs_mean", {}).items()},
                std_by_solver={str(k): [float(x) for x in v] for k, v in gtbin.get("abs_std", {}).items()},
                y_label="Avg patch absolute error |GT-PRED| (mm/h)",
                dpi=dpi,
            )

    print(f"Wrote plots under: {img_dir}")
    return {"excel_path": excel_path, "images_dir": img_dir}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--render-config", default=None)
    args = ap.parse_args()

    cache_path = Path(args.cache).resolve()
    cache = read_report_cache(cache_path)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    render_cfg_path = resolve_render_config_path(cache, args.render_config)
    render_cfg = load_config_file(render_cfg_path) if render_cfg_path is not None else {}
    render_report_from_cache(cache, output_dir=output_dir, render_config=render_cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
