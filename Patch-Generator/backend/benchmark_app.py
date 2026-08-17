# benchmark_app_revised.py (fixed)
import os
from io import BytesIO
from typing import Dict, Optional, Any, Tuple

import h5py
import numpy as np
from fastapi import Body, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from scipy.ndimage import gaussian_filter
from matplotlib import cm, colors
from PIL import Image

MISSING_SENTINEL = -9e6
UPSAMPLE_FACTOR = 16  # raw-pixel -> refined-pixel factor (2km / 125m)

app = FastAPI(title="Rain Patch Smoothing (refined)")

_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
_CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# patch_id -> {"source_file", "x_min", "x_max", "y_min", "y_max"}
_BENCHMARK_PATCHES: Dict[str, dict] = {}
_LAST_DETECTION_PARAMS: Optional[dict] = None


# -------------------------
# Data IO utilities
# -------------------------
def _load_rain(path: str) -> np.ndarray:
    """Load rainfall from ODIM HDF5 and replace missing with 0."""
    try:
        f = h5py.File(path, "r")
    except OSError:
        raise HTTPException(status_code=404, detail=f"HDF5 file not found: {path}")
    with f:
        data = np.array(f["/dataset1/data1/data"], dtype=np.float32)
    data[data <= MISSING_SENTINEL] = 0.0
    return data


def _get_patch_subarray(patch_id: str) -> np.ndarray:
    if patch_id not in _BENCHMARK_PATCHES:
        raise HTTPException(status_code=404, detail="Patch not found. Load patches first.")
    p = _BENCHMARK_PATCHES[patch_id]
    rain = _load_rain(p["source_file"])
    return rain[p["y_min"] : p["y_max"] + 1, p["x_min"] : p["x_max"] + 1]


# -------------------------
# Core pipeline (approved)
# -------------------------
def refine_raw_to_refinedraw(coarse: np.ndarray) -> np.ndarray:
    """Refinement: copy each raw-pixel to a 16x16 block of refined-pixels."""
    coarse = np.asarray(coarse, dtype=np.float32)
    R = UPSAMPLE_FACTOR
    return np.repeat(np.repeat(coarse, R, axis=0), R, axis=1)


def smooth_refined(refined_raw: np.ndarray) -> np.ndarray:
    """SMOOTH: Gaussian filter with sigma=1 in refined-pixel units."""
    sigma = 1.0
    return gaussian_filter(refined_raw, sigma=sigma, mode="nearest")


def difference(smooth: np.ndarray, refined_raw: np.ndarray) -> np.ndarray:
    """DIFF = SMOOTH - refinedRAW (as requested)."""
    return smooth - refined_raw


# -------------------------
# Stats on refined grid
# -------------------------
def _map_stats(arr: np.ndarray) -> dict:
    """
    Stats for a single refined-grid map (treating it as deviation from 0):
      L1 = sum_p |arr(p)|
      Linf = max_p |arr(p)|
      L1/(h*w) with h,w = refined dimensions
    """
    arr = np.asarray(arr, dtype=np.float32)
    H, W = arr.shape
    a = np.abs(arr)
    l1 = float(a.sum())
    linf = float(a.max()) if a.size else 0.0
    denom = float(H * W) if H > 0 and W > 0 else 1.0
    l1_per_hw = float(l1 / denom)
    # Provide both keys for backward/forward compatibility with frontend
    return {
        "shape_refined": [int(H), int(W)],
        "l1": l1,
        "linf": linf,
        "l1_per_hw": l1_per_hw,
        "l1_per_area": l1_per_hw,  # alias; frontend falls back to this if needed
    }


# -------------------------
# Image rendering: 1 refined-pixel -> 1 PNG pixel (data only)
# -------------------------
def _make_data_image(arr: np.ndarray, vmin: float, vmax: float) -> bytes:
    """
    Render arr to PNG where image dims equal array dims (w x h).
    No labels/axes/legend in PNG. Each refined-pixel maps to one PNG pixel.
    """
    arr = np.asarray(arr, dtype=np.float32)
    norm = colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    cmap = cm.get_cmap("viridis")
    rgba = cmap(norm(arr))  # (h,w,4) floats 0..1
    rgba8 = (rgba * 255).astype(np.uint8)
    img = Image.fromarray(rgba8, mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _patch_vmin_vmax(refined_raw: np.ndarray, smooth: np.ndarray, diff: np.ndarray) -> Tuple[float, float]:
    vmin = float(min(refined_raw.min(), smooth.min(), diff.min()))
    vmax = float(max(refined_raw.max(), smooth.max(), diff.max()))
    if vmin == vmax:
        vmin -= 0.5
        vmax += 0.5
    return vmin, vmax


# -------------------------
# Endpoints
# -------------------------
@app.post("/benchmark/load_patches")
def load_patches(body: Any = Body(...)):
    """
    Accept selection JSON:
      - either a bare list of patch objects, or
      - {"patches":[...], "detection_params": {...}}

    Patch objects must contain:
      id, source_file, x_min, x_max, y_min, y_max
    """
    global _LAST_DETECTION_PARAMS
    _BENCHMARK_PATCHES.clear()

    if isinstance(body, list):
        patches = body
        detection_params = None
    elif isinstance(body, dict):
        patches = body.get("patches", [])
        detection_params = body.get("detection_params")
    else:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if not isinstance(patches, list):
        raise HTTPException(status_code=400, detail="'patches' must be a list.")

    for p in patches:
        try:
            pid = str(p["id"])
            info = {
                "source_file": p["source_file"],
                "x_min": int(p["x_min"]),
                "x_max": int(p["x_max"]),
                "y_min": int(p["y_min"]),
                "y_max": int(p["y_max"]),
            }
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Missing key in patch: {exc!s}")
        _BENCHMARK_PATCHES[pid] = info

    _LAST_DETECTION_PARAMS = detection_params
    return {"count": len(_BENCHMARK_PATCHES), "patch_ids": sorted(_BENCHMARK_PATCHES.keys())}


@app.get("/benchmark/patch_list")
def patch_list() -> dict:
    out = []
    for pid, p in _BENCHMARK_PATCHES.items():
        out.append(
            {
                "patch_id": pid,
                "source_file": p["source_file"],
                "x_min": p["x_min"],
                "x_max": p["x_max"],
                "y_min": p["y_min"],
                "y_max": p["y_max"],
            }
        )
    return {"patches": out, "detection_params": _LAST_DETECTION_PARAMS}


@app.get("/benchmark/stats/{patch_id}")
def stats_endpoint(
    patch_id: str,
    method: str = Query("gaussian"),
    max_components: float = Query(1.0 / 16.0, ge=1.0 / 16.0, le=20.0),
):
    """
    Returns stats for RAW (refinedRAW), SMOOTH, and DIFF on refined grid.
    For UI: also returns per-patch colormap and vmin/vmax to use as shared legend for the 3 maps.
    """
    coarse = _get_patch_subarray(patch_id)
    refined_raw = refine_raw_to_refinedraw(coarse)

    # Only gaussian is used here; keep args for compatibility
    smooth_map = smooth_refined(refined_raw)
    diff_map = difference(smooth_map, refined_raw)

    vmin, vmax = _patch_vmin_vmax(refined_raw, smooth_map, diff_map)

    return {
        "raw": _map_stats(refined_raw),
        "smooth": _map_stats(smooth_map),
        "diff": _map_stats(diff_map),
        "meta": {
            "x_label": "x (refined-px)",
            "y_label": "y (refined-px)",
            "raw_title": "Raw (refined grid)",
            "smooth_title": "Smoothed (sigma=1 refined-px)",
            "diff_title": "Difference (SMOOTH - refinedRAW)",
            "colormap": "viridis",
            "vmin": vmin,
            "vmax": vmax,
        },
    }


@app.get("/benchmark/patch_image/{patch_id}")
def patch_image(
    patch_id: str,
    method: str = Query("gaussian"),
    max_components: float = Query(1.0 / 16.0, ge=1.0 / 16.0, le=20.0),
):
    coarse = _get_patch_subarray(patch_id)
    refined_raw = refine_raw_to_refinedraw(coarse)
    smooth_map = smooth_refined(refined_raw)
    diff_map = difference(smooth_map, refined_raw)
    vmin, vmax = _patch_vmin_vmax(refined_raw, smooth_map, diff_map)
    png = _make_data_image(refined_raw, vmin, vmax)
    return Response(png, media_type="image/png")


@app.get("/benchmark/smooth_image/{patch_id}")
def smooth_image(
    patch_id: str,
    method: str = Query("gaussian"),
    max_components: float = Query(1.0 / 16.0, ge=1.0 / 16.0, le=20.0),
):
    coarse = _get_patch_subarray(patch_id)
    refined_raw = refine_raw_to_refinedraw(coarse)
    smooth_map = smooth_refined(refined_raw)
    diff_map = difference(smooth_map, refined_raw)
    vmin, vmax = _patch_vmin_vmax(refined_raw, smooth_map, diff_map)
    png = _make_data_image(smooth_map, vmin, vmax)
    return Response(png, media_type="image/png")


@app.get("/benchmark/diff_image/{patch_id}")
def diff_image(
    patch_id: str,
    method: str = Query("gaussian"),
    max_components: float = Query(1.0 / 16.0, ge=1.0 / 16.0, le=20.0),
):
    coarse = _get_patch_subarray(patch_id)
    refined_raw = refine_raw_to_refinedraw(coarse)
    smooth_map = smooth_refined(refined_raw)
    diff_map = difference(smooth_map, refined_raw)
    vmin, vmax = _patch_vmin_vmax(refined_raw, smooth_map, diff_map)
    png = _make_data_image(diff_map, vmin, vmax)
    return Response(png, media_type="image/png")
