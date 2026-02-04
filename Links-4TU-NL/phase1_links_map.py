#!/usr/bin/env python3
"""
Phase 1 interactive map:
- plots all microwave links
- overlays a 95 x 95 km rectangle
- rectangle is FILLED RED with opacity 0.2

Output: phase1_all_links_with_red_rect.html
"""

import json
import math
import folium

INPUT = "unique_links.jsonl"
OUTPUT = "phase1_all_links_with_red_rect.html"

# --- Create base map ---
m = folium.Map(
    location=[52.2, 5.3],
    zoom_start=7,
    tiles="CartoDB positron"
)

# --- Plot all links ---
count = 0
with open(INPUT, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)

        p1 = [r["YStart"], r["XStart"]]  # lat, lon
        p2 = [r["YEnd"],   r["XEnd"]]

        folium.PolyLine(
            [p1, p2],
            weight=1,
            opacity=0.25,
            color="black"
        ).add_to(m)

        count += 1
        if count % 1000 == 0:
            print(f"plotted {count} links")

print(f"Total links plotted: {count}")

# --- Rectangle: 95 x 95 km from given SW corner ---
lat_sw = 51.53311135810945
lon_sw = 4.528701910089581
size_km = 95.0

# Approximate km → degree conversion (OK for interactive view)
deg_per_km_lat = 1.0 / 111.0
deg_per_km_lon = 1.0 / (111.0 * math.cos(math.radians(lat_sw)))

dlat = size_km * deg_per_km_lat
dlon = size_km * deg_per_km_lon

lat_ne = lat_sw + dlat
lon_ne = lon_sw + dlon

# --- Draw filled red rectangle ---
folium.Rectangle(
    bounds=[[lat_sw, lon_sw], [lat_ne, lon_ne]],
    color="red",
    weight=3,
    fill=True,
    fill_color="red",
    fill_opacity=0.2,
    tooltip="95 km x 95 km patch"
).add_to(m)

# Optional: mark SW corner
folium.CircleMarker(
    location=[lat_sw, lon_sw],
    radius=5,
    color="red",
    fill=True,
    fill_opacity=1.0,
    tooltip="SW corner"
).add_to(m)

# --- Save ---
m.save(OUTPUT)
print(f"Done → {OUTPUT}")
