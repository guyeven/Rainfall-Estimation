from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import scipy.ndimage as ndi

from config import PIXEL_SIZE_KM
from cities import nearest_city
from io_rainfall import get_latlon_grid_from_h5, load_rain_map


@dataclass
class RainPatch:
    id: str
    source_file: str
    timestamp: dt.datetime

    y_min: int
    y_max: int
    x_min: int
    x_max: int

    mean_rainfall: float
    max_rainfall: float
    width_km: float
    height_km: float
    area_km2: float

    center_lat: float
    center_lon: float
    nearest_city: str


def smooth_rain(
    rain: np.ndarray,
    avg_window_y: int,
    avg_window_x: int,
) -> np.ndarray:
    """Uniform filter over avg_window_y × avg_window_x pixels; 1×1 → original."""
    if avg_window_y <= 1 and avg_window_x <= 1:
        return rain

    kernel = np.ones((avg_window_y, avg_window_x), dtype=float)
    kernel /= kernel.sum()
    smoothed = ndi.convolve(rain, kernel, mode="nearest")
    return smoothed


def find_rain_bboxes(
    rain: np.ndarray,
    threshold_mm: float,
    min_width_km: float,
    min_height_km: float,
    max_width_km: Optional[float] = None,
    max_height_km: Optional[float] = None,
) -> List[tuple[int, int, int, int]]:
    """
    Find bounding boxes of connected rain regions satisfying size limits.

    Returns list of (y_min, y_max, x_min, x_max) in pixel indices.
    """
    mask = rain >= threshold_mm
    if not mask.any():
        return []

    structure = np.ones((3, 3), dtype=int)
    labeled, num = ndi.label(mask, structure=structure)

    min_w_px = int(min_width_km / PIXEL_SIZE_KM)
    min_h_px = int(min_height_km / PIXEL_SIZE_KM)
    max_w_px = int(max_width_km / PIXEL_SIZE_KM) if max_width_km else None
    max_h_px = int(max_height_km / PIXEL_SIZE_KM) if max_height_km else None

    bboxes: List[tuple[int, int, int, int]] = []

    for label_id in range(1, num + 1):
        ys, xs = np.where(labeled == label_id)
        if ys.size == 0:
            continue

        y_min = int(ys.min())
        y_max = int(ys.max())
        x_min = int(xs.min())
        x_max = int(xs.max())

        h_px = y_max - y_min + 1
        w_px = x_max - x_min + 1

        if h_px < min_h_px or w_px < min_w_px:
            continue
        if max_h_px is not None and h_px > max_h_px:
            continue
        if max_w_px is not None and w_px > max_w_px:
            continue

        bboxes.append((y_min, y_max, x_min, x_max))

    return bboxes


def extract_patches_from_file(
    filepath: Path,
    threshold_mm: float,
    avg_window_y: int,
    avg_window_x: int,
    min_width_km: float,
    min_height_km: float,
    max_width_km: Optional[float],
    max_height_km: Optional[float],
) -> List[RainPatch]:
    """Load one rainfall map and detect patches according to the parameters."""
    loaded = load_rain_map(filepath)
    rain = loaded["rain"]
    timestamp = loaded["timestamp"]

    rain_proc = smooth_rain(rain, avg_window_y, avg_window_x)
    LAT, LON = get_latlon_grid_from_h5(filepath)

    bboxes = find_rain_bboxes(
        rain_proc,
        threshold_mm=threshold_mm,
        min_width_km=min_width_km,
        min_height_km=min_height_km,
        max_width_km=max_width_km,
        max_height_km=max_height_km,
    )

    patches: List[RainPatch] = []
    for i, (y_min, y_max, x_min, x_max) in enumerate(bboxes):
        sub = rain[y_min : y_max + 1, x_min : x_max + 1]
        h_px, w_px = sub.shape

        width_km = w_px * PIXEL_SIZE_KM
        height_km = h_px * PIXEL_SIZE_KM
        area_km2 = width_km * height_km
        mean_r = float(sub.mean())
        max_r = float(sub.max())

        sub_lat = LAT[y_min : y_max + 1, x_min : x_max + 1]
        sub_lon = LON[y_min : y_max + 1, x_min : x_max + 1]
        lat_center = float(sub_lat.mean())
        lon_center = float(sub_lon.mean())
        city = nearest_city(lat_center, lon_center)

        patch_id = f"{filepath.stem}_patch{i:03d}"

        patch = RainPatch(
            id=patch_id,
            source_file=str(filepath),
            timestamp=timestamp,
            y_min=y_min,
            y_max=y_max,
            x_min=x_min,
            x_max=x_max,
            mean_rainfall=mean_r,
            max_rainfall=max_r,
            width_km=width_km,
            height_km=height_km,
            area_km2=area_km2,
            center_lat=lat_center,
            center_lon=lon_center,
            nearest_city=city,
        )

        # Attach raw data for later export / image
        setattr(patch, "_data", sub)
        patches.append(patch)

    return patches

