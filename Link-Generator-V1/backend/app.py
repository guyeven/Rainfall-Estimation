from typing import List, Optional
import math
import random

from fastapi import FastAPI
from pydantic import BaseModel

from itu_r_p8383 import gamma_specific, Pol

app = FastAPI()


class InputParams(BaseModel):
    W: float
    H: float
    N: int
    C: int
    pmst: float
    frequencies: List[float]
    Rmax: float
    attenuation_max: float
    polarization: Pol


class PointOut(BaseModel):
    index: int
    x: float
    y: float
    is_center: bool
    is_mst_node: bool


class LinkOut(BaseModel):
    link_id: int
    type: str  # "access" or "mst"
    from_index: int
    to_index: int
    from_coord: List[float]
    to_coord: List[float]
    length: float
    max_allowed_frequency: Optional[float]


class OutputData(BaseModel):
    W: float
    H: float
    N: int
    points: List[PointOut]
    links: List[LinkOut]
    frequencies: List[float]


def euclid_sq(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = x1 - x2
    dy = y1 - y2
    return dx * dx + dy * dy


def build_centers(points, W: float, H: float, C: int) -> List[int]:
    """Select centers by k×k grid with k = ceil(sqrt(C))."""
    N = len(points)
    if N == 0:
        return []

    if C <= 0:
        raise ValueError("C must be > 0")

    k = max(1, math.ceil(math.sqrt(C)))
    cell_w = W / k if k > 0 else W
    cell_h = H / k if k > 0 else H

    cells = {}
    for idx, (x, y) in enumerate(points):
        ix = min(k - 1, int(x / cell_w)) if cell_w > 0 else 0
        iy = min(k - 1, int(y / cell_h)) if cell_h > 0 else 0
        key = (ix, iy)
        cells.setdefault(key, []).append(idx)

    centers: List[int] = []
    for _, idxs in cells.items():
        centers.append(random.choice(idxs))

    # Guarantee at least one center
    if not centers:
        centers.append(random.randrange(N))

    return centers


def build_access_links(points, centers_idx: List[int]) -> List[tuple]:
    """Connect every non-center point to its closest center."""
    center_set = set(centers_idx)
    links = []
    if not centers_idx:
        return links
    for i, (x, y) in enumerate(points):
        if i in center_set:
            continue
        best_c = None
        best_d = float("inf")
        for c in centers_idx:
            x_c, y_c = points[c]
            d = euclid_sq(x, y, x_c, y_c)
            if d < best_d:
                best_d = d
                best_c = c
        links.append(("access", i, best_c))
    return links


def choose_mst_nodes(centers_idx: List[int], pmst: float) -> List[int]:
    if pmst <= 0:
        return []
    return [c for c in centers_idx if random.random() < pmst]


def build_mst_links(points, mst_nodes: List[int]) -> List[tuple]:
    """Prim-like MST on mst_nodes."""
    if len(mst_nodes) < 2:
        return []
    visited = {mst_nodes[0]}
    edges: List[tuple] = []
    while len(visited) < len(mst_nodes):
        best = None
        best_d = float("inf")
        for u in visited:
            x_u, y_u = points[u]
            for v in mst_nodes:
                if v in visited:
                    continue
                x_v, y_v = points[v]
                d = euclid_sq(x_u, y_u, x_v, y_v)
                if d < best_d:
                    best_d = d
                    best = (u, v)
        if best is None:
            break
        edges.append(("mst", best[0], best[1]))
        visited.add(best[1])
    return edges


def compute_max_freq(
    length: float,
    freqs: List[float],
    Rmax: float,
    attenuation_max: float,
    pol: Pol,
) -> Optional[float]:
    max_ok = None
    for f in sorted(freqs):
        gamma = gamma_specific(f, Rmax, pol)  # dB/km
        if gamma * length <= attenuation_max:
            max_ok = f
    return max_ok


@app.post("/generate_links", response_model=OutputData)
def generate_links(params: InputParams) -> OutputData:
    W = params.W
    H = params.H
    N = params.N

    # 1. Sample points
    points = [
        (random.uniform(0.0, W), random.uniform(0.0, H))
        for _ in range(N)
    ]

    # 2. Centers via grid
    centers_idx = build_centers(points, W, H, params.C)

    # 3. Access links (non-center → nearest center)
    access_edges = build_access_links(points, centers_idx)

    # 4. MST nodes
    mst_nodes = choose_mst_nodes(centers_idx, params.pmst)

    # 5. MST links
    mst_edges = build_mst_links(points, mst_nodes)

    all_edges = access_edges + mst_edges

    center_set = set(centers_idx)
    mst_set = set(mst_nodes)

    point_out: List[PointOut] = []
    for i, (x, y) in enumerate(points):
        point_out.append(
            PointOut(
                index=i,
                x=x,
                y=y,
                is_center=i in center_set,
                is_mst_node=i in mst_set,
            )
        )

    links_out: List[LinkOut] = []
    link_id = 0
    freqs = sorted(params.frequencies)

    for t, i, j in all_edges:
        x1, y1 = points[i]
        x2, y2 = points[j]
        length = math.sqrt(euclid_sq(x1, y1, x2, y2))
        max_f = compute_max_freq(
            length, freqs, params.Rmax, params.attenuation_max, params.polarization
        )
        links_out.append(
            LinkOut(
                link_id=link_id,
                type=t,
                from_index=i,
                to_index=j,
                from_coord=[x1, y1],
                to_coord=[x2, y2],
                length=length,
                max_allowed_frequency=max_f,
            )
        )
        link_id += 1

    return OutputData(
        W=W,
        H=H,
        N=N,
        points=point_out,
        links=links_out,
        frequencies=freqs,
    )
