from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

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
    """Return nearest city as 'City:CC' using squared distance in lat/lon."""
    best: Optional[str] = None
    best_dist = float("inf")

    for name, cc in EU_CITIES:
        coords = CITY_COORDS.get(name)
        if coords is None:
            continue
        c_lat, c_lon = coords
        dist = (lat - c_lat) ** 2 + (lon - c_lon) ** 2
        if dist < best_dist:
            best_dist = dist
            best = f"{name}:{cc}"

    return best or "Unknown:??"

