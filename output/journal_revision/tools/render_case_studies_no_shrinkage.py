#!/usr/bin/env python3
"""Render the two Journal case studies with saved no-shrinkage solver outputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
COMPUTE = ROOT / "Compute-Link-Attenuations"
ASSETS = ROOT / "output/journal_revision/Overleaf_additive_200patches_oct21/Journal_200patches_assets_oct21/images"
WINTER = COMPUTE / "HundredPatches"
CASES = [
    ("RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301280900_patch000", "case1", "Black Sea coast, Romania | 01/28/2023 09:00", (448, 270, 1022, 1125)),
    ("RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301310900_patch000", "case2", "Northern Norway | 01/31/2023 09:00", (448, 471, 1022, 923)),
]
SOLVERS = [
    ("IDW", "sol_dir_idw"),
    ("Solver(GT)", "sol_dir_solver_gt_no_shrinkage"),
    ("Convex Solver", "sol_dir_convex_no_shrinkage"),
]


def load_npz(path: Path, key: str) -> np.ndarray:
    with np.load(path) as data:
        return np.asarray(data[key], dtype=np.float64)


def composite_case(patch: str, case_id: str, title: str, map_crop) -> Path:
    gt = load_npz(WINTER / "gt_dir" / f"gt_{patch}.npz", "R_gt")
    source_map = ASSETS / "case_studies/new_pattern_one" / f"{patch}.png"
    with Image.open(source_map) as im:
        map_panel = np.asarray(im.crop(map_crop).convert("RGB"))
    rainy = gt >= 0.6
    predictions = []
    for label, solver_dir in SOLVERS:
        pred = load_npz(WINTER / "pipeline/solutions" / solver_dir / f"est_input_{patch}_solution.npz", "R_hat")
        if pred.shape != gt.shape:
            raise ValueError(f"Shape mismatch for {patch}/{label}: {gt.shape} and {pred.shape}")
        rel = np.full_like(gt, np.nan)
        valid = rainy & np.isfinite(gt) & np.isfinite(pred) & (gt != 0)
        rel[valid] = (pred[valid] - gt[valid]) / gt[valid]
        predictions.append((label, pred, rel))
    vmax = max(float(np.max(gt)), *(float(np.nanmax(p)) for _, p, _ in predictions))
    rel_values = np.concatenate([r[np.isfinite(r)] for _, _, r in predictions])
    rel_max = max(float(np.max(np.abs(rel_values))), 1e-9)

    fig = plt.figure(figsize=(24.0, 9.2), dpi=150)
    gs = GridSpec(2, 5, figure=fig, width_ratios=[1.45, 1.35, 1.0, 1.0, 1.0], hspace=0.22, wspace=0.28)
    ax_map = fig.add_subplot(gs[:, 0])
    ax_map.imshow(map_panel)
    ax_map.set_title("Map", fontsize=12)
    ax_map.set_xticks([]); ax_map.set_yticks([])

    ax_gt = fig.add_subplot(gs[:, 1])
    im = ax_gt.imshow(gt, cmap="viridis", vmin=0, vmax=vmax)
    ax_gt.set_title("Ground Truth", fontsize=12)
    ax_gt.set_xticks([]); ax_gt.set_yticks([])
    fig.colorbar(im, ax=ax_gt, fraction=0.046, pad=0.03)

    for col, (label, pred, rel) in enumerate(predictions, start=2):
        top = fig.add_subplot(gs[0, col])
        bot = fig.add_subplot(gs[1, col])
        im = top.imshow(pred, cmap="viridis", vmin=0, vmax=vmax)
        top.set_title(label, fontsize=10)
        top.set_xticks([]); top.set_yticks([])
        fig.colorbar(im, ax=top, fraction=0.046, pad=0.03)
        rel_cmap = plt.get_cmap("seismic").copy()
        rel_cmap.set_bad("#7a7a7a")
        im = bot.imshow(rel, cmap=rel_cmap, vmin=-rel_max, vmax=rel_max)
        bot.contour((~rainy).astype(float), levels=[0.5], colors="white", linewidths=0.8, linestyles="--")
        bot.set_title("(predicted - observed)/observed\nrainy pixels only; gray = non-rainy", fontsize=10)
        bot.set_xticks([]); bot.set_yticks([])
        fig.colorbar(im, ax=bot, fraction=0.046, pad=0.03)
    fig.suptitle(f"{title}\nGround Truth, solver predictions, and signed relative error over rainy pixels", fontsize=14, y=.99)
    fig.tight_layout(rect=(.01, .01, .99, .82))
    out = ASSETS / "case_studies/no_shrinkage" / f"{patch}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


def objective_traces(patch: str, case_id: str, title: str) -> list[Path]:
    sys.path.insert(0, str(COMPUTE))
    import render_analysis_report as renderer  # noqa: E402

    out_dir = ASSETS / "j_behavior/no_shrinkage"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for short, solver_dir, label in (
        ("gt", "sol_dir_solver_gt_no_shrinkage", "Solver(GT)"),
        ("convex", "sol_dir_convex_no_shrinkage", "Convex Solver"),
    ):
        trace = WINTER / "pipeline/solutions" / solver_dir / f"est_input_{patch}_solution_itertrace.json"
        payload = json.loads(trace.read_text())
        output = out_dir / f"{case_id}-{short}-iterations.png"
        renderer.plot_j_behavior(output, title=f"Objective trace for {label}\n{title}", iterations=payload.get("iterations", []), dpi=150)
        outputs.append(output)
    return outputs


def main():
    for patch, case_id, title, map_crop in CASES:
        print(composite_case(patch, case_id, title, map_crop))
        for path in objective_traces(patch, case_id, title):
            print(path)


if __name__ == "__main__":
    main()
