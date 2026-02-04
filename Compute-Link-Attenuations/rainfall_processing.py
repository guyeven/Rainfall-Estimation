"""Rainfall loading, cropping, refinement, and smoothing.

Assumptions (per spec):
- Patch JSON contains full H5 path in key 'source_file'.
- Patch JSON contains crop indices: x_min,x_max,y_min,y_max for the OPERA grid.
- Rain rate units are mm/h (as stored).
- NaN values are replaced by 0.
- OPERA missing flag values (very negative) are replaced by 0.
- Refinement: 2km -> 125m via 16x16 inheritance (repeat).
- Smoothing: Gaussian sigma=1 refined pixel, mode='nearest'.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter


# Common OPERA-like dataset paths; we keep this tiny and explicit.
_DATASET_CANDIDATES = [
    "/dataset1/data1/data",
    "/dataset1/data",
    "/data",
]


@dataclass(frozen=True)
class RainPrepResult:
    coarse_mmph: np.ndarray
    refined_mmph: np.ndarray
    refined_smoothed_mmph: np.ndarray


def _find_dataset(f: h5py.File) -> h5py.Dataset:
    for p in _DATASET_CANDIDATES:
        if p in f and isinstance(f[p], h5py.Dataset):
            return f[p]  # type: ignore[return-value]

    # fallback: largest 2D dataset
    best = None
    best_size = -1

    def visitor(_name, obj):
        nonlocal best, best_size
        if isinstance(obj, h5py.Dataset) and obj.ndim >= 2:
            size = int(np.prod(obj.shape))
            if size > best_size:
                best_size = size
                best = obj

    f.visititems(visitor)
    if best is None:
        raise KeyError("No 2D dataset found in H5 rainfall file")
    return best


def load_coarse_patch_rain(patch: Dict) -> np.ndarray:
    """Load and crop rainfall for a patch from its H5 file.

    Returns a 2D float array in mm/h.
    """
    h5_path = Path(str(patch["source_file"]))
    if not h5_path.is_file():
        raise FileNotFoundError(f"H5 file not found: {h5_path}")

    y_min = int(patch["y_min"])
    y_max = int(patch["y_max"])
    x_min = int(patch["x_min"])
    x_max = int(patch["x_max"])

    with h5py.File(h5_path, "r") as f:
        ds = _find_dataset(f)
        data = ds[()]

    # Ensure 2D: if >2D, use last frame
    if data.ndim > 2:
        data = data.reshape((-1, data.shape[-2], data.shape[-1]))[-1]

    # Crop (inclusive bounds in patch JSON)
    cropped = data[y_min : y_max + 1, x_min : x_max + 1]
    rain = np.array(cropped, dtype=float)

    # OPERA missing flag
    rain[rain <= -9e6] = 0.0
    # NaNs to zero
    rain = np.nan_to_num(rain, nan=0.0, posinf=0.0, neginf=0.0)

    return rain


def refine_16x16_inherit(coarse_mmph: np.ndarray) -> np.ndarray:
    """Upsample by 16x16 using inheritance (nearest / repeat)."""
    if coarse_mmph.ndim != 2:
        raise ValueError("coarse_mmph must be a 2D array")
    refined = np.repeat(np.repeat(coarse_mmph, 16, axis=0), 16, axis=1)
    return refined.astype(float)


def smooth_refined_gaussian(refined_mmph: np.ndarray) -> np.ndarray:
    """Gaussian smoothing with sigma=1 refined pixel, mode='nearest'."""
    refined_mmph = np.nan_to_num(refined_mmph, nan=0.0, posinf=0.0, neginf=0.0)
    return gaussian_filter(refined_mmph, sigma=1.0, mode="nearest")


def prepare_rainfall_for_patch(patch: Dict) -> RainPrepResult:
    """Load -> crop -> NaN->0 -> refine -> gaussian smooth."""
    coarse = load_coarse_patch_rain(patch)
    refined = refine_16x16_inherit(coarse)
    refined_smoothed = smooth_refined_gaussian(refined)
    return RainPrepResult(
        coarse_mmph=coarse,
        refined_mmph=refined,
        refined_smoothed_mmph=refined_smoothed,
    )


def refined_shape_from_patch(patch: Dict) -> Tuple[int, int]:
    """Return (ny_refined, nx_refined) for this patch given coarse indices."""
    ny = int(patch["y_max"]) - int(patch["y_min"]) + 1
    nx = int(patch["x_max"]) - int(patch["x_min"]) + 1
    return ny * 16, nx * 16
