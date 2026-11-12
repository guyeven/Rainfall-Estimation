#!/usr/bin/env python3
"""Download the OpenStreetMap zoom-7 tiles needed for the two map panels (27 tiles).

The tiles used for the published figures are already stored in ../osm_tiles_z7 (downloaded 2026-11-12).
Existing tiles are skipped, so this script only fills gaps. Tiles downloaded later may differ from the
stored ones because OpenStreetMap data change. Follow the OSMF Tile Usage Policy
(https://operations.osmfoundation.org/policies/tiles/) when using tile.openstreetmap.org.

Map data (c) OpenStreetMap contributors, available under the Open Database License,
https://www.openstreetmap.org/copyright

Usage:  python fetch_osm_tiles.py [--out DIR]
"""
import argparse
import math
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES, TILES, ZOOM  # noqa: E402


def world_pixel(lon, lat, zoom):
    scale = 256.0 * (2**zoom)
    return scale * (lon + 180.0) / 360.0, scale * (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0


def needed_tiles():
    need = set()
    for c in CASES:
        clat, clon, wkm, hkm = c["geo"]
        hh = (hkm / 2) / 111.32
        hw = (wkm / 2) / (111.32 * math.cos(math.radians(clat)))
        lo0, lo1, la0, la1 = clon - hw, clon + hw, clat - hh, clat + hh
        lp, ap = 4 * (lo1 - lo0), 4 * (la1 - la0)
        left, top = world_pixel(lo0 - lp, la1 + ap, ZOOM)
        right, bottom = world_pixel(lo1 + lp, la0 - ap, ZOOM)
        xs = range(int(left // 256), int(right // 256) + 1)
        ys = range(int(top // 256), int(bottom // 256) + 1)
        print(c["case"], "x", list(xs), "y", list(ys))
        need |= {(x, y) for x in xs for y in ys}
    return sorted(need)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=TILES)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    need = needed_tiles()
    for x, y in need:
        p = args.out / f"{x}_{y}.png"
        if p.exists():
            continue
        req = urllib.request.Request(f"https://tile.openstreetmap.org/{ZOOM}/{x}/{y}.png",
                                     headers={"User-Agent": "rainfall-case-study-figure/1.0 (one-off research figure)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            p.write_bytes(resp.read())
        time.sleep(0.5)
    print(len(need), "tiles in", args.out)


if __name__ == "__main__":
    main()
