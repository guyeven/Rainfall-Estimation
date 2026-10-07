#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from typing import Dict, List, Tuple
from pyproj import Transformer

# Match link_geometry.py anchor
ANCHOR_NW_LAT = 52.38897
ANCHOR_NW_LON = 4.528701910089581

TO_RD = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)

def write_jsonl(path: Path, rows: List[Dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

def rd_to_lonlat(x: float, y: float) -> Tuple[float, float]:
    lon, lat = TO_WGS.transform(x, y)
    return float(lon), float(lat)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--h5_path", required=True, help="full path to synthetic h5")
    ap.add_argument("--patch_id", default="synth_patch_001")
    ap.add_argument("--ny", type=int, default=8)
    ap.add_argument("--nx", type=int, default=8)
    ap.add_argument("--missing_freq_link", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    h5_path = str(Path(args.h5_path).resolve())

    # Coarse pixels are 2km x 2km
    width_km = args.nx * 2.0
    height_km = args.ny * 2.0
    width_m = width_km * 1000.0
    height_m = height_km * 1000.0

    # Place patch NW corner P at anchor Q so translation t = P-Q = 0
    qx, qy = TO_RD.transform(ANCHOR_NW_LON, ANCHOR_NW_LAT)
    px, py = qx, qy  # P in RD meters

    # Patch rectangle in RD
    x_min, x_max = px, px + width_m
    y_max, y_min = py, py - height_m

    # Convert rectangle corners to lon/lat for patch JSON
    lon_min, lat_max = rd_to_lonlat(x_min, y_max)  # NW
    lon_max, lat_min = rd_to_lonlat(x_max, y_min)  # SE

    # Patch JSONL record
    patch = {
        "patch_id": args.patch_id,
        "source_file": h5_path,            # full path (per your correction)
        "x_min": 0, "x_max": args.nx - 1,  # crop full array
        "y_min": 0, "y_max": args.ny - 1,
        "width_km": width_km,
        "height_km": height_km,
        "patch_lon_min": lon_min,
        "patch_lon_max": lon_max,
        "patch_lat_min": lat_min,
        "patch_lat_max": lat_max,
    }

    # Attributes JSONL: selecting this patch
    attr = {"patch_id": args.patch_id, "selected": True}

    # Build 3 links inside the patch (in RD), then convert endpoints to lon/lat
    def mk_link(x0,y0,x1,y1,freq=15.0):
        lon0, lat0 = rd_to_lonlat(x0,y0)
        lon1, lat1 = rd_to_lonlat(x1,y1)
        d = {
            "XStart": lon0, "YStart": lat0,
            "XEnd": lon1, "YEnd": lat1,
            "Frequency": freq,   # GHz
            "PathLength": None,
        }
        # Polarization intentionally omitted (matches your data reality)
        return d

    # Link A: horizontal across middle
    linkA = mk_link(x_min + 0.1*width_m, y_min + 0.5*height_m,
                    x_min + 0.9*width_m, y_min + 0.5*height_m, freq=15.0)

    # Link B: diagonal
    linkB = mk_link(x_min + 0.2*width_m, y_min + 0.2*height_m,
                    x_min + 0.8*width_m, y_min + 0.8*height_m, freq=18.0)

    # Link C: short vertical near right side
    linkC = mk_link(x_min + 0.75*width_m, y_min + 0.2*height_m,
                    x_min + 0.75*width_m, y_min + 0.8*height_m, freq=23.0)

    if args.missing_freq_link:
        linkB.pop("Frequency", None)

    patches_path = out_dir / "patches.jsonl"
    attrs_path = out_dir / "patch_attrs.jsonl"
    links_path = out_dir / "links.jsonl"

    write_jsonl(patches_path, [patch])
    write_jsonl(attrs_path, [attr])
    write_jsonl(links_path, [linkA, linkB, linkC])

    print("Wrote:")
    print(" ", patches_path)
    print(" ", attrs_path)
    print(" ", links_path)

if __name__ == "__main__":
    main()
