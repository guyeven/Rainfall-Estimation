"""
FastAPI app exposing the ITU calculator and link generator
for your React UI.

Endpoints:

GET  /itu/summary
GET  /itu/gamma-freq
GET  /itu/gamma-rain
POST /links/generate
POST /links/assign-frequencies
"""

from __future__ import annotations
from typing import List, Literal, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .itu_coeffs import k_alpha, PolType
from .attenuation import (
    specific_attenuation,
    path_attenuation,
    gamma_vs_frequency,
    gamma_vs_rain,
)
from .frequency_policy import build_freq_set, choose_freq_for_link
from .link_geometry import generate_links, Link as GeoLink


app = FastAPI(title="Rainfall Map ITU Backend")

# Allow calls from local React dev server (Vite, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can tighten this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------- Pydantic models -----------

class ItuSummaryResponse(BaseModel):
    f: float
    R: float
    pol: PolType
    k: float
    alpha: float
    k_dB: float
    gamma: float  # dB/km


class GammaFreqPoint(BaseModel):
    f: float
    g: float


class GammaRainPoint(BaseModel):
    R: float
    g: float


class LinkGenRequest(BaseModel):
    width_km: float
    height_km: float
    n_links: int = 300
    len_mode: Literal["uniform", "exponential"] = "uniform"
    L_uniform: float = 5.0
    L_exp_mean: float = 3.0
    center_mode: Literal["uniform", "gaussian"] = "uniform"
    cx_mean: float = 30.0
    cy_mean: float = 20.0
    c_std: float = 10.0
    seed: Optional[int] = None


class LinkOut(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    length_km: float
    freq_ghz: Optional[float] = None


class AssignFreqRequest(BaseModel):
    links: List[LinkOut]
    f_min: float
    f_max: float
    f_step: float
    R_star: float
    alpha_star: float
    pol: PolType
    mode: Literal["rule", "uniform"] = "rule"
    uniform_freq: Optional[float] = None


# ----------- ITU endpoints -----------

@app.get("/itu/summary", response_model=ItuSummaryResponse)
def itu_summary(f: float, R: float, pol: PolType):
    k, alpha = k_alpha(f, pol)
    gamma = specific_attenuation(f, R, pol)
    k_dB = 10.0 * (0 if k <= 0 else __import__("math").log10(k))
    return ItuSummaryResponse(
        f=f,
        R=R,
        pol=pol,
        k=k,
        alpha=alpha,
        k_dB=k_dB,
        gamma=gamma,
    )


@app.get("/itu/gamma-freq", response_model=List[GammaFreqPoint])
def itu_gamma_freq(R: float, pol: PolType):
    pts = gamma_vs_frequency(R, pol)
    return [GammaFreqPoint(**p) for p in pts]


@app.get("/itu/gamma-rain", response_model=List[GammaRainPoint])
def itu_gamma_rain(f: float, pol: PolType):
    pts = gamma_vs_rain(f, pol)
    return [GammaRainPoint(**p) for p in pts]


# ----------- Link generator endpoints -----------

@app.post("/links/generate", response_model=List[LinkOut])
def links_generate(req: LinkGenRequest):
    links = generate_links(
        n_links=req.n_links,
        width_km=req.width_km,
        height_km=req.height_km,
        len_mode=req.len_mode,
        L_uniform=req.L_uniform,
        L_exp_mean=req.L_exp_mean,
        center_mode=req.center_mode,
        cx_mean=req.cx_mean,
        cy_mean=req.cy_mean,
        c_std=req.c_std,
        seed=req.seed,
    )
    return [
        LinkOut(
            x1=L.x1, y1=L.y1, x2=L.x2, y2=L.y2, length_km=L.length_km
        )
        for L in links
    ]


@app.post("/links/assign-frequencies", response_model=List[LinkOut])
def links_assign_frequencies(req: AssignFreqRequest):
    F = build_freq_set(req.f_min, req.f_max, req.f_step)
    out: List[LinkOut] = []
    for lin in req.links:
        f = choose_freq_for_link(
            d_km=lin.length_km,
            F=F,
            R_star=req.R_star,
            alpha_star=req.alpha_star,
            pol=req.pol,
            mode=req.mode,
            uniform_freq=req.uniform_freq,
        )
        out.append(
            LinkOut(
                x1=lin.x1,
                y1=lin.y1,
                x2=lin.x2,
                y2=lin.y2,
                length_km=lin.length_km,
                freq_ghz=f,
            )
        )
    return out

