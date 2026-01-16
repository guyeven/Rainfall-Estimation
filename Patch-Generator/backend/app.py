from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = (
    Path(sys._MEIPASS)
    if hasattr(sys, "_MEIPASS")
    else Path(__file__).resolve().parent
)


import json
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import List
from collections import OrderedDict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from config import EXPORT_DIR
from io_rainfall import list_rain_files, load_rain_map
from patches import RainPatch, extract_patches_from_file
from schemas import (
    BenchmarkLoadRequest,
    BenchmarkSaveRequest,
    FileInfo,
    PatchGeoInfo,
    PatchOut,
    PatchParams,
)
from benchmarks import list_benchmarks, load_benchmark_npz, save_benchmark_npz

app = FastAPI(title="Rain Patch Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------
# Simple root endpoint so "/" is not 404
# --------------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "Rain patch backend is running"}


# --------------------------------------------------------------------
# In-memory state
# --------------------------------------------------------------------
_LAST_PATCHES: List[RainPatch] = []
_LAST_PATCH_DATA: "OrderedDict[str, np.ndarray]" = OrderedDict()
_LAST_PATCH_BY_ID: dict[str, RainPatch] = {}
_PATCH_CACHE_MAX = 8  # keep only the most recent patches in memory (LRU)


# --------------------------------------------------------------------
# Detection parameter defaults (persisted in JSON)
# --------------------------------------------------------------------
#DETECTION_CONFIG_PATH = Path("detection_params.json")
DETECTION_CONFIG_PATH = BASE_DIR / "detection_params.json"



def _load_detection_defaults() -> dict:
    if DETECTION_CONFIG_PATH.exists():
        try:
            data = json.loads(DETECTION_CONFIG_PATH.read_text())
            return PatchParams(**data).model_dump()
        except Exception:
            # fall back to model defaults
            pass
    defaults = PatchParams().model_dump()
    DETECTION_CONFIG_PATH.write_text(json.dumps(defaults, indent=2))
    return defaults


DETECTION_DEFAULTS: dict = _load_detection_defaults()


@app.get("/detection_params", response_model=PatchParams)
def api_get_detection_params() -> PatchParams:
    return PatchParams(**DETECTION_DEFAULTS)


@app.post("/detection_params", response_model=PatchParams)
def api_set_detection_params(params: PatchParams) -> PatchParams:
    global DETECTION_DEFAULTS
    DETECTION_DEFAULTS = params.model_dump()
    DETECTION_CONFIG_PATH.write_text(json.dumps(DETECTION_DEFAULTS, indent=2))
    return params



# --------------------------------------------------------------------
# Files
# --------------------------------------------------------------------
@app.get("/files", response_model=List[FileInfo])
def api_list_files(limit: int = Query(50, ge=1, le=500)) -> List[FileInfo]:
    files = list_rain_files(limit)
    return [FileInfo(path=str(p), timestamp=ts) for p, ts in files]


# --------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------
@app.post("/detect_patches", response_model=List[PatchOut])
def api_detect_patches(params: PatchParams) -> List[PatchOut]:
    """
    Run patch detection on selected or automatically chosen files.

    If something goes wrong in reading a file or detecting patches,
    we RETURN a clear error message instead of a generic 500.
    """
    global _LAST_PATCHES, _LAST_PATCH_DATA, _LAST_PATCH_BY_ID

    # Decide which files to use
    if params.files:
        filepaths = [Path(p) for p in params.files]
    else:
        filepaths = [p for p, _ in list_rain_files(params.max_files)]

    if not filepaths:
        raise HTTPException(
            status_code=400,
            detail="No rainfall files found in data/raw. "
                   "Put EURADCLIM .h5 files there or pass explicit 'files'.",
        )

    all_patches: List[RainPatch] = []
    patch_data: "OrderedDict[str, np.ndarray]" = OrderedDict()

    for f in filepaths:
        try:
            patches = extract_patches_from_file(
                filepath=f,
                threshold_mm=params.threshold_mm,
                avg_window_y=params.avg_window_y,
                avg_window_x=params.avg_window_x,
                min_width_km=params.min_width_km,
                min_height_km=params.min_height_km,
                max_width_km=params.max_width_km,
                max_height_km=params.max_height_km,
            )
        except Exception as e:
            # <---- THIS is the important part:
            # you will see this 'detail' in the HTTP response
            raise HTTPException(
                status_code=500,
                detail=f"Error while processing file '{f}': {type(e).__name__}: {e}",
            ) from e

        for p in patches:
            all_patches.append(p)
            arr = getattr(p, "_data", None)
            if arr is not None:
                patch_data[p.id] = arr

    _LAST_PATCHES = all_patches
    _LAST_PATCH_DATA = patch_data

    return [PatchOut(**asdict(p)) for p in all_patches]



# --------------------------------------------------------------------
# Benchmark browsing: load a single patch (crop from H5 on-demand)
# --------------------------------------------------------------------
@app.post("/benchmark/load_patch")
def api_benchmark_load_patch(patch: PatchOut):
    """Load one patch into the in-memory cache so /patch_image and /patch_geo work.

    The frontend sends a patch record (from JSONL). We crop the rainfall array
    directly from patch.source_file and store only a small number of most-recent
    patches to keep memory bounded.
    """
    global _LAST_PATCHES, _LAST_PATCH_DATA, _LAST_PATCH_BY_ID, _LAST_PATCH_BY_ID

    patch_id = patch.id

    # Fast path: already cached -> bump LRU order and return
    if patch_id in _LAST_PATCH_DATA:
        _LAST_PATCH_DATA.move_to_end(patch_id)
        return {"status": "cached", "id": patch_id}

    # Load full rainfall grid from H5 and crop bbox
    try:
        m = load_rain_map(patch.source_file)
        rain = m['rain']
        _ts = m.get('timestamp')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read H5 file: {e}")

    y0, y1 = int(patch.y_min), int(patch.y_max) + 1
    x0, x1 = int(patch.x_min), int(patch.x_max) + 1

    if y0 < 0 or x0 < 0 or y1 > rain.shape[0] or x1 > rain.shape[1] or y0 >= y1 or x0 >= x1:
        raise HTTPException(status_code=400, detail="Invalid patch bounding box for source grid")

    sub = np.array(rain[y0:y1, x0:x1], dtype=float)

    # Enforce the same missing-data rule as detection
    sub[sub <= -9e6] = 0.0

    # Build a RainPatch metadata object (no re-computation; we trust JSONL values)
    rp = RainPatch(
        id=patch.id,
        source_file=patch.source_file,
        timestamp=patch.timestamp,
        y_min=patch.y_min,
        y_max=patch.y_max,
        x_min=patch.x_min,
        x_max=patch.x_max,
        mean_rainfall=patch.mean_rainfall,
        max_rainfall=patch.max_rainfall,
        width_km=patch.width_km,
        height_km=patch.height_km,
        area_km2=patch.area_km2,
        center_lat=patch.center_lat,
        center_lon=patch.center_lon,
        nearest_city=patch.nearest_city,
    )

    # Store cropped data + metadata in cache (LRU)
    _LAST_PATCH_DATA[patch_id] = sub
    _LAST_PATCH_DATA.move_to_end(patch_id)

    _LAST_PATCH_BY_ID[patch_id] = rp

    # Maintain _LAST_PATCHES list for existing endpoints (patch_geo uses it)
    _LAST_PATCHES = list(_LAST_PATCH_BY_ID.values())

    # Evict old entries if cache grows too large
    while len(_LAST_PATCH_DATA) > _PATCH_CACHE_MAX:
        old_id, _old_arr = _LAST_PATCH_DATA.popitem(last=False)
        _LAST_PATCH_BY_ID.pop(old_id, None)
        # Re-sync list after eviction
        _LAST_PATCHES = list(_LAST_PATCH_BY_ID.values())

    return {"status": "loaded", "id": patch_id, "cached": len(_LAST_PATCH_DATA)}

@app.get("/patches", response_model=List[PatchOut])
def api_get_patches() -> List[PatchOut]:
    return [PatchOut(**asdict(p)) for p in _LAST_PATCHES]


# --------------------------------------------------------------------
# Patch image
# --------------------------------------------------------------------
@app.get("/patch_image/{patch_id}")
def api_patch_image(patch_id: str):
    if patch_id not in _LAST_PATCH_DATA:
        raise HTTPException(status_code=404, detail="Patch not found in memory")

    data = _LAST_PATCH_DATA[patch_id]

    fig, ax = plt.subplots(figsize=(4, 4))

    # Assume 2 km per pixel (OPERA grid). Adjust here if you change resolution.
    km_per_pixel = 2.0

    h, w = data.shape
    # Map pixel indices to km using imshow "extent"
    extent = [0, w * km_per_pixel, h * km_per_pixel, 0]

    im = ax.imshow(data, origin="upper", extent=extent)
    plt.colorbar(im, ax=ax, label="mm")

    # No title inside PNG; frontend shows patch metadata
    ax.set_title("")

    # Ticks directly in km
    xticks_km = np.linspace(0, w * km_per_pixel, num=min(5, w))
    yticks_km = np.linspace(0, h * km_per_pixel, num=min(5, h))
    ax.set_xticks(xticks_km)
    ax.set_yticks(yticks_km)
    ax.set_xlabel("x (km)")
    ax.set_ylabel("y (km)")

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)

    return Response(content=buf.read(), media_type="image/png")


# --------------------------------------------------------------------
# Geo info for map panel
# --------------------------------------------------------------------
@app.get("/patch_geo/{patch_id}", response_model=PatchGeoInfo)
def api_patch_geo(
    patch_id: str,
    zoom_factor: float = Query(3.0, ge=1.0, le=10.0),
) -> PatchGeoInfo:
    patch = next((p for p in _LAST_PATCHES if p.id == patch_id), None)
    if patch is None:
        raise HTTPException(status_code=404, detail="Patch not found in memory")

    KM_PER_DEG_LAT = 111.0
    lat_rad = np.deg2rad(patch.center_lat)
    km_per_deg_lon = KM_PER_DEG_LAT * np.cos(lat_rad) or KM_PER_DEG_LAT

    patch_lat_half = (patch.height_km / 2.0) / KM_PER_DEG_LAT
    patch_lon_half = (patch.width_km / 2.0) / km_per_deg_lon

    patch_lat_min = patch.center_lat - patch_lat_half
    patch_lat_max = patch.center_lat + patch_lat_half
    patch_lon_min = patch.center_lon - patch_lon_half
    patch_lon_max = patch.center_lon + patch_lon_half

    map_lat_half = patch_lat_half * zoom_factor
    map_lon_half = patch_lon_half * zoom_factor

    map_lat_min = patch.center_lat - map_lat_half
    map_lat_max = patch.center_lat + map_lat_half
    map_lon_min = patch.center_lon - map_lon_half
    map_lon_max = patch.center_lon + map_lon_half

    return PatchGeoInfo(
        patch_id=patch.id,
        center_lat=patch.center_lat,
        center_lon=patch.center_lon,
        patch_lat_min=patch_lat_min,
        patch_lat_max=patch_lat_max,
        patch_lon_min=patch_lon_min,
        patch_lon_max=patch_lon_max,
        map_lat_min=map_lat_min,
        map_lat_max=map_lat_max,
        map_lon_min=map_lon_min,
        map_lon_max=map_lon_max,
    )


# --------------------------------------------------------------------
# Excel export
# --------------------------------------------------------------------
@app.get("/patches/export_excel")
def api_export_patches_excel():
    if not _LAST_PATCHES:
        return {"status": "no_patches", "message": "Run /detect_patches first."}

    rows = []
    for p in _LAST_PATCHES:
        rows.append(
            {
                "id": p.id,
                "source_file": p.source_file,
                "timestamp": p.timestamp,
                "nearest_city": p.nearest_city,
                "width_km": p.width_km,
                "height_km": p.height_km,
                "area_km2": p.area_km2,
                "mean_rainfall": p.mean_rainfall,
                "max_rainfall": p.max_rainfall,
            }
        )

    df = pd.DataFrame(rows)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="patches")
    buf.seek(0)

    filename = EXPORT_DIR / "patches.xlsx"
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename.name}"'},
    )


# --------------------------------------------------------------------
# Benchmark save/load
# --------------------------------------------------------------------
@app.post("/benchmark/save")
def api_save_benchmark(req: BenchmarkSaveRequest) -> dict:
    if not _LAST_PATCHES:
        return {"status": "no_patches", "message": "Run /detect_patches first."}
    return save_benchmark_npz(req.name, _LAST_PATCHES, req.patch_ids)


@app.get("/benchmark/list", response_model=List[str])
def api_list_benchmarks() -> List[str]:
    return list_benchmarks()


@app.post("/benchmark/load", response_model=List[PatchOut])
def api_load_benchmark(req: BenchmarkLoadRequest) -> List[PatchOut]:
    global _LAST_PATCHES, _LAST_PATCH_DATA, _LAST_PATCH_BY_ID

    patches = load_benchmark_npz(req.name)
    _LAST_PATCHES = patches
    _LAST_PATCH_DATA = OrderedDict()

    return [PatchOut(**asdict(p)) for p in patches]


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

#guy: old. edit for PyInstaller    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
    uvicorn.run(app, host="127.0.0.1", port=8000)
