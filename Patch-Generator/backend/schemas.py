from __future__ import annotations

import datetime as dt
from typing import List, Optional

from pydantic import BaseModel


class PatchParams(BaseModel):
    threshold_mm: float = 10
    avg_window_y: int = 10
    avg_window_x: int = 10
    min_width_km: float = 50.0
    min_height_km: float = 50.0
    max_width_km: Optional[float] = 250
    max_height_km: Optional[float] = 250
    max_files: int = 10

    # optional list of file paths selected in UI
    files: Optional[List[str]] = []


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


class FileInfo(BaseModel):
    path: str
    timestamp: dt.datetime


class PatchGeoInfo(BaseModel):
    patch_id: str
    center_lat: float
    center_lon: float
    patch_lat_min: float
    patch_lat_max: float
    patch_lon_min: float
    patch_lon_max: float
    map_lat_min: float
    map_lat_max: float
    map_lon_min: float
    map_lon_max: float
    tile_url_template: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"


class BenchmarkSaveRequest(BaseModel):
    name: str
    patch_ids: List[str]


class BenchmarkLoadRequest(BaseModel):
    name: str

