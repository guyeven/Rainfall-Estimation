"""Generate the Taylor-diagram figures used in the defense deck.

Reads the saved patch-level Taylor statistics; no reconstruction is rerun.
"""
from pathlib import Path
import json
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

PROJECT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "images"
DATA = PROJECT / "output/taylor_unnormalized/statistics.json"
OUT.mkdir(parents=True, exist_ok=True)
report = json.loads(DATA.read_text())

METHODS = [
    ("IDW", "#667085", "s"),
    ("ILDW", "#56A8C7", "^"),
    ("Solver(ILDW)", "#23835C", "D"),
    ("Solver(GT)", "#2563B0", "o"),
    ("Convex solver", "#D87819", "o"),
    ("Homotopy solver", "#A13D82", "P"),
]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.labelcolor": "#253047",
    "xtick.color": "#4B5563",
    "ytick.color": "#4B5563",
    "text.color": "#253047",
    "savefig.facecolor": "white",
})


def draw_axes(ax, reference, rmax, normalized):
    ax.set_thetamin(0)
    ax.set_thetamax(90)
    ax.set_ylim(0, rmax)
    correlations = np.array([0, .4, .6, .8, .9, .95, .99, 1.0])
    ax.set_thetagrids(np.degrees(np.arccos(correlations)),
                      [f"{x:g}" for x in correlations])
    ax.set_rlabel_position(67)
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.grid(color="#DDE3EA", linewidth=.7)
    ax.spines["polar"].set_color("#98A2B3")

    theta, radius = np.meshgrid(
        np.linspace(0, np.pi / 2, 240), np.linspace(0, rmax, 240)
    )
    centered_error = np.sqrt(np.maximum(
        0, radius**2 + reference**2 - 2 * radius * reference * np.cos(theta)
    ))
    levels = np.arange(.25, rmax, .25) if normalized else np.arange(.5, rmax, .5)
    contours = ax.contour(theta, radius, centered_error, levels=levels,
                          colors="#73967D", linestyles="--", linewidths=.75)
    ax.clabel(contours, fontsize=6.5, inline=True, fmt="%.2g")
    ax.plot(0, reference, marker="*", color="#18253B", markersize=10,
            linestyle="None", clip_on=False)
    # The correlation tick labels already annotate the angle.  A long xlabel
    # collides with them on polar axes; explain both encodings in slide text.


def normalized_summary(rows):
    ratios = np.array([p["model_sd"] / p["reference_sd"] for p in rows])
    correlations = np.array([p["correlation"] for p in rows])
    std_ratio = float(np.sqrt(np.mean(ratios**2)))
    corr = float(np.mean(ratios * correlations) / std_ratio)
    centered_error = float(np.sqrt(np.mean(ratios**2 + 1 - 2 * ratios * correlations)))
    return std_ratio, corr, centered_error


# One aggregate point per method, in physical units (mm/h).
summary = {row["method"]: row for row in report["summary"]}
reference_sd = summary["IDW"]["reference_sd"]
fig = plt.figure(figsize=(7.3, 5.3))
ax = fig.add_axes([.025, .07, .70, .86], projection="polar")
draw_axes(ax, reference_sd, 3.75, False)
for method, color, marker in METHODS:
    raw = summary[method]
    ax.plot(np.arccos(np.clip(raw["correlation"], -1, 1)), raw["model_sd"],
                 marker=marker, color=color, markersize=7, linestyle="None")

legend = [Line2D([], [], marker=marker, linestyle="None", color=color,
                 markersize=7, label=method)
          for method, color, marker in METHODS]
fig.legend(handles=legend, loc="center left", frameon=False,
           bbox_to_anchor=(.75, .50), fontsize=8)
fig.savefig(OUT / "taylor-aggregate-comparison.png", dpi=220,
            bbox_inches="tight", facecolor="white")
plt.close(fig)


# Patch-level clouds for the methods requested for the follow-up slide.
selected = [
    ("IDW", "#667085"),
    ("ILDW", "#56A8C7"),
    ("Convex solver", "#D87819"),
]
fig, axes = plt.subplots(
    1, 3, figsize=(13.2, 5.2),
    subplot_kw={"projection": "polar"},
    gridspec_kw={"wspace": .48},
)
for ax, (method, color) in zip(axes, selected):
    rows = report["individual"][method]
    ratios = np.array([p["model_sd"] / p["reference_sd"] for p in rows])
    correlations = np.array([p["correlation"] for p in rows])
    draw_axes(ax, 1.0, 1.17, True)
    ax.set_title(method, pad=17, fontsize=11, fontweight="bold", color=color)
    ax.scatter(np.arccos(np.clip(correlations, -1, 1)), ratios,
               s=13, c=color, alpha=.48, edgecolors="none", zorder=3)
    pooled_ratio, pooled_corr, _ = normalized_summary(rows)
    ax.plot(np.arccos(np.clip(pooled_corr, -1, 1)), pooled_ratio,
            marker="D", color="#18253B", markersize=5, linestyle="None", zorder=5)

fig.text(.5, .005,
         "100 dots per method (one per patch)  ·  black star: reference  ·  black diamond: pooled moments  ·  dashed arcs: centered RMSE",
         ha="center", va="bottom", fontsize=8, color="#4B5563")
fig.subplots_adjust(left=.01, right=.99, top=.88, bottom=.16)
fig.savefig(OUT / "taylor-selected-patch-clouds.png", dpi=220,
            bbox_inches="tight", facecolor="white")
plt.close(fig)

print("Wrote Taylor figures from saved patch statistics:")
print(OUT / "taylor-aggregate-comparison.png")
print(OUT / "taylor-selected-patch-clouds.png")
