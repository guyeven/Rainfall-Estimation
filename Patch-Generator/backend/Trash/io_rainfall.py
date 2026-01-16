from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple, Union

import h5py
import numpy as np


PathLike = Union[str, Path]


@dataclass
class RainfallField:
    """
    Container for a rainfall field and its geolocation grid.
    """
    data: np.ndarray          # 2D rainfall array [mm]
    lat: np.ndarray           # 2D latitude grid (same shape as data)
    lon: np.ndarray           # 2D longitude grid (same shape as data)
    meta: Dict[str, object]   # Additional metadata (attrs, shape, path, etc.)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _as_path(path: PathLike) -> Path:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Rainfall file not found: {p}")
    return p


def _try_paths(f: h5py.File, candidates: Iterable[str]) -> Optional[h5py.Dataset]:
    """
    Try several dataset paths and return the first one that exists.
    """
    for p in candidates:
        if p in f:
            obj = f[p]
            if isinstance(obj, h5py.Dataset):
                return obj
    return None


def _find_main_dataset(f: h5py.File) -> h5py.Dataset:
    """
    Heuristic to find the main rainfall dataset in the HDF5 file.

    First tries common OPERA-like paths, then falls back to "largest 2D dataset".
    """
    common_paths = [
        "/dataset1/data1/data",
        "/dataset1/data",
        "/data",
        "/image1/data",
        "/image1/image_data",
    ]

    ds = _try_paths(f, common_paths)
    if ds is not None:
        return ds

    # Fallback: pick the largest 2D dataset in the file
    best_ds = None
    best_size = -1

    def visitor(name, obj):
        nonlocal best_ds, best_size
        if isinstance(obj, h5py.Dataset) and obj.ndim >= 2:
            size = int(np.prod(obj.shape))
            if size > best_size:
                best_size = size
                best_ds = obj

    f.visititems(visitor)

    if best_ds is None:
        raise KeyError(
            "Could not find a suitable rainfall dataset in HDF5 file. "
            "No 2D datasets detected. Please inspect the file structure "
            "and update _find_main_dataset()."
        )

    return best_ds


def _get_attr_case_insensitive(attrs: h5py.AttributeManager, *names: str) -> Optional[object]:
    """
    Try to get an attribute by trying several names, case-insensitively.
    Returns None if nothing matches.
    """
    lookup = {str(k).lower(): k for k in attrs.keys()}

    for candidate in names:
        key_lc = candidate.lower()
        if key_lc in lookup:
            return attrs[lookup[key_lc]]

    return None


def _find_geo_attr_group(f: h5py.File) -> h5py.AttributeManager:
    """
    Find the attribute group that holds geolocation information (corner lat/lon, nrows, ncols).
    Common candidates: '/where', '/geolocation', '/grid'.
    """
    group_candidates = [
        "/where",
        "/geolocation",
        "/grid",
        "/geolocation_data",
    ]

    for gpath in group_candidates:
        if gpath in f:
            grp = f[gpath]
            if isinstance(grp, h5py.Group):
                return grp.attrs

    # Fallback: try top-level attrs
    return f.attrs


def _build_latlon_grid_from_attrs(attrs: h5py.AttributeManager, ny: int, nx: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build a 2D lat/lon grid from corner coordinates stored in attributes.
    Expects (or tries to guess):

      - LL_lat, LL_lon
      - LR_lat, LR_lon
      - UL_lat, UL_lon
      - UR_lat, UR_lon

    but supports several naming variations (case-insensitive).
    """

    def get_corner(lat_names, lon_names, label: str) -> Tuple[float, float]:
        lat = _get_attr_case_insensitive(attrs, *lat_names)
        lon = _get_attr_case_insensitive(attrs, *lon_names)

        if lat is None or lon is None:
            raise KeyError(
                f"Missing {label} corner attributes. "
                f"Tried lat names {lat_names} and lon names {lon_names}. "
                f"Available attributes: {list(attrs.keys())}"
            )

        return float(lat), float(lon)

    # Try a few variants for each corner
    LL_lat, LL_lon = get_corner(
        ("LL_lat", "ll_lat", "Lat_LL", "lat_ll", "lower_left_lat"),
        ("LL_lon", "ll_lon", "Lon_LL", "lon_ll", "lower_left_lon"),
        "lower-left (LL)",
    )
    LR_lat, LR_lon = get_corner(
        ("LR_lat", "lr_lat", "Lat_LR", "lat_lr", "lower_right_lat"),
        ("LR_lon", "lr_lon", "Lon_LR", "lon_lr", "lower_right_lon"),
        "lower-right (LR)",
    )
    UL_lat, UL_lon = get_corner(
        ("UL_lat", "ul_lat", "Lat_UL", "lat_ul", "upper_left_lat"),
        ("UL_lon", "ul_lon", "Lon_UL", "lon_ul", "upper_left_lon"),
        "upper-left (UL)",
    )
    UR_lat, UR_lon = get_corner(
        ("UR_lat", "ur_lat", "Lat_UR", "lat_ur", "upper_right_lat"),
        ("UR_lon", "ur_lon", "Lon_UR", "lon_ur", "upper_right_lon"),
        "upper-right (UR)",
    )

    # Approximate a rectilinear grid:
    lat_edge_top = UL_lat
    lat_edge_bottom = LL_lat
    lon_edge_left = UL_lon
    lon_edge_right = UR_lon

    lat_1d = np.linspace(lat_edge_top, lat_edge_bottom, ny, endpoint=True)
    lon_1d = np.linspace(lon_edge_left, lon_edge_right, nx, endpoint=True)

    # meshgrid(x, y) -> X (lon), Y (lat)
    lon_grid, lat_grid = np.meshgrid(lon_1d, lat_1d)

    return lat_grid, lon_grid


def _get_shape_from_attrs(attrs: h5py.AttributeManager, data_shape: Tuple[int, ...]) -> Tuple[int, int]:
    """
    Determine (ny, nx) either from attributes or from the data shape.
    """
    ny_attr = _get_attr_case_insensitive(attrs, "nrows", "rows", "ny", "y_size", "y_dim")
    nx_attr = _get_attr_case_insensitive(attrs, "ncols", "columns", "nx", "x_size", "x_dim")

    if ny_attr is not None and nx_attr is not None:
        return int(ny_attr), int(nx_attr)

    # Fallback: use data shape (take last two dims)
    if len(data_shape) < 2:
        raise ValueError(
            f"Data shape {data_shape} is not at least 2D; cannot infer ny/nx."
        )

    ny, nx = data_shape[-2], data_shape[-1]
    return int(ny), int(nx)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_rainfall_h5(path: PathLike) -> RainfallField:
    """
    Read a rainfall HDF5 file and return data + lat/lon grid + metadata.
    """
    filepath = _as_path(path)

    with h5py.File(filepath, "r") as f:
        ds = _find_main_dataset(f)
        data = ds[()]

        # Ensure we end up with a 2D array (strip time or other leading dims if needed)
        if data.ndim > 2:
            # Assume last two dimensions are (y, x); take the last time slice
            data_2d = data.reshape((-1, data.shape[-2], data.shape[-1]))[-1]
        else:
            data_2d = data

        attrs = _find_geo_attr_group(f)
        ny, nx = _get_shape_from_attrs(attrs, data_2d.shape)

        if data_2d.shape != (ny, nx):
            # Just a sanity check; we don't enforce equality.
            pass

        lat_grid, lon_grid = _build_latlon_grid_from_attrs(attrs, ny, nx)

        meta: Dict[str, object] = {
            "file": str(filepath),
            "dataset_path": ds.name,
            "data_shape": data.shape,
            "used_shape": data_2d.shape,
            "available_attrs": list(attrs.keys()),
        }

        return RainfallField(
            data=data_2d.astype(float),
            lat=lat_grid,
            lon=lon_grid,
            meta=meta,
        )


def get_rainfall_array(path: PathLike) -> np.ndarray:
    """
    Convenience wrapper: return only the rainfall 2D array [mm].
    """
    return read_rainfall_h5(path).data


def get_latlon_grid_from_h5(path: PathLike) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convenience wrapper: return (lat_grid, lon_grid) only.
    """
    rf = read_rainfall_h5(path)
    return rf.lat, rf.lon


def load_rain_map(filepath: PathLike) -> dict:
    """
    Legacy compatibility wrapper used by other parts of the project.

    Returns a dict:
        {
            "rain": 2D np.ndarray,
            "timestamp": datetime | None,
            "coords": None  # (kept for future extension)
        }
    """
    p = Path(filepath)
    rain = get_rainfall_array(p)

    ts = None
    # Try to parse timestamp from filename: *_YYYYMMDDHHMM.h5
    try:
        stem = p.stem
        tail = stem.rsplit("_", 1)[-1]
        ts = datetime.strptime(tail, "%Y%m%d%H%M")
    except Exception:
        pass

    return {
        "rain": rain,
        "timestamp": ts,
        "coords": None,
    }


def list_rain_files(limit: Optional[int] = None):
    """
    Return a list of (Path, timestamp_iso_str_or_None) for rainfall files.

    This matches how app.api_list_files expects to use it:
        files = list_rain_files(limit)
        for p, ts in files: ...
    """
    root = Path("data/raw")
    pattern = "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_*.h5"

    files = sorted(root.glob(pattern))

    results: list[tuple[Path, Optional[str]]] = []

    for f in files:
        ts_iso: Optional[str] = None

        # Filenames like: RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301312300.h5
        try:
            stem = f.stem
            tail = stem.rsplit("_", 1)[-1]
            dt = datetime.strptime(tail, "%Y%m%d%H%M")
            ts_iso = dt.isoformat()
        except Exception:
            pass

        results.append((f, ts_iso))

    if limit is not None:
        results = results[:limit]

    return results
