from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import List

import numpy as np

from config import BENCHMARK_DIR
from patches import RainPatch


def _benchmark_path(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
    if not safe:
        safe = "benchmark"
    return BENCHMARK_DIR / f"{safe}.npz"


def save_benchmark_npz(name: str, patches: List[RainPatch], ids: List[str]) -> dict:
    path = _benchmark_path(name)
    selected = [p for p in patches if p.id in ids]
    if not selected:
        return {"status": "empty", "message": "No matching patches to save."}

    n = len(selected)
    ids_arr = np.array([p.id for p in selected], dtype=object)
    source_files = np.array([p.source_file for p in selected], dtype=object)
    timestamps = np.array([p.timestamp.isoformat() for p in selected], dtype=object)
    y_min = np.array([p.y_min for p in selected])
    y_max = np.array([p.y_max for p in selected])
    x_min = np.array([p.x_min for p in selected])
    x_max = np.array([p.x_max for p in selected])
    width_km = np.array([p.width_km for p in selected])
    height_km = np.array([p.height_km for p in selected])
    area_km2 = np.array([p.area_km2 for p in selected])
    mean_rainfall = np.array([p.mean_rainfall for p in selected])
    max_rainfall = np.array([p.max_rainfall for p in selected])
    nearest_cities = np.array([p.nearest_city for p in selected], dtype=object)

    np.savez_compressed(
        path,
        ids=ids_arr,
        source_files=source_files,
        timestamps=timestamps,
        y_min=y_min,
        y_max=y_max,
        x_min=x_min,
        x_max=x_max,
        width_km=width_km,
        height_km=height_km,
        area_km2=area_km2,
        mean_rainfall=mean_rainfall,
        max_rainfall=max_rainfall,
        nearest_cities=nearest_cities,
    )

    return {"status": "ok", "file": path.name, "count": n}


def list_benchmarks() -> List[str]:
    return sorted(p.name for p in BENCHMARK_DIR.glob("*.npz"))


def load_benchmark_npz(name: str) -> List[RainPatch]:
    path = _benchmark_path(name)
    if not path.exists():
        raise FileNotFoundError(path)

    npz = np.load(path, allow_pickle=True)
    ids = npz["ids"]
    source_files = npz["source_files"]
    timestamps = npz["timestamps"]
    y_min = npz["y_min"]
    y_max = npz["y_max"]
    x_min = npz["x_min"]
    x_max = npz["x_max"]
    width_km = npz["width_km"]
    height_km = npz["height_km"]
    area_km2 = npz["area_km2"]
    mean_rainfall = npz["mean_rainfall"]
    max_rainfall = npz["max_rainfall"]
    nearest_cities = npz["nearest_cities"]

    patches: List[RainPatch] = []
    for i in range(len(ids)):
        ts = dt.datetime.fromisoformat(str(timestamps[i]))
        p = RainPatch(
            id=str(ids[i]),
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
            center_lat=0.0,  # can be recomputed if needed
            center_lon=0.0,
            nearest_city=str(nearest_cities[i]),
        )
        patches.append(p)

    return patches

