#!/usr/bin/env python3
"""Render the case-study panels, the map panels and the w-labelled objective traces.

Layout follows output/journal_revision/tools/render_case_studies_no_shrinkage.py (branch oct26).
The map is drawn from OpenStreetMap zoom-7 tiles in ../osm_tiles_z7 (no network access):
view = patch bounding box enlarged by 4 times its width and height on each side, patch outlined in red.

Usage:  python render_case_figures.py [--out DIR]
Without --out the figures are written to <case dir>/figures/, overwriting the stored copies.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES, TILES, ZOOM, SOLVER_DIRS, gt_path, solution_path  # noqa: E402
from jplot_w import plot_j_behavior  # noqa: E402


def world_pixel(lon, lat, zoom):
    scale = 256.0 * (2**zoom)
    return scale * (lon + 180.0) / 360.0, scale * (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0


def make_map(clat, clon, wkm, hkm):
    hh = (hkm / 2.0) / 111.32
    hw = (wkm / 2.0) / (111.32 * math.cos(math.radians(clat)))
    lo0, lo1, la0, la1 = clon - hw, clon + hw, clat - hh, clat + hh
    lp, ap = 4.0 * (lo1 - lo0), 4.0 * (la1 - la0)
    left, top = world_pixel(lo0 - lp, la1 + ap, ZOOM)
    right, bottom = world_pixel(lo1 + lp, la0 - ap, ZOOM)
    xs = list(range(int(left // 256), int(right // 256) + 1))
    ys = list(range(int(top // 256), int(bottom // 256) + 1))
    mosaic = Image.new("RGB", (len(xs) * 256, len(ys) * 256))
    for c, x in enumerate(xs):
        for r, y in enumerate(ys):
            mosaic.paste(Image.open(TILES / f"{x}_{y}.png").convert("RGB"), (c * 256, r * 256))
    ox, oy = xs[0] * 256, ys[0] * 256
    img = mosaic.crop((round(left - ox), round(top - oy), round(right - ox), round(bottom - oy)))
    px0, py0 = world_pixel(lo0, la1, ZOOM)
    px1, py1 = world_pixel(lo1, la0, ZOOM)
    ImageDraw.Draw(img).rectangle((round(px0 - left), round(py0 - top), round(px1 - left), round(py1 - top)),
                                  outline="#d62828", width=4)
    return np.asarray(img)


def load(path, key):
    with np.load(path) as d:
        return np.asarray(d[key], dtype=np.float64)


def composite_case(c, out_dir):
    patch = c["patch"]
    gt = load(gt_path(c), "R_gt")
    map_panel = make_map(*c["geo"])
    rainy = gt >= 0.6
    predictions = []
    for label in SOLVER_DIRS:
        pred = load(solution_path(c, label), "R_hat")
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
        top = fig.add_subplot(gs[0, col]); bot = fig.add_subplot(gs[1, col])
        im = top.imshow(pred, cmap="viridis", vmin=0, vmax=vmax)
        top.set_title(label, fontsize=10)
        top.set_xticks([]); top.set_yticks([])
        fig.colorbar(im, ax=top, fraction=0.046, pad=0.03)
        rel_cmap = plt.get_cmap("seismic").copy(); rel_cmap.set_bad("#7a7a7a")
        im = bot.imshow(rel, cmap=rel_cmap, vmin=-rel_max, vmax=rel_max)
        bot.contour((~rainy).astype(float), levels=[0.5], colors="white", linewidths=0.8, linestyles="--")
        bot.set_title("(predicted - observed)/observed\nrainy pixels only; gray = non-rainy", fontsize=10)
        bot.set_xticks([]); bot.set_yticks([])
        fig.colorbar(im, ax=bot, fraction=0.046, pad=0.03)
    fig.suptitle(f"{c['title']}\nGround Truth, solver predictions, and signed relative error over rainy pixels", fontsize=14, y=.99)
    fig.tight_layout(rect=(.01, .01, .99, .82))
    out = out_dir / f"{patch}.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    map_out = out_dir / f"map_{c['case']}.png"
    Image.fromarray(map_panel).save(map_out)
    return [out, map_out]


def objective_traces(c, out_dir):
    outs = []
    for short, label in (("gt", "Solver(GT)"), ("convex", "Convex Solver")):
        it = json.loads(solution_path(c, label, "_itertrace.json").read_text()).get("iterations", [])
        out = out_dir / f"{c['case']}-{short}-iterations.png"
        plot_j_behavior(out, title=f"Objective trace for {label}\n{c['title']}", iterations=it, dpi=150)
        outs.append(out)
    return outs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="write all figures to this directory instead of <case>/figures")
    args = ap.parse_args()
    for c in CASES:
        out_dir = args.out if args.out is not None else c["dir"] / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)
        for p in composite_case(c, out_dir) + objective_traces(c, out_dir):
            print(p)


if __name__ == "__main__":
    main()
