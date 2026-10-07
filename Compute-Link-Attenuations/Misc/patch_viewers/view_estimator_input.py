#!/usr/bin/env python3
"""
view_estimator_input.py

Visualize ground-truth rainfall (gt_*.npz) and estimator input links (est_input_*.json)
in the SAME patch-local coordinate frame.

- Background: heatmap of R_gt (mm/h), refined+smoothed, 125m grid
- Overlay: links as line segments colored by attenuation A_db (dB)
- Uses disjoint colormaps:
    * Rain: 'Blues'
    * Links: 'autumn'

Run:
  python view_estimator_input.py --est est_input_<patch_id>.json --gt gt_<patch_id>.npz
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np


def load_est_input(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_gt_npz(path: Path) -> Tuple[np.ndarray, float]:
    z = np.load(path)
    if "R_gt" not in z:
        raise KeyError(f"{path} missing key 'R_gt'")
    R = z["R_gt"]
    px = float(z["pixel_size_m"]) if "pixel_size_m" in z else 125.0
    return R, px


def extent_local_m(H: int, W: int, pixel_size_m: float) -> List[float]:
    # local frame: origin at NW; x east, y south
    width_m = W * pixel_size_m
    height_m = H * pixel_size_m
    return [0.0, width_m, height_m, 0.0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--est", required=True, help="Path to est_input_<patch_id>.json")
    ap.add_argument("--gt", required=True, help="Path to gt_<patch_id>.npz")
    ap.add_argument("--title", default=None, help="Optional figure title override")
    ap.add_argument("--linewidth", type=float, default=1.8, help="Link line width")
    ap.add_argument("--alpha", type=float, default=0.95, help="Link line alpha")
    args = ap.parse_args()

    est_path = Path(args.est).expanduser()
    gt_path = Path(args.gt).expanduser()

    est = load_est_input(est_path)
    R_gt, px = load_gt_npz(gt_path)

    H, W = int(R_gt.shape[0]), int(R_gt.shape[1])
    ext = extent_local_m(H, W, px)

    links: List[Dict[str, Any]] = est.get("links", [])
    if not isinstance(links, list):
        raise TypeError("est_input['links'] must be a list")

    # Collect attenuations for coloring
    atts = []
    for lk in links:
        a = lk.get("A_db", lk.get("attenuation_db", None))
        if a is None:
            continue
        try:
            atts.append(float(a))
        except Exception:
            pass

    # Disjoint colormaps:
    # - Rain (background): Blues
    # - Links (overlay): autumn (warm reds/yellows)
    rain_cmap = plt.get_cmap("Blues")
    link_cmap = plt.get_cmap("autumn")

    if atts:
        amin, amax = min(atts), max(atts)
        if amin == amax:
            amin -= 0.5
            amax += 0.5
        norm = plt.Normalize(vmin=amin, vmax=amax)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=link_cmap)
    else:
        norm = None
        sm = None

    fig, ax = plt.subplots(figsize=(10, 8))

    im = ax.imshow(
        R_gt,
        origin="upper",
        extent=ext,
        interpolation="nearest",
        aspect="equal",
        cmap=rain_cmap,
    )
    cbar_r = fig.colorbar(im, ax=ax, label="Rain rate (mm/h) [GT refined+smoothed]")
    cbar_r.ax.tick_params(labelsize=9)

    # Plot links colored by attenuation (dB)
    for lk in links:
        x0 = float(lk["x0_m"])
        y0 = float(lk["y0_m"])
        x1 = float(lk["x1_m"])
        y1 = float(lk["y1_m"])

        a = lk.get("A_db", lk.get("attenuation_db", None))
        if a is not None and norm is not None:
            col = link_cmap(norm(float(a)))
        else:
            col = "orange"  # still distinct from blue background

        ax.plot([x0, x1], [y0, y1], linewidth=args.linewidth, alpha=args.alpha, color=col)

    # Link colorbar for attenuation
    if sm is not None:
        cbar_a = fig.colorbar(sm, ax=ax, label="Link attenuation A (dB)")
        cbar_a.ax.tick_params(labelsize=9)

    patch_id = est.get("patch_id", None)
    title = args.title or f"Patch {patch_id} — GT rain + links (colored by attenuation)"
    ax.set_title(title)

    ax.set_xlabel("x_local (m) from NW corner (east +)")
    ax.set_ylabel("y_local (m) from NW corner (south +)")

    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])

    plt.show()


if __name__ == "__main__":
    main()
