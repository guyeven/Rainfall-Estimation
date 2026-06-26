#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

from pyproj import Transformer


TO_WGS = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
TO_RD = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


@dataclass(frozen=True)
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def min_x(self) -> float:
        return self.x1 if self.x1 < self.x2 else self.x2

    @property
    def max_x(self) -> float:
        return self.x2 if self.x1 < self.x2 else self.x1

    @property
    def min_y(self) -> float:
        return self.y1 if self.y1 < self.y2 else self.y2

    @property
    def max_y(self) -> float:
        return self.y2 if self.y1 < self.y2 else self.y1


def clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _dot(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * bx + ay * by


def _point_segment_sqdist(px: float, py: float, s: Segment) -> float:
    vx = s.x2 - s.x1
    vy = s.y2 - s.y1
    wx = px - s.x1
    wy = py - s.y1
    vv = _dot(vx, vy, vx, vy)
    if vv <= 0.0:
        dx = px - s.x1
        dy = py - s.y1
        return dx * dx + dy * dy
    t = _dot(wx, wy, vx, vy) / vv
    t = clamp(t, 0.0, 1.0)
    qx = s.x1 + t * vx
    qy = s.y1 + t * vy
    dx = px - qx
    dy = py - qy
    return dx * dx + dy * dy


def _orient(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _on_segment(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> bool:
    eps = 1e-9
    return (
        min(ax, bx) - eps <= px <= max(ax, bx) + eps
        and min(ay, by) - eps <= py <= max(ay, by) + eps
    )


def _segments_intersect(a: Segment, b: Segment) -> bool:
    o1 = _orient(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1)
    o2 = _orient(a.x1, a.y1, a.x2, a.y2, b.x2, b.y2)
    o3 = _orient(b.x1, b.y1, b.x2, b.y2, a.x1, a.y1)
    o4 = _orient(b.x1, b.y1, b.x2, b.y2, a.x2, a.y2)
    eps = 1e-9

    if o1 * o2 < -eps and o3 * o4 < -eps:
        return True
    if abs(o1) <= eps and _on_segment(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1):
        return True
    if abs(o2) <= eps and _on_segment(a.x1, a.y1, a.x2, a.y2, b.x2, b.y2):
        return True
    if abs(o3) <= eps and _on_segment(b.x1, b.y1, b.x2, b.y2, a.x1, a.y1):
        return True
    if abs(o4) <= eps and _on_segment(b.x1, b.y1, b.x2, b.y2, a.x2, a.y2):
        return True
    return False


def segment_distance_m(a: Segment, b: Segment) -> float:
    if _segments_intersect(a, b):
        return 0.0
    d2 = min(
        _point_segment_sqdist(a.x1, a.y1, b),
        _point_segment_sqdist(a.x2, a.y2, b),
        _point_segment_sqdist(b.x1, b.y1, a),
        _point_segment_sqdist(b.x2, b.y2, a),
    )
    return math.sqrt(d2)


def bbox_cells(seg: Segment, grid_m: float, margin_m: float) -> List[Tuple[int, int]]:
    min_x = seg.min_x - margin_m
    max_x = seg.max_x + margin_m
    min_y = seg.min_y - margin_m
    max_y = seg.max_y + margin_m
    ix0 = math.floor(min_x / grid_m)
    ix1 = math.floor(max_x / grid_m)
    iy0 = math.floor(min_y / grid_m)
    iy1 = math.floor(max_y / grid_m)
    out: List[Tuple[int, int]] = []
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            out.append((ix, iy))
    return out


def sample_segment(
    rng: random.Random,
    width_m: float,
    height_m: float,
    min_len_m: float,
    max_len_m: float,
) -> Segment:
    length = rng.uniform(min_len_m, max_len_m)
    cx = rng.uniform(0.0, width_m)
    cy = rng.uniform(0.0, height_m)
    theta = rng.uniform(0.0, math.pi)
    hx = 0.5 * length * math.cos(theta)
    hy = 0.5 * length * math.sin(theta)
    return Segment(x1=cx - hx, y1=cy - hy, x2=cx + hx, y2=cy + hy)


def inside(seg: Segment, width_m: float, height_m: float) -> bool:
    return (
        0.0 <= seg.x1 <= width_m
        and 0.0 <= seg.y1 <= height_m
        and 0.0 <= seg.x2 <= width_m
        and 0.0 <= seg.y2 <= height_m
    )


def to_link_json(seg: Segment, *, qx: float, qy: float, freq_ghz: float, pol: str) -> Dict:
    # Anchor is treated as NW corner: +x goes east, +y goes south.
    lon_s, lat_s = TO_WGS.transform(qx + seg.x1, qy - seg.y1)
    lon_e, lat_e = TO_WGS.transform(qx + seg.x2, qy - seg.y2)
    length_km = math.hypot(seg.x2 - seg.x1, seg.y2 - seg.y1) / 1000.0
    return {
        "XStart": float(lon_s),
        "YStart": float(lat_s),
        "XEnd": float(lon_e),
        "YEnd": float(lat_e),
        "Frequency": float(freq_ghz),
        "Polarization": pol,
        "PathLength": round(length_km, 3),
    }


def generate_links(
    *,
    n_links: int,
    width_m: float,
    height_m: float,
    min_sep_m: float,
    min_len_m: float,
    max_len_m: float,
    max_attempts: int,
    seed: int,
) -> List[Segment]:
    rng = random.Random(seed)
    accepted: List[Segment] = []
    grid: Dict[Tuple[int, int], List[int]] = {}
    grid_m = max(1.0, min_sep_m)
    min_sep_strict = float(min_sep_m)

    attempts = 0
    while len(accepted) < n_links and attempts < max_attempts:
        attempts += 1
        seg = sample_segment(rng, width_m, height_m, min_len_m, max_len_m)
        if not inside(seg, width_m, height_m):
            continue

        candidate_ids: Set[int] = set()
        for c in bbox_cells(seg, grid_m=grid_m, margin_m=min_sep_strict):
            ids = grid.get(c)
            if ids:
                candidate_ids.update(ids)

        ok = True
        for idx in candidate_ids:
            d = segment_distance_m(seg, accepted[idx])
            if d <= min_sep_strict:
                ok = False
                break
        if not ok:
            continue

        new_idx = len(accepted)
        accepted.append(seg)
        for c in bbox_cells(seg, grid_m=grid_m, margin_m=min_sep_strict):
            grid.setdefault(c, []).append(new_idx)

    if len(accepted) != n_links:
        raise RuntimeError(
            f"Could only place {len(accepted)} links after {attempts} attempts. "
            f"Try larger area or shorter links."
        )
    return accepted


def verify_all_pairs(segments: List[Segment], min_sep_m: float) -> Tuple[float, Tuple[int, int]]:
    best = float("inf")
    best_pair = (-1, -1)
    n = len(segments)
    for i in range(n):
        si = segments[i]
        for j in range(i + 1, n):
            d = segment_distance_m(si, segments[j])
            if d < best:
                best = d
                best_pair = (i, j)
            if d <= min_sep_m:
                return d, (i, j)
    return best, best_pair


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate synthetic links with pairwise distance > threshold."
    )
    ap.add_argument("--out", required=True, help="Output JSONL file path.")
    ap.add_argument("--n-links", type=int, default=2000)
    ap.add_argument("--min-separation-m", type=float, default=125.0)
    ap.add_argument("--area-width-m", type=float, default=130000.0)
    ap.add_argument("--area-height-m", type=float, default=180000.0)
    ap.add_argument("--min-length-m", type=float, default=400.0)
    ap.add_argument("--max-length-m", type=float, default=2500.0)
    ap.add_argument("--max-attempts", type=int, default=2_000_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--anchor-lon", type=float, default=4.5, help="NW anchor longitude")
    ap.add_argument("--anchor-lat", type=float, default=52.4, help="NW anchor latitude")
    ap.add_argument("--frequency-ghz", type=float, default=39.0)
    ap.add_argument("--polarization", default="H", choices=["H", "V"])
    args = ap.parse_args()

    if args.n_links <= 0:
        raise SystemExit("--n-links must be > 0.")
    if args.min_separation_m <= 0:
        raise SystemExit("--min-separation-m must be > 0.")
    if args.min_length_m <= 0 or args.max_length_m <= 0:
        raise SystemExit("--min-length-m and --max-length-m must be > 0.")
    if args.min_length_m > args.max_length_m:
        raise SystemExit("--min-length-m cannot exceed --max-length-m.")
    if args.area_width_m <= 0 or args.area_height_m <= 0:
        raise SystemExit("--area-width-m and --area-height-m must be > 0.")

    qx, qy = TO_RD.transform(float(args.anchor_lon), float(args.anchor_lat))

    segs = generate_links(
        n_links=int(args.n_links),
        width_m=float(args.area_width_m),
        height_m=float(args.area_height_m),
        min_sep_m=float(args.min_separation_m),
        min_len_m=float(args.min_length_m),
        max_len_m=float(args.max_length_m),
        max_attempts=int(args.max_attempts),
        seed=int(args.seed),
    )

    min_d, pair = verify_all_pairs(segs, float(args.min_separation_m))
    if min_d <= float(args.min_separation_m):
        raise RuntimeError(
            f"Verification failed: links {pair[0]} and {pair[1]} are only {min_d:.3f} m apart."
        )

    links = [
        to_link_json(
            s,
            qx=qx,
            qy=qy,
            freq_ghz=float(args.frequency_ghz),
            pol=str(args.polarization),
        )
        for s in segs
    ]

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for rec in links:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")

    print(f"Wrote {len(links)} links to: {out}")
    print(f"Guaranteed minimum pairwise distance: {min_d:.3f} m")


if __name__ == "__main__":
    main()
