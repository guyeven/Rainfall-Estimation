#!/usr/bin/env python3
"""Compare the six Table 3 patch descriptors by season (100 winter, 100 summer)."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COMPUTE = ROOT / "Compute-Link-Attenuations"
OUT = ROOT / "output/journal_revision/Overleaf_additive_200patches_oct21/Journal_200patches_assets_oct21/images/rain_pattern_distributions_200"

DESCRIPTORS = [
    ("wet_fraction", "Fraction of wet pixels", "Fraction (wet: rain $\\geq 0.6$ mm/h)"),
    ("mean_wet_rate_mm_h", "Mean wet rain rate (mm/h)", "Rain rate (mm/h)"),
    ("p95_wet_rate_mm_h", "95th percentile wet rain rate (mm/h)", "Rain rate (mm/h)"),
    ("wet_cv", "Coefficient of variation, wet pixels", "Coefficient of variation"),
    ("area_fraction_above_5", "Fraction of pixels above 5 mm/h", "Fraction of pixels"),
    ("relative_gradient_km_inv", "Relative gradient (mm h$^{-1}$ km$^{-1}$)", "Relative gradient (mm h$^{-1}$ km$^{-1}$)"),
]
SEASONS = [("Winter", "#2563eb"), ("Summer", "#dc2626")]


def compute_rows():
    rows = []
    seasons = [("Winter", COMPUTE / "HundredPatches"), ("Summer", COMPUTE / "June2023HundredPatches")]
    for season, base in seasons:
        for path in sorted((base / "gt_dir").glob("gt_*.npz")):
            patch = path.stem.removeprefix("gt_")
            with np.load(path) as f:
                rain = np.asarray(f["R_gt"], dtype=np.float64)
            wet = rain[rain >= 0.6]
            gy, gx = np.gradient(rain, 0.125)
            mean_rain = float(np.mean(rain))
            rows.append({
                "season": season,
                "patch": patch,
                "wet_fraction": float(wet.size / rain.size),
                "mean_wet_rate_mm_h": float(np.mean(wet)) if wet.size else 0.0,
                "p95_wet_rate_mm_h": float(np.percentile(wet, 95)) if wet.size else 0.0,
                "wet_cv": float(np.std(wet) / np.mean(wet)) if wet.size and np.mean(wet) else 0.0,
                "area_fraction_above_5": float(np.mean(rain > 5.0)),
                "relative_gradient_km_inv": float(np.mean(np.hypot(gx, gy)) / mean_rain) if mean_rain else 0.0,
            })
    for season, _ in SEASONS:
        if sum(r["season"] == season for r in rows) != 100:
            raise ValueError(f"Expected 100 {season.lower()} patches")
    return rows


def save_figure(rows, combined=False):
    all_values_by_key = {
        key: np.asarray([r[key] for r in rows], dtype=float)
        for key, _, _ in DESCRIPTORS
    }
    fig, axes = plt.subplots(2, 3, figsize=(12.2, 7.4))
    fig.suptitle(
        "Rain-pattern descriptor distributions across all 200 benchmark patches"
        if combined else "Rain-pattern descriptor distributions across the 200-patch benchmark",
        x=0.06, y=0.985, ha="left", fontsize=15, fontweight="bold")
    for ax, (key, title, xlabel) in zip(axes.flat, DESCRIPTORS):
        all_values = all_values_by_key[key]
        edges = np.histogram_bin_edges(all_values, bins="fd")
        if len(edges) < 7 or len(edges) > 16:
            edges = np.linspace(float(np.min(all_values)), float(np.max(all_values)), 13)
        if combined:
            ax.hist(all_values, bins=edges, histtype="stepfilled", alpha=0.38,
                    color="#526D82", edgecolor="#526D82", linewidth=1.1,
                    label="All patches (n=200)")
            ax.hist(all_values, bins=edges, histtype="step", color="#34495E", linewidth=1.7)
        else:
            for season, color in SEASONS:
                vals = [r[key] for r in rows if r["season"] == season]
                ax.hist(vals, bins=edges, histtype="stepfilled", alpha=0.36,
                        color=color, edgecolor=color, linewidth=1.1, label=f"{season} (n=100)")
                ax.hist(vals, bins=edges, histtype="step", color=color, linewidth=1.7)
        ax.set_title(title, loc="left", fontweight="bold", pad=7)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Patches")
        ax.set_xlim(edges[0], edges[-1])
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color="#D0D5DD", linestyle=":", linewidth=0.7, alpha=0.9)
        ax.set_axisbelow(True)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.55, 0.94),
               ncol=2 if not combined else 1, frameon=False, columnspacing=2.0, handletextpad=0.6)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.86, bottom=0.09,
                        wspace=0.30, hspace=0.40)
    stem = OUT / ("rain_pattern_histograms_200_combined" if combined else "rain_pattern_histograms_200")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(stem.with_suffix(".pdf"))
    print(stem.with_suffix(".png"))


def main():
    rows = compute_rows()
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "rain_pattern_descriptors_200.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9,
        "axes.titlesize": 10, "axes.labelsize": 8.5,
        "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#667085", "axes.labelcolor": "#253047",
        "text.color": "#253047", "xtick.color": "#475467", "ytick.color": "#475467",
    })
    save_figure(rows, combined=False)
    save_figure(rows, combined=True)
    print(csv_path)


if __name__ == "__main__":
    main()
