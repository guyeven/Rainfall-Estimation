#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import textwrap
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from batch_analyze_multi import (
    load_config_file,
    load_est_payload,
    load_npz_first_key,
    mask_to_nan,
    objective_header_comments_map,
    parse_bins,
    read_report_cache,
    reorder_report_sheets,
    resolve_path,
    safe_path_token,
    save_png_2x2,
    write_workbook,
)

_PATCH_CATALOG_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_PATCH_LOCATION_OVERRIDES: Dict[str, str] = {
    "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301280900_patch000": "Black Sea coast, Romania",
    "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301310900_patch000": "Northern Norway",
    "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301282100_patch000": "Barents Sea area",
    "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301310200_patch000": "Edinburgh area",
    "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301311600_patch000": "Western Norway",
}

_COMBINED_PATCH_SOLVER_ORDER: Dict[str, int] = {
    "IDW": 0,
    "ILDW": 1,
    "OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG": 2,
    "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL": 3,
    "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL": 4,
    "OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL": 5,
}

_DEFAULT_SOLVER_DISPLAY_NAMES: Dict[str, str] = {
    "IDW": "IDW",
    "ILDW": "ILDW",
    "OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG": "Solver(ILDW)",
    "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL": "Convex Solver",
    "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL": "Homotopy Solver",
    "OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL": "Solver(GT)",
}

_COMBINED_FEW_SOLVERS = {
    "IDW",
    "OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL",
    "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL",
}

_COMBINED_FEW_SOLVER_ORDER: Dict[str, int] = {
    "IDW": 0,
    "OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL": 1,
    "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL": 2,
}


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


def ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def pretty_patch_label(patch_key: str) -> str:
    key = str(patch_key)
    parts = key.split("_")
    date_token: Optional[str] = None
    for part in parts:
        if len(part) == 12 and part.isdigit():
            date_token = part
    if date_token is None:
        return key
    dt = datetime.strptime(date_token, "%Y%m%d%H%M")
    date_str = dt.strftime("%m/%d/%Y")
    time_str = dt.strftime("%H:%M")
    location = _PATCH_LOCATION_OVERRIDES.get(key)
    if location:
        return f"{location} | {date_str} {time_str}"
    return f"{date_str} {time_str}"


def reorder_row_columns(
    rows: List[Dict[str, Any]],
    preferred_order: Sequence[str],
) -> List[Dict[str, Any]]:
    if not rows:
        return rows
    out: List[Dict[str, Any]] = []
    for row in rows:
        reordered: Dict[str, Any] = {}
        for key in preferred_order:
            if key in row:
                reordered[key] = row[key]
        for key, value in row.items():
            if key not in reordered:
                reordered[key] = value
        out.append(reordered)
    return out


def solver_display_map(cache: Dict[str, Any], render_config: Dict[str, Any]) -> Dict[str, str]:
    base = {
        str(v): _DEFAULT_SOLVER_DISPLAY_NAMES.get(str(v), str(v))
        for v in cache.get("solvers", {}).get("order", [])
    }
    overrides = render_value(render_config, "labels.solver_overrides", {})
    if not isinstance(overrides, dict):
        return base
    for key, value in overrides.items():
        base[str(key)] = str(value)
    return base


def apply_solver_display(label: str, display_map: Dict[str, str]) -> str:
    return display_map.get(str(label), str(label))


def combined_patch_solver_sort_key(job: Dict[str, Any], display_map: Dict[str, str]) -> Tuple[int, str]:
    raw_label = str(job["solver_label"])
    return _COMBINED_PATCH_SOLVER_ORDER.get(raw_label, 100), apply_solver_display(raw_label, display_map)


def ordered_solver_labels(cache: Dict[str, Any]) -> List[str]:
    labels = [str(v) for v in cache.get("solvers", {}).get("order", [])]
    return sorted(labels, key=lambda label: (_COMBINED_PATCH_SOLVER_ORDER.get(label, 100), label))


def combined_patch_solver_sort_key_with_order(
    job: Dict[str, Any],
    display_map: Dict[str, str],
    solver_order: Dict[str, int],
) -> Tuple[int, str]:
    raw_label = str(job["solver_label"])
    return solver_order.get(raw_label, 100), apply_solver_display(raw_label, display_map)


def replace_solver_labels_in_text(text: str, display_map: Dict[str, str]) -> str:
    out = str(text)
    for raw, shown in sorted(display_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        out = out.replace(str(raw), str(shown))
    return out


def remap_solver_dict(data: Dict[str, Any], display_map: Dict[str, str]) -> Dict[str, Any]:
    return {apply_solver_display(str(k), display_map): v for k, v in data.items()}


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


def load_patch_catalog() -> Dict[str, Dict[str, Any]]:
    global _PATCH_CATALOG_CACHE
    if _PATCH_CATALOG_CACHE is not None:
        return _PATCH_CATALOG_CACHE
    catalog_path = Path(__file__).resolve().parent / "JSON-files" / "benchmark-500-files-758-patches.local.jsonl"
    catalog: Dict[str, Dict[str, Any]] = {}
    if catalog_path.exists():
        with catalog_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                patch_id = str(row.get("id") or row.get("patch_id") or "").strip()
                if patch_id:
                    catalog[patch_id] = row
    _PATCH_CATALOG_CACHE = catalog
    return catalog


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
    broken_y: bool = False,
    log_scale: bool = False,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore
    from matplotlib.ticker import MultipleLocator  # type: ignore
    import textwrap

    n_bins = len(dist_labels)
    n_methods = len(method_order)
    x = np.arange(n_bins) * float(bin_spacing)
    width = 0.8 / max(1, n_methods)
    offsets = (np.arange(n_methods) - (n_methods - 1) / 2.0) * width

    fig_w = max(8.8, n_bins * 1.35 * float(bin_spacing))
    fig_h = 7.0 if broken_y else (6.4 if footnote else 5.5)
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors = {m: color_cycle[i % max(1, len(color_cycle))] for i, m in enumerate(method_order)}

    finite_vals = np.concatenate(
        [
            np.asarray(per_patch_values.get(method, {}).get(lab, []), dtype=np.float64)
            for method in method_order
            for lab in dist_labels
        ]
        or [np.array([], dtype=np.float64)]
    )
    finite_vals = finite_vals[np.isfinite(finite_vals)]
    median_vals = np.asarray(
        [
            float(np.percentile(clean_vals, 50))
            for method in method_order
            for lab in dist_labels
            for raw_vals in [np.asarray(per_patch_values.get(method, {}).get(lab, []), dtype=np.float64)]
            for clean_vals in [raw_vals[np.isfinite(raw_vals)]]
            if clean_vals.size > 0
        ],
        dtype=np.float64,
    )
    positive_vals = finite_vals[finite_vals > 0]
    log_floor = float(np.min(positive_vals)) * 0.5 if positive_vals.size else 1e-6
    if broken_y and finite_vals.size:
        low_end = float(np.percentile(finite_vals, 90))
        if median_vals.size:
            low_end = max(low_end, float(np.max(median_vals)) * 1.08)
        high_start = float(np.percentile(finite_vals, 98))
        y_top = float(np.max(finite_vals))
        if high_start <= low_end * 1.15 or y_top <= high_start:
            broken_y = False
    if log_scale:
        broken_y = False
    if broken_y:
        fig, (ax_top, ax) = plt.subplots(
            2,
            1,
            sharex=True,
            figsize=(fig_w, fig_h),
            dpi=dpi,
            gridspec_kw={"height_ratios": [1.0, 2.2], "hspace": 0.05},
        )
        axes = [ax_top, ax]
    else:
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        axes = [ax]

    def draw_contents(target_ax: Any) -> None:
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
                if log_scale:
                    vals = np.maximum(vals, log_floor)
                medians.append(float(np.percentile(vals, 50)))
                if show_boxes:
                    target_ax.boxplot(
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
            target_ax.plot(
                x + off,
                medians,
                marker="o",
                linestyle="None",
                color=color,
                markersize=6.2,
                zorder=8,
                label=method,
            )

    for target_ax in axes:
        draw_contents(target_ax)

    ax.set_xticks(x)
    tick_labels = tick_labels or dist_labels
    has_multiline = any("\n" in str(lab) for lab in tick_labels)
    if has_multiline:
        interval_only = [str(lab).split("\n", 1)[0] for lab in tick_labels]
        ax.set_xticklabels(interval_only, rotation=0, ha="center", fontsize=7.2)
        ax.set_xlabel(x_label or "Distance bin (m)")
    else:
        ax.set_xticklabels(tick_labels, rotation=0)
    ax.set_ylabel(y_label or "Per-patch median error", labelpad=8, fontsize=9)
    wrapped_title = "\n".join(textwrap.wrap(str(title), width=95, break_long_words=False, break_on_hyphens=False))
    if broken_y:
        ax_top.set_title(wrapped_title, fontsize=11, pad=4)
        ax_top.legend(loc="best")
    else:
        ax.set_title(wrapped_title, fontsize=11, pad=4)
        ax.legend(loc="best")
    for target_ax in axes:
        target_ax.grid(True, axis="y", linestyle=":", linewidth=0.5, alpha=0.45)
        if not log_scale:
            target_ax.yaxis.set_minor_locator(MultipleLocator(0.1))

    if broken_y:
        low_ylim_top = low_end * 1.05
        high_ylim_bottom = high_start * 0.98
        high_ylim_top = y_top * 1.03
        ax.set_ylim(0, low_ylim_top)
        ax_top.set_ylim(high_ylim_bottom, high_ylim_top)
        ax_top.spines["bottom"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax_top.tick_params(labeltop=False, bottom=False)
        d = 0.015
        kwargs = dict(transform=ax_top.transAxes, color="k", clip_on=False, linewidth=0.8)
        ax_top.plot((-d, +d), (-d, +d), **kwargs)
        ax_top.plot((1 - d, 1 + d), (-d, +d), **kwargs)
        kwargs.update(transform=ax.transAxes)
        ax.plot((-d, +d), (1 - d, 1 + d), **kwargs)
        ax.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)
    elif y_max is not None:
        ax.set_ylim(0, y_max)
    else:
        ax.set_ylim(bottom=0)

    if log_scale:
        for target_ax in axes:
            target_ax.set_yscale("log")
        if finite_vals.size:
            y_top = float(np.max(np.maximum(finite_vals, log_floor)))
            ax.set_ylim(log_floor, y_top * 1.05)

    if footnote:
        footnote_y = 0.08
        bottom = 0.32 if has_multiline else 0.18
        fig.text(0.5, footnote_y, str(footnote), ha="center", va="bottom", fontsize=8, wrap=True)
        fig.tight_layout(rect=(0.04, bottom, 0.98, 0.94))
    else:
        bottom = 0.24 if has_multiline else 0.1
        fig.tight_layout(rect=(0.04, bottom, 0.98, 0.94))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def plot_patch_map_metrics_boxplots(
    out_png: Path,
    *,
    title: str,
    data_by_solver: Dict[str, Dict[str, List[float]]],
    solver_order: List[str],
    corr_ylim: Optional[Tuple[float, float]] = (-1.0, 1.0),
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    metrics = [
        ("rmse_mmph", "RMSE"),
        ("bias_mmph", "Bias"),
        ("pearson_corr", "Correlation"),
    ]
    display_labels = [
        "Nonlinear\noptimizer" if solver_label == "Nonlinear optimizer" else solver_label
        for solver_label in solver_order
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.8), dpi=dpi)
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors = [color_cycle[i % max(1, len(color_cycle))] for i in range(len(solver_order))]

    for ax, (metric_key, metric_title) in zip(axes, metrics):
        values_per_solver: List[np.ndarray] = []
        positions: List[int] = []
        colors_used: List[str] = []
        for idx, solver_label in enumerate(solver_order, start=1):
            vals = np.asarray(data_by_solver.get(solver_label, {}).get(metric_key, []), dtype=np.float64)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                continue
            values_per_solver.append(vals)
            positions.append(idx)
            colors_used.append(colors[idx - 1])

        if values_per_solver:
            bp = ax.boxplot(
                values_per_solver,
                positions=positions,
                widths=0.58,
                patch_artist=True,
                showfliers=False,
                whis=(0, 100),
            )
            for patch, color in zip(bp["boxes"], colors_used):
                patch.set_facecolor(color)
                patch.set_alpha(0.45)
            for median in bp["medians"]:
                median.set_color("black")
                median.set_linewidth(1.4)
            for whisker in bp["whiskers"]:
                whisker.set_color("#444444")
                whisker.set_linewidth(1.0)
            for cap in bp["caps"]:
                cap.set_color("#444444")
                cap.set_linewidth(1.0)
        ax.set_title(metric_title)
        ax.set_xticks(positions if positions else list(range(1, len(solver_order) + 1)))
        ax.set_xticklabels(display_labels[: len(positions)] if positions else display_labels, rotation=0, ha="center")
        ax.grid(axis="y", alpha=0.28, linestyle="-", linewidth=0.7)
        if metric_key == "pearson_corr" and corr_ylim is not None:
            ax.set_ylim(*corr_ylim)

    fig.suptitle(title)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def merge_distance_tail_bin(
    dist_labels: List[str],
    counts_by_label: Dict[str, List[float]],
    *value_maps: Dict[str, Dict[str, List[float]]],
) -> Tuple[List[str], Dict[str, List[float]], List[Dict[str, Dict[str, List[float]]]]]:
    tail_a = "(6000,9000]"
    tail_b = ">9000"
    if tail_a not in dist_labels or tail_b not in dist_labels:
        return dist_labels, counts_by_label, list(value_maps)

    merged_label = r"$(6000,\infty)$"
    merged_labels = [lab for lab in dist_labels if lab not in {tail_a, tail_b}] + [merged_label]

    merged_counts = {lab: list(counts_by_label.get(lab, [])) for lab in merged_labels if lab != merged_label}
    merged_counts[merged_label] = list(counts_by_label.get(tail_a, [])) + list(counts_by_label.get(tail_b, []))

    merged_value_maps: List[Dict[str, Dict[str, List[float]]]] = []
    for value_map in value_maps:
        merged_map: Dict[str, Dict[str, List[float]]] = {}
        for method, by_bin in value_map.items():
            merged_map[method] = {lab: list(by_bin.get(lab, [])) for lab in merged_labels if lab != merged_label}
            merged_map[method][merged_label] = list(by_bin.get(tail_a, [])) + list(by_bin.get(tail_b, []))
        merged_value_maps.append(merged_map)
    return merged_labels, merged_counts, merged_value_maps


def plot_iqr_summary(
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
    show_iqr: bool = True,
    broken_y: bool = False,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore
    import textwrap

    n_bins = len(dist_labels)
    n_methods = len(method_order)
    x = np.arange(n_bins) * float(bin_spacing)
    width = 0.8 / max(1, n_methods)
    offsets = (np.arange(n_methods) - (n_methods - 1) / 2.0) * width

    fig_w = max(8.8, n_bins * 1.35 * float(bin_spacing))
    fig_h = 7.2 if broken_y else (6.6 if footnote else 5.9)
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    colors = {m: color_cycle[i % max(1, len(color_cycle))] for i, m in enumerate(method_order)}
    finite_vals = np.concatenate(
        [
            np.asarray(per_patch_values.get(method, {}).get(lab, []), dtype=np.float64)
            for method in method_order
            for lab in dist_labels
        ]
        or [np.array([], dtype=np.float64)]
    )
    finite_vals = finite_vals[np.isfinite(finite_vals)]
    if broken_y and finite_vals.size:
        low_end = float(np.percentile(finite_vals, 90))
        high_start = float(np.percentile(finite_vals, 98))
        y_top = float(np.max(finite_vals))
        if high_start <= low_end * 1.15 or y_top <= high_start:
            broken_y = False
    if broken_y:
        fig, (ax_top, ax) = plt.subplots(
            2,
            1,
            sharex=True,
            figsize=(fig_w, fig_h),
            dpi=dpi,
            gridspec_kw={"height_ratios": [1.0, 2.2], "hspace": 0.05},
        )
        axes = [ax_top, ax]
    else:
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        axes = [ax]

    def draw_contents(target_ax: Any) -> None:
        for mi, method in enumerate(method_order):
            off = offsets[mi]
            color = colors.get(method, None)
            for bi, lab in enumerate(dist_labels):
                vals = np.asarray(per_patch_values.get(method, {}).get(lab, []), dtype=np.float64)
                vals = vals[np.isfinite(vals)]
                if vals.size == 0:
                    continue
                p25 = float(np.percentile(vals, 25))
                p50 = float(np.percentile(vals, 50))
                p75 = float(np.percentile(vals, 75))
                xpos = x[bi] + off
                if show_iqr:
                    target_ax.vlines(xpos, p25, p75, color=color, linewidth=1.8, alpha=0.95)
                    target_ax.hlines([p25, p75], xpos - width * 0.18, xpos + width * 0.18, color=color, linewidth=1.3, alpha=0.95)
                target_ax.plot(xpos, p50, marker="o", linestyle="None", color=color, markersize=4.8, label=method if bi == 0 else None)

    for target_ax in axes:
        draw_contents(target_ax)

    ax.set_xticks(x)
    tick_labels = tick_labels or dist_labels
    has_multiline = any("\n" in str(lab) for lab in tick_labels)
    x_label_text = x_label or "Distance bin (m)"
    if has_multiline:
        interval_only = [str(lab).split("\n", 1)[0] for lab in tick_labels]
        ax.set_xticklabels(interval_only, rotation=0, ha="center", fontsize=7.2)
        ax.set_xlabel(x_label_text)
    else:
        ax.set_xticklabels(tick_labels, rotation=0)
        if x_label_text:
            ax.set_xlabel(x_label_text)
    y_label_text = y_label or "Per-patch values\nDot: median, bar: IQR"
    y_label_text = "\n".join(textwrap.fill(line, width=28) for line in str(y_label_text).splitlines())
    ax.set_ylabel(y_label_text, labelpad=12, fontsize=9)
    wrapped_title = "\n".join(textwrap.wrap(str(title), width=88, break_long_words=False, break_on_hyphens=False))
    if broken_y:
        ax_top.set_title(wrapped_title, fontsize=11, pad=4)
        ax_top.legend(loc="best")
    else:
        ax.set_title(wrapped_title, fontsize=11, pad=4)
        ax.legend(loc="best")
    for target_ax in axes:
        target_ax.grid(True, axis="y", linestyle=":", linewidth=0.5, alpha=0.45)

    if broken_y:
        low_ylim_top = low_end * 1.05
        high_ylim_bottom = high_start * 0.98
        high_ylim_top = y_top * 1.03
        ax.set_ylim(0, low_ylim_top)
        ax_top.set_ylim(high_ylim_bottom, high_ylim_top)
        ax_top.spines["bottom"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax_top.tick_params(labeltop=False, bottom=False)
        d = 0.015
        kwargs = dict(transform=ax_top.transAxes, color="k", clip_on=False, linewidth=0.8)
        ax_top.plot((-d, +d), (-d, +d), **kwargs)
        ax_top.plot((1 - d, 1 + d), (-d, +d), **kwargs)
        kwargs.update(transform=ax.transAxes)
        ax.plot((-d, +d), (1 - d, 1 + d), **kwargs)
        ax.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)
    elif y_max is not None:
        ax.set_ylim(0, y_max)
    else:
        ax.set_ylim(bottom=0)

    if footnote:
        footnote_y = 0.06
        bottom = 0.31 if has_multiline else 0.2
        fig.text(0.5, footnote_y, str(footnote), ha="center", va="bottom", fontsize=8, wrap=True)
        fig.tight_layout(rect=(0.08, bottom, 0.98, 0.94))
    else:
        bottom = 0.24 if has_multiline else 0.1
        fig.tight_layout(rect=(0.08, bottom, 0.98, 0.94))
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

    patch_plot_dir = img_dir / safe_path_token(solver_label)
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


def render_combined_patch_error_map(
    patch_key: str,
    jobs: List[Dict[str, Any]],
    *,
    img_dir: Path,
    render_cfg: Dict[str, Any],
    display_map: Dict[str, str],
    output_subdir: str = "combined",
    solver_allowlist: Optional[set[str]] = None,
    solver_order: Optional[Dict[str, int]] = None,
    include_map_override: Optional[bool] = None,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore
    from matplotlib.gridspec import GridSpec  # type: ignore

    if solver_allowlist is not None:
        jobs = [job for job in jobs if str(job["solver_label"]) in solver_allowlist]
    if not jobs:
        return

    if solver_order is None:
        jobs_sorted = sorted(jobs, key=lambda j: combined_patch_solver_sort_key(j, display_map))
    else:
        jobs_sorted = sorted(jobs, key=lambda j: combined_patch_solver_sort_key_with_order(j, display_map, solver_order))
    gt = load_npz_first_key(Path(str(jobs_sorted[0]["gt_path"])), list(jobs_sorted[0]["gt_key_pref"])).astype(np.float64)
    thr = float(render_cfg["threshold_mmph"])
    plot_dpi = int(render_cfg["dpi"])
    cmap_gt = str(render_cfg["cmap_gt"])
    cmap_sol = str(render_cfg["cmap_sol"])
    cmap_rel = str(render_cfg["cmap_rel"])
    include_map = bool(render_cfg.get("include_map", False)) if include_map_override is None else include_map_override

    rainy = gt >= thr
    solver_payloads: List[Tuple[str, np.ndarray, np.ndarray]] = []
    finite_gt_sol = [gt[np.isfinite(gt)]]
    rel_arrays: List[np.ndarray] = []

    for job in jobs_sorted:
        pred = load_npz_first_key(Path(str(job["sol_path"])), list(job["sol_key_pref"])).astype(np.float64)
        if pred.shape != gt.shape:
            raise ValueError(f"Shape mismatch for combined patch plot {patch_key}: GT {gt.shape} vs SOL {pred.shape}")
        rel_full = np.full_like(gt, np.nan, dtype=np.float64)
        valid_rel = rainy & np.isfinite(gt) & np.isfinite(pred) & (gt != 0.0)
        rel_full[valid_rel] = (pred[valid_rel] - gt[valid_rel]) / gt[valid_rel]
        solver_payloads.append((apply_solver_display(str(job["solver_label"]), display_map), pred, rel_full))
        finite_gt_sol.append(pred[np.isfinite(pred)])
        rel_arrays.append(rel_full[np.isfinite(rel_full)])

    finite_gt_sol_arr = np.concatenate([arr for arr in finite_gt_sol if arr.size > 0]) if any(arr.size > 0 for arr in finite_gt_sol) else np.array([0.0])
    rmax = float(np.max(finite_gt_sol_arr)) if finite_gt_sol_arr.size else 1.0
    rmax = max(rmax, 1e-9)
    finite_rel = np.concatenate([arr for arr in rel_arrays if arr.size > 0]) if any(arr.size > 0 for arr in rel_arrays) else np.array([0.0])
    rel_max = float(np.max(np.abs(finite_rel))) if finite_rel.size else 1.0
    rel_max = max(rel_max, 1e-9)

    n_solver = len(solver_payloads)
    n_cols = n_solver + 1 + (1 if include_map else 0)
    width_ratios = ([1.45] if include_map else []) + [1.35] + [1.0] * n_solver
    fig = plt.figure(figsize=(4.8 * n_cols, 9.2), dpi=plot_dpi)
    gs = GridSpec(2, n_cols, width_ratios=width_ratios, hspace=0.22, wspace=0.28)

    next_col = 0
    if include_map:
        catalog = load_patch_catalog()
        patch_meta = catalog.get(str(patch_key))
        if patch_meta is None:
            raise RuntimeError(
                f"Patch metadata for {patch_key} not found in benchmark patch catalog; cannot render map panel."
            )
        try:
            import contextily as ctx  # type: ignore
            import geopandas as gpd  # type: ignore
            from shapely.geometry import box  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "patch_error_maps_include_map requires contextily, geopandas, and shapely in the rendering environment."
            ) from exc

        lon = float(patch_meta["center_lon"])
        lat = float(patch_meta["center_lat"])
        width_km = float(patch_meta["width_km"])
        height_km = float(patch_meta["height_km"])
        half_h_deg = (height_km / 2.0) / 111.32
        cos_lat = max(1e-6, math.cos(math.radians(lat)))
        half_w_deg = (width_km / 2.0) / (111.32 * cos_lat)
        patch_poly = box(lon - half_w_deg, lat - half_h_deg, lon + half_w_deg, lat + half_h_deg)
        gdf = gpd.GeoDataFrame({"patch_key": [patch_key]}, geometry=[patch_poly], crs="EPSG:4326").to_crs(epsg=3857)
        xmin, ymin, xmax, ymax = gdf.total_bounds
        xpad = 4.0 * (xmax - xmin)
        ypad = 4.0 * (ymax - ymin)

        ax_map = fig.add_subplot(gs[:, next_col])
        ax_map.set_xlim(xmin - xpad, xmax + xpad)
        ax_map.set_ylim(ymin - ypad, ymax + ypad)
        ctx.add_basemap(
            ax_map,
            source=ctx.providers.OpenStreetMap.Mapnik,
            attribution=False,
            zoom="auto",
            zorder=1,
        )
        gdf.boundary.plot(ax=ax_map, color="#c71f17", linewidth=1.8, alpha=0.9, zorder=3)
        ax_map.set_title("Map", fontsize=12)
        ax_map.set_xticks([])
        ax_map.set_yticks([])
        next_col += 1

    ax_gt = fig.add_subplot(gs[:, next_col])
    gt_im = ax_gt.imshow(gt, cmap=cmap_gt, vmin=0.0, vmax=rmax)
    ax_gt.set_title("Ground Truth", fontsize=12)
    ax_gt.set_xticks([])
    ax_gt.set_yticks([])
    fig.colorbar(gt_im, ax=ax_gt, fraction=0.046, pad=0.03)

    for idx, (solver_title, pred, rel_full) in enumerate(solver_payloads, start=next_col + 1):
        ax_top = fig.add_subplot(gs[0, idx])
        ax_bot = fig.add_subplot(gs[1, idx])

        pred_im = ax_top.imshow(pred, cmap=cmap_sol, vmin=0.0, vmax=rmax)
        wrapped_solver_title = "\n".join(textwrap.wrap(solver_title, width=28)) or solver_title
        ax_top.set_title(wrapped_solver_title, fontsize=10)
        ax_top.set_xticks([])
        ax_top.set_yticks([])
        fig.colorbar(pred_im, ax=ax_top, fraction=0.046, pad=0.03)

        rel_cmap = plt.get_cmap(cmap_rel).copy()
        rel_cmap.set_bad(color="#7a7a7a")
        rel_im = ax_bot.imshow(rel_full, cmap=rel_cmap, vmin=-rel_max, vmax=rel_max)
        ax_bot.contour(
            (~rainy).astype(float),
            levels=[0.5],
            colors="white",
            linewidths=0.8,
            linestyles="--",
        )
        ax_bot.set_title("(predicted - observed)/observed\nrainy pixels only; gray = non-rainy", fontsize=10)
        ax_bot.set_xticks([])
        ax_bot.set_yticks([])
        fig.colorbar(rel_im, ax=ax_bot, fraction=0.046, pad=0.03)

    fig.suptitle(
        f"{pretty_patch_label(patch_key)}\n"
        "Ground Truth, solver predictions, and signed relative error over rainy pixels",
        fontsize=14,
        y=0.99,
    )
    out_path = img_dir / output_subdir / f"{safe_path_token(str(patch_key))}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.01, 0.01, 0.99, 0.82))
    fig.savefig(out_path)
    plt.close(fig)


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


def plot_ratio_iqr_summary(
    out_png: Path,
    *,
    title: str,
    entries: List[Tuple[str, str, List[float]]],
    dpi: int = 150,
    footnote: Optional[str] = None,
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

    for i, (solver, _, vals) in enumerate(entries):
        color = colors.get(solver, None)
        arr = np.asarray(vals, dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            continue
        p25 = float(np.percentile(arr, 25))
        p50 = float(np.percentile(arr, 50))
        p75 = float(np.percentile(arr, 75))
        ax.vlines(x[i], p25, p75, color=color, linewidth=1.8, alpha=0.95)
        ax.hlines([p25, p75], x[i] - 0.12, x[i] + 0.12, color=color, linewidth=1.3, alpha=0.95)
        ax.plot(x[i], p50, marker="o", linestyle="None", color=color, markersize=4.8)

    ax.set_xticks(x)
    ax.set_xticklabels([lab for _, lab, _ in entries], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Across-patch ratio summary")
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)
    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[s], label=s) for s in solver_labels]
    ax.legend(handles=handles, loc="best")

    fig.text(
        0.5,
        0.01,
        footnote or (
            "Marker = median across patches; vertical segment spans p25 to p75 across patches. "
            "Ratios are computed relative to IDW per patch."
        ),
        ha="center",
        fontsize=8,
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
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


def plot_confusion_map(
    out_png: Path,
    *,
    title: str,
    solver_label: str,
    threshold_mmph: float,
    tp_mean: float,
    tp_sem: float,
    fp_mean: float,
    fp_sem: float,
    fn_mean: float,
    fn_sem: float,
    tn_mean: float,
    tn_sem: float,
    n_patches: int,
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    matrix = np.array([[tp_mean, fn_mean], [fp_mean, tn_mean]], dtype=np.float64)
    fig, ax = plt.subplots(figsize=(6.7, 5.8), dpi=dpi)
    im = ax.imshow(matrix, cmap="Blues", vmin=0.0, vmax=max(1e-9, float(np.max(matrix))))

    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["Wet", "Dry"])
    ax.set_yticklabels(["Wet", "Dry"])
    ax.xaxis.tick_top()
    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False)
    ax.set_xlabel("Prediction")
    ax.xaxis.set_label_position("top")
    ax.set_ylabel("Ground truth")
    ax.set_title(title, pad=22)

    cell_labels = [
        ("TP", tp_mean, tp_sem),
        ("FN", fn_mean, fn_sem),
        ("FP", fp_mean, fp_sem),
        ("TN", tn_mean, tn_sem),
    ]
    for idx, (label, mean_val, sem_val) in enumerate(cell_labels):
        i, j = divmod(idx, 2)
        txt = f"{label}\n{mean_val:.3f}\n± {sem_val:.3f}"
        ax.text(j, i, txt, ha="center", va="center", color="black", fontsize=11, fontweight="bold")

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks(np.arange(-0.5, 2, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 2, 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=2)
    ax.tick_params(which="minor", bottom=False, left=False)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.set_ylabel("Mean pixel fraction", rotation=90)

    fig.text(
        0.5,
        0.03,
        (
            f"Threshold = {threshold_mmph:.3g} mm/h. "
            f"Each cell shows mean pixel fraction across n={n_patches} patches, with ± SEM."
        ),
        ha="center",
        fontsize=8,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
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

    def series_from_rows(rows: Sequence[Dict[str, Any]], key: str) -> List[float]:
        out: List[float] = []
        for it in rows:
            v = it.get(key, None)
            try:
                out.append(float(v) if v is not None else float("nan"))
            except Exception:
                out.append(float("nan"))
        return out

    def weighted_or_raw_from_rows(rows: Sequence[Dict[str, Any]], weighted_key: str, raw_key: str) -> List[float]:
        vals = series_from_rows(rows, weighted_key)
        if not vals or all(math.isnan(v) for v in vals):
            return series_from_rows(rows, raw_key)
        return vals

    def finite_values(vals: Sequence[float]) -> np.ndarray:
        arr = np.asarray(vals, dtype=np.float64)
        return arr[np.isfinite(arr)]

    def build_series(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Tuple[str, List[float], float]], List[float]]:
        j_series: List[Tuple[str, List[float], float]] = [
            (r"$J_{\mathrm{weighted\ sum}}$", series_from_rows(rows, "J_weighted_sum"), 1.0),
            (r"$\alpha_{\mathrm{atten}} \cdot J_{\mathrm{atten}}$", weighted_or_raw_from_rows(rows, "weighted_J_atten", "J_atten"), 0.9),
            (r"$\alpha_{1d} \cdot J_{1d}$", weighted_or_raw_from_rows(rows, "weighted_J_1d", "J_1d"), 0.9),
            (r"$\alpha_{\mathrm{total}} \cdot J_{\mathrm{total}}$", weighted_or_raw_from_rows(rows, "weighted_J_total", "J_total"), 0.9),
            (r"$\alpha_{2d} \cdot J_{2d}$", weighted_or_raw_from_rows(rows, "weighted_J_2d", "J_2d"), 0.9),
        ]
        weighted_sum = j_series[0][1]
        if not weighted_sum or all(math.isnan(v) for v in weighted_sum):
            j_series[0] = (r"$J_{\mathrm{weighted\ sum}}$", series_from_rows(rows, "J_native_total"), 1.0)
        return j_series, j_series[0][1]

    def draw_series(ax: Any, xs_local: Sequence[int], j_series: Sequence[Tuple[str, List[float], float]], *, lower_only: bool = False, upper_only: bool = False, cutoff: Optional[float] = None, show_legend: bool = True) -> None:
        for label, vals, linewidth in j_series:
            arr = np.asarray(vals, dtype=np.float64)
            if cutoff is not None:
                if lower_only:
                    arr = np.where(arr <= cutoff, arr, np.nan)
                elif upper_only:
                    arr = np.where(arr > cutoff, arr, np.nan)
            ax.plot(xs_local, arr, marker="o", markersize=2.0, linewidth=linewidth, label=(label if show_legend else None))

    def add_final_weighted_sum_marker(ax: Any, final_value: float) -> None:
        ymin, ymax = ax.get_ylim()
        if not (ymin <= final_value <= ymax):
            return
        existing_ticks = list(ax.get_yticks())
        ticks = sorted(existing_ticks + [final_value])
        deduped: List[float] = []
        for tick in ticks:
            if not deduped or abs(tick - deduped[-1]) > 1e-9:
                deduped.append(float(tick))
        ax.set_yticks(deduped)
        labels: List[str] = []
        for tick in deduped:
            if abs(tick - final_value) <= 1e-9:
                labels.append(f"{final_value:.6g}")
            else:
                labels.append(f"{tick:g}")
        ax.set_yticklabels(labels)
        ax.axhline(final_value, color="#666666", linestyle=":", linewidth=0.8, alpha=0.45, zorder=0)

    def plot_single_panel(rows: Sequence[Dict[str, Any]], *, fig_title: str) -> None:
        xs_local = [int(it.get("iter", i + 1)) for i, it in enumerate(rows)]
        j_series, weighted_sum = build_series(rows)
        all_finite = np.concatenate([finite_values(vals) for _, vals, _ in j_series] or [np.array([], dtype=np.float64)])
        y_break = 5.0
        use_broken_y = bool(all_finite.size) and float(np.max(all_finite)) > y_break

        out_png.parent.mkdir(parents=True, exist_ok=True)
        if use_broken_y:
            fig, (ax_top, ax) = plt.subplots(
                2,
                1,
                sharex=True,
                figsize=(8.5, 6.0),
                dpi=dpi,
                gridspec_kw={"height_ratios": [1.0, 2.4], "hspace": 0.05},
            )
            draw_series(ax_top, xs_local, j_series, upper_only=True, cutoff=y_break)
            draw_series(ax, xs_local, j_series, lower_only=True, cutoff=y_break)
            y_top = float(np.max(all_finite))
            high_vals = all_finite[all_finite > y_break]
            upper_start = max(y_break * 1.02, float(np.min(high_vals)) * 0.98 if high_vals.size else y_break * 1.02)
            if upper_start >= y_top:
                upper_start = y_break * 1.02
            ax.set_ylim(0.0, y_break)
            ax_top.set_ylim(upper_start, y_top * 1.03)
            ax_top.spines["bottom"].set_visible(False)
            ax.spines["top"].set_visible(False)
            ax_top.tick_params(labeltop=False, bottom=False)
            d = 0.015
            kwargs = dict(transform=ax_top.transAxes, color="k", clip_on=False, linewidth=0.8)
            ax_top.plot((-d, +d), (-d, +d), **kwargs)
            ax_top.plot((1 - d, 1 + d), (-d, +d), **kwargs)
            kwargs.update(transform=ax.transAxes)
            ax.plot((-d, +d), (1 - d, 1 + d), **kwargs)
            ax.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)
            ax_top.set_title(fig_title)
            ax_top.legend(loc="best", fontsize=8)
            finite_weighted_sum = finite_values(weighted_sum)
            if finite_weighted_sum.size:
                final_weighted_sum = float(finite_weighted_sum[-1])
                add_final_weighted_sum_marker(ax, final_weighted_sum)
                add_final_weighted_sum_marker(ax_top, final_weighted_sum)
            axes = [ax_top, ax]
        else:
            fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=dpi)
            draw_series(ax, xs_local, j_series)
            ax.set_title(fig_title)
            ax.legend(loc="best", fontsize=8)
            finite_weighted_sum = finite_values(weighted_sum)
            if finite_weighted_sum.size:
                add_final_weighted_sum_marker(ax, float(finite_weighted_sum[-1]))
            axes = [ax]

        ax.set_xlabel("Iteration")
        ax.set_ylabel("Weighted objective contribution")
        for axis in axes:
            axis.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(out_png, dpi=dpi)
        plt.close(fig)

    stage_ids = sorted(
        {
            int(it.get("stage"))
            for it in iterations
            if it.get("stage", None) is not None
        }
    )
    if len(stage_ids) <= 1:
        plot_single_panel(iterations, fig_title=title)
        return

    stage_rows: List[Tuple[int, float, List[Dict[str, Any]]]] = []
    for stage_id in stage_ids:
        rows = [dict(it) for it in iterations if int(it.get("stage", -1)) == stage_id]
        if not rows:
            continue
        beta = float(rows[0].get("beta", float("nan")))
        stage_rows.append((stage_id, beta, rows))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    n_stages = len(stage_rows)
    fig_h = max(3.0 * n_stages, 5.0)
    fig, axes = plt.subplots(n_stages, 1, figsize=(9.0, fig_h), dpi=dpi, sharex=False)
    if n_stages == 1:
        axes = [axes]
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    for ax, (stage_id, beta, rows) in zip(axes, stage_rows):
        xs_local = list(range(len(rows)))
        j_series, weighted_sum = build_series(rows)
        for idx, (label, vals, linewidth) in enumerate(j_series):
            color = color_cycle[idx % max(1, len(color_cycle))] if color_cycle else None
            arr = np.asarray(vals, dtype=np.float64)
            ax.plot(xs_local, arr, marker="o", markersize=2.0, linewidth=linewidth, label=label, color=color)
        finite_weighted_sum = finite_values(weighted_sum)
        if finite_weighted_sum.size:
            add_final_weighted_sum_marker(ax, float(finite_weighted_sum[-1]))
        inner_iters = max(0, len(rows) - 1)
        beta_str = f"{beta:.2f}" if math.isfinite(beta) else "NA"
        ax.set_title(f"Stage {stage_id + 1} (beta={beta_str}, inner iterations={inner_iters})", fontsize=10)
        ax.set_ylabel("Weighted objective\ncontribution")
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Inner iteration within stage")
    fig.suptitle(title)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
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


def ensure_label_present(labels: List[str], required_label: str) -> List[str]:
    if required_label in labels:
        return labels
    return labels + [required_label]


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


def compute_parallel_link_ratio(
    links: Sequence[Dict[str, Any]],
    *,
    endpoint_tol_m: float = 1.0,
) -> float:
    n_links = len(links)
    if n_links <= 1:
        return 0.0
    link_rows: List[Tuple[float, float, float, float]] = []
    for link in links:
        x0 = float(link["x0_m"])
        y0 = float(link["y0_m"])
        x1 = float(link["x1_m"])
        y1 = float(link["y1_m"])
        dx = x1 - x0
        dy = y1 - y0
        if dx == 0.0 and dy == 0.0:
            continue
        link_rows.append((x0, y0, x1, y1))
    if len(link_rows) <= 1:
        return 0.0
    endpoint_tol_sq = float(endpoint_tol_m) ** 2

    def sqdist(ax: float, ay: float, bx: float, by: float) -> float:
        return (ax - bx) ** 2 + (ay - by) ** 2

    matched = np.zeros(len(link_rows), dtype=bool)
    for left, (x0_i, y0_i, x1_i, y1_i) in enumerate(link_rows):
        for cand in range(left + 1, len(link_rows)):
            x0_j, y0_j, x1_j, y1_j = link_rows[cand]
            direct = (
                sqdist(x0_i, y0_i, x0_j, y0_j) <= endpoint_tol_sq
                and sqdist(x1_i, y1_i, x1_j, y1_j) <= endpoint_tol_sq
            )
            flipped = (
                sqdist(x0_i, y0_i, x1_j, y1_j) <= endpoint_tol_sq
                and sqdist(x1_i, y1_i, x0_j, y0_j) <= endpoint_tol_sq
            )
            if direct or flipped:
                matched[left] = True
                matched[cand] = True
    return float(np.mean(matched))


def collect_patch_overview_rows(
    *,
    analysis_config: Dict[str, Any],
    cfg_path: Optional[Path],
) -> List[Dict[str, Any]]:
    if cfg_path is None:
        return []
    base_dir = cfg_path.parent
    est_dir_raw = render_value(analysis_config, "input.est_input_dir", None)
    est_dir = resolve_path(est_dir_raw, base_dir=base_dir) if est_dir_raw is not None else None
    if est_dir is None or not est_dir.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for est_path in sorted(est_dir.glob("est_input_*.json")):
        try:
            est = load_est_payload(est_path)
            header = est.get("header", {})
            H = int(header["H"])
            W = int(header["W"])
            pix = float(header.get("pixel_size_m", 125.0))
            width_m = float(header.get("width_m", W * pix))
            height_m = float(header.get("height_m", H * pix))
            links = list(est.get("links", []) or [])
            rows.append(
                dict(
                    patch_key=str(header.get("patch_id", est_path.stem.replace("est_input_", ""))),
                    width_m=width_m,
                    height_m=height_m,
                    n_pixels=int(H * W),
                    n_links=int(len(links)),
                    parallel_link_ratio=compute_parallel_link_ratio(links),
                )
            )
        except Exception:
            continue
    return rows


def plot_patch_extent_scatter(
    out_png: Path,
    *,
    rows: List[Dict[str, Any]],
    title: str,
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    if not rows:
        return
    widths_km = np.asarray([float(r["width_m"]) / 1000.0 for r in rows], dtype=np.float64)
    heights_km = np.asarray([float(r["height_m"]) / 1000.0 for r in rows], dtype=np.float64)

    fig, ax = plt.subplots(figsize=(7.0, 5.4), dpi=dpi)
    ax.scatter(widths_km, heights_km, s=42, alpha=0.72, color="#1f77b4", edgecolors="white", linewidths=0.6)
    lo = min(float(np.min(widths_km)), float(np.min(heights_km)))
    hi = max(float(np.max(widths_km)), float(np.max(heights_km)))
    ax.plot([lo, hi], [lo, hi], linestyle="--", linewidth=1.0, color="#7f7f7f", alpha=0.8)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Width (km)")
    ax.set_ylabel("Height (km)")
    ax.set_title(title)
    ax.grid(True, linestyle=":", linewidth=0.6, alpha=0.35)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.08, 0.06, 0.98, 0.95))
    fig.savefig(out_png)
    plt.close(fig)


def plot_link_count_histogram(
    out_png: Path,
    *,
    rows: List[Dict[str, Any]],
    title: str,
    dpi: int = 150,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    if not rows:
        return
    n_links = np.asarray([float(r["n_links"]) for r in rows], dtype=np.float64)
    parallel_ratio = np.asarray([float(r["parallel_link_ratio"]) for r in rows], dtype=np.float64)
    unique_counts = np.unique(n_links.astype(int))
    if unique_counts.size <= 12:
        edges = np.arange(unique_counts.min() - 0.5, unique_counts.max() + 1.5, 1.0)
    else:
        n_bins = min(16, max(10, int(round(1.4 * math.sqrt(float(n_links.size))))))
        width = max(25.0, math.ceil((float(n_links.max()) - float(n_links.min())) / n_bins / 25.0) * 25.0)
        left = math.floor(float(n_links.min()) / width) * width
        right = math.ceil(float(n_links.max()) / width) * width
        edges = np.arange(left, right + 0.5 * width, width)

    fig, ax = plt.subplots(figsize=(8.2, 6.0), dpi=dpi)
    counts, bin_edges, _ = ax.hist(
        n_links,
        bins=edges,
        color="#ff7f0e",
        alpha=0.85,
        edgecolor="black",
        linewidth=0.6,
    )
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    bin_labels = [f"[{left:.0f}, {right:.0f})" for left, right in zip(bin_edges[:-1], bin_edges[1:])]
    if bin_labels:
        bin_labels[-1] = f"[{bin_edges[-2]:.0f}, {bin_edges[-1]:.0f}]"
    if len(bin_centers) <= 12:
        tick_positions = bin_centers
        tick_labels = bin_labels
    else:
        step = 2 if len(bin_centers) <= 20 else 3
        tick_positions = bin_centers[::step]
        tick_labels = bin_labels[::step]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=28, ha="right", fontsize=8)
    ax.set_xlabel("Links per patch (histogram bin intervals)")
    ax.set_ylabel("Frequency over patches")
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7)
    fig.text(
        0.5,
        0.05,
        (
            f"Average links per patch = {float(np.mean(n_links)):.1f}; SD = {float(np.std(n_links, ddof=0)):.1f}.\n"
            f"Average parallel-link ratio (#parallel links / #links; links are counted as matching when\n"
            f"their corresponding endpoints are within 1 m in Euclidean distance) = {float(np.mean(parallel_ratio)):.3f}; "
            f"SD = {float(np.std(parallel_ratio, ddof=0)):.3f}."
        ),
        ha="center",
        fontsize=8,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.08, 0.20, 0.98, 0.95))
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
                # Dark halo first, then a bright center line so links stay visible on any bin color.
                ax.plot([x0[i], x1[i]], [y0[i], y1[i]], color="black", linewidth=1.8, alpha=0.9, solid_capstyle="round")
                ax.plot([x0[i], x1[i]], [y0[i], y1[i]], color="white", linewidth=1.0, alpha=1.0, solid_capstyle="round")

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_ticks(np.arange(n_bins))
        cbar.set_ticklabels(labels)
        cbar.ax.set_ylabel(f"d{k} distance bin (m)")
        width_km = (float(W) * pix) / 1000.0
        height_km = (float(H) * pix) / 1000.0
        ax.set_title(
            f"Largest patch in the data set: distance bins to the {ordinal(k)} closest link\n"
            f"Size = {width_km:.1f} x {height_km:.1f} km, area = {area_km2:.1f} km$^2$, links = {x0.size}"
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
    def log_progress(message: str) -> None:
        print(f"[render] {message}")

    def progress_interval(total: int) -> int:
        if total <= 10:
            return 1
        if total <= 50:
            return 5
        return 25

    def start_major(name: str) -> None:
        log_progress(f"[{major_state['completed']}/{major_state['total']}] Starting {name}")

    def finish_major(name: str) -> None:
        major_state["completed"] += 1
        log_progress(f"[{major_state['completed']}/{major_state['total']}] Finished {name}")

    render_config = render_config or {}
    analysis_config: Dict[str, Any] = {}
    cfg_path = cache.get("config_path", None)
    cfg_path_resolved: Optional[Path] = None
    if cfg_path:
        cfg_path_resolved = Path(str(cfg_path)).resolve()
        analysis_config = load_config_file(cfg_path_resolved)
    out_dir = output_dir or Path(str(render_value(render_config, "output.out_dir", cache["output"]["out_dir"])))
    images_subdir = str(render_value(render_config, "output.images_subdir", cache["output"]["images_subdir"]))
    excel_name = str(render_value(render_config, "output.excel_filename", cache["output"]["excel_filename"]))
    img_dir = out_dir / images_subdir
    excel_path = out_dir / excel_name
    largest_patch_img_dir = img_dir / "largest_patch_distance_bins"
    j_behavior_img_dir = img_dir / "j_behavior"
    patch_error_maps_img_dir = img_dir / "patch_error_maps"
    old_patch_error_maps_img_dir = img_dir / "old_patch_error_maps"
    rae_hist_img_dir = img_dir / "rae_histograms"
    threshold_img_dir = img_dir / "threshold_sweeps"
    distance_iqr_img_dir = img_dir / "distance_profiles_iqr"
    distance_box_img_dir = img_dir / "distance_profiles_box_whisker"
    distance_box_linear_img_dir = distance_box_img_dir / "linear"
    distance_box_log_img_dir = distance_box_img_dir / "log"
    jatten_iqr_img_dir = img_dir / "jatten_profiles_iqr"
    jatten_box_img_dir = img_dir / "jatten_profiles_box_whisker"
    summary_img_dir = img_dir / "summaries"
    gtbin_img_dir = img_dir / "gt_binned_patchavg"
    confusion_img_dir = img_dir / "confusion_maps"
    patch_overview_img_dir = img_dir / "patch_overview"

    ordered_sheets = cache.get("ordered_sheets", {})
    if not isinstance(ordered_sheets, dict):
        raise ValueError("Cache missing ordered_sheets.")
    ordered_sheets = reorder_report_sheets(ordered_sheets)
    display_map = solver_display_map(cache, render_config)
    for sheet_name, rows in list(ordered_sheets.items()):
        if not isinstance(rows, list):
            continue
        updated_rows: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                updated_rows.append(row)
                continue
            new_row = dict(row)
            if "solver" in new_row:
                new_row["solver"] = apply_solver_display(str(new_row["solver"]), display_map)
            updated_rows.append(new_row)
        ordered_sheets[sheet_name] = updated_rows
    if "FPFN_ByThreshold" in ordered_sheets:
        ordered_sheets["FPFN_ByThreshold"] = reorder_row_columns(
            list(ordered_sheets["FPFN_ByThreshold"]),
            [
                "solver",
                "threshold_mmph",
                "positive_definition",
                "fp_definition",
                "fn_definition",
                "fp_rate_all_mean",
                "fp_rate_all_std",
                "fn_rate_all_mean",
                "fn_rate_all_std",
                "fp_rate_dry_mean",
                "fp_rate_dry_std",
                "fn_rate_wet_mean",
                "fn_rate_wet_std",
                "n_patches",
                "tp_definition",
                "tn_definition",
                "tp_rate_all_mean",
                "tp_rate_all_std",
                "tp_rate_all_sem",
                "fp_rate_all_sem",
                "fn_rate_all_sem",
                "tn_rate_all_mean",
                "tn_rate_all_std",
                "tn_rate_all_sem",
            ],
        )

    objective_sheet_comments: Dict[str, str] = {}
    obj_rows = ordered_sheets.get("Objective_J", [])
    if obj_rows:
        header_comments = objective_header_comments_map()
        for col_name in obj_rows[0].keys():
            if col_name in header_comments:
                objective_sheet_comments[col_name] = header_comments[col_name]

    if render_bool(render_config, "excel.enabled", True):
        log_progress("Writing Excel workbook")
        write_workbook(excel_path, ordered_sheets, header_comments={"Objective_J": objective_sheet_comments})
        print(f"Wrote Excel: {excel_path}")

    dpi = int(render_value(render_config, "style.dpi", cache["render"]["dpi"]))
    bin_spacing = float(render_value(render_config, "style.bin_spacing", cache["render"]["bin_spacing"]))
    y_max_raw = render_value(render_config, "style.y_max", cache["render"].get("y_max", None))
    y_max = None if y_max_raw is None else float(y_max_raw)
    prune_bins_enabled = bool(render_value(render_config, "style.prune_bins_enabled", cache["render"]["prune_bins_enabled"]))
    prune_bins_zero_frac = float(render_value(render_config, "style.prune_bins_zero_frac", cache["render"]["prune_bins_zero_frac"]))
    rae_bins = int(render_value(render_config, "style.rae_bins", cache["render"]["rae_bins"]))
    patch_map_render_cfg = {
        "threshold_mmph": float(render_value(render_config, "patch_error_maps.threshold_mmph", render_value(analysis_config, "rain.threshold_mmph", 1.0))),
        "dpi": int(render_value(render_config, "patch_error_maps.dpi", dpi)),
        "cmap_gt": str(render_value(render_config, "patch_error_maps.cmap_gt", render_value(analysis_config, "plots.cmap_gt", "viridis"))),
        "cmap_sol": str(render_value(render_config, "patch_error_maps.cmap_sol", render_value(analysis_config, "plots.cmap_sol", "viridis"))),
        "cmap_diff": str(render_value(render_config, "patch_error_maps.cmap_diff", render_value(analysis_config, "plots.cmap_diff", "seismic"))),
        "cmap_abs_diff": str(render_value(render_config, "patch_error_maps.cmap_abs_diff", render_value(analysis_config, "plots.cmap_abs_diff", "magma"))),
        "cmap_rel": str(render_value(render_config, "patch_error_maps.cmap_rel", render_value(analysis_config, "plots.cmap_rel", "seismic"))),
        "cmap_abs_rel": str(render_value(render_config, "patch_error_maps.cmap_abs_rel", render_value(analysis_config, "plots.cmap_abs_rel", "magma"))),
        "include_map": bool(render_value(render_config, "plots.patch_error_maps_include_map", False)),
    }

    labels = cache["labels"]
    k_values = [int(v) for v in labels["k_values"]]
    dist_labels = [str(v) for v in labels["dist_labels"]]
    jatten_k_values = [int(v) for v in labels["jatten_k_values"]]
    jatten_dist_labels = [str(v) for v in labels["jatten_dist_labels"]]

    solver_order = ordered_solver_labels(cache)
    solver_order_display = [apply_solver_display(v, display_map) for v in solver_order]
    largest_patch_payload = cache.get("largest_patch_plot_payload", None)
    j_behavior_plots = cache.get("j_behavior_plots", []) or []
    patch_plot_jobs = cache.get("patch_plot_jobs", []) or []
    rae_hist_plots = cache.get("rae_hist_plots", []) or []
    fpfn_rows = ordered_sheets.get("FPFN_ByThreshold", [])
    link_ratio_entries = cache.get("link_ratio_entries", []) or []
    gtbin = cache.get("gtbin_plot_data", None)
    patch_map_metrics_plot_data = cache.get("patch_map_metrics_plot_data", {}) or {}
    patch_overview_rows = collect_patch_overview_rows(analysis_config=analysis_config, cfg_path=cfg_path_resolved)

    major_steps: List[Tuple[str, bool]] = [
        ("Excel workbook", render_bool(render_config, "excel.enabled", True)),
        ("Largest-patch distance-bin maps", bool(largest_patch_payload) and render_bool(render_config, "plots.largest_patch_distance_bins", True)),
        ("Patch overview plots", bool(patch_overview_rows) and render_bool(render_config, "plots.patch_overview", True)),
        ("J-behavior plots", bool(j_behavior_plots) and render_bool(render_config, "plots.j_behavior", True)),
        ("Patch error maps", bool(patch_plot_jobs) and render_bool(render_config, "plots.patch_error_maps", True)),
        ("RAE histograms", bool(rae_hist_plots) and render_bool(render_config, "plots.rae_histograms", True)),
        ("FP/FN vs threshold plot", bool(fpfn_rows) and render_bool(render_config, "plots.fp_fn_vs_threshold", True)),
        ("Confusion maps", bool(fpfn_rows) and render_bool(render_config, "plots.confusion_maps", True)),
        ("Distance-profile plots", render_bool(render_config, "plots.distance_profiles", True) or render_bool(render_config, "plots.p90_profiles", True) or render_bool(render_config, "plots.distance_profiles_relative", True)),
        ("J_atten plots", render_bool(render_config, "plots.jatten_profiles", True) or render_bool(render_config, "plots.jatten_profiles_relative", True)),
        ("Link-ratio summary plot", bool(link_ratio_entries) and render_bool(render_config, "plots.link_ratio_summary", True)),
        ("Patch-map metrics plot", bool(patch_map_metrics_plot_data) and render_bool(render_config, "plots.patch_map_metrics", True)),
        ("GT-binned patch-average plots", bool(gtbin) and render_bool(render_config, "plots.gt_binned_patchavg", True)),
    ]
    major_state = {"completed": 0, "total": sum(1 for _, enabled in major_steps if enabled)}
    if major_state["total"] > 0:
        log_progress(f"Major plot groups to render: {major_state['total']}")

    if largest_patch_payload and render_bool(render_config, "plots.largest_patch_distance_bins", True):
        start_major("largest-patch distance-bin maps")
        log_progress("Rendering largest-patch distance-bin maps")
        render_largest_patch_distance_bin_maps(
            largest_patch_payload,
            out_dir=largest_patch_img_dir,
            dpi=dpi,
        )
        finish_major("largest-patch distance-bin maps")

    if patch_overview_rows and render_bool(render_config, "plots.patch_overview", True):
        start_major("Patch overview plots")
        log_progress(f"Rendering patch overview plots ({len(patch_overview_rows)} patches)")
        plot_patch_extent_scatter(
            patch_overview_img_dir / "patch_dimensions_scatter.png",
            rows=patch_overview_rows,
            title="Scatter plot of patch dimensions",
            dpi=dpi,
        )
        plot_link_count_histogram(
            patch_overview_img_dir / "link_count_histogram.png",
            rows=patch_overview_rows,
            title="Link-count distribution across patches",
            dpi=dpi,
        )
        finish_major("Patch overview plots")

    if j_behavior_plots and render_bool(render_config, "plots.j_behavior", True):
        start_major("J-behavior plots")
        log_progress(f"Rendering J-behavior plots ({len(j_behavior_plots)} jobs)")
        interval = progress_interval(len(j_behavior_plots))
        for idx, plot_payload in enumerate(j_behavior_plots, start=1):
            plot_j_behavior(
                j_behavior_img_dir / safe_path_token(str(plot_payload["solver_name"])) / f"{safe_path_token(str(plot_payload['patch_key']))}.png",
                title=(
                    f"Objective trace for {apply_solver_display(str(plot_payload['solver_label']), display_map)}\n"
                    f"{pretty_patch_label(str(plot_payload['patch_key']))}"
                ),
                iterations=plot_payload.get("iterations", []) or [],
                dpi=dpi,
            )
            if idx == len(j_behavior_plots) or idx % interval == 0:
                log_progress(f"J-behavior plots: {idx}/{len(j_behavior_plots)}")
        finish_major("J-behavior plots")

    if patch_plot_jobs and render_bool(render_config, "plots.old_patch_error_maps", False):
        start_major("old patch error maps")
        log_progress(f"Rendering old patch error maps ({len(patch_plot_jobs)} jobs)")
        interval = progress_interval(len(patch_plot_jobs))
        for idx, patch_plot_job in enumerate(patch_plot_jobs, start=1):
            render_patch_error_maps_from_job(patch_plot_job, img_dir=old_patch_error_maps_img_dir, render_cfg=patch_map_render_cfg)
            if idx == len(patch_plot_jobs) or idx % interval == 0:
                log_progress(f"Old patch error maps: {idx}/{len(patch_plot_jobs)}")
        finish_major("old patch error maps")

    if patch_plot_jobs and render_bool(render_config, "plots.patch_error_maps", True):
        start_major("patch error maps")
        jobs_by_patch: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for patch_plot_job in patch_plot_jobs:
            jobs_by_patch[str(patch_plot_job["patch_key"])].append(patch_plot_job)
        patch_keys = sorted(jobs_by_patch.keys())
        log_progress(f"Rendering combined patch error maps ({len(patch_keys)} patches)")
        interval = progress_interval(len(patch_keys))
        for idx, patch_key in enumerate(patch_keys, start=1):
            render_combined_patch_error_map(
                patch_key,
                jobs_by_patch[patch_key],
                img_dir=patch_error_maps_img_dir,
                render_cfg=patch_map_render_cfg,
                display_map=display_map,
            )
            if idx == len(patch_keys) or idx % interval == 0:
                log_progress(f"Combined patch error maps: {idx}/{len(patch_keys)}")
        log_progress(f"Rendering reduced combined patch error maps ({len(patch_keys)} patches)")
        for idx, patch_key in enumerate(patch_keys, start=1):
            render_combined_patch_error_map(
                patch_key,
                jobs_by_patch[patch_key],
                img_dir=patch_error_maps_img_dir,
                render_cfg=patch_map_render_cfg,
                display_map=display_map,
                output_subdir="combined_few",
                solver_allowlist=_COMBINED_FEW_SOLVERS,
                solver_order=_COMBINED_FEW_SOLVER_ORDER,
            )
            if idx == len(patch_keys) or idx % interval == 0:
                log_progress(f"Reduced combined patch error maps: {idx}/{len(patch_keys)}")
        finish_major("patch error maps")

    if rae_hist_plots and render_bool(render_config, "plots.rae_histograms", True):
        start_major("RAE histograms")
        log_progress(f"Rendering RAE histograms ({len(rae_hist_plots)} jobs)")
        interval = progress_interval(len(rae_hist_plots))
        for idx, payload in enumerate(rae_hist_plots, start=1):
            plot_rae_histograms(
                rae_hist_img_dir / Path(str(payload["out_relpath"])).name,
                title=str(payload["title"]),
                dist_labels=[str(v) for v in payload["dist_labels"]],
                data_by_bin={str(k): list(v) for k, v in payload["data_by_bin"].items()},
                bins=rae_bins,
                dpi=dpi,
            )
            if idx == len(rae_hist_plots) or idx % interval == 0:
                log_progress(f"RAE histograms: {idx}/{len(rae_hist_plots)}")
        finish_major("RAE histograms")

    if fpfn_rows and render_bool(render_config, "plots.fp_fn_vs_threshold", True):
        start_major("FP/FN vs threshold plot")
        log_progress("Rendering FP/FN vs threshold plot")
        plot_fp_fn_vs_threshold(
            threshold_img_dir / "fp_fn_vs_threshold.png",
            title="Wet-class FP/FN rates vs threshold",
            rows=fpfn_rows,
            dpi=dpi,
        )
        finish_major("FP/FN vs threshold plot")

    if fpfn_rows and render_bool(render_config, "plots.confusion_maps", True):
        threshold_target = float(render_value(render_config, "confusion_maps.threshold_mmph", cache["render"].get("threshold_mmph", patch_map_render_cfg["threshold_mmph"])))
        by_solver: Dict[str, List[Dict[str, Any]]] = {}
        for row in fpfn_rows:
            if "tp_rate_all_mean" not in row or "tn_rate_all_mean" not in row:
                continue
            by_solver.setdefault(str(row["solver"]), []).append(row)
        if by_solver:
            start_major("Confusion maps")
            log_progress(f"Rendering confusion maps at threshold {threshold_target:.3g} mm/h")
            for solver_label, rows in sorted(by_solver.items()):
                chosen = min(rows, key=lambda r: abs(float(r.get("threshold_mmph", threshold_target)) - threshold_target))
                chosen_thr = float(chosen.get("threshold_mmph", threshold_target))
                display_solver_label = apply_solver_display(solver_label, display_map)
                plot_confusion_map(
                    confusion_img_dir / f"{safe_path_token(solver_label)}_confusion_map.png",
                    title=f"Wet/dry confusion matrix (patch-averaged): {display_solver_label}",
                    solver_label=display_solver_label,
                    threshold_mmph=chosen_thr,
                    tp_mean=float(chosen.get("tp_rate_all_mean", 0.0)),
                    tp_sem=float(chosen.get("tp_rate_all_sem", 0.0)),
                    fp_mean=float(chosen.get("fp_rate_all_mean", 0.0)),
                    fp_sem=float(chosen.get("fp_rate_all_sem", 0.0)),
                    fn_mean=float(chosen.get("fn_rate_all_mean", 0.0)),
                    fn_sem=float(chosen.get("fn_rate_all_sem", 0.0)),
                    tn_mean=float(chosen.get("tn_rate_all_mean", 0.0)),
                    tn_sem=float(chosen.get("tn_rate_all_sem", 0.0)),
                    n_patches=int(chosen.get("n_patches", 0)),
                    dpi=dpi,
                )
            finish_major("Confusion maps")

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
    method_order_display = [apply_solver_display(label, display_map) for label in method_order]
    if method_order:
        distance_major_started = False
        jatten_major_started = False
        if render_bool(render_config, "plots.distance_profiles", True) or render_bool(render_config, "plots.p90_profiles", True) or render_bool(render_config, "plots.distance_profiles_relative", True):
            start_major("distance-profile plots")
            distance_major_started = True
            log_progress(f"Rendering distance-profile plots for k values {enabled_k_values}")
        for k in [v for v in k_values if v in enabled_k_values]:
            kstr = str(k)
            distance_box_linear_k_img_dir = distance_box_linear_img_dir / f"k{k}"
            distance_box_log_k_img_dir = distance_box_log_img_dir / f"k{k}"
            focus_rainy_k3 = (k == 3)
            labels_r = list(dist_labels)
            labels_n = list(dist_labels)
            counts_r = {str(kb): list(v) for kb, v in bin_counts[kstr]["rainy"].items()}
            counts_n = {str(kb): list(v) for kb, v in bin_counts[kstr]["nonrainy"].items()}
            medians_rainy_raw = medians_rainy[kstr]
            medians_nonrainy_raw = medians_nonrainy[kstr]
            p90s_rainy_raw = p90s_rainy[kstr]
            p90s_nonrainy_raw = p90s_nonrainy[kstr]
            labels_r, counts_r, merged_r_maps = merge_distance_tail_bin(
                labels_r, counts_r, medians_rainy_raw, p90s_rainy_raw
            )
            medians_rainy_merged, p90s_rainy_merged = merged_r_maps
            labels_n, counts_n, merged_n_maps = merge_distance_tail_bin(
                labels_n, counts_n, medians_nonrainy_raw, p90s_nonrainy_raw
            )
            medians_nonrainy_merged, p90s_nonrainy_merged = merged_n_maps
            if prune_bins_enabled:
                labels_r = filter_bins_by_zero_fraction(labels_r, counts_r, zero_frac_threshold=prune_bins_zero_frac)
                labels_n = filter_bins_by_zero_fraction(labels_n, counts_n, zero_frac_threshold=prune_bins_zero_frac)
            merged_tail_label = r"$(6000,\infty)$"
            labels_r = ensure_label_present(labels_r, merged_tail_label)
            labels_n = ensure_label_present(labels_n, merged_tail_label)
            tick_labels_r = build_bin_tick_labels(labels_r, counts_r)
            tick_labels_n = build_bin_tick_labels(labels_n, counts_n)

            if len(k_values) == 1 and k == 3:
                rainy_name = "distance_iqr_medians_rainy_multi.png"
                nonrainy_name = "distance_iqr_medians_nonrainy_multi.png"
                rainy_title = "Rainy pixels. IQR of per-patch median rainy-pixel relative absolute error (RAE) by distance bin"
                nonrainy_title = "Non-rainy pixels. IQR of per-patch median non-rainy-pixel absolute error by distance bin"
                rainy_p90_name = "distance_iqr_p90s_rainy_multi.png"
                nonrainy_p90_name = "distance_iqr_p90s_nonrainy_multi.png"
                rainy_p90_title = "Rainy pixels. IQR of per-patch rainy-pixel 90th-percentile relative absolute error (RAE) by distance bin"
                nonrainy_p90_title = "Non-rainy pixels. IQR of per-patch non-rainy-pixel 90th-percentile absolute error by distance bin"
            else:
                rainy_name = f"distance_iqr_medians_rainy_multi_k{k}.png"
                nonrainy_name = f"distance_iqr_medians_nonrainy_multi_k{k}.png"
                rainy_title = f"Rainy pixels. IQR of per-patch median rainy-pixel relative absolute error (RAE) by distance bin (to the {ordinal(k)} closest link)"
                nonrainy_title = f"Non-rainy pixels. IQR of per-patch median non-rainy-pixel absolute error by distance bin (to the {ordinal(k)} closest link)"
                rainy_p90_name = f"distance_iqr_p90s_rainy_multi_k{k}.png"
                nonrainy_p90_name = f"distance_iqr_p90s_nonrainy_multi_k{k}.png"
                rainy_p90_title = f"Rainy pixels. IQR of per-patch rainy-pixel 90th-percentile relative absolute error (RAE) by distance bin (to the {ordinal(k)} closest link)"
                nonrainy_p90_title = f"Non-rainy pixels. IQR of per-patch non-rainy-pixel 90th-percentile absolute error by distance bin (to the {ordinal(k)} closest link)"

            rainy_box_name = rainy_name.replace(".png", "_box_whisker.png")
            nonrainy_box_name = nonrainy_name.replace(".png", "_box_whisker.png")
            rainy_p90_box_name = rainy_p90_name.replace(".png", "_box_whisker.png")
            nonrainy_p90_box_name = nonrainy_p90_name.replace(".png", "_box_whisker.png")
            if len(k_values) == 1 and k == 3:
                rainy_box_title = "Rainy pixels. Box-and-whisker of per-patch median rainy-pixel relative absolute error (RAE) by distance bin"
                nonrainy_box_title = "Non-rainy pixels. Box-and-whisker of per-patch median non-rainy-pixel absolute error by distance bin"
                rainy_p90_box_title = "Rainy pixels. Box-and-whisker of per-patch rainy-pixel 90th-percentile relative absolute error (RAE) by distance bin"
                nonrainy_p90_box_title = "Non-rainy pixels. Box-and-whisker of per-patch non-rainy-pixel 90th-percentile absolute error by distance bin"
                rainy_rel_box_title = "Rainy pixels. Box-and-whisker of per-patch median rainy-pixel relative absolute error (RAE) by distance bin (relative to IDW bin medians)"
                nonrainy_rel_box_title = "Non-rainy pixels. Box-and-whisker of per-patch median non-rainy-pixel absolute error by distance bin (relative to IDW bin medians)"
            else:
                rainy_box_title = f"Rainy pixels. Box-and-whisker of per-patch median rainy-pixel relative absolute error (RAE) by distance bin (to the {ordinal(k)} closest link)"
                nonrainy_box_title = f"Non-rainy pixels. Box-and-whisker of per-patch median non-rainy-pixel absolute error by distance bin (to the {ordinal(k)} closest link)"
                rainy_p90_box_title = f"Rainy pixels. Box-and-whisker of per-patch rainy-pixel 90th-percentile relative absolute error (RAE) by distance bin (to the {ordinal(k)} closest link)"
                nonrainy_p90_box_title = f"Non-rainy pixels. Box-and-whisker of per-patch non-rainy-pixel 90th-percentile absolute error by distance bin (to the {ordinal(k)} closest link)"
                rainy_rel_box_title = f"Rainy pixels. Box-and-whisker of per-patch median rainy-pixel relative absolute error (RAE) by distance bin (to the {ordinal(k)} closest link), relative to IDW bin medians"
                nonrainy_rel_box_title = f"Non-rainy pixels. Box-and-whisker of per-patch median non-rainy-pixel absolute error by distance bin (to the {ordinal(k)} closest link), relative to IDW bin medians"
            rainy_footnote = (
                "Metric (RAE): |GT(p)-PRED(p)| / GT(p) over rainy pixels p.\n"
                "Each patch contributes one median rainy-pixel relative absolute error value in each distance bin.\n"
                "Dot = median of those per-patch medians across patches.\n"
                "Bar = 25th to 75th percentile of those per-patch medians across patches.\n"
                "Tick labels show the average rainy-pixel count per patch in the bin."
            )
            nonrainy_footnote = (
                "Metric: |GT(p)-PRED(p)| over non-rainy pixels p.\n"
                "Each patch contributes one median non-rainy-pixel absolute error value in each distance bin.\n"
                "Dot = median of those per-patch medians across patches.\n"
                "Bar = 25th to 75th percentile of those per-patch medians across patches.\n"
                "Tick labels show the average non-rainy-pixel count per patch in the bin."
            )
            rainy_box_footnote = (
                "Metric (RAE): |GT(p)-PRED(p)| / GT(p) over rainy pixels p.\n"
                "Each patch contributes one median rainy-pixel relative absolute error value in each distance bin.\n"
                "Box = q1 to q3, center line = median, whiskers = min to max across patches."
            )
            nonrainy_box_footnote = (
                "Metric: |GT(p)-PRED(p)| over non-rainy pixels p.\n"
                "Each patch contributes one median non-rainy-pixel absolute error value in each distance bin.\n"
                "Box = q1 to q3, center line = median, whiskers = min to max across patches."
            )
            medians_rainy_display = remap_solver_dict(medians_rainy_merged, display_map)
            medians_nonrainy_display = remap_solver_dict(medians_nonrainy_merged, display_map)
            p90s_rainy_display = remap_solver_dict(p90s_rainy_merged, display_map)
            p90s_nonrainy_display = remap_solver_dict(p90s_nonrainy_merged, display_map)
            rainy_plot_title = "Distribution of patch-level median RAE over rainy pixels by distance bin" if focus_rainy_k3 else rainy_title
            rainy_box_plot_title = "Distribution of patch-level median RAE over rainy pixels by distance bin" if focus_rainy_k3 else rainy_box_title
            nonrainy_box_plot_title = "Distribution of patch-level median non-rainy-pixel absolute error by distance bin" if focus_rainy_k3 else nonrainy_box_title
            distance_x_label = "d3 bin(m)" if focus_rainy_k3 else None
            rainy_plot_footnote = None if focus_rainy_k3 else rainy_footnote
            rainy_box_plot_footnote = None

            if render_bool(render_config, "plots.distance_profiles", True):
                log_progress(f"Distance-profile medians: k={k}")
                plot_iqr_summary(distance_iqr_img_dir / rainy_name, rainy_plot_title, medians_rainy_display, labels_r, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r, x_label=distance_x_label, y_label="Patch-level median rainy-pixel RAE\nDot: median, bar: IQR", footnote=rainy_plot_footnote, broken_y=focus_rainy_k3)
                plot_iqr_summary(distance_iqr_img_dir / nonrainy_name, nonrainy_title, medians_nonrainy_display, labels_n, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n, x_label=distance_x_label, y_label="Per-patch median non-rainy-pixel absolute error\nDot: median, bar: IQR", footnote=nonrainy_footnote)
                plot_box_whisker(distance_box_linear_k_img_dir / rainy_box_name, rainy_box_plot_title, medians_rainy_display, labels_r, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r, x_label=distance_x_label, y_label="Median rainy-pixel RAE per patch", footnote=rainy_box_plot_footnote, broken_y=True)
                plot_box_whisker(distance_box_linear_k_img_dir / nonrainy_box_name, nonrainy_box_plot_title, medians_nonrainy_display, labels_n, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n, x_label=distance_x_label, y_label="Median non-rainy-pixel absolute error per patch", footnote=None, broken_y=True)
                plot_box_whisker(distance_box_log_k_img_dir / rainy_box_name, rainy_box_plot_title + " (log scale)", medians_rainy_display, labels_r, method_order_display, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r, x_label=distance_x_label, y_label="Median rainy-pixel RAE per patch", footnote=None, log_scale=True)
                plot_box_whisker(distance_box_log_k_img_dir / nonrainy_box_name, nonrainy_box_plot_title + " (log scale)", medians_nonrainy_display, labels_n, method_order_display, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n, x_label=distance_x_label, y_label="Median non-rainy-pixel absolute error per patch", footnote=None, log_scale=True)
            if render_bool(render_config, "plots.p90_profiles", True):
                log_progress(f"Distance-profile p90s: k={k}")
                plot_iqr_summary(distance_iqr_img_dir / rainy_p90_name, rainy_p90_title, p90s_rainy_display, labels_r, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r, y_label="Per-patch rainy-pixel p90 RAE\nDot: median, bar: IQR", footnote="Metric (RAE): |GT(p)-PRED(p)| / GT(p) over rainy pixels p.\nEach patch contributes one rainy-pixel 90th-percentile relative absolute error value in each distance bin.\nDot = median of those per-patch p90 values across patches.\nBar = 25th to 75th percentile of those per-patch p90 values across patches.\nTick labels show the average rainy-pixel count per patch in the bin.")
                plot_iqr_summary(distance_iqr_img_dir / nonrainy_p90_name, nonrainy_p90_title, p90s_nonrainy_display, labels_n, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n, y_label="Per-patch non-rainy-pixel p90 absolute error\nDot: median, bar: IQR", footnote="Metric: |GT(p)-PRED(p)| over non-rainy pixels p.\nEach patch contributes one non-rainy-pixel 90th-percentile absolute error value in each distance bin.\nDot = median of those per-patch p90 values across patches.\nBar = 25th to 75th percentile of those per-patch p90 values across patches.\nTick labels show the average non-rainy-pixel count per patch in the bin.")
                plot_box_whisker(distance_box_linear_k_img_dir / rainy_p90_box_name, rainy_p90_box_title, p90s_rainy_display, labels_r, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r, y_label="Per-patch rainy-pixel p90 RAE", footnote=None, broken_y=True)
                plot_box_whisker(distance_box_linear_k_img_dir / nonrainy_p90_box_name, nonrainy_p90_box_title, p90s_nonrainy_display, labels_n, method_order_display, y_max=y_max, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n, y_label="Per-patch non-rainy-pixel p90 absolute error", footnote=None, broken_y=True)
                plot_box_whisker(distance_box_log_k_img_dir / rainy_p90_box_name, rainy_p90_box_title + " (log scale)", p90s_rainy_display, labels_r, method_order_display, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_r, y_label="Per-patch rainy-pixel p90 RAE", footnote=None, log_scale=True)
                plot_box_whisker(distance_box_log_k_img_dir / nonrainy_p90_box_name, nonrainy_p90_box_title + " (log scale)", p90s_nonrainy_display, labels_n, method_order_display, dpi=dpi, bin_spacing=bin_spacing, tick_labels=tick_labels_n, y_label="Per-patch non-rainy-pixel p90 absolute error", footnote=None, log_scale=True)

            if "IDW" in medians_rainy[kstr] and render_bool(render_config, "plots.distance_profiles_relative", True):
                log_progress(f"Relative distance profiles: k={k}")
                rainy_rel_name = rainy_name.replace(".png", "_rel.png")
                nonrainy_rel_name = nonrainy_name.replace(".png", "_rel.png")
                rainy_rel_box_name = rainy_box_name.replace(".png", "_rel.png")
                nonrainy_rel_box_name = nonrainy_box_name.replace(".png", "_rel.png")
                rainy_rel_plot_title = "Distribution of patch-level median rainy-pixel RAE by distance bin, relative to IDW" if focus_rainy_k3 else rainy_rel_box_title
                plot_box_whisker(
                    distance_box_linear_k_img_dir / rainy_rel_box_name,
                    rainy_rel_plot_title,
                    remap_solver_dict(compute_relative_distribution_profile(medians_rainy_merged, baseline_label="IDW", dist_labels=labels_r), display_map),
                    labels_r,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_r,
                    x_label=distance_x_label,
                    y_label="Patch-level median rainy-pixel RAE relative to IDW",
                    footnote=None,
                    broken_y=True,
                )
                plot_box_whisker(
                    distance_box_log_k_img_dir / rainy_rel_box_name,
                    rainy_rel_plot_title + " (log scale)",
                    remap_solver_dict(compute_relative_distribution_profile(medians_rainy_merged, baseline_label="IDW", dist_labels=labels_r), display_map),
                    labels_r,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_r,
                    x_label=distance_x_label,
                    y_label="Patch-level median rainy-pixel RAE relative to IDW",
                    footnote=None,
                    log_scale=True,
                )
                plot_iqr_summary(
                    distance_iqr_img_dir / rainy_rel_name,
                    "Distribution of patch-level median rainy-pixel RAE by distance bin, relative to IDW" if focus_rainy_k3 else f"Rainy pixels. IQR of per-patch median rainy-pixel relative absolute error (RAE) by distance bin (to the {ordinal(k)} closest link), relative to IDW bin medians",
                    remap_solver_dict(compute_relative_distribution_profile(medians_rainy_merged, baseline_label="IDW", dist_labels=labels_r), display_map),
                    labels_r,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_r,
                    x_label=distance_x_label,
                    y_label="Patch-level median rainy-pixel RAE relative to IDW\nDot: median, bar: IQR",
                    footnote=None if focus_rainy_k3 else (
                        "Metric (RAE): |GT(p)-PRED(p)| / GT(p) over rainy pixels p.\n"
                        "Each per-patch median is divided by IDW's median in the same distance bin, so IDW is the baseline at 1.0.\n"
                        "Dot = median of those patch-level ratios across patches.\n"
                        "Bar = 25th to 75th percentile of those patch-level ratios across patches."
                    ),
                    broken_y=True,
                )
                plot_iqr_summary(
                    distance_iqr_img_dir / nonrainy_rel_name,
                    f"Non-rainy pixels. IQR of per-patch median non-rainy-pixel absolute error by distance bin (to the {ordinal(k)} closest link), relative to IDW bin medians",
                    remap_solver_dict(compute_relative_distribution_profile(medians_nonrainy_merged, baseline_label="IDW", dist_labels=labels_n), display_map),
                    labels_n,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_n,
                    x_label=distance_x_label,
                    y_label="Per-patch error-median ratio to IDW\nDot: median, bar: IQR",
                    footnote=(
                        "Metric: |GT(p)-PRED(p)| over non-rainy pixels p.\n"
                        "Each per-patch median is divided by IDW's median in the same distance bin, so IDW is the baseline at 1.0.\n"
                        "Dot = median of those patch-level ratios across patches.\n"
                        "Bar = 25th to 75th percentile of those patch-level ratios across patches."
                    ),
                )
                plot_box_whisker(
                    distance_box_linear_k_img_dir / nonrainy_rel_box_name,
                    nonrainy_rel_box_title,
                    remap_solver_dict(compute_relative_distribution_profile(medians_nonrainy_merged, baseline_label="IDW", dist_labels=labels_n), display_map),
                    labels_n,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_n,
                    x_label=distance_x_label,
                    y_label="Per-patch median non-rainy-pixel error relative to IDW",
                    footnote=None,
                    broken_y=True,
                )
                plot_box_whisker(
                    distance_box_log_k_img_dir / nonrainy_rel_box_name,
                    nonrainy_rel_box_title + " (log scale)",
                    remap_solver_dict(compute_relative_distribution_profile(medians_nonrainy_merged, baseline_label="IDW", dist_labels=labels_n), display_map),
                    labels_n,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_n,
                    x_label=distance_x_label,
                    y_label="Per-patch median non-rainy-pixel error relative to IDW",
                    footnote=None,
                    log_scale=True,
                )
        if distance_major_started:
            finish_major("distance-profile plots")

        if enabled_jatten_k_values and (render_bool(render_config, "plots.jatten_profiles", True) or render_bool(render_config, "plots.jatten_profiles_relative", True)):
            start_major("J_atten plots")
            jatten_major_started = True
            log_progress(f"Rendering J_atten plots for k values {enabled_jatten_k_values}")
        for k in [v for v in jatten_k_values if v in enabled_jatten_k_values]:
            kstr = str(k)
            labels_jatten = list(jatten_dist_labels)
            if prune_bins_enabled:
                labels_jatten = filter_bins_by_zero_fraction(jatten_dist_labels, {str(kb): list(v) for kb, v in jatten_link_bin_counts[kstr].items()}, zero_frac_threshold=prune_bins_zero_frac)
            tick_labels_jatten = build_bin_tick_labels(labels_jatten, {str(kb): list(v) for kb, v in jatten_link_bin_counts[kstr].items()}, count_label="links")
            jatten_medians_display = remap_solver_dict(jatten_medians[kstr], display_map)
            if len(jatten_k_values) == 1 and k == 3:
                jatten_name = "distance_iqr_medians_jatten_multi.png"
                jatten_title = "J_atten by link-distance bin: median across patches with interquartile range"
            else:
                jatten_name = f"distance_iqr_medians_jatten_multi_k{k}.png"
                jatten_title = f"J_atten by link d{k} distance bin: median across patches with interquartile range"
            jatten_box_name = jatten_name.replace(".png", "_box_whisker.png")
            jatten_footnote = (
                f"Each marker summarizes per-patch median J_atten in one link d{k} distance bin. "
                "Vertical segment spans p25 to p75 across patches. Tick labels show average number of links per patch in the bin."
            )
            jatten_box_footnote = (
                f"Box-and-whisker across per-patch median J_atten values in each link d{k} distance bin. "
                "Box = q1 to q3, center line = median, whiskers = min to max."
            )

            if render_bool(render_config, "plots.jatten_profiles", True):
                log_progress(f"J_atten profiles: k={k}") 
                plot_iqr_summary(
                    jatten_iqr_img_dir / jatten_name,
                    jatten_title,
                    jatten_medians_display,
                    labels_jatten,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label="Across-patch summary of per-patch median J_atten",
                    footnote=jatten_footnote,
                )
                plot_box_whisker(
                    jatten_box_img_dir / jatten_box_name,
                    f"{jatten_title} (box-and-whisker view)",
                    jatten_medians_display,
                    labels_jatten,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label="Per-patch median J_atten",
                    footnote=jatten_box_footnote,
                )

            for baseline_label, tag in (("IDW", "idw"), ("ILDW", "ildw")):
                if not render_bool(render_config, "plots.jatten_profiles_relative", True):
                    continue
                if baseline_label not in jatten_medians[kstr]:
                    continue
                log_progress(f"Relative J_atten profiles: k={k}, baseline={baseline_label}")
                rel_profile = compute_relative_distribution_profile(jatten_medians[kstr], baseline_label=baseline_label, dist_labels=jatten_dist_labels)
                rel_profile_display = remap_solver_dict(rel_profile, display_map)
                rel_name = f"distance_iqr_medians_jatten_multi_rel_{tag}.png" if len(jatten_k_values) == 1 and k == 3 else f"distance_iqr_medians_jatten_multi_k{k}_rel_{tag}.png"
                rel_box_name = rel_name.replace(".png", "_box_whisker.png")
                rel_footnote = f"Marker = median across patches; vertical segment = p25 to p75 after dividing each patch by {baseline_label}'s median in the same link-distance bin."
                plot_box_whisker(
                    jatten_box_img_dir / rel_box_name,
                    f"J_atten by link d{k} distance bin relative to {baseline_label} bin median (box-and-whisker view)",
                    rel_profile_display,
                    labels_jatten,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label=f"Per-patch ratio to {baseline_label} bin median",
                    footnote=f"Each per-patch value is divided by {baseline_label}'s median in the same link d{k} distance bin. Box = q1 to q3; whiskers = min to max.",
                )
                plot_iqr_summary(
                    jatten_iqr_img_dir / rel_name,
                    f"J_atten by link d{k} distance bin relative to {baseline_label} bin median",
                    rel_profile_display,
                    labels_jatten,
                    method_order_display,
                    dpi=dpi,
                    bin_spacing=bin_spacing,
                    tick_labels=tick_labels_jatten,
                    x_label="Distance bin (m)\nSecond line: avg links [avg-std, avg+std]",
                    y_label=f"Across-patch summary of ratio to {baseline_label} bin median",
                    footnote=rel_footnote,
                )
        if jatten_major_started:
            finish_major("J_atten plots")

    if link_ratio_entries and render_bool(render_config, "plots.link_ratio_summary", True):
        start_major("link-ratio summary plot")
        log_progress("Rendering link-ratio summary plot")
        entries = [
            (
                apply_solver_display(str(r["solver"]), display_map),
                replace_solver_labels_in_text(str(r["label"]), display_map),
                [float(v) for v in r.get("values", [])],
            )
            for r in link_ratio_entries
        ]
        plot_ratio_iqr_summary(
            summary_img_dir / "link_ratio_summary.png",
            title="Link-metric ratios vs IDW: median across patches with interquartile range",
            entries=entries,
            dpi=dpi,
            footnote="Marker = median across patches; vertical segment spans p25 to p75 across patches. Ratios are computed per patch relative to IDW.",
        )
        plot_ratio_box_whisker(
            summary_img_dir / "link_ratio_summary_box_whisker.png",
            title="Link-metric ratios vs IDW: box-and-whisker across patches",
            entries=entries,
            dpi=dpi,
        )
        finish_major("link-ratio summary plot")

    if patch_map_metrics_plot_data and render_bool(render_config, "plots.patch_map_metrics", True):
        start_major("Patch-map metrics plot")
        log_progress("Rendering patch-level RMSE / bias / correlation boxplots")
        plot_patch_map_metrics_boxplots(
            summary_img_dir / "patch_map_metrics_boxplots.png",
            title="Patch-level map metrics across the benchmark",
            data_by_solver=remap_solver_dict(patch_map_metrics_plot_data, display_map),
            solver_order=solver_order_display,
            corr_ylim=(-1.0, 1.0),
            dpi=dpi,
        )
        plot_patch_map_metrics_boxplots(
            summary_img_dir / "patch_map_metrics_boxplots_readable_corr.png",
            title="Patch-level map metrics across the benchmark",
            data_by_solver=remap_solver_dict(patch_map_metrics_plot_data, display_map),
            solver_order=solver_order_display,
            corr_ylim=(0.65, 1.0),
            dpi=dpi,
        )
        finish_major("Patch-map metrics plot")

    if gtbin and render_bool(render_config, "plots.gt_binned_patchavg", True):
        labels_to_plot = [str(v) for v in gtbin.get("labels_to_plot", [])]
        solver_plot_order = [label for label in solver_order if label in gtbin.get("rel_mean", {})]
        if labels_to_plot and solver_plot_order:
            solver_plot_order_display = [apply_solver_display(label, display_map) for label in solver_plot_order]
            start_major("GT-binned patch-average plots")
            log_progress("Rendering GT-binned patch-average plots")
            bin_count_stats = {str(k): (float(v[0]), float(v[1])) for k, v in gtbin.get("bin_count_stats", {}).items()}
            plot_gt_binned_patchavg_error(
                gtbin_img_dir / "gt_binned_patchavg_relative_abs_error_all_pixels.png",
                title="GT-binned all-pixels error (avg of patch-averaged error ± std)",
                bin_labels=labels_to_plot,
                bin_count_stats=bin_count_stats,
                solver_order=solver_plot_order_display,
                mean_by_solver={apply_solver_display(str(k), display_map): [float(x) for x in v] for k, v in gtbin.get("rel_mean", {}).items()},
                std_by_solver={apply_solver_display(str(k), display_map): [float(x) for x in v] for k, v in gtbin.get("rel_std", {}).items()},
                y_label="Avg patch error (|GT-PRED|/GT; [0,1) uses |GT-PRED|)",
                footnote="Note: For GT in [0,1) mm/h, the metric uses absolute error |GT-PRED| (not RAE).",
                dpi=dpi,
            )
            plot_gt_binned_patchavg_error(
                gtbin_img_dir / "gt_binned_patchavg_absolute_error_all_pixels.png",
                title="GT-binned all-pixels absolute error (avg of patch means ± std)",
                bin_labels=labels_to_plot,
                bin_count_stats=bin_count_stats,
                solver_order=solver_plot_order_display,
                mean_by_solver={apply_solver_display(str(k), display_map): [float(x) for x in v] for k, v in gtbin.get("abs_mean", {}).items()},
                std_by_solver={apply_solver_display(str(k), display_map): [float(x) for x in v] for k, v in gtbin.get("abs_std", {}).items()},
                y_label="Avg patch absolute error |GT-PRED| (mm/h)",
                dpi=dpi,
            )
            finish_major("GT-binned patch-average plots")

    log_progress(f"Wrote plots under: {img_dir}")
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
