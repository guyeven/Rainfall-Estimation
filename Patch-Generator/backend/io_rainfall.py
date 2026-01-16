from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import h5py
import numpy as np

from config import RAW_DIR

# Optional dependency for proper map projection
try:
    from pyproj import CRS, Transformer

    _HAS_PYPROJ = True
except ImportError:  # pragma: no cover - graceful fallback
    CRS = Transformer = None  # type: ignore
    _HAS_PYPROJ = False


PathLike = Union[str, Path]


# ---------------------------------------------------------------------------
# Simple file listing and legacy loader (used by app.py and others)
# ---------------------------------------------------------------------------


def list_rain_files(limit: int | None = None) -> List[Tuple[Path, dt.datetime]]:
    """Return [(filepath, timestamp), ...] sorted by timestamp descending."""
    files = sorted(
        RAW_DIR.glob("RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_*.h5"),
        key=lambda p: p.stem,
        reverse=True,
    )
    if limit is not None:
        files = files[:limit]

    result: List[Tuple[Path, dt.datetime]] = []
    for f in files:
        stem = f.stem
        dt_str = stem.split("_")[-1]  # e.g. 202301010600
        try:
            ts = dt.datetime.strptime(dt_str, "%Y%m%d%H%M")
        except ValueError:
            ts = dt.datetime.fromtimestamp(f.stat().st_mtime)
        result.append((f, ts))
    return result


def load_rain_map(filepath: PathLike) -> dict:
    """
    Legacy helper: load rainfall [mm] and timestamp from an ODIM HDF5 file.

    NOTE: This does NOT return lat/lon; use read_rainfall_h5() instead
    if you need a proper geolocated field.
    """
    filepath = Path(filepath)
    with h5py.File(filepath, "r") as f:
        data = f["/dataset1/data1/data"][:]

    rain = np.array(data, dtype=float)
    # Missing data flag as in OPERA products
    rain[rain <= -9e6] = 0.0

    stem = filepath.stem
    dt_str = stem.split("_")[-1]
    timestamp = dt.datetime.strptime(dt_str, "%Y%m%d%H%M")

    return {"rain": rain, "timestamp": timestamp}


# ---------------------------------------------------------------------------
# Geolocated rainfall container
# ---------------------------------------------------------------------------


@dataclass
class RainfallField:
    """
    Container for a rainfall field and its geolocation grid.
    """

    data: np.ndarray  # 2D rainfall array [mm]
    lat: np.ndarray   # 2D latitude grid (same shape as data)
    lon: np.ndarray   # 2D longitude grid (same shape as data)
    meta: Dict[str, object]  # Additional metadata (attrs, shape, path, etc.)


# ---------------------------------------------------------------------------
# Helpers
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

    return best_ds  # type: ignore[return-value]


def _get_attr_case_insensitive(
    attrs: h5py.AttributeManager, *names: str
) -> Optional[object]:
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

    # Fallback: top-level attrs
    return f.attrs


# ---------------------------------------------------------------------------
# Lat/lon grid builders
# ---------------------------------------------------------------------------


def _build_latlon_grid_from_attrs(
    attrs: h5py.AttributeManager, ny: int, nx: int
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Legacy method: build a 2D lat/lon grid from four corner coordinates
    stored in attributes, by bilinear interpolation in *lat/lon* space.

    This is approximate but robust, and works without pyproj.
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

    # Assume rectilinear lat/lon grid between UL–LL and UL–UR.
    lat_edge_top = UL_lat
    lat_edge_bottom = LL_lat
    lon_edge_left = UL_lon
    lon_edge_right = UR_lon

    lat_1d = np.linspace(lat_edge_top, lat_edge_bottom, ny, endpoint=True)
    lon_1d = np.linspace(lon_edge_left, lon_edge_right, nx, endpoint=True)

    lon_grid_2d, lat_grid_2d = np.meshgrid(lon_1d, lat_1d)  # (X, Y)

    return lat_grid_2d.astype(float), lon_grid_2d.astype(float)


def _build_latlon_grid_precise(
    attrs: h5py.AttributeManager, ny: int, nx: int
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Projection-aware lat/lon grid using PROJ4 parameters + corner coordinates.

    Steps:
      1) Read projdef (PROJ4 string) from attrs.
      2) Project the four corner lon/lat to projection plane (x,y).
      3) Bilinear interpolation in *projection* space over (ny, nx).
      4) Transform full (x,y) grid back to WGS84 lon/lat.

    This uses the correct projection (e.g. LAEA) and is much more accurate
    than interpolating directly in lat/lon.
    """
    if not _HAS_PYPROJ:
        raise ImportError(
            "pyproj is not installed; cannot build projection-based lat/lon grid."
        )

    projdef = _get_attr_case_insensitive(attrs, "projdef", "projection_proj4_params")
    if projdef is None:
        raise KeyError(
            "No 'projdef' / 'projection_proj4_params' attribute found for projection."
        )

    if isinstance(projdef, bytes):
        projdef_str = projdef.decode()
    else:
        projdef_str = str(projdef)

    proj_crs = CRS.from_proj4(projdef_str)
    geo_crs = CRS.from_epsg(4326)

    # Forward: lon,lat -> x,y (projection plane)
    to_proj = Transformer.from_crs(geo_crs, proj_crs, always_xy=True)
    # Inverse: x,y -> lon,lat
    to_geo = Transformer.from_crs(proj_crs, geo_crs, always_xy=True)

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

    # Corner lat/lon (as in KNMI/ODIM spec).
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

    # Project corners into x/y (meters)
    X_UL, Y_UL = to_proj.transform(UL_lon, UL_lat)
    X_UR, Y_UR = to_proj.transform(UR_lon, UR_lat)
    X_LL, Y_LL = to_proj.transform(LL_lon, LL_lat)
    X_LR, Y_LR = to_proj.transform(LR_lon, LR_lat)

    # Fractions along Y (0 at top/UL, 1 at bottom/LL) and X (0 left, 1 right)
    ys = np.linspace(0.0, 1.0, ny)
    xs = np.linspace(0.0, 1.0, nx)

    # Interpolate along left and right edges in projection space
    X_left = X_UL + (X_LL - X_UL) * ys[:, None]
    Y_left = Y_UL + (Y_LL - Y_UL) * ys[:, None]
    X_right = X_UR + (X_LR - X_UR) * ys[:, None]
    Y_right = Y_UR + (Y_LR - Y_UR) * ys[:, None]

    # Bilinear interpolation across each row
    X_grid = X_left + (X_right - X_left) * xs[None, :]
    Y_grid = Y_left + (Y_right - Y_left) * xs[None, :]

    # Back to lon/lat
    lon_grid, lat_grid = to_geo.transform(X_grid, Y_grid)

    return lat_grid.astype(float), lon_grid.astype(float)


def _get_shape_from_attrs(
    attrs: h5py.AttributeManager, data_shape: Tuple[int, ...]
) -> Tuple[int, int]:
    """
    Determine (ny, nx) either from attributes or from the data shape.
    """
    ny_attr = _get_attr_case_insensitive(
        attrs, "nrows", "rows", "ny", "y_size", "y_dim", "ysize"
    )
    nx_attr = _get_attr_case_insensitive(
        attrs, "ncols", "columns", "nx", "x_size", "x_dim", "xsize"
    )

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
# Public API: main geolocated reader
# ---------------------------------------------------------------------------


def read_rainfall_h5(path: PathLike) -> RainfallField:
    """
    Read a rainfall HDF5 file and return data + lat/lon grid + metadata.

    Geolocation:
      - If 'projdef' (or 'projection_proj4_params') is present and pyproj is
        installed, use a projection-aware grid in the projection plane and
        transform back to WGS84 ("proj4_corners").
      - Otherwise, fall back to bilinear interpolation in lat/lon space using
        the four corner coordinates ("corner_bilinear").
    """
    filepath = _as_path(path)

    with h5py.File(filepath, "r") as f:
        ds = _find_main_dataset(f)
        data = ds[()]

        # Ensure we end up with a 2D array (strip time or other leading dims if needed)
        if data.ndim > 2:
            # Assume last two dimensions are (y, x)
            data_2d = data.reshape((-1, data.shape[-2], data.shape[-1]))[-1]
        else:
            data_2d = data

        attrs = _find_geo_attr_group(f)
        ny, nx = _get_shape_from_attrs(attrs, data_2d.shape)

        if data_2d.shape != (ny, nx):
            # Just a sanity check; we don't enforce equality.
            # You can tighten this if needed.
            pass

        geo_method = "corner_bilinear"

        # Try projection-aware grid first if possible
        lat_grid: np.ndarray
        lon_grid: np.ndarray
        try:
            if _HAS_PYPROJ:
                lat_grid, lon_grid = _build_latlon_grid_precise(attrs, ny, nx)
                geo_method = "proj4_corners"
            else:
                # pyproj missing: fall back
                lat_grid, lon_grid = _build_latlon_grid_from_attrs(attrs, ny, nx)
        except Exception:
            # Any failure in the precise path -> safe fallback
            lat_grid, lon_grid = _build_latlon_grid_from_attrs(attrs, ny, nx)
            geo_method = "corner_bilinear"

        meta: Dict[str, object] = {
            "file": str(filepath),
            "dataset_path": ds.name,
            "data_shape": data.shape,
            "used_shape": data_2d.shape,
            "available_attrs": list(attrs.keys()),
            "geo_method": geo_method,
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
