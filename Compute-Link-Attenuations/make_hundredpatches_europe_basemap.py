#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box


ROOT = Path(__file__).resolve().parent
PATCH_LIST = ROOT / "JSON-files/benchmark-500-files-758-patches.local.jsonl"
HUNDRED_DIR = ROOT / "HundredPatches/patch_jsonl_files"
OUT_DIR = ROOT / "HundredPatches/norm/report/images/patch_overview"
OUT_PNG = OUT_DIR / "hundredpatches_europe_overview_basemap.png"
OUT_PDF = OUT_DIR / "hundredpatches_europe_overview_basemap.pdf"


def load_patch_metadata() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    with PATCH_LIST.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            pid = str(row.get("id") or "").strip()
            if pid:
                meta[pid] = row
    return meta


def hundred_patch_ids() -> list[str]:
    ids: list[str] = []
    for p in sorted(HUNDRED_DIR.glob("patch_*.jsonl")):
        name = p.name
        if name.startswith("patch_") and name.endswith(".jsonl"):
            ids.append(name[len("patch_") : -len(".jsonl")])
    return ids


def patch_polygon(row: dict):
    lon = float(row["center_lon"])
    lat = float(row["center_lat"])
    width_km = float(row["width_km"])
    height_km = float(row["height_km"])
    half_h_deg = (height_km / 2.0) / 111.32
    cos_lat = max(1e-6, math.cos(math.radians(lat)))
    half_w_deg = (width_km / 2.0) / (111.32 * cos_lat)
    return box(lon - half_w_deg, lat - half_h_deg, lon + half_w_deg, lat + half_h_deg)


def build_geodataframe() -> gpd.GeoDataFrame:
    meta = load_patch_metadata()
    ids = hundred_patch_ids()
    rows = [meta[pid] for pid in ids if pid in meta]
    if len(rows) != len(ids):
        missing = [pid for pid in ids if pid not in meta]
        raise SystemExit(f"Missing metadata for patch ids: {missing[:5]}")
    gdf = gpd.GeoDataFrame(
        {
            "patch_id": [row["id"] for row in rows],
            "nearest_city": [row.get("nearest_city") for row in rows],
        },
        geometry=[patch_polygon(row) for row in rows],
        crs="EPSG:4326",
    )
    return gdf.to_crs(epsg=3857)


def padded_limits(gdf: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = gdf.total_bounds
    xpad = 0.08 * (xmax - xmin)
    ypad = 0.10 * (ymax - ymin)
    return xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gdf = build_geodataframe()
    xmin, xmax, ymin, ymax = padded_limits(gdf)

    fig, ax = plt.subplots(figsize=(15.5, 10.5), dpi=220)
    fig.patch.set_facecolor("#f8f5ef")
    ax.set_facecolor("#f8f5ef")

    gdf.boundary.plot(ax=ax, color="#c71f17", linewidth=1.2, alpha=0.78, zorder=3)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    ctx.add_basemap(
        ax,
        source=ctx.providers.CartoDB.PositronNoLabels,
        attribution=False,
        zoom="auto",
        zorder=1,
    )

    ax.set_axis_off()
    fig.text(
        0.82,
        0.865,
        "Patch footprint",
        ha="left",
        va="center",
        fontsize=11.5,
        color="#222",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "white",
            "edgecolor": "#d1cbc2",
            "alpha": 0.95,
        },
    )
    fig.lines.append(
        plt.Line2D(
            [0.775, 0.812],
            [0.865, 0.865],
            transform=fig.transFigure,
            color="#c71f17",
            linewidth=2.2,
            alpha=0.85,
        )
    )

    fig.tight_layout(rect=(0.015, 0.02, 0.985, 0.985))
    fig.savefig(OUT_PNG, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(OUT_PDF, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(OUT_PNG)
    print(OUT_PDF)


if __name__ == "__main__":
    main()
