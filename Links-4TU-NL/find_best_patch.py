#!/usr/bin/env python3
import json, math, argparse
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, box, Point
from shapely.strtree import STRtree

# --- helpers ---
def load_links_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)

def make_lines_gdf(df):
    # lon,lat order in your JSON
    geoms = [LineString([(r.XStart, r.YStart), (r.XEnd, r.YEnd)]) for r in df.itertuples(index=False)]
    return gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")

def max_gap_in_window(window_poly, lines_tree, lines_geoms, sample_m):
    # Sample grid points inside window and compute distance to nearest line
    minx, miny, maxx, maxy = window_poly.bounds
    worst = -1.0
    worst_pt = None

    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            p = Point(x, y)
            # Query nearby candidate lines using bbox
            cand = lines_tree.query(p)
            if not cand:
                # should not happen if tree built correctly; treat as huge gap
                d = float("inf")
            else:
                d = min(p.distance(g) for g in cand)
            if d > worst:
                worst = d
                worst_pt = p
            x += sample_m
        y += sample_m

    return worst, worst_pt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("links_jsonl", help="unique_links.jsonl")
    ap.add_argument("--out", default="best_patch.json", help="output patch metadata json")
    ap.add_argument("--patch-km", type=float, default=100.0, help="patch size in km (square)")
    ap.add_argument("--stride-km", type=float, default=10.0, help="sliding stride in km")
    ap.add_argument("--sample-km", type=float, default=2.0, help="sampling grid spacing in km")
    args = ap.parse_args()

    df = load_links_jsonl(args.links_jsonl)
    gdf = make_lines_gdf(df).to_crs("EPSG:28992")  # meters for NL

    # Build STRtree for fast nearest-distance queries
    lines = list(gdf.geometry.values)
    tree = STRtree(lines)

    patch_m  = args.patch_km * 1000.0
    stride_m = args.stride_km * 1000.0
    sample_m = args.sample_km * 1000.0

    # Search area: bbox of all links (in meters)
    minx, miny, maxx, maxy = gdf.total_bounds

    best = None  # (max_gap_m, window_poly, worst_pt)
    tried = 0

    y0 = miny
    while y0 + patch_m <= maxy:
        x0 = minx
        while x0 + patch_m <= maxx:
            window = box(x0, y0, x0 + patch_m, y0 + patch_m)

            # Optional speed-up: only evaluate if window intersects some links
            if not tree.query(window):
                x0 += stride_m
                continue

            tried += 1
            max_gap_m, worst_pt = max_gap_in_window(window, tree, lines, sample_m)

            if (best is None) or (max_gap_m < best[0]):
                best = (max_gap_m, window, worst_pt)
                print(f"NEW BEST: max gap = {max_gap_m:.1f} m  @ window origin ({x0:.0f},{y0:.0f})  tried={tried}")

            if tried % 50 == 0:
                print(f"tried {tried} windows... current best max gap = {best[0]:.1f} m")

            x0 += stride_m
        y0 += stride_m

    if best is None:
        raise SystemExit("No suitable window found (did not intersect any links).")

    max_gap_m, window, worst_pt = best

    # Convert patch + worst point back to WGS84 for mapping
    window_gdf = gpd.GeoSeries([window], crs="EPSG:28992").to_crs("EPSG:4326")
    worst_gdf  = gpd.GeoSeries([worst_pt], crs="EPSG:28992").to_crs("EPSG:4326")

    w = window_gdf.iloc[0]
    wp = worst_gdf.iloc[0]

    out = {
        "patch_km": args.patch_km,
        "stride_km": args.stride_km,
        "sample_km": args.sample_km,
        "max_empty_disk_radius_m": float(max_gap_m),
        "patch_bounds_wgs84": {
            "min_lon": w.bounds[0], "min_lat": w.bounds[1],
            "max_lon": w.bounds[2], "max_lat": w.bounds[3],
        },
        "worst_point_wgs84": {"lon": wp.x, "lat": wp.y},
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"\nSaved: {args.out}")
    print(f"Best patch max empty-disk radius: {max_gap_m:.1f} m")

if __name__ == "__main__":
    main()
