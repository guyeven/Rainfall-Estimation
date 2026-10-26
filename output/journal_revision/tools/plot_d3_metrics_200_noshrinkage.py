#!/usr/bin/env python3
"""Plot five patchwise metrics by d3 bin for the 200-patch no-shrinkage benchmark."""
from __future__ import annotations

import csv
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[3]
COMPUTE = ROOT / "Compute-Link-Attenuations"
OUT = ROOT / "output/journal_revision/Overleaf_additive_200patches_oct21/Journal_200patches_assets_oct21/images/d3_metrics_200_noshrinkage"
if str(ROOT / "output/journal_revision/tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "output/journal_revision/tools"))
from build_noshrinkage_metrics_tables import (  # noqa: E402
    BINS, BIN_TUPLES, METHODS, SOLUTION_DIRS, WINTER, SUMMER,
    fast_sampled_d3_map,
)
if str(COMPUTE) not in sys.path:
    sys.path.insert(0, str(COMPUTE))
from batch_analyze_multi import assign_bin_labels, load_est_payload  # noqa: E402

COLORS = {
    "IDW": "#667085",
    "ILDW": "#56A8C7",
    "Solver(ILDW)": "#23835C",
    "Convex Solver": "#2563B0",
    "Homotopy Solver": "#D87819",
    "Solver(GT)": "#A13D82",
}
DISPLAY = {"Solver(ILDW)": "Solver(ILDW)", "Convex Solver": "Convex Solver", "Homotopy Solver": "Homotopy Solver", "Solver(GT)": "Solver(GT)"}


def patch_metrics() -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    patch_counts = {b: 0 for b in BINS}
    for season, base in (("Winter", WINTER), ("Summer", SUMMER)):
        for gt_path in sorted((base / "gt_dir").glob("gt_*.npz")):
            patch = gt_path.stem.removeprefix("gt_")
            with np.load(gt_path) as z:
                gt = np.asarray(z["R_gt"], dtype=np.float64)
            est_path = base / "est_dir" / f"est_input_{patch}.json"
            labels = assign_bin_labels(fast_sampled_d3_map(load_est_payload(est_path)), BIN_TUPLES)
            for bin_name in BINS:
                mask = labels == bin_name
                n_pixels = int(np.count_nonzero(mask))
                if not n_pixels:
                    continue
                patch_counts[bin_name] += 1
                truth = gt[mask]
                for method in METHODS:
                    sol_path = (base / "pipeline/solutions" / SOLUTION_DIRS[season.lower()][method]
                                / f"est_input_{patch}_solution.npz")
                    with np.load(sol_path) as z:
                        pred = np.asarray(z["R_hat"], dtype=np.float64)[mask]
                    delta = pred - truth
                    pearson = float(np.corrcoef(truth, pred)[0, 1]) if np.std(truth) and np.std(pred) else 0.0
                    patch_mean_gt = float(np.mean(gt))
                    rows.append({
                        "season": season,
                        "patch": patch,
                        "d3_bin": bin_name,
                        "solver": method,
                        "n_pixels": n_pixels,
                        "rmse_mm_h": float(np.sqrt(np.mean(delta * delta))),
                        "nrmse": float(np.sqrt(np.mean(delta * delta)) / patch_mean_gt),
                        "bias_mm_h": float(np.mean(delta)),
                        "normalized_bias": float(np.mean(delta) / patch_mean_gt),
                        "pearson_r": pearson,
                    })
    if len({r["patch"] for r in rows if r["season"] == "Winter"}) != 100:
        raise RuntimeError("Expected all 100 winter patches")
    if len({r["patch"] for r in rows if r["season"] == "Summer"}) != 100:
        raise RuntimeError("Expected all 100 summer patches")
    return rows, patch_counts


def draw(rows: list[dict], counts: dict[str, int]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "d3_patch_metrics_200.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#667085",
        "axes.labelcolor": "#253047",
        "text.color": "#253047",
        "xtick.color": "#475467",
        "ytick.color": "#475467",
        "savefig.facecolor": "white",
    })
    metrics = [
        ("rmse_mm_h", "RMSE (mm h$^{-1}$)"),
        ("nrmse", "Normalized RMSE"),
        ("bias_mm_h", "Bias (mm h$^{-1}$)"),
        ("normalized_bias", "Normalized bias"),
        ("pearson_r", "Pearson correlation, $r$"),
    ]
    labels = ["IDW", "ILDW", "S(ILDW)", "Convex", "Homotopy", "S(GT)"]
    handles = [plt.Line2D([0], [0], color=COLORS[m], marker="s", markersize=7,
                          linewidth=0, markerfacecolor=COLORS[m], alpha=0.75,
                          label=DISPLAY.get(m, m)) for m in METHODS]
    multipage = OUT / "d3_metric_distributions_200.pdf"
    with PdfPages(multipage) as pdf:
        for key, ylabel in metrics:
            fig, axes = plt.subplots(4, 2, figsize=(8.0, 8.5), squeeze=False)
            fig.suptitle(f"{ylabel} by distance to the third-closest link",
                         x=0.06, y=0.985, ha="left", fontsize=15, fontweight="bold")
            for i, (ax, bin_name) in enumerate(zip(axes.flat, BINS)):
                values = [
                    [r[key] for r in rows if r["d3_bin"] == bin_name and r["solver"] == method]
                    for method in METHODS
                ]
                bp = ax.boxplot(values, patch_artist=True, showfliers=False, whis=(5, 95),
                                medianprops={"color": "#172033", "linewidth": 0.9},
                                whiskerprops={"linewidth": 0.75}, capprops={"linewidth": 0.75},
                                boxprops={"linewidth": 0.8})
                for box, method in zip(bp["boxes"], METHODS):
                    box.set_facecolor(COLORS[method])
                    box.set_edgecolor(COLORS[method])
                    box.set_alpha(0.65)
                for line_index, method in enumerate(METHODS):
                    for line in (bp["whiskers"][2 * line_index:2 * line_index + 2]
                                 + bp["caps"][2 * line_index:2 * line_index + 2]):
                        line.set_color(COLORS[method])
                if key in ("bias_mm_h", "normalized_bias"):
                    ax.axhline(0, color="#344054", linewidth=0.9, linestyle="--", zorder=0)
                finite = np.asarray([v for group in values for v in group], dtype=float)
                if finite.size:
                    lo, hi = np.percentile(finite, [2, 98])
                    span = max(hi - lo, 1e-6)
                    if key in ("rmse_mm_h", "nrmse"):
                        ax.set_ylim(0, max(hi + 0.10 * span, 1e-6))
                    elif key == "pearson_r":
                        ax.set_ylim(max(-1, lo - 0.10 * span), min(1, hi + 0.10 * span))
                    else:
                        ax.set_ylim(lo - 0.12 * span, hi + 0.12 * span)
                ax.set_title(f"{bin_name} m  (n={counts[bin_name]})", fontsize=9, pad=4)
                ax.set_xticks(range(1, len(METHODS) + 1))
                ax.set_xticklabels(labels, rotation=38, ha="right", fontsize=7)
                ax.grid(axis="y", color="#D0D5DD", linestyle=":", linewidth=0.7, alpha=0.9)
                ax.set_axisbelow(True)
                ax.tick_params(axis="y", labelsize=7)
                if i % 2 == 0:
                    ax.set_ylabel(ylabel, fontsize=8)
            fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.53, 0.955),
                       ncol=3, frameon=False, columnspacing=1.8, handletextpad=0.5)
            fig.subplots_adjust(left=0.13, right=0.98, top=0.85, bottom=0.13,
                                hspace=0.64, wspace=0.25)
            footnote = (
                "Each box is one value per contributing patch; center line is the median, box is the IQR, whiskers show the 5th–95th percentiles. "
                "Vertical scales are independently set within each distance bin. Normalized errors divide by the mean ground-truth rain rate over the full patch. No-shrinkage outputs."
            )
            fig.text(0.06, 0.018, textwrap.fill(footnote, width=95),
                     fontsize=7.5, color="#667085", va="bottom")
            stem = OUT / f"d3_{key}_by_bin_200"
            fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
            fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
            fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
            print(stem.with_suffix(".pdf"))
    print(multipage)
    print(f"Rows: {len(rows)}; contributing patches by bin: {counts}")


if __name__ == "__main__":
    csv_path = OUT / "d3_patch_metrics_200.csv"
    if csv_path.exists():
        with csv_path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        mean_gt: dict[tuple[str, str], float] = {}
        bases = {"Winter": WINTER, "Summer": SUMMER}
        for row in rows:
            key = (row["season"], row["patch"])
            if key not in mean_gt:
                with np.load(bases[row["season"]] / "gt_dir" / f"gt_{row['patch']}.npz") as z:
                    mean_gt[key] = float(np.mean(np.asarray(z["R_gt"], dtype=np.float64)))
            row["n_pixels"] = int(row["n_pixels"])
            for name in ("rmse_mm_h", "bias_mm_h", "pearson_r"):
                row[name] = float(row[name])
            row["nrmse"] = row["rmse_mm_h"] / mean_gt[key]
            row["normalized_bias"] = row["bias_mm_h"] / mean_gt[key]
        counts = {b: len({r["patch"] for r in rows if r["d3_bin"] == b}) for b in BINS}
        draw(rows, counts)
    else:
        draw(*patch_metrics())
