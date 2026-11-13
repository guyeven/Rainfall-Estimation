"""Shared data and operators for the patch006 robustness runs.

Link quantities follow the repository code exactly:
- IDW / ILDW: endpoint length (link_lengths_km) and idw_baseline.itu838_k_alpha.
- Convex solver: in-grid length (sum of ds over segments_by_link) and itu_r_p_8383.k_alpha.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
# Checkout of Compute-Link-Attenuations. Default: the one in this repository, with this folder at
# output/journal_revision/robustness_patch006/. Set CLA_REPO to use another checkout.
# The runs used branch oct26, commit c7a485d.
REPO = Path(os.environ.get("CLA_REPO", OUT.parents[2] / "Compute-Link-Attenuations"))
assert (REPO / "cml_attenuation").is_dir(), f"Compute-Link-Attenuations not found at {REPO}. Set CLA_REPO."
sys.path.insert(0, str(REPO))
P = "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202306192200_patch006"
S = REPO / "June2023HundredPatches"
EST = S / "est_dir" / f"est_input_{P}.json"
SOL = S / "pipeline" / "solutions"
IDW_NPZ = SOL / "sol_dir_idw" / f"est_input_{P}_solution.npz"
CONVEX_NPZ = SOL / "sol_dir_convex_no_shrinkage" / f"est_input_{P}_solution.npz"

from cml_attenuation.idw_baseline import itu838_k_alpha, link_lengths_km  # noqa: E402

D = json.loads(EST.read_text())
HDR = D["header"]
H, W, PX = int(HDR["H"]), int(HDR["W"]), float(HDR["pixel_size_m"])
LINKS = D["links"]
assert [l["link_index"] for l in LINKS] == list(range(len(LINKS)))
NL = len(LINKS)
g = lambda key: np.array([l[key] for l in LINKS])
x0, y0, x1, y1 = g("x0_m"), g("y0_m"), g("x1_m"), g("y1_m")
F = g("freq_ghz").astype(float)
POL = np.array([str(l["pol"]).upper() for l in LINKS])
A = g("A_db").astype(float)
LKM = link_lengths_km(LINKS)  # endpoint length, km (IDW)
K, ALPHA = itu838_k_alpha(F, POL)
INV = 1.0 / ALPHA
OK = LKM > 0  # positive length
WET = OK & (A > 0)

# in-grid length from segments (convex solver)
LSEG = np.zeros(NL)
for li in range(NL):
    for s in D["segments_by_link"].get(str(li), []):
        LSEG[li] += float(s["ds_m"]) / 1000.0


def req(Av, L=LKM, k=K, inv=INV):
    """Rain-rate equivalent with clipping at 0. Zero-length links give 0."""
    Av = np.maximum(np.asarray(Av, float), 0.0)
    out = np.zeros_like(Av)
    ok = L > 0
    out[ok] = (Av[ok] / (k[ok] * L[ok])) ** inv[ok]
    return out


def noise(seed, model, E):
    """Noise vector in dB per link. Same u draws for IDW and Convex."""
    u = np.random.default_rng(seed).uniform(0, 1, size=NL)
    if model == "N1":
        m = np.minimum(E, A)
        e = m * (2 * u - 1)
        e[~OK] = 0.0
    elif model == "N2":
        e = np.where(WET, E * u, 0.0)
    else:
        raise ValueError(model)
    assert np.all(A + e >= 0)
    return e


def idw_apply(V, r_max=15000.0):
    """Apply the IDW operator (midpoint rule, d^-2 within r_max) to link vectors V (NL,) or (NL, m)."""
    V = np.asarray(V, float)
    one = V.ndim == 1
    if one:
        V = V[:, None]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    mi, mj = np.floor(my / PX).astype(int), np.floor(mx / PX).astype(int)
    xc = (np.arange(W) + 0.5) * PX
    out = np.zeros((H, W, V.shape[1]))
    for i in range(H):
        yc = (i + 0.5) * PX
        Dd = np.hypot(xc[:, None] - mx[None, :], yc - my[None, :])
        with np.errstate(divide="ignore"):
            Wt = np.where(Dd <= r_max, 1.0 / Dd**2, 0.0)
        inside = (mi[None, :] == i) & (mj[None, :] == np.arange(W)[:, None])
        has = inside.any(1)
        Wt[has] = inside[has].astype(float)
        bad = ~np.isfinite(Wt).all(1)
        assert not np.any(bad & ~has), "pixel centre on a midpoint outside the midpoint rule"
        s = Wt.sum(1, keepdims=True)
        Wt = np.divide(Wt, s, out=np.zeros_like(Wt), where=s > 0)
        out[i] = Wt @ V
    return out[..., 0] if one else out


def stats(X):
    X = np.abs(np.asarray(X, float)).ravel()
    return {"max": float(X.max()), "rms": float(np.sqrt(np.mean(X**2))), "median": float(np.median(X))}
