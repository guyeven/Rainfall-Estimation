"""Objective-trace plot used for the case-study figures.

Copy of plot_j_behavior from Compute-Link-Attenuations/render_analysis_report.py (branch oct26).
The only change is in the legend labels: the weights are written w_* (as in the paper) instead of alpha_*.
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

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

    series_colors: Dict[str, str] = {
        r"$J$": "#1f77b4",
        r"$w_{\mathrm{atten}} \cdot J_{\mathrm{atten}}$": "#ff7f0e",
        r"$w_{1d} \cdot J_{1d}$": "#2ca02c",
        r"$w_{\mathrm{total}} \cdot J_{\mathrm{total}}$": "#d62728",
        r"$w_{2d} \cdot J_{2d}$": "#9467bd",
    }

    def series_style(label: str, linewidth: float, color: Optional[str] = None) -> Dict[str, Any]:
        base_color = series_colors.get(label, color)
        if label == r"$J$":
            return {
                "color": base_color or "#1f77b4",
                "linewidth": max(1.8, linewidth + 0.6),
                "markersize": 2.6,
                "alpha": 1.0,
                "zorder": 5,
            }
        return {
            "color": base_color,
            "linewidth": linewidth,
            "markersize": 2.0,
            "alpha": 0.8,
            "zorder": 3,
        }

    def build_series(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Tuple[str, List[float], float]], List[float]]:
        j_series: List[Tuple[str, List[float], float]] = [
            (r"$J$", series_from_rows(rows, "J_weighted_sum"), 1.0),
            (r"$w_{\mathrm{atten}} \cdot J_{\mathrm{atten}}$", weighted_or_raw_from_rows(rows, "weighted_J_atten", "J_atten"), 0.9),
            (r"$w_{1d} \cdot J_{1d}$", weighted_or_raw_from_rows(rows, "weighted_J_1d", "J_1d"), 0.9),
            (r"$w_{\mathrm{total}} \cdot J_{\mathrm{total}}$", weighted_or_raw_from_rows(rows, "weighted_J_total", "J_total"), 0.9),
            (r"$w_{2d} \cdot J_{2d}$", weighted_or_raw_from_rows(rows, "weighted_J_2d", "J_2d"), 0.9),
        ]
        weighted_sum = j_series[0][1]
        if not weighted_sum or all(math.isnan(v) for v in weighted_sum):
            j_series[0] = (r"$J$", series_from_rows(rows, "J_native_total"), 1.0)
        return j_series, j_series[0][1]

    def draw_series(ax: Any, xs_local: Sequence[int], j_series: Sequence[Tuple[str, List[float], float]], *, lower_only: bool = False, upper_only: bool = False, cutoff: Optional[float] = None, show_legend: bool = True) -> None:
        for label, vals, linewidth in j_series:
            arr = np.asarray(vals, dtype=np.float64)
            if cutoff is not None:
                if lower_only:
                    arr = np.where(arr <= cutoff, arr, np.nan)
                elif upper_only:
                    arr = np.where(arr > cutoff, arr, np.nan)
            style = series_style(label, linewidth)
            ax.plot(xs_local, arr, marker="o", label=(label if show_legend else None), **style)

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
        for tick_value, tick_label in zip(deduped, ax.get_yticklabels()):
            if abs(tick_value - final_value) <= 1e-9:
                tick_label.set_bbox(
                    {
                        "facecolor": "#1f77b4",
                        "edgecolor": "#1f77b4",
                        "boxstyle": "round,pad=0.22",
                        "linewidth": 0.8,
                        "alpha": 1.0,
                    }
                )
                tick_label.set_color("white")
                tick_label.set_zorder(6)
            else:
                tick_label.set_bbox(None)
                tick_label.set_color("black")
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
            fig, ax = plt.subplots(figsize=(8.5, 6.0), dpi=dpi)
            draw_series(ax, xs_local, j_series)
            ax.set_ylim(bottom=0.0)
            ax.set_title(fig_title, pad=6)
            ax.legend(loc="best", fontsize=8)
            finite_weighted_sum = finite_values(weighted_sum)
            if finite_weighted_sum.size:
                add_final_weighted_sum_marker(ax, float(finite_weighted_sum[-1]))
            axes = [ax]

        ax.set_xlabel("Iteration")
        for axis in axes:
            axis.grid(axis="y", alpha=0.25)
        fig.supylabel("Weighted objective contribution", x=0.015, y=0.47)
        fig.subplots_adjust(left=0.13, right=0.95, bottom=0.14, top=0.90)
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
    for ax, (stage_id, beta, rows) in zip(axes, stage_rows):
        xs_local = list(range(len(rows)))
        j_series, weighted_sum = build_series(rows)
        for idx, (label, vals, linewidth) in enumerate(j_series):
            arr = np.asarray(vals, dtype=np.float64)
            style = series_style(label, linewidth)
            ax.plot(xs_local, arr, marker="o", label=label, **style)
        ax.set_ylim(bottom=0.0)
        finite_weighted_sum = finite_values(weighted_sum)
        if finite_weighted_sum.size:
            add_final_weighted_sum_marker(ax, float(finite_weighted_sum[-1]))
        inner_iters = max(0, len(rows) - 1)
        beta_str = f"{beta:.2f}" if math.isfinite(beta) else "NA"
        ax.set_title(f"Stage {stage_id + 1} (beta={beta_str}, inner iterations={inner_iters})", fontsize=10)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Inner iteration within stage")
    fig.supylabel("Weighted objective contribution", x=0.015, y=0.5)
    fig.suptitle(title)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
    fig.savefig(out_png, dpi=dpi)
    plt.close(fig)


