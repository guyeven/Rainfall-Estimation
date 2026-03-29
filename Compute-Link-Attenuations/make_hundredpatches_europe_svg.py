#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PATCH_LIST = ROOT / "JSON-files/benchmark-500-files-758-patches.local.jsonl"
HUNDRED_DIR = ROOT / "HundredPatches/patch_jsonl_files"
OUT = ROOT / "HundredPatches/norm/report/images/patch_overview/hundredpatches_europe_overview.svg"


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
            ids.append(name[len("patch_"):-len(".jsonl")])
    return ids


def rect_lonlat(row: dict) -> tuple[float, float, float, float]:
    lon = float(row["center_lon"])
    lat = float(row["center_lat"])
    width_km = float(row["width_km"])
    height_km = float(row["height_km"])
    half_h_deg = (height_km / 2.0) / 111.32
    cos_lat = max(1e-6, math.cos(math.radians(lat)))
    half_w_deg = (width_km / 2.0) / (111.32 * cos_lat)
    return lon - half_w_deg, lon + half_w_deg, lat - half_h_deg, lat + half_h_deg


def main() -> None:
    meta = load_patch_metadata()
    ids = hundred_patch_ids()
    rows = [meta[pid] for pid in ids if pid in meta]
    if len(rows) != len(ids):
        missing = [pid for pid in ids if pid not in meta]
        raise SystemExit(f"Missing metadata for {len(missing)} patch ids: {missing[:5]}")

    # Europe-like plotting extent.
    lon_min, lon_max = -15.0, 35.0
    lat_min, lat_max = 34.0, 72.0
    width, height = 1600, 1100
    pad_l, pad_r, pad_t, pad_b = 90, 40, 60, 80
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_of(lon: float) -> float:
        return pad_l + (lon - lon_min) / (lon_max - lon_min) * plot_w

    def y_of(lat: float) -> float:
        return pad_t + (lat_max - lat) / (lat_max - lat_min) * plot_h

    lines: list[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    lines.append('<rect width="100%" height="100%" fill="#fffdf8"/>')
    lines.append(f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" fill="#f8f8f8" stroke="#666" stroke-width="1.2"/>')
    lines.append(f'<text x="{width/2:.1f}" y="34" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="28" font-weight="700">HundredPatches overview over Europe</text>')
    lines.append(f'<text x="{width/2:.1f}" y="58" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="15" fill="#444">100 patch footprints shown as red outline rectangles</text>')

    # Grid.
    for lon in range(-10, 36, 5):
        x = x_of(float(lon))
        lines.append(f'<line x1="{x:.2f}" y1="{pad_t}" x2="{x:.2f}" y2="{pad_t + plot_h}" stroke="#d8d8d8" stroke-width="1"/>')
        lines.append(f'<text x="{x:.2f}" y="{pad_t + plot_h + 26}" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="14" fill="#555">{lon}°</text>')
    for lat in range(35, 71, 5):
        y = y_of(float(lat))
        lines.append(f'<line x1="{pad_l}" y1="{y:.2f}" x2="{pad_l + plot_w}" y2="{y:.2f}" stroke="#d8d8d8" stroke-width="1"/>')
        lines.append(f'<text x="{pad_l - 16}" y="{y + 5:.2f}" text-anchor="end" font-family="Helvetica,Arial,sans-serif" font-size="14" fill="#555">{lat}°</text>')

    lines.append(f'<text x="{pad_l + plot_w/2:.1f}" y="{height - 20}" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="16">Longitude</text>')
    lines.append(f'<text x="24" y="{pad_t + plot_h/2:.1f}" transform="rotate(-90 24,{pad_t + plot_h/2:.1f})" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="16">Latitude</text>')

    # Patch rectangles.
    for row in rows:
        a, b, c, d = rect_lonlat(row)
        x0 = x_of(a)
        x1 = x_of(b)
        y0 = y_of(d)
        y1 = y_of(c)
        lines.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{(x1-x0):.2f}" height="{(y1-y0):.2f}" '
            'fill="none" stroke="#cc1f1a" stroke-width="1.4" stroke-opacity="0.72"/>'
        )

    # Small legend.
    lx = pad_l + plot_w - 280
    ly = pad_t + 18
    lines.append(f'<rect x="{lx}" y="{ly}" width="248" height="46" rx="6" fill="#ffffff" fill-opacity="0.88" stroke="#bbb"/>')
    lines.append(f'<rect x="{lx+16}" y="{ly+16}" width="26" height="14" fill="none" stroke="#cc1f1a" stroke-width="1.6"/>')
    lines.append(f'<text x="{lx+52}" y="{ly+28}" font-family="Helvetica,Arial,sans-serif" font-size="14" fill="#333">Patch footprint</text>')

    lines.append("</svg>")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
