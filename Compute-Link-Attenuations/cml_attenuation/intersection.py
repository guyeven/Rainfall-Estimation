"""Compute intersections of a line segment with a uniform refined pixel grid.

Grid definition (per spec):
- Patch rectangle is axis-aligned in EPSG:28992 meters.
- Refined pixel size is 125m x 125m.
- Pixel indices (i,j) are 0-based with:
    i: row index increasing southward (y decreasing)
    j: col index increasing eastward (x increasing)
- Pixel (0,0) is the NW-most refined pixel.

This module returns the list of refined pixels intersected by a segment and
for each pixel the length of the segment inside that pixel (in meters).

We use a fast voxel traversal (Amanatides & Woo style) in 2D.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import inf, sqrt
from typing import List, Tuple


@dataclass(frozen=True)
class GridSpec:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    pixel_m: float = 125.0

    @property
    def nx(self) -> int:
        return int(round((self.x_max - self.x_min) / self.pixel_m))

    @property
    def ny(self) -> int:
        return int(round((self.y_max - self.y_min) / self.pixel_m))

    def clamp_ij(self, i: int, j: int) -> Tuple[int, int]:
        return max(0, min(self.ny - 1, i)), max(0, min(self.nx - 1, j))

    def ij_from_xy(self, x: float, y: float) -> Tuple[int, int]:
        # j eastward from x_min, i southward from y_max
        j = int((x - self.x_min) // self.pixel_m)
        i = int((self.y_max - y) // self.pixel_m)
        return self.clamp_ij(i, j)

    def cell_bounds(self, i: int, j: int) -> Tuple[float, float, float, float]:
        # returns (x0,x1,y0,y1) with y0<y1
        x0 = self.x_min + j * self.pixel_m
        x1 = x0 + self.pixel_m
        y1 = self.y_max - i * self.pixel_m
        y0 = y1 - self.pixel_m
        return x0, x1, y0, y1

    def cell_center(self, i: int, j: int) -> Tuple[float, float]:
        x0, x1, y0, y1 = self.cell_bounds(i, j)
        return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def _seg_len(x0: float, y0: float, x1: float, y1: float) -> float:
    dx = x1 - x0
    dy = y1 - y0
    return sqrt(dx * dx + dy * dy)


def traverse_segment_pixels(
    grid: GridSpec,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> List[Tuple[int, int, float]]:
    """Return list of (i,j,ds_m) for pixels intersected by segment.

    Assumes both endpoints lie within the patch rectangle.
    """
    total_len = _seg_len(x0, y0, x1, y1)
    if total_len == 0.0:
        i, j = grid.ij_from_xy(x0, y0)
        return [(i, j, 0.0)]

    dx = x1 - x0
    dy = y1 - y0

    # Starting cell
    i, j = grid.ij_from_xy(x0, y0)

    # Direction steps in grid index space
    step_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
    step_y = -1 if dy > 0 else (1 if dy < 0 else 0)
    # Note: y index increases southward, so dy>0 (north->south?) changes sign accordingly.

    # Compute initial tMax and tDelta for x
    if dx != 0.0:
        if step_x > 0:
            next_x_boundary = grid.x_min + (j + 1) * grid.pixel_m
        else:
            next_x_boundary = grid.x_min + j * grid.pixel_m
        t_max_x = (next_x_boundary - x0) / dx
        t_delta_x = grid.pixel_m / abs(dx)
    else:
        t_max_x = inf
        t_delta_x = inf

    # For y, remember grid y decreases with i
    if dy != 0.0:
        if step_y > 0:
            # moving south (i+1) means y decreasing, next boundary is lower y
            x0b, x1b, y0b, y1b = grid.cell_bounds(i, j)
            next_y_boundary = y0b
        else:
            x0b, x1b, y0b, y1b = grid.cell_bounds(i, j)
            next_y_boundary = y1b
        t_max_y = (next_y_boundary - y0) / dy
        t_delta_y = grid.pixel_m / abs(dy)
    else:
        t_max_y = inf
        t_delta_y = inf

    # Clip numerical noise: start at t=0
    t = 0.0
    out: List[Tuple[int, int, float]] = []

    # Traverse until t reaches 1
    while True:
        # determine next crossing
        t_next = min(t_max_x, t_max_y, 1.0)
        ds = max(0.0, (t_next - t) * total_len)
        out.append((i, j, ds))

        if t_next >= 1.0:
            break

        # advance
        if t_max_x < t_max_y:
            j += step_x
            t = t_max_x
            t_max_x += t_delta_x
        else:
            i += step_y
            t = t_max_y
            t_max_y += t_delta_y

        # Safety clamp (should not happen if endpoints inside and grid dims consistent)
        if i < 0 or i >= grid.ny or j < 0 or j >= grid.nx:
            break

    # Merge consecutive duplicates (rare) and drop tiny lengths
    merged: List[Tuple[int, int, float]] = []
    for ii, jj, ds in out:
        if ds <= 0:
            continue
        if merged and merged[-1][0] == ii and merged[-1][1] == jj:
            merged[-1] = (ii, jj, merged[-1][2] + ds)
        else:
            merged.append((ii, jj, ds))
    return merged
