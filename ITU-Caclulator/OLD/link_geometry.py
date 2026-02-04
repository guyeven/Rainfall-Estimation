"""
Link geometry generator.

This mirrors your React link-generation logic:
- constant length or exponential distribution
- uniform or Gaussian center
- clamp links to area [0,width] × [0,height]
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Literal
import math
import random


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def randn() -> float:
    """Gaussian(0,1) via Box–Muller, same as JS randn()."""
    while True:
        u = random.random()
        v = random.random()
        if u > 0.0 and v > 0.0:
            break
    return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)


@dataclass
class Link:
    x1: float
    y1: float
    x2: float
    y2: float
    length_km: float
    freq_ghz: float | None = None


def sample_link(
    width_km: float,
    height_km: float,
    len_mode: Literal["uniform", "exponential"],
    L_uniform: float,
    L_exp_mean: float,
    center_mode: Literal["uniform", "gaussian"],
    cx_mean: float,
    cy_mean: float,
    c_std: float,
) -> Link:
    # length
    if len_mode == "uniform":
        Ldraw = L_uniform
    else:
        # Exponential: max(0.05, -mean*log(1-U))
        U = random.random()
        Ldraw = max(0.05, -L_exp_mean * math.log(1 - U))

    # center
    if center_mode == "uniform":
        cx = random.random() * width_km
        cy = random.random() * height_km
    else:
        cx = cx_mean + c_std * randn()
        cy = cy_mean + c_std * randn()
        cx = clamp(cx, 0.0, width_km)
        cy = clamp(cy, 0.0, height_km)

    # orientation
    theta = random.random() * math.pi
    dx = 0.5 * Ldraw * math.cos(theta)
    dy = 0.5 * Ldraw * math.sin(theta)

    x1 = clamp(cx - dx, 0.0, width_km)
    y1 = clamp(cy - dy, 0.0, height_km)
    x2 = clamp(cx + dx, 0.0, width_km)
    y2 = clamp(cy + dy, 0.0, height_km)
    L = math.hypot(x2 - x1, y2 - y1)

    return Link(x1=x1, y1=y1, x2=x2, y2=y2, length_km=L)


def generate_links(
    n_links: int,
    width_km: float,
    height_km: float,
    len_mode: str = "uniform",
    L_uniform: float = 5.0,
    L_exp_mean: float = 3.0,
    center_mode: str = "uniform",
    cx_mean: float = 30.0,
    cy_mean: float = 20.0,
    c_std: float = 10.0,
    seed: int | None = None,
) -> List[Link]:
    if seed is not None:
        random.seed(seed)

    out: List[Link] = []
    for _ in range(n_links):
        out.append(
          sample_link(
              width_km,
              height_km,
              len_mode, L_uniform, L_exp_mean,
              center_mode, cx_mean, cy_mean, c_std,
          )
        )
    return out

