"""Compute per-link rain attenuation for a patch.

This module:
- computes per-link attenuation (dB) from a refined+smoothed rain-rate grid (mm/h)
- precomputes per-link pixel intersection segments (i,j,ds_m)
- writes per-patch JSONL (one record per link) for convenience
- optionally writes a debug JSON trace for one link

Conventions:
- Geometry in EPSG:28992 meters.
- Refined grid pixel size = 125 m.
- Rainfall array indexing: [i,j] where i increases southward, j increases eastward.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from intersection import GridSpec, traverse_segment_pixels
from itu_model import gamma_db_per_km
from link_geometry import PatchRectRD


@dataclass(frozen=True)
class DebugRequest:
    patch_id: str
    link_index: int  # 0-based, matches link_index in outputs


def _write_jsonl(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _write_json(path: Path, obj: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def compute_attenuation_for_patch(
    patch: Dict,
    rect_rd: PatchRectRD,
    links_in_patch: List[Dict],
    refined_smoothed_mmph: np.ndarray,
    out_jsonl_path: Path,
    debug: Optional[DebugRequest] = None,
) -> Tuple[List[Dict], Dict[str, List[Dict]], Optional[Dict]]:
    """Compute attenuation for each link and write per-patch JSONL.

    Parameters
    - links_in_patch: links with translated endpoints in RD meters:
        xs_m, ys_m, xe_m, ye_m, plus freq_ghz and pol.
    - refined_smoothed_mmph: ground-truth rain rate on refined grid, mm/h.
    - out_jsonl_path: output JSONL for link summaries (includes attenuation_db).

    Returns
    - out_records: list of per-link dicts (original fields + link_index + attenuation_db)
    - segments_by_link: dict[str(link_index)] -> list of {i,j,ds_m}
    - debug_dump: optional debug payload (if requested and available)
    """
    grid = GridSpec(
        x_min=rect_rd.x_min,
        x_max=rect_rd.x_max,
        y_min=rect_rd.y_min,
        y_max=rect_rd.y_max,
        pixel_m=125.0,
    )

    ny, nx = refined_smoothed_mmph.shape
    if (ny, nx) != (grid.ny, grid.nx):
        raise ValueError(
            f"Refined rainfall shape {refined_smoothed_mmph.shape} does not match grid "
            f"({grid.ny},{grid.nx})."
        )

    pid = str(patch.get("patch_id") or patch.get("id") or "").strip()
    debug_dump: Optional[Dict] = None
    if debug is not None and pid == debug.patch_id:
        debug_dump = {"type": "debug_trace", "patch_id": pid, "link_index": debug.link_index, "rows": []}

    out_records: List[Dict] = []
    segments_by_link: Dict[str, List[Dict]] = {}

    for link_index, link in enumerate(links_in_patch):
        x0 = float(link["xs_m"])
        y0 = float(link["ys_m"])
        x1 = float(link["xe_m"])
        y1 = float(link["ye_m"])

        pixels = traverse_segment_pixels(grid, x0, y0, x1, y1)  # [(i,j,ds_m),...]

        # Store segments (compact records)
        seg_list: List[Dict] = []
        for (i, j, ds_m) in pixels:
            seg_list.append({"i": int(i), "j": int(j), "ds_m": float(ds_m)})
        segments_by_link[str(link_index)] = seg_list

        # Compute attenuation
        freq_ghz = float(link["freq_ghz"])
        pol = str(link["pol"]).upper()

        total_db = 0.0
        cumsum = 0.0

        for (i, j, ds_m) in pixels:
            ds_km = ds_m / 1000.0
            rain = float(refined_smoothed_mmph[i, j])
            gamma = float(gamma_db_per_km(freq_ghz, rain, pol))  # dB/km
            a_db = gamma * ds_km
            total_db += a_db

            if debug_dump is not None and link_index == debug.link_index:
                cumsum += a_db
                cx, cy = grid.cell_center(i, j)
                debug_dump["rows"].append(
                    {
                        "i": int(i),
                        "j": int(j),
                        "x_center_m": float(cx),
                        "y_center_m": float(cy),
                        "ds_m": float(ds_m),
                        "ds_km": float(ds_km),
                        "rain_mmph": float(rain),
                        "gamma_db_per_km": float(gamma),
                        "atten_db_pixel": float(a_db),
                        "atten_db_cumsum": float(cumsum),
                    }
                )

        rec = dict(link)
        rec["link_index"] = int(link_index)
        rec["attenuation_db"] = float(total_db)
        out_records.append(rec)

        if debug_dump is not None and link_index == debug.link_index:
            debug_dump["summary"] = {
                "num_pixels": int(len(pixels)),
                "total_attenuation_db": float(total_db),
                "total_length_km": float(sum(ds for (_, _, ds) in pixels) / 1000.0),
            }

    _write_jsonl(out_jsonl_path, out_records)

    if debug_dump is not None:
        dbg_path = out_jsonl_path.parent / f"debug_{pid}_link{debug.link_index}.json"
        _write_json(dbg_path, debug_dump)

    return out_records, segments_by_link, debug_dump
