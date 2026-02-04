"""
app.py — Rainfall patch backend with benchmark support

Backend stack:
    - FastAPI   : HTTP API
    - uvicorn   : ASGI server

Core features:
    1. Load EURADCLIM rainfall maps from data/raw/ (.h5 ODIM).
    2. Detect "rain patches" using:
         - rainfall threshold [mm]
         - optional local averaging over a×b pixels
         - min / max patch width/height in km
    3. Attach nearest European city to each patch.
    4. Provide endpoints for React UI:
         - list available files
         - run patch detection
         - fetch patch metadata
         - PNG image for a given patch (heat map with legend)
         - export Excel with patch summary
         - save / list / load benchmarks (NPZ files)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional

import datetime as dt

import numpy as np
import h5py
from scipy import ndimage as ndi
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Configuration & paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
EXPORT_DIR = DATA_DIR / "exports"
BENCHMARK_DIR = DATA_DIR / "benchmarks"
CITIES_FILE = DATA_DIR / "cities_europe_100.txt"

for d in (DATA_DIR, RAW_DIR, EXPORT_DIR, BENCHMARK_DIR):
    d.mkdir(parents=True, exist_ok=True)

PIXEL_SIZE_KM = 2.0  # EURADCLIM grid spacing in x,y (2 km)


# ---------------------------------------------------------------------------
# City database
# ---------------------------------------------------------------------------

def ensure_cities_file(path: Path = CITIES_FILE) -> None:
    """
    Create a simple 'city:CC' file with ~100 European cities
    if it does not already exist.
    """
    if path.exists():
        return

    print(f"[cities] Creating default city list at {path}")
    content = """London:GB
Birmingham:GB
Manchester:GB
Glasgow:GB
Dublin:IE
Belfast:GB
Edinburgh:GB

Paris:FR
Marseille:FR
Lyon:FR
Toulouse:FR
Nice:FR
Nantes:FR
Strasbourg:FR

Berlin:DE
Hamburg:DE
Munich:DE
Cologne:DE
Frankfurt:DE
Stuttgart:DE
Düsseldorf:DE
Dresden:DE
Leipzig:DE

Amsterdam:NL
Rotterdam:NL
The Hague:NL
Utrecht:NL
Eindhoven:NL

Brussels:BE
Antwerp:BE
Ghent:BE
Liège:BE
Luxembourg City:LU

Vienna:AT
Graz:AT
Linz:AT

Zurich:CH
Geneva:CH
Basel:CH
Lausanne:CH

Copenhagen:DK
Aarhus:DK

Stockholm:SE
Gothenburg:SE
Malmö:SE

Oslo:NO
Bergen:NO

Helsinki:FI
Tampere:FI
Espoo:FI

Madrid:ES
Barcelona:ES
Valencia:ES
Sevilla:ES
Zaragoza:ES
Málaga:ES
Bilbao:ES

Lisbon:PT
Porto:PT
Braga:PT

Rome:IT
Milan:IT
Naples:IT
Turin:IT
Palermo:IT
Genoa:IT
Bologna:IT
Florence:IT

Athens:GR
Thessaloniki:GR

Warsaw:PL
Kraków:PL
Łódź:PL
Wrocław:PL
Poznań:PL
Gdańsk:PL

Prague:CZ
Brno:CZ

Budapest:HU
Debrecen:HU

Bucharest:RO
Cluj-Napoca:RO

Sofia:BG
Varna:BG

Belgrade:RS
Novi Sad:RS

Zagreb:HR
Ljubljana:SI
Bratislava:SK

Tallinn:EE
Riga:LV
Vilnius:LT
"""
    path.write_text(content, encoding="utf-8")


def load_europe_cities(path: Path = CITIES_FILE) -> list[tuple[str, str]]:
    """
    Load a 'city:CC' file into a list of (name, country_code).
    """
    ensure_cities_file(path)

    cities: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, cc = line.split(":")
            cities.append((name, cc))
    return cities


CITY_COORDS = {
    "London": (51.5074, -0.1278),
    "Birmingham": (52.4862, -1.8904),
    "Manchester": (53.4808, -2.2426),
    "Glasgow": (55.8642, -4.2518),
    "Dublin": (53.3498, -6.2603),
    "Belfast": (54.5970, -5.9301),
    "Edinburgh": (55.9533, -3.1883),
    "Paris": (48.8566, 2.3522),
    "Marseille": (43.2965, 5.3698),
    "Lyon": (45.7640, 4.8357),
    "Toulouse": (43.6047, 1.4442),
    "Nice": (43.7102, 7.2620),
    "Nantes": (47.2184, -1.5536),
    "Strasbourg": (48.5734, 7.7521),
    "Berlin": (52.5200, 13.4050),
    "Hamburg": (53.5511, 9.9937),
    "Munich": (48.1351, 11.5820),
    "Cologne": (50.9375, 6.9603),
    "Frankfurt": (50.1109, 8.6821),
    "Stuttgart": (48.7758, 9.1829),
    "Düsseldorf": (51.2277, 6.7735),
    "Dresden": (51.0504, 13.7373),
    "Leipzig": (51.3397, 12.3731),
    "Amsterdam": (52.3676, 4.9041),
    "Rotterdam": (51.9244, 4.4777),
    "The Hague": (52.0705, 4.3007),
    "Utrecht": (52.0907, 5.1214),
    "Eindhoven": (51.4416, 5.4697),
    "Brussels": (50.8503, 4.3517),
    "Antwerp": (51.2194, 4.4025),
    "Ghent": (51.0543, 3.7174),
    "Liège": (50.6326, 5.5797),
    "Luxembourg City": (49.6116, 6.1319),
    "Vienna": (48.2082, 16.3738),
    "Graz": (47.0707, 15.4395),
    "Linz": (48.3069, 14.2858),
    "Zurich": (47.3769, 8.5417),
    "Geneva": (46.2044, 6.1432),
    "Basel": (47.5596, 7.5886),
    "Lausanne": (46.5197, 6.6323),
    "Copenhagen": (55.6761, 12.5683),
    "Aarhus": (56.1629, 10.2039),
    "Stockholm": (59.3293, 18.0686),
    "Gothenburg": (57.7089, 11.9746),
    "Malmö": (55.6050, 13.0038),
    "Oslo": (59.9139, 10.7522),
    "Bergen": (60.3920, 5.3221),
    "Helsinki": (60.1699, 24.9384),
    "Tampere": (61.4978, 23.7610),
    "Espoo": (60.2055, 24.6559),
    "Madrid": (40.4168, -3.7038),
    "Barcelona": (41.3851, 2.1734),
    "Valencia": (39.4699, -0.3763),
    "Sevilla": (37.3891, -5.9845),
    "Zaragoza": (41.6488, -0.8891),
    "Málaga": (36.7213, -4.4214),
    "Bilbao": (43.2630, -2.9350),
    "Lisbon": (38.7223, -9.1393),
    "Porto": (41.1579, -8.6291),
    "Braga": (41.5454, -8.4265),
    "Rome": (41.9028, 12.4964),
    "Milan": (45.4642, 9.1900),
    "Naples": (40.8518, 14.2681),
    "Turin": (45.0703, 7.6869),
    "Palermo": (38.1157, 13.3613),
    "Genoa": (44.4056, 8.9463),
    "Bologna": (44.4949, 11.3426),
    "Florence": (43.7696, 11.2558),
    "Athens": (37.9838, 23.7275),
    "Thessaloniki": (40.6401, 22.9444),
    "Warsaw": (52.2297, 21.0122),
    "Kraków": (50.0647, 19.9450),
    "Łódź": (51.7592, 19.4550),
    "Wrocław": (51.1079, 17.0385),
    "Poznań": (52.4064, 16.9252),
    "Gdańsk": (54.3520, 18.6466),
    "Prague": (50.0755, 14.4378),
    "Brno": (49.1951, 16.6068),
    "Budapest": (47.4979, 19.0402),
    "Debrecen": (47.5316, 21.6273),
    "Bucharest": (44.4268, 26.1025),
    "Cluj-Napoca": (46.7712, 23.6236),
    "Sofia": (42.6977, 23.3219),
    "Varna": (43.2141, 27.9147),
    "Belgrade": (44.7866, 20.4489),
    "Novi Sad": (45.2671, 19.8335),
    "Zagreb": (45.8150, 15.9819),
    "Ljubljana": (46.0569, 14.5058),
    "Bratislava": (48.1486, 17.1077),
    "Tallinn": (59.4370, 24.7536),
    "Riga": (56.9496, 24.1052),
    "Vilnius": (54.6872, 25.2797),
}

EU_CITIES = load_europe_cities()


def nearest_city(lat: float, lon: float) -> str:
    """
    Find nearest city as 'City:CC' using squared distance in lat/lon.
    """
    best: Optional[str] = None
    best_dist = float("inf")

    for name, cc in EU_CITIES:
        if name not in CITY_COORDS:
            continue
        c_lat, c_lon = CITY_COORDS[name]
        dist = (lat - c_lat) ** 2 + (lon - c_lon) ** 2
        if dist < best_dist:
            best_dist = dist
            best = f"{name}:{cc}"

    return best or "unknown"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_rain_map(filepath: Path) -> dict:
    """
    Load a rainfall map from ODIM-HDF5 (.h5).

    Returns:
        {
            'rain': 2D numpy array (mm),
            'timestamp': datetime,
        }
    """
    filepath = Path(filepath)
    if filepath.suffix != ".h5":
        raise ValueError(f"Only .h5 is supported here, got {filepath.suffix}")

    with h5py.File(filepath, "r") as f:
        data = f["/dataset1/data1/data"][:]

    rain = np.array(data, dtype=float)
    rain[rain <= -9e6] = 0.0  # missing-data flag

    stem = filepath.stem
    dt_str = stem.split("_")[-1]
    timestamp = dt.datetime.strptime(dt_str, "%Y%m%d%H%M")

    return {"rain": rain, "timestamp": timestamp}


def get_latlon_grid_from_h5(filepath: Path) -> tuple[np.ndarray, np.ndarray]:
    """
    Approximate lat/lon grid from /where corner attributes.
    """
    filepath = Path(filepath)
    with h5py.File(filepath, "r") as f:
        where = f["/where"].attrs

        LL_lat = where["LL_lat"]
        LL_lon = where["LL_lon"]
        LR_lat = where["LR_lat"]
        LR_lon = where["LR_lon"]
        UL_lat = where["UL_lat"]
        UL_lon = where["UL_lon"]
        UR_lat = where["UR_lat"]
        UR_lon = where["UR_lon"]

        ysize = int(where["ysize"])
        xsize = int(where["xsize"])

    r = np.linspace(0.0, 1.0, ysize)  # south->north
    c = np.linspace(0.0, 1.0, xsize)  # west->east
    R, C = np.meshgrid(r, c, indexing="ij")

    lat_south = (1 - C) * LL_lat + C * LR_lat
    lon_south = (1 - C) * LL_lon + C * LR_lon
    lat_north = (1 - C) * UL_lat + C * UR_lat
    lon_north = (1 - C) * UL_lon + C * UR_lon

    LAT = (1 - R) * lat_south + R * lat_north
    LON = (1 - R) * lon_south + R * lon_north

    return LAT, LON


# ---------------------------------------------------------------------------
# Patch detection
# ---------------------------------------------------------------------------

@dataclass
class RainPatch:
    """
    Container for a rainfall patch extracted from one full map.
    """

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
    """
    Optionally smooth rainfall using a uniform filter over
    avg_window_y × avg_window_x pixels. If window = 1×1, returns original.
    """
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
) -> list[tuple[int, int, int, int]]:
    """
    Find bounding boxes of connected rain regions satisfying size limits.

    Returns list of (y_min, y_max, x_min, x_max) in pixel indices.
    """
    mask = rain >= threshold_mm
    labeled, num = ndi.label(mask)

    min_w_px = int(round(min_width_km / PIXEL_SIZE_KM))
    min_h_px = int(round(min_height_km / PIXEL_SIZE_KM))
    max_w_px = None if max_width_km is None else int(round(max_width_km / PIXEL_SIZE_KM))
    max_h_px = None if max_height_km is None else int(round(max_height_km / PIXEL_SIZE_KM))

    bboxes: list[tuple[int, int, int, int]] = []

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
    """
    Load one rainfall map and detect patches according to the parameters.
    """
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
        sub = rain[y_min:y_max + 1, x_min:x_max + 1]
        h_px, w_px = sub.shape

        width_km = w_px * PIXEL_SIZE_KM
        height_km = h_px * PIXEL_SIZE_KM
        area_km2 = width_km * height_km
        mean_r = float(sub.mean())
        max_r = float(sub.max())

        sub_lat = LAT[y_min:y_max + 1, x_min:x_max + 1]
        sub_lon = LON[y_min:y_max + 1, x_min:x_max + 1]
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


# ---------------------------------------------------------------------------
# FastAPI models
# ---------------------------------------------------------------------------

class PatchParams(BaseModel):
    threshold_mm: float = 0.5
    avg_window_y: int = 1
    avg_window_x: int = 1
    min_width_km: float = 200.0
    min_height_km: float = 200.0
    max_width_km: Optional[float] = None
    max_height_km: Optional[float] = None
    max_files: int = 10


class PatchOut(BaseModel):
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


class BenchmarkSaveRequest(BaseModel):
    name: str
    patch_ids: list[str]


class BenchmarkLoadRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# FastAPI app & globals
# ---------------------------------------------------------------------------

app = FastAPI(title="Rain Patch Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_LAST_PATCHES: list[RainPatch] = []
_LAST_PATCH_DATA: dict[str, np.ndarray] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/files")
def list_files(limit: int = Query(50, ge=1, le=500)) -> list[str]:
    """
    List available EURADCLIM .h5 files (for UI info).
    """
    files = sorted(RAW_DIR.rglob("RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_*.h5"))
    return [str(f) for f in files[:limit]]


@app.post("/detect_patches", response_model=list[PatchOut])
def detect_patches(params: PatchParams):
    """
    Run patch detection over a subset of files with the given parameters.
    """
    global _LAST_PATCHES, _LAST_PATCH_DATA

    files = sorted(RAW_DIR.rglob("RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_*.h5"))
    files = files[: params.max_files]
    print(f"[detect_patches] Using {len(files)} files")

    all_patches: list[RainPatch] = []
    patch_data: dict[str, np.ndarray] = {}

    for f in files:
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
        for p in patches:
            all_patches.append(p)
            arr = getattr(p, "_data", None)
            if arr is not None:
                patch_data[p.id] = arr

    _LAST_PATCHES = all_patches
    _LAST_PATCH_DATA = patch_data

    print(f"[detect_patches] Found {len(all_patches)} patches in total")

    return [PatchOut(**asdict(p)) for p in all_patches]


@app.get("/patches", response_model=list[PatchOut])
def get_patches() -> list[PatchOut]:
    """
    Return the patches from the last detection or benchmark load.
    """
    return [PatchOut(**asdict(p)) for p in _LAST_PATCHES]


@app.get("/patch_image/{patch_id}")
def patch_image(patch_id: str):
    """
    Return a PNG heat map for a given patch_id.
    Uses the data from the last detection or loaded benchmark.
    """
    if patch_id not in _LAST_PATCH_DATA:
        raise HTTPException(status_code=404, detail="Patch not found in memory")

    data = _LAST_PATCH_DATA[patch_id]

    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(data, origin="upper")
    cbar = plt.colorbar(im, ax=ax, label="mm")
    ax.set_title(patch_id, fontsize=8)
    ax.set_xticks([])
    ax.set_yticks([])

    from io import BytesIO
    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)

    return Response(content=buf.read(), media_type="image/png")


@app.get("/patches/export_excel")
def export_patches_excel() -> dict:
    """
    Export the last patch set to an Excel file containing:
        - nearest city
        - width, height
        - mean & max rainfall
        - etc.
    """
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
                "center_lat": p.center_lat,
                "center_lon": p.center_lon,
            }
        )

    df = pd.DataFrame(rows)
    out_path = EXPORT_DIR / "patches_export.xlsx"
    df.to_excel(out_path, index=False)
    return {"status": "ok", "excel_path": str(out_path)}


@app.get("/benchmark/list")
def list_benchmarks() -> list[str]:
    """
    List available benchmark NPZ files (names without extension).
    """
    files = sorted(BENCHMARK_DIR.glob("*.npz"))
    names = [f.stem for f in files]
    return names


def _save_patches_to_npz(path: Path, patches: list[RainPatch], data_map: dict[str, np.ndarray]):
    ids = []
    source_files = []
    timestamps = []
    nearest_cities = []
    y_min = []
    y_max = []
    x_min = []
    x_max = []
    width_km = []
    height_km = []
    area_km2 = []
    mean_rainfall = []
    max_rainfall = []
    center_lat = []
    center_lon = []
    patch_arrays = []

    for p in patches:
        ids.append(p.id)
        source_files.append(p.source_file)
        timestamps.append(p.timestamp.isoformat())
        nearest_cities.append(p.nearest_city)
        y_min.append(p.y_min)
        y_max.append(p.y_max)
        x_min.append(p.x_min)
        x_max.append(p.x_max)
        width_km.append(p.width_km)
        height_km.append(p.height_km)
        area_km2.append(p.area_km2)
        mean_rainfall.append(p.mean_rainfall)
        max_rainfall.append(p.max_rainfall)
        center_lat.append(p.center_lat)
        center_lon.append(p.center_lon)

        arr = data_map.get(p.id)
        if arr is None:
            patch_arrays.append(np.array([[]], dtype=float))
        else:
            patch_arrays.append(arr)

    np.savez_compressed(
        path,
        ids=np.array(ids),
        source_files=np.array(source_files),
        timestamps=np.array(timestamps),
        nearest_cities=np.array(nearest_cities),
        y_min=np.array(y_min),
        y_max=np.array(y_max),
        x_min=np.array(x_min),
        x_max=np.array(x_max),
        width_km=np.array(width_km),
        height_km=np.array(height_km),
        area_km2=np.array(area_km2),
        mean_rainfall=np.array(mean_rainfall),
        max_rainfall=np.array(max_rainfall),
        center_lat=np.array(center_lat),
        center_lon=np.array(center_lon),
        patch_data=np.array(patch_arrays, dtype=object),
    )


@app.post("/benchmark/save")
def save_benchmark(req: BenchmarkSaveRequest) -> dict:
    """
    Save the selected patches (by id) from the last detection into a benchmark NPZ.

    File path: data/benchmarks/<name>.npz
    """
    if not _LAST_PATCHES:
        return {"status": "no_patches", "message": "Run /detect_patches first."}

    patch_ids_set = set(req.patch_ids)
    selected = [p for p in _LAST_PATCHES if p.id in patch_ids_set]

    if not selected:
        return {"status": "empty", "message": "No matching patches to save."}

    safe_name = "".join(c for c in req.name if c.isalnum() or c in ("-", "_"))
    if not safe_name:
        safe_name = "benchmark"

    out_path = BENCHMARK_DIR / f"{safe_name}.npz"
    _save_patches_to_npz(out_path, selected, _LAST_PATCH_DATA)

    return {"status": "ok", "npz_path": str(out_path), "count": len(selected)}


@app.post("/benchmark/load", response_model=list[PatchOut])
def load_benchmark(req: BenchmarkLoadRequest):
    """
    Load a benchmark NPZ (by name) and replace the in-memory patch set.
    Returns the patch metadata as PatchOut list.
    """
    global _LAST_PATCHES, _LAST_PATCH_DATA

    name = req.name
    if name.endswith(".npz"):
        path = BENCHMARK_DIR / name
    else:
        path = BENCHMARK_DIR / f"{name}.npz"

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Benchmark {name} not found")

    npz = np.load(path, allow_pickle=True)

    ids = npz["ids"]
    source_files = npz["source_files"]
    timestamps = npz["timestamps"]
    nearest_cities = npz["nearest_cities"]
    y_min = npz["y_min"]
    y_max = npz["y_max"]
    x_min = npz["x_min"]
    x_max = npz["x_max"]
    width_km = npz["width_km"]
    height_km = npz["height_km"]
    area_km2 = npz["area_km2"]
    mean_rainfall = npz["mean_rainfall"]
    max_rainfall = npz["max_rainfall"]
    center_lat = npz["center_lat"]
    center_lon = npz["center_lon"]
    patch_data = npz["patch_data"]

    patches: list[RainPatch] = []
    data_map: dict[str, np.ndarray] = {}

    for i in range(len(ids)):
        pid = str(ids[i])
        ts = dt.datetime.fromisoformat(str(timestamps[i]))

        p = RainPatch(
            id=pid,
            source_file=str(source_files[i]),
            timestamp=ts,
            y_min=int(y_min[i]),
            y_max=int(y_max[i]),
            x_min=int(x_min[i]),
            x_max=int(x_max[i]),
            mean_rainfall=float(mean_rainfall[i]),
            max_rainfall=float(max_rainfall[i]),
            width_km=float(width_km[i]),
            height_km=float(height_km[i]),
            area_km2=float(area_km2[i]),
            center_lat=float(center_lat[i]),
            center_lon=float(center_lon[i]),
            nearest_city=str(nearest_cities[i]),
        )
        patches.append(p)
        data_map[pid] = patch_data[i]

    _LAST_PATCHES = patches
    _LAST_PATCH_DATA = data_map

    return [PatchOut(**asdict(p)) for p in patches]


# Entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

