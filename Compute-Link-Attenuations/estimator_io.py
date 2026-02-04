"""Estimator I/O helpers.

We export per-patch estimator input in a patch-local coordinate frame:

- Origin is the NW corner of the patch in RD meters: (x_min, y_max)
- Local meters:
    x_local = x_rd - x_min   (east positive)
    y_local = y_max - y_rd   (south positive)

Estimator input file per patch:
  est_input_<patch_id>.json

Ground truth (optional, evaluation only):
  gt_<patch_id>.npz  (compressed), contains R_gt float32 (mm/h)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from link_geometry import PatchRectRD


def rd_to_local_m(x_rd: float, y_rd: float, rect_rd: PatchRectRD) -> Tuple[float, float]:
    x_local = float(x_rd - rect_rd.x_min)
    y_local = float(rect_rd.y_max - y_rd)
    return x_local, y_local


def write_estimator_input_json(
    path: Path,
    *,
    patch_id: str,
    rect_rd: PatchRectRD,
    H: int,
    W: int,
    links: List[Dict],
    segments_by_link: Dict[str, List[Dict]],
    pixel_size_m: float = 125.0,
) -> None:
    """Write estimator input JSON for one patch."""
    header = {
        "patch_id": patch_id,
        "pixel_size_m": float(pixel_size_m),
        "H": int(H),
        "W": int(W),
        "width_m": float(W * pixel_size_m),
        "height_m": float(H * pixel_size_m),
        "frame": "local_from_NW",
        "origin_rd_m": {"x_min": float(rect_rd.x_min), "y_max": float(rect_rd.y_max)},
    }

    links_out: List[Dict] = []
    for rec in links:
        x0, y0 = rd_to_local_m(float(rec["xs_m"]), float(rec["ys_m"]), rect_rd)
        x1, y1 = rd_to_local_m(float(rec["xe_m"]), float(rec["ye_m"]), rect_rd)
        links_out.append(
            {
                "link_index": int(rec["link_index"]),
                "x0_m": float(x0),
                "y0_m": float(y0),
                "x1_m": float(x1),
                "y1_m": float(y1),
                "freq_ghz": float(rec.get("freq_ghz")),
                "pol": str(rec.get("pol")).upper(),
                "A_db": float(rec.get("attenuation_db")),
            }
        )

    payload = {"header": header, "links": links_out, "segments_by_link": segments_by_link}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def write_ground_truth_npz(path: Path, *, patch_id: str, R_gt_mmph: np.ndarray, pixel_size_m: float = 125.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gt = np.asarray(R_gt_mmph, dtype=np.float32)
    np.savez_compressed(
        path,
        R_gt=gt,
        pixel_size_m=np.float32(pixel_size_m),
        H=np.int32(gt.shape[0]),
        W=np.int32(gt.shape[1]),
        patch_id=str(patch_id),
    )
