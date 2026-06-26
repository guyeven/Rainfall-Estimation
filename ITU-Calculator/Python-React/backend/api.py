# api.py
from __future__ import annotations

import math
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal

from itu_r_p8383 import gamma_specific, k_alpha, Pol

app = FastAPI(title="ITU Rain Attenuation API")

# Allow local React/Vite dev servers. Browsers treat localhost and
# 127.0.0.1 as different origins, so keep both forms here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GammaPoint(BaseModel):
    x: float
    gamma: float


class GammaCurveResponse(BaseModel):
    points: List[GammaPoint]


class GammaResponse(BaseModel):
    f_ghz: float
    R_mm_per_h: float
    pol: Pol
    k: float
    alpha: float
    gamma: float


@app.get("/itu/gamma", response_model=GammaResponse)
def gamma_single(
    f_ghz: float,
    R_mm_per_h: float,
    pol: Pol = "horizontal",
):
    k, alpha = k_alpha(f_ghz, pol)
    g = gamma_specific(f_ghz, R_mm_per_h, pol)
    return GammaResponse(
        f_ghz=f_ghz,
        R_mm_per_h=R_mm_per_h,
        pol=pol,
        k=k,
        alpha=alpha,
        gamma=g,
    )


@app.get("/itu/gamma-freq", response_model=GammaCurveResponse)
def gamma_vs_frequency(
    R_mm_per_h: float,
    pol: Pol = "horizontal",
    f_min: float = 1.0,
    f_max: float = 100.0,
    n_points: int = 100,
):
    """
    gamma_R(f, R_fixed) vs frequency, linear spacing in f.
    """
    if n_points < 2:
        n_points = 2
    step = (f_max - f_min) / (n_points - 1)
    points = []
    for i in range(n_points):
        f = f_min + i * step
        g = gamma_specific(f, R_mm_per_h, pol)
        points.append(GammaPoint(x=f, gamma=g))
    return GammaCurveResponse(points=points)


@app.get("/itu/gamma-rain", response_model=GammaCurveResponse)
def gamma_vs_rain(
    f_ghz: float,
    pol: Pol = "horizontal",
    R_min: float = 0.1,
    R_max: float = 100.0,
    n_points: int = 100,
):
    """
    gamma_R(f_fixed, R) vs rain rate.

    R is sampled logarithmically between R_min and R_max
    so that the log-scale y-axis + wide R range looks nice.
    """
    if n_points < 2:
        n_points = 2
    log_R_min = math.log10(R_min)
    log_R_max = math.log10(R_max)
    dlog = (log_R_max - log_R_min) / (n_points - 1)

    points = []
    for i in range(n_points):
        logR = log_R_min + i * dlog
        R = 10 ** logR
        g = gamma_specific(f_ghz, R, pol)
        points.append(GammaPoint(x=R, gamma=g))
    return GammaCurveResponse(points=points)

