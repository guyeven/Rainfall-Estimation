#!/usr/bin/env python3
"""Regenerate the 200-patch rainy-RAE and dry-AE d3 boxplots.

The optimized solver series come from the winter and summer no-shrinkage
analysis caches. IDW and ILDW are unchanged by shrinkage, so their series come
from the corresponding season's standard analysis caches.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import gaussian_kde

from render_analysis_report import plot_box_whisker


ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / "Compute-Link-Attenuations"
WINTER = PIPE / "HundredPatches" / "pipeline"
SUMMER = PIPE / "June2023HundredPatches" / "pipeline"
SUMMER_FINAL = SUMMER / "June2023HundredPatches" / "pipeline" / "batch_analyze_output_final"
OUT = (
    ROOT
    / "output/journal_revision/Overleaf_additive_200patches_oct21"
    / "Journal_200patches_assets_oct21/images/distance_profiles_box_whisker/no_shrinkage"
)


def load(path: Path) -> dict:
    with path.open() as stream:
        return json.load(stream)


winter_base = load(WINTER / "batch_analyze_output/stats_report_cache.json")
summer_base = load(SUMMER_FINAL / "stats_report_cache.json")
winter_ns = load(WINTER / "batch_analyze_output_no_shrinkage/stats_report_cache.json")
summer_ns = load(SUMMER / "batch_analyze_output_no_shrinkage/stats_report_cache.json")

labels = winter_ns["labels"]["dist_labels"]
methods = ["IDW", "ILDW", "Solver(ILDW)", "Convex Solver", "Homotopy Solver", "Solver(GT)"]
sources = {
    "IDW": (winter_base, "IDW", summer_base, "IDW"),
    "ILDW": (winter_base, "ILDW", summer_base, "ILDW"),
    "Solver(ILDW)": (winter_ns, "Solver(ILDW) no shrinkage", summer_ns, "Solver(ILDW) no shrinkage"),
    "Convex Solver": (winter_ns, "Convex Solver no shrinkage", summer_ns, "Convex Solver no shrinkage"),
    "Homotopy Solver": (winter_ns, "Homotopy Solver no shrinkage", summer_ns, "Homotopy Solver no shrinkage"),
    "Solver(GT)": (winter_ns, "Solver(GT) no shrinkage", summer_ns, "Solver(GT) no shrinkage"),
}


def combined_values(plot_key: str) -> dict[str, dict[str, list[float]]]:
    combined: dict[str, dict[str, list[float]]] = {}
    for display_name in methods:
        wc, winter_name, sc, summer_name = sources[display_name]
        combined[display_name] = {}
        for label in labels:
            winter_vals = wc["plot_data"][plot_key]["3"].get(winter_name, {}).get(label, [])
            summer_vals = sc["plot_data"][plot_key]["3"].get(summer_name, {}).get(label, [])
            combined[display_name][label] = list(winter_vals) + list(summer_vals)
    return combined


OUT.mkdir(parents=True, exist_ok=True)
for kind, key, title, y_label in [
    (
        "rainy",
        "medians_rainy",
        "Distribution of patch-level median RAE over rainy pixels by distance bin",
        "Median rainy-pixel RAE per patch",
    ),
    (
        "nonrainy",
        "medians_nonrainy",
        "Distribution of patch-level median AE over non-rainy pixels by distance bin",
        "Median non-rainy-pixel AE per patch (mm/h)",
    ),
]:
    values = combined_values(key)
    plot_box_whisker(
        OUT / f"distance_iqr_medians_{kind}_multi_k3_box_whisker.png",
        title,
        values,
        labels,
        methods,
        dpi=180,
        x_label="d3 bin (m)",
        y_label=y_label,
        broken_y=True,
    )
    print(f"Wrote {kind} boxplot to {OUT}")


def plot_raincloud_preview() -> None:
    """Draw a small-multiple raincloud alternative for the wet-pixel RAE."""
    key = "medians_rainy"
    values_by_method = combined_values(key)
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"][: len(methods)]
    linthresh = 0.01
    fig, axs = plt.subplots(2, 3, figsize=(19, 10), sharey=True)
    rng = np.random.default_rng(12)
    all_vals = [
        v
        for method in methods
        for label in labels
        for v in values_by_method[method][label]
        if np.isfinite(v)
    ]
    ymax = max(all_vals) if all_vals else 1.0
    ymin = min(all_vals) if all_vals else 0.0
    y_low = min(0.0, ymin)
    y_high = ymax * 1.08
    z_low = np.arcsinh(y_low / linthresh)
    z_high = np.arcsinh(y_high / linthresh)
    z_grid = np.linspace(z_low, z_high, 220)
    y_grid = linthresh * np.sinh(z_grid)

    for ax, method, color in zip(axs.flat, methods, colors):
        for i, label in enumerate(labels):
            raw = np.asarray(values_by_method[method][label], dtype=float)
            vals = raw[np.isfinite(raw)]
            if vals.size == 0:
                continue
            z_vals = np.arcsinh(vals / linthresh)
            if vals.size > 1 and float(np.std(z_vals)) > 1e-9:
                density = gaussian_kde(z_vals)(z_grid)
            else:
                center = float(np.mean(z_vals))
                density = np.exp(-0.5 * ((z_grid - center) / 0.025) ** 2)
            width = 0.31 * density / max(float(np.max(density)), 1e-12)
            ax.fill_betweenx(y_grid, i - width, i, color=color, alpha=0.28, linewidth=0)

            jitter = rng.uniform(0.025, 0.13, size=vals.size)
            ax.scatter(
                i + jitter,
                vals,
                s=5,
                color=color,
                alpha=0.16,
                linewidths=0,
                rasterized=True,
                zorder=2,
            )
            q1, median, q3 = np.percentile(vals, [25, 50, 75])
            ax.vlines(i + 0.18, q1, q3, color=color, linewidth=2.1, zorder=4)
            ax.hlines(median, i + 0.13, i + 0.23, color="#202938", linewidth=1.5, zorder=5)

        ax.set_title(method, color=color, fontsize=12, fontweight="bold", loc="left")
        ax.set_xlim(-0.42, len(labels) - 0.55)
        ax.set_xticks(range(len(labels)))
        counts = [len(values_by_method[method][lab]) for lab in labels]
        ax.set_xticklabels(
            [f"{label}\n$n$={count}" for label, count in zip(labels, counts)],
            rotation=28,
            ha="right",
            fontsize=7.5,
        )
        ax.set_yscale("symlog", linthresh=linthresh, linscale=1.0)
        ax.set_ylim(y_low, y_high)
        ax.grid(axis="y", which="both", linestyle=":", linewidth=0.55, alpha=0.4)
        ax.set_xlabel("$d_3$ bin (m)", fontsize=9)

    for ax in axs[:, 0]:
        ax.set_ylabel("Patch-level median rainy-pixel RAE", fontsize=9)
    fig.suptitle("Raincloud view of wet-pixel error by $d_3$ bin", fontsize=17, fontweight="bold", y=0.99)
    fig.text(
        0.5,
        0.015,
        "One distribution per solver and distance bin · half-violin = density · dots = patches · vertical bar = IQR, dark mark = median · symlog axis",
        ha="center",
        fontsize=9,
        color="#596273",
    )
    fig.tight_layout(rect=(0.02, 0.06, 0.99, 0.96), h_pad=2.0, w_pad=1.5)
    out = OUT / "distance_iqr_medians_rainy_multi_k3_raincloud_preview.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote rainy RAE raincloud preview to {out}")


plot_raincloud_preview()
