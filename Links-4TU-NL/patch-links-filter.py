#!/usr/bin/env python3
"""
patch-links-filter.py

FastAPI backend that:
- Anchors a rectangle at a fixed NW corner (lat/lon)
- Computes rectangle EXACTLY in meters using EPSG:28992 (RD New)
- Filters links whose BOTH endpoints lie inside the rectangle
- Returns rectangle bounds (for Leaflet) + filtered links JSON

Run:
  LINKS_JSONL=/full/path/to/unique_links.jsonl \
  uvicorn patch-links-filter:app --port 8300
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pyproj import Transformer

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

ANCHOR_NW_LAT = 52.38897
ANCHOR_NW_LON = 4.528701910089581

WGS84 = "EPSG:4326"
RDNEW = "EPSG:28992"   # meters, Netherlands

to_rd = Transformer.from_crs(WGS84, RDNEW, always_xy=True)
to_wgs = Transformer.from_crs(RDNEW, WGS84, always_xy=True)

# ------------------------------------------------------------
# Data model
# ------------------------------------------------------------

@dataclass(frozen=True)
class Link:
    XStart: float
    YStart: float
    XEnd: float
    YEnd: float
    Frequency: float
    PathLength: float
    xs_m: float
    ys_m: float
    xe_m: float
    ye_m: float

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def resolve_links_path() -> Path:
    """
    Priority:
    1) env LINKS_JSONL
    2) unique_links.jsonl in same directory as this script
    """
    env = os.environ.get("LINKS_JSONL")
    if env:
        return Path(env).expanduser().resolve()

    script_dir = Path(__file__).resolve().parent
    candidate = script_dir / "unique_links.jsonl"
    return candidate.resolve()


def load_links(path: Path) -> List[Link]:
    if not path.exists():
        raise RuntimeError(
            f"Links file not found: {path}\n"
            f"Set env LINKS_JSONL=/path/to/unique_links.jsonl "
            f"or place unique_links.jsonl next to this script."
        )

    links: List[Link] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            r = json.loads(line)

            xs = float(r["XStart"])
            ys = float(r["YStart"])
            xe = float(r["XEnd"])
            ye = float(r["YEnd"])

            xs_m, ys_m = to_rd.transform(xs, ys)
            xe_m, ye_m = to_rd.transform(xe, ye)

            links.append(
                Link(
                    XStart=xs,
                    YStart=ys,
                    XEnd=xe,
                    YEnd=ye,
                    Frequency=float(r.get("Frequency", 0.0)),
                    PathLength=float(r.get("PathLength", 0.0)),
                    xs_m=xs_m,
                    ys_m=ys_m,
                    xe_m=xe_m,
                    ye_m=ye_m,
                )
            )

            if i % 200_000 == 0:
                print(f"Loaded {i:,} links...")

    print(f"Loaded {len(links):,} links from {path}")
    return links


def build_rectangle(width_km: float, height_km: float) -> Dict:
    x_min, y_max = to_rd.transform(ANCHOR_NW_LON, ANCHOR_NW_LAT)

    width_m = width_km * 1000.0
    height_m = height_km * 1000.0

    x_max = x_min + width_m
    y_min = y_max - height_m

    corners_rd = {
        "nw": (x_min, y_max),
        "ne": (x_max, y_max),
        "se": (x_max, y_min),
        "sw": (x_min, y_min),
    }

    corners_wgs = {}
    for k, (x, y) in corners_rd.items():
        lon, lat = to_wgs.transform(x, y)
        corners_wgs[k] = {"lat": lat, "lon": lon}

    return {
        "rect_rd_m": {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
        },
        "leaflet_bounds": {
            "sw": corners_wgs["sw"],
            "ne": corners_wgs["ne"],
        },
        "corners_wgs84": corners_wgs,
        "anchor_nw": {"lat": ANCHOR_NW_LAT, "lon": ANCHOR_NW_LON},
    }


def filter_links(links: List[Link], rect: Dict) -> List[Dict]:
    x_min = rect["rect_rd_m"]["x_min"]
    x_max = rect["rect_rd_m"]["x_max"]
    y_min = rect["rect_rd_m"]["y_min"]
    y_max = rect["rect_rd_m"]["y_max"]

    out = []
    for L in links:
        if not (x_min <= L.xs_m <= x_max and y_min <= L.ys_m <= y_max):
            continue
        if not (x_min <= L.xe_m <= x_max and y_min <= L.ye_m <= y_max):
            continue

        out.append({
            "XStart": L.XStart,
            "YStart": L.YStart,
            "XEnd": L.XEnd,
            "YEnd": L.YEnd,
            "Frequency": L.Frequency,
            "PathLength": L.PathLength,
        })

    return out

# ------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------

app = FastAPI(title="Patch Links Filter (Exact meters)")

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

LINKS: List[Link] = []

@app.on_event("startup")
def startup():
    global LINKS
    path = resolve_links_path()
    LINKS = load_links(path)


@app.get("/patch")
def get_patch(
    width_km: float = Query(..., gt=0),
    height_km: float = Query(..., gt=0),
):
    rect = build_rectangle(width_km, height_km)
    inside = filter_links(LINKS, rect)

    return {
        "inputs": {"width_km": width_km, "height_km": height_km},
        "rectangle": rect,
        "count": len(inside),
        "links": inside,
    }
