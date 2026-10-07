from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple
from math import asin, cos, radians, sin, sqrt

from config import CITIES_FILE
from cities_list import CITIES_TEXT, CITY_COORDS


def ensure_cities_file(path: Path = CITIES_FILE) -> None:
    """Create the city list file if it does not exist yet."""
    if path.exists():
        return
    path.write_text(CITIES_TEXT, encoding="utf-8")


def load_europe_cities(path: Path = CITIES_FILE) -> List[Tuple[str, str]]:
    """Load 'City:CC' rows from the city file."""
    ensure_cities_file(path)
    cities: List[Tuple[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, cc = line.split(":")
            cities.append((name, cc))
    return cities


EU_CITIES = load_europe_cities()


def nearest_city(lat: float, lon: float) -> str:
    """Return the nearest meaningful city as ``City:CC``.

    Use a haversine distance so longitude is scaled correctly at European
    latitudes.  The catalogue intentionally contains regional cities as well
    as capitals, so a patch does not get labelled with a distant major city.
    """
    best: Optional[str] = None
    best_dist = float("inf")

    for name, cc in EU_CITIES:
        coords = CITY_COORDS.get(name)
        if coords is None:
            continue
        c_lat, c_lon = coords
        lat1, lon1, lat2, lon2 = map(radians, (lat, lon, c_lat, c_lon))
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        dist = asin(sqrt(a))
        if dist < best_dist:
            best_dist = dist
            best = f"{name}:{cc}"

    return best or "Unknown:??"
