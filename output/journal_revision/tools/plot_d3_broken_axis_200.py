#!/usr/bin/env python3
"""Create a broken-y-axis alternative to the 3-panel 200-patch d3 plot."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/journal_revision/Overleaf_additive_200patches_oct21/Journal_200patches_assets_oct21/images/d3_metrics_200_noshrinkage"
CSV = OUT / "d3_patch_metrics_200.csv"
BINS = ["≤125", "(125,375]", "(375,750]", "(750,1500]", "(1500,3125]", "(3125,6000]", "(6000,9000]", ">9000"]
METHODS = ["IDW", "ILDW", "Solver(ILDW)", "Convex Solver", "Homotopy Solver", "Solver(GT)"]
COLORS = {
    "IDW": "#667085", "ILDW": "#56A8C7", "Solver(ILDW)": "#23835C",
    "Convex Solver": "#2563B0", "Homotopy Solver": "#D87819", "Solver(GT)": "#A13D82",
}
XLABELS = ["IDW", "ILDW", "S(ILDW)", "Convex", "Homotopy", "S(GT)"]


def box_data(ax, rows, key, x, offsets, width):
    for j, method in enumerate(METHODS):
        data = [[float(r[key]) for r in rows if r["d3_bin"] == b and r["solver"] == method] for b in BINS]
        bp = ax.boxplot(
            data, positions=x + offsets[j], widths=width * 0.86, patch_artist=True,
            showfliers=False, whis=(5, 95),
            medianprops={"color": "#172033", "linewidth": 0.9},
            whiskerprops={"color": COLORS[method], "linewidth": 0.75},
            capprops={"color": COLORS[method], "linewidth": 0.75},
            boxprops={"color": COLORS[method], "linewidth": 0.8},
        )
        for b in bp["boxes"]:
            b.set_facecolor(COLORS[method])
            b.set_alpha(0.65)


def break_marks(ax_top, ax_bottom):
    d = 0.009
    kwargs = dict(color="#344054", clip_on=False, linewidth=1.0)
    for x in (0, 1):
        ax_top.plot((x - d, x + d), (-d, d), transform=ax_top.transAxes, **kwargs)
        ax_bottom.plot((x - d, x + d), (1 - d, 1 + d), transform=ax_bottom.transAxes, **kwargs)


def main():
    with CSV.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"No patch data in {CSV}")

    counts = {b: len({(r["season"], r["patch"]) for r in rows if r["d3_bin"] == b}) for b in BINS}
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 10,
        "axes.labelsize": 9, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#667085", "axes.labelcolor": "#253047",
        "text.color": "#253047", "xtick.color": "#475467", "ytick.color": "#475467",
    })
    fig = plt.figure(figsize=(12.4, 10.0))
    gs = GridSpec(6, 1, figure=fig, height_ratios=[1.45, 0.65, 1.0, 0.55, 0.75, 0.9], hspace=0.17)
    ax_rmse = fig.add_subplot(gs[0])
    ax_bias_high = fig.add_subplot(gs[1], sharex=ax_rmse)
    ax_bias_zoom = fig.add_subplot(gs[2], sharex=ax_rmse)
    ax_bias_low = fig.add_subplot(gs[3], sharex=ax_rmse)
    ax_corr_high = fig.add_subplot(gs[4], sharex=ax_rmse)
    ax_corr_low = fig.add_subplot(gs[5], sharex=ax_rmse)
    axes = [ax_rmse, ax_bias_high, ax_bias_zoom, ax_bias_low, ax_corr_high, ax_corr_low]

    x = np.arange(1, len(BINS) + 1, dtype=float)
    width = 0.115
    offsets = (np.arange(len(METHODS)) - (len(METHODS) - 1) / 2) * width
    box_data(ax_rmse, rows, "rmse_mm_h", x, offsets, width)
    box_data(ax_bias_high, rows, "bias_mm_h", x, offsets, width)
    box_data(ax_bias_zoom, rows, "bias_mm_h", x, offsets, width)
    box_data(ax_bias_low, rows, "bias_mm_h", x, offsets, width)
    box_data(ax_corr_high, rows, "pearson_r", x, offsets, width)
    box_data(ax_corr_low, rows, "pearson_r", x, offsets, width)

    ax_rmse.set_title("RMSE (mm h$^{-1}$)", loc="left", fontweight="bold", pad=6)
    ax_bias_high.set_title("Bias (mm h$^{-1}$)", loc="left", fontweight="bold", pad=5)
    ax_corr_high.set_title("Pearson correlation, $r$", loc="left", fontweight="bold", pad=5)
    ax_rmse.set_ylim(0, 8.0)
    ax_bias_high.set_ylim(0.30, 4.0)
    ax_bias_zoom.set_ylim(-0.20, 0.20)
    ax_bias_low.set_ylim(-1.05, -0.30)
    ax_corr_high.set_ylim(0.86, 1.005)
    ax_corr_low.set_ylim(-1.02, 0.82)
    ax_bias_high.spines["bottom"].set_visible(False)
    ax_bias_zoom.spines["top"].set_visible(False)
    ax_bias_zoom.spines["bottom"].set_visible(False)
    ax_bias_low.spines["top"].set_visible(False)
    ax_corr_high.spines["bottom"].set_visible(False)
    ax_corr_low.spines["top"].set_visible(False)
    break_marks(ax_bias_high, ax_bias_zoom)
    break_marks(ax_bias_zoom, ax_bias_low)
    break_marks(ax_corr_high, ax_corr_low)

    for ax in axes:
        ax.set_xlim(0.5, len(BINS) + 0.5)
        ax.grid(axis="y", color="#D0D5DD", linestyle=":", linewidth=0.7, alpha=0.9)
        ax.set_axisbelow(True)
    ax_rmse.set_xticks(x)
    ax_rmse.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_bias_high.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_bias_zoom.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_bias_low.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_corr_high.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_corr_low.set_xticks(x)
    ax_corr_low.set_xticklabels([f"{b}\n$n={counts[b]}$" for b in BINS])
    ax_corr_low.set_xlabel("Distance to third-closest link, $d_3$ (m)", labelpad=6)

    handles = [plt.Line2D([0], [0], color=COLORS[m], marker="s", markersize=6,
                          linewidth=0, markerfacecolor=COLORS[m], alpha=0.75,
                          label=m) for m in METHODS]
    fig.suptitle("Patchwise reconstruction metrics by distance to the third-closest link",
                 x=0.07, y=0.99, ha="left", fontsize=14, fontweight="bold")
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.57, 0.966),
               ncol=3, frameon=False, columnspacing=1.8, handletextpad=0.5)
    fig.text(0.07, 0.012,
             "Boxes: IQR; center line: median; whiskers: 5th–95th percentiles. Bias omits (−0.30,−0.20) and (0.20,0.30) mm h$^{-1}$; Pearson omits 0.82–0.86. No-shrinkage outputs.",
             fontsize=7.5, color="#667085")
    fig.subplots_adjust(left=0.105, right=0.985, top=0.91, bottom=0.08)
    stem = OUT / "d3_rmse_bias_pearson_boxplots_200_broken_y"
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(stem.with_suffix(".pdf"))
    print(stem.with_suffix(".png"))


if __name__ == "__main__":
    main()
