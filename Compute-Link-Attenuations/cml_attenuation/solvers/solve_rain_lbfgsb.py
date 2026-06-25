#!/usr/bin/env python3
# solve_rain_lbfgsb_ildw_init.py
#
# Rainfall inversion from link attenuations using SciPy L-BFGS-B.
# Supports:
#   - Single-run via CLI flags
#   - Config-driven runs via YAML/JSON:
#       python solve_rain_lbfgsb.py --config solve_config.yaml
#   - Batch runs in one config via `runs:` list.
#
# Robustness fix:
#   Some links may have zero in-grid length (no intersected pixels). Those links are
#   automatically excluded from the data term (to avoid division by zero), instead of erroring.
#
# Output .npz contains:
#   R_hat (H,W)
#   A_hat (L,)
#   A_obs (L,)
#   r     (L,) length-normalized residuals (0 for invalid links)
#   valid_links (L,) bool mask (True if link has positive in-grid length)
#   L_km, freq_ghz, pol, k, alpha
#   plus meta_* scalars
#
# Dependencies: numpy, scipy, (optional) pyyaml for YAML configs

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple, Any, Optional, List

import numpy as np
from scipy.optimize import minimize


# Optional: IDW/ILDW baseline initialisation (shared with batch_analyze / baselines)
# Only required when solve_lbfgsb_and_save is called with R0_from_IDW=True or R0_from_ILDW=True.
try:
    from cml_attenuation.idw_baseline import idw_field_from_est_input  # type: ignore
except Exception:
    idw_field_from_est_input = None  # type: ignore

try:
    from cml_attenuation.ildw_baseline import ildw_field_from_est_input  # type: ignore
except Exception:
    ildw_field_from_est_input = None  # type: ignore


# Uses your repo's ITU implementation
from cml_attenuation.itu_r_p_8383 import k_alpha


def _build_neighbor_triplets(H: int, W: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build collinear triplets (a,b,c) of consecutive pixels in a row/column.
    """
    a_idx: List[int] = []
    b_idx: List[int] = []
    c_idx: List[int] = []
    for i in range(H):
        base = i * W
        for j in range(W - 2):
            a_idx.append(base + j)
            b_idx.append(base + j + 1)
            c_idx.append(base + j + 2)
    for i in range(H - 2):
        base0 = i * W
        base1 = (i + 1) * W
        base2 = (i + 2) * W
        for j in range(W):
            a_idx.append(base0 + j)
            b_idx.append(base1 + j)
            c_idx.append(base2 + j)
    if not a_idx:
        z = np.zeros(0, dtype=np.int64)
        return z, z, z
    return (
        np.asarray(a_idx, dtype=np.int64),
        np.asarray(b_idx, dtype=np.int64),
        np.asarray(c_idx, dtype=np.int64),
    )


def _projected_grad_inf_norm(x: np.ndarray, g: np.ndarray, *, lb: float = 0.0) -> float:
    """
    Infinity norm of projected gradient for bounds [lb, +inf).
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    g = np.asarray(g, dtype=np.float64).ravel()
    pg = g.copy()
    active_lower = (x <= lb) & (g > 0.0)
    pg[active_lower] = 0.0
    if pg.size == 0:
        return 0.0
    return float(np.max(np.abs(pg)))


def _write_opt_diagnostics(
    out_path: Path,
    *,
    res,
    x_star: np.ndarray,
    jac_fn,
    f_history: List[float],
    maxiter: int,
    ftol: float,
    gtol: float,
    maxls: int,
) -> Dict[str, Any]:
    message = str(getattr(res, "message", ""))
    f_final = float(getattr(res, "fun", np.nan))
    nit = int(getattr(res, "nit", -1))
    nfev = int(getattr(res, "nfev", -1))
    njev = int(getattr(res, "njev", -1))
    proj_grad = _projected_grad_inf_norm(x_star, jac_fn(x_star), lb=0.0)

    rel_decrease = None
    f_prev = None
    if len(f_history) >= 2:
        f_prev = float(f_history[-2])
        denom = max(1.0, abs(f_prev), abs(f_final))
        rel_decrease = float(abs(f_prev - f_final) / denom)

    msg_upper = message.upper()
    line_search_issue = ("LNSRCH" in msg_upper) or ("LINE SEARCH" in msg_upper)
    hit_maxiter = (nit >= int(maxiter)) or ("TOTAL NO. OF ITERATIONS REACHED LIMIT" in msg_upper)
    gtol_met = (proj_grad <= float(gtol))
    ftol_met = (rel_decrease is not None) and (rel_decrease <= float(ftol))

    if hit_maxiter:
        stop_reason = "maxiter"
    elif line_search_issue:
        stop_reason = "line_search"
    elif gtol_met:
        stop_reason = "gtol"
    elif ftol_met:
        stop_reason = "ftol"
    elif bool(getattr(res, "success", False)):
        stop_reason = "converged_other"
    else:
        stop_reason = "other"

    payload = {
        "success": bool(getattr(res, "success", False)),
        "status": int(getattr(res, "status", -1)),
        "message": message,
        "stop_reason": stop_reason,
        "iteration": nit,
        "maxiter": int(maxiter),
        "nfev": nfev,
        "njev": njev,
        "f_final": f_final,
        "f_prev": f_prev,
        "rel_decrease": rel_decrease,
        "ftol": float(ftol),
        "ftol_met": bool(ftol_met),
        "proj_grad_inf": float(proj_grad),
        "gtol": float(gtol),
        "gtol_met": bool(gtol_met),
        "maxls": int(maxls),
        "line_search_issue": bool(line_search_issue),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


# ----------------------------
# Data model
# ----------------------------

@dataclass
class EstProblem:
    H: int
    W: int
    P: int                 # pixels = H*W
    L: int                 # links
    # sparse intersections (length nnz)
    pix_idx: np.ndarray    # int64, (nnz,) flattened pixel index p=i*W+j
    link_idx: np.ndarray   # int64, (nnz,) link index
    ds_km: np.ndarray      # float64, (nnz,) intersection length in km
    # per-link
    A_obs: np.ndarray      # float64, (L,) observed attenuation [dB]
    L_km: np.ndarray       # float64, (L,) link length within grid [km]
    valid_links: np.ndarray  # bool, (L,) True if L_km>0
    freq_ghz: np.ndarray   # float64, (L,)
    pol: np.ndarray        # object, (L,) 'H'/'V'
    k: np.ndarray          # float64, (L,)
    alpha: np.ndarray      # float64, (L,)
    # 4-neighborhood edges (each once), length E
    n_u: np.ndarray        # int64, (E,)
    n_v: np.ndarray        # int64, (E,)


# ----------------------------
# Config loading
# ----------------------------

def load_config_file(path: str | Path) -> dict:
    """Load YAML (.yaml/.yml) or JSON (.json) config."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in [".yaml", ".yml"]:
        try:
            import yaml  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "YAML config requested but PyYAML is not installed. Install with: pip install pyyaml"
            ) from e
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if cfg is None:
            cfg = {}
        if not isinstance(cfg, dict):
            raise ValueError("YAML config must parse to a dict at top level.")
        return cfg

    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("JSON config must parse to a dict at top level.")
        return cfg

    raise ValueError(f"Unsupported config extension {suffix!r}. Use .yaml/.yml or .json.")


def deep_get(d: dict, path: str, default=None):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


# ----------------------------
# Problem loading
# ----------------------------

def _pol_to_itu(pol: str) -> str:
    pol = str(pol).strip().upper()
    if pol == "H":
        return "horizontal"
    if pol == "V":
        return "vertical"
    raise ValueError(f"Unsupported polarization {pol!r}. Expected 'H' or 'V'.")


def load_est_input_json(path: str | Path, *, warn: bool = True) -> EstProblem:
    """
    Expected JSON layout:
      header: {H, W, ...}
      links: list of {link_index, freq_ghz, pol, A_db, ...}
      segments_by_link: dict[str(link_index)] -> list of {i, j, ds_m}
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    header = payload["header"]
    H = int(header["H"])
    W = int(header["W"])
    P = H * W

    links = payload["links"]
    L = len(links)

    A_obs = np.zeros(L, dtype=np.float64)
    freq_ghz = np.zeros(L, dtype=np.float64)
    pol = np.empty(L, dtype=object)
    k_arr = np.zeros(L, dtype=np.float64)
    a_arr = np.zeros(L, dtype=np.float64)

    for rec in links:
        li = int(rec["link_index"])
        A_obs[li] = float(rec["A_db"])
        freq_ghz[li] = float(rec["freq_ghz"])
        pol_str = str(rec["pol"]).strip().upper()
        pol[li] = pol_str
        k_li, a_li = k_alpha(freq_ghz[li], _pol_to_itu(pol_str))
        k_arr[li] = float(k_li)
        a_arr[li] = float(a_li)

    segs: Dict[str, list] = payload["segments_by_link"]

    # Count nnz
    nnz = 0
    for li in range(L):
        nnz += len(segs.get(str(li), []))

    pix_idx = np.empty(nnz, dtype=np.int64)
    link_idx = np.empty(nnz, dtype=np.int64)
    ds_km = np.empty(nnz, dtype=np.float64)
    L_km = np.zeros(L, dtype=np.float64)

    pos = 0
    for li in range(L):
        for s in segs.get(str(li), []):
            i = int(s["i"])
            j = int(s["j"])
            ds = float(s["ds_m"]) / 1000.0  # meters -> km
            p = i * W + j

            pix_idx[pos] = p
            link_idx[pos] = li
            ds_km[pos] = ds
            L_km[li] += ds
            pos += 1

    valid_links = L_km > 0
    if warn:
        n_bad = int(np.sum(~valid_links))
        if n_bad > 0:
            bad = np.where(~valid_links)[0][:10].tolist()
            print(f"[warn] {n_bad}/{L} links have zero in-grid length; they will be ignored in the data term. Examples: {bad}")

    # 4-neighborhood edges: right + down
    E = H * (W - 1) + (H - 1) * W
    n_u = np.empty(E, dtype=np.int64)
    n_v = np.empty(E, dtype=np.int64)
    e = 0
    for i in range(H):
        base = i * W
        for j in range(W - 1):
            p = base + j
            n_u[e] = p
            n_v[e] = p + 1
            e += 1
    for i in range(H - 1):
        base = i * W
        for j in range(W):
            p = base + j
            n_u[e] = p
            n_v[e] = p + W
            e += 1

    return EstProblem(
        H=H, W=W, P=P, L=L,
        pix_idx=pix_idx, link_idx=link_idx, ds_km=ds_km,
        A_obs=A_obs, L_km=L_km, valid_links=valid_links,
        freq_ghz=freq_ghz, pol=pol,
        k=k_arr, alpha=a_arr,
        n_u=n_u, n_v=n_v,
    )


# ----------------------------
# Model + objective
# ----------------------------

def forward_Ahat_and_r(prob: EstProblem, R_flat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes:
      A_hat[link] = sum_p ds_km * k_link * R_p^alpha_link
      r[link]     = (A_hat - A_obs) / L_km  (0 for invalid links)
    """
    R = np.asarray(R_flat, dtype=np.float64).ravel()

    pix = prob.pix_idx
    li = prob.link_idx
    ds = prob.ds_km

    Rp = R[pix]
    pow_a = np.power(Rp, prob.alpha[li], where=(Rp > 0), out=np.zeros_like(Rp))
    contrib = ds * prob.k[li] * pow_a

    A_hat = np.bincount(li, weights=contrib, minlength=prob.L).astype(np.float64)

    r = np.zeros(prob.L, dtype=np.float64)
    v = prob.valid_links
    r[v] = (A_hat[v] - prob.A_obs[v]) / prob.L_km[v]
    return A_hat, r


def make_objective(prob: EstProblem, lam: float, mu: float, eps: float, eta: float = 0.0):
    """
    Objective:
      J = sum_{valid l} ((A_hat_l - A_obs_l)/L_l)^2
        + lam * sum_(p,q in N4) (log(Rp+eps)-log(Rq+eps))^2
        + mu  * sum_p Rp^2
    """
    pix = prob.pix_idx
    li = prob.link_idx
    ds = prob.ds_km
    A_obs = prob.A_obs
    L_km = prob.L_km
    valid = prob.valid_links
    k = prob.k
    a = prob.alpha
    n_u = prob.n_u
    n_v = prob.n_v
    t_a, t_b, t_c = _build_neighbor_triplets(prob.H, prob.W)

    def f_and_g(R_flat: np.ndarray) -> Tuple[float, np.ndarray]:
        R = np.asarray(R_flat, dtype=np.float64).ravel()

        # --- data term ---
        Rp = R[pix]
        pow_a = np.power(Rp, a[li], where=(Rp > 0), out=np.zeros_like(Rp))
        contrib = ds * k[li] * pow_a
        A_hat = np.bincount(li, weights=contrib, minlength=prob.L).astype(np.float64)

        r = np.zeros(prob.L, dtype=np.float64)
        r[valid] = (A_hat[valid] - A_obs[valid]) / L_km[valid]
        J_data = float(np.dot(r[valid], r[valid]))

        # gradient wrt A_hat: dJ/dA_hat = 2 * r / L_km (only valid links)
        dJ_dAhat = np.zeros(prob.L, dtype=np.float64)
        dJ_dAhat[valid] = 2.0 * r[valid] / L_km[valid]

        # dA_hat/dR for each nnz: ds * k_l * a_l * R^(a_l-1)
        Rp_safe = np.maximum(Rp, 1e-12)
        pow_a_minus_1 = np.power(Rp_safe, a[li] - 1.0)
        dA_dR_nnz = ds * k[li] * a[li] * pow_a_minus_1

        dJ_dR_nnz = dJ_dAhat[li] * dA_dR_nnz
        g_data = np.bincount(pix, weights=dJ_dR_nnz, minlength=prob.P).astype(np.float64)

        # --- smoothness term on log(R+eps) ---
        R_eps = R + eps
        u = np.log(R_eps)
        du = u[n_u] - u[n_v]
        J_smooth = float(np.dot(du, du))

        w = 2.0 * du
        g_u = np.bincount(n_u, weights=w, minlength=prob.P) - np.bincount(n_v, weights=w, minlength=prob.P)
        g_smooth = g_u / R_eps

        # --- shrinkage ---
        J_shrink = float(np.dot(R, R))
        g_shrink = 2.0 * R

        # --- second-derivative triplet term ---
        if t_a.size > 0:
            d_triplet = (R[t_b] - R[t_a]) - (R[t_c] - R[t_b])
            J_curv = float(np.dot(d_triplet, d_triplet))
            g_curv = (
                np.bincount(t_a, weights=(-2.0 * d_triplet), minlength=prob.P).astype(np.float64)
                + np.bincount(t_b, weights=(4.0 * d_triplet), minlength=prob.P).astype(np.float64)
                + np.bincount(t_c, weights=(-2.0 * d_triplet), minlength=prob.P).astype(np.float64)
            )
        else:
            J_curv = 0.0
            g_curv = np.zeros(prob.P, dtype=np.float64)

        J = J_data + lam * J_smooth + mu * J_shrink + eta * J_curv
        g = g_data + lam * g_smooth + mu * g_shrink + eta * g_curv
        return J, g

    def fun(R_flat: np.ndarray) -> float:
        J, _ = f_and_g(R_flat)
        return J

    def jac(R_flat: np.ndarray) -> np.ndarray:
        _, g = f_and_g(R_flat)
        return g

    return fun, jac


# ----------------------------
# Solve + save
# ----------------------------

def solve_lbfgsb_and_save(
    est_input_json: str | Path,
    *,
    lam: float,
    mu: float,
    eps: float = 0.01,
    eta: float = 0.0,
    R0: float = 0.0,
    maxiter: int = 80,
    ftol: float = 1e-9,
    gtol: float = 1e-6,
    maxls: int = 20,
    npz_out: str | Path = "solution.npz",
    warn: bool = True,
    # --- optional IDW/ILDW-based initialisation ---
    R0_from_IDW: bool = False,
    R0_from_ILDW: bool = False,
    idw_r_max_m: float = 3125.0,
    idw_power: float = 2.0,
    idw_eps_m: float = 1.0,
    idw_default_value: float = 0.0,
    optinfo_out: str | Path | None = None,
) -> dict:
    prob = load_est_input_json(est_input_json, warn=warn)
    fun, jac = make_objective(prob, lam=lam, mu=mu, eps=eps, eta=eta)

    # ----------------------------
    # Initialisation
    # ----------------------------
    init_method = "constant"

    if R0_from_ILDW and R0_from_IDW:
        raise ValueError("Choose exactly one of R0_from_ILDW or R0_from_IDW (not both).")

    # Priority: ILDW if requested, else IDW, else constant.
    if R0_from_ILDW:
        init_method = "ildw"
        if ildw_field_from_est_input is None:
            raise RuntimeError(
                "R0_from_ILDW=True but ildw_baseline.py could not be imported. "
                "Place ildw_baseline.py next to this solver and ensure scipy is installed."
            )
        R0_grid, _ = ildw_field_from_est_input(
            Path(est_input_json),
            r_max_m=float(idw_r_max_m),
            power=float(idw_power),
            eps_m=float(idw_eps_m),
            default_value=float(idw_default_value),
        )
        x0 = np.asarray(R0_grid, dtype=np.float64).reshape(prob.P)

    elif R0_from_IDW:
        init_method = "idw"
        if idw_field_from_est_input is None:
            raise RuntimeError(
                "R0_from_IDW=True but idw_baseline.py could not be imported. "
                "Place idw_baseline.py next to this solver and ensure scipy is installed."
            )
        R0_grid, _ = idw_field_from_est_input(
            Path(est_input_json),
            r_max_m=float(idw_r_max_m),
            power=float(idw_power),
            eps_m=float(idw_eps_m),
            default_value=float(idw_default_value),
        )
        x0 = np.asarray(R0_grid, dtype=np.float64).reshape(prob.P)

    else:
        x0 = np.full(prob.P, float(R0), dtype=np.float64)

    bounds = [(0.0, None)] * prob.P
    f_history: List[float] = [float(fun(x0))]

    def _cb(xk: np.ndarray):
        f_history.append(float(fun(xk)))

    res = minimize(
        fun,
        x0,
        method="L-BFGS-B",
        jac=jac,
        callback=_cb,
        bounds=bounds,
        options={
            "maxiter": int(maxiter),
            "ftol": float(ftol),
            "gtol": float(gtol),
            "maxls": int(maxls),
        },
    )

    R_hat = res.x.reshape(prob.H, prob.W).astype(np.float32)
    A_hat, r = forward_Ahat_and_r(prob, res.x)

    npz_out = Path(npz_out)
    npz_out.parent.mkdir(parents=True, exist_ok=True)
    if optinfo_out is None:
        optinfo_path = npz_out.with_name(f"{npz_out.stem}_optinfo.json")
    else:
        optinfo_path = Path(optinfo_out)
    opt_diag = _write_opt_diagnostics(
        optinfo_path,
        res=res,
        x_star=res.x,
        jac_fn=jac,
        f_history=f_history if len(f_history) >= 2 else [float(fun(x0)), float(res.fun)],
        maxiter=maxiter,
        ftol=ftol,
        gtol=gtol,
        maxls=maxls,
    )

    np.savez(
        npz_out,
        R_hat=R_hat,
        A_hat=A_hat.astype(np.float64),
        A_obs=prob.A_obs.astype(np.float64),
        r=r.astype(np.float64),
        valid_links=prob.valid_links.astype(bool),
        L_km=prob.L_km.astype(np.float64),
        freq_ghz=prob.freq_ghz.astype(np.float64),
        pol=np.array(prob.pol, dtype="U1"),
        k=prob.k.astype(np.float64),
        alpha=prob.alpha.astype(np.float64),
        # provenance / meta
        meta_success=bool(res.success),
        meta_status=int(res.status),
        meta_message=str(res.message),
        meta_nit=int(getattr(res, "nit", -1)),
        meta_fun=float(res.fun),
        meta_H=int(prob.H),
        meta_W=int(prob.W),
        meta_L=int(prob.L),
        meta_P=int(prob.P),
        meta_nnz=int(prob.pix_idx.size),
        meta_lambda=float(lam),
        meta_mu=float(mu),
        meta_eps=float(eps),
        meta_eta=float(eta),
        meta_R0=float(R0),
        meta_maxiter=int(maxiter),
        meta_ftol=float(ftol),
        meta_gtol=float(gtol),
        meta_maxls=int(maxls),
        meta_est_input_json=str(Path(est_input_json)),
        meta_num_valid_links=int(np.sum(prob.valid_links)),
        meta_num_invalid_links=int(np.sum(~prob.valid_links)),
        meta_init_method=str(init_method),
        meta_R0_from_IDW=bool(R0_from_IDW),
        meta_R0_from_ILDW=bool(R0_from_ILDW),
        meta_idw_r_max_m=float(idw_r_max_m),
        meta_idw_power=float(idw_power),
        meta_idw_eps_m=float(idw_eps_m),
        meta_idw_default_value=float(idw_default_value),
        meta_stop_reason=str(opt_diag.get("stop_reason", "other")),
        meta_proj_grad_inf=float(opt_diag.get("proj_grad_inf", 0.0)),
        meta_rel_decrease=float(opt_diag.get("rel_decrease") if opt_diag.get("rel_decrease") is not None else np.nan),
        meta_optinfo_json=str(optinfo_path),
    )

    return {
        "success": bool(res.success),
        "status": int(res.status),
        "message": str(res.message),
        "nit": int(getattr(res, "nit", -1)),
        "fun": float(res.fun),
        "out_npz": str(npz_out),
        "optinfo_json": str(optinfo_path),
        "init_method": str(init_method),
    }
def run_from_config(cfg: dict) -> List[dict]:
    """
    Supports two styles:

    Style A (single run):
      input: { est_input_json: "..." }
      output: { out_npz: "..." }
      optimization: { lambda: 1e-2, mu: 1e-6, epsilon: 0.01, R0: 0.0, maxiter: 80 }
      tolerances: { ftol: 1e-9, gtol: 1e-6, maxls: 20 }

    Style B (batch runs):
      runs:
        - input: { est_input_json: "..." }
          output: { out_npz: "..." }
          optimization: { lambda: 1e-2, mu: 1e-6 }
          tolerances: { ... }
        - ...
    """
    runs = cfg.get("runs")
    if runs is None:
        runs = [cfg]
    if not isinstance(runs, list) or not runs:
        raise ValueError("Config must contain a non-empty `runs:` list, or be a single-run dict.")

    results: List[dict] = []
    for idx, rcfg in enumerate(runs):
        if not isinstance(rcfg, dict):
            raise ValueError(f"Run #{idx} is not a dict.")

        est_input_json = deep_get(rcfg, "input.est_input_json")
        if not est_input_json:
            raise ValueError(f"Run #{idx}: missing input.est_input_json")

        out_npz = deep_get(rcfg, "output.out_npz", deep_get(rcfg, "output.npz_out", None))
        if not out_npz:
            out_npz = str(Path(est_input_json).with_suffix("")) + "_solution.npz"

        lam = deep_get(rcfg, "optimization.lambda")
        mu = deep_get(rcfg, "optimization.mu")
        if lam is None or mu is None:
            raise ValueError(f"Run #{idx}: missing optimization.lambda and/or optimization.mu")

        eps = float(deep_get(rcfg, "optimization.epsilon", 0.01))
        eta = float(deep_get(rcfg, "optimization.eta", 0.0))
        R0 = float(deep_get(rcfg, "optimization.R0", 0.0))
        maxiter = int(deep_get(rcfg, "optimization.maxiter", 80))

        ftol = float(deep_get(rcfg, "tolerances.ftol", 1e-9))
        gtol = float(deep_get(rcfg, "tolerances.gtol", 1e-6))
        maxls = int(deep_get(rcfg, "tolerances.maxls", 20))

        warn = bool(deep_get(rcfg, "output.warn", True))

        info = solve_lbfgsb_and_save(
            est_input_json,
            lam=float(lam),
            mu=float(mu),
            eps=eps,
            eta=eta,
            R0=R0,
            maxiter=maxiter,
            ftol=ftol,
            gtol=gtol,
            maxls=maxls,
            npz_out=out_npz,
            warn=warn,
        )
        info["run_index"] = idx
        info["est_input_json"] = str(est_input_json)
        info["lambda"] = float(lam)
        info["mu"] = float(mu)
        info["epsilon"] = eps
        info["eta"] = eta
        results.append(info)

    return results


# ----------------------------
# CLI
# ----------------------------

def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Solve rainfall inverse problem with SciPy L-BFGS-B. Supports YAML/JSON configs."
    )
    ap.add_argument("--config", type=str, default=None, help="Path to YAML/JSON config. If set, CLI flags are ignored.")

    # Direct CLI mode (single run)
    ap.add_argument("est_input_json", nargs="?", type=str, help="Path to est_input_*.json (CLI mode)")
    ap.add_argument("--lam", type=float, default=None, help="Smoothness weight lambda (CLI mode)")
    ap.add_argument("--mu", type=float, default=None, help="Shrinkage weight mu (CLI mode)")
    ap.add_argument("--eps", type=float, default=0.01, help="Epsilon for log(R+eps) (CLI mode)")
    ap.add_argument("--eta", type=float, default=0.0, help="Triplet-term weight eta (CLI mode)")
    ap.add_argument("--R0", type=float, default=0.0, help="Initial rainfall value (mm/h) (CLI mode)")
    ap.add_argument("--maxiter", type=int, default=80, help="Max L-BFGS-B iterations (CLI mode)")
    ap.add_argument("--ftol", type=float, default=1e-9, help="L-BFGS-B ftol (CLI mode)")
    ap.add_argument("--gtol", type=float, default=1e-6, help="L-BFGS-B gtol (CLI mode)")
    ap.add_argument("--maxls", type=int, default=20, help="L-BFGS-B max line search steps (CLI mode)")
    ap.add_argument("--out", type=str, default="solution.npz", help="Output .npz path (CLI mode)")
    ap.add_argument("--quiet", action="store_true", help="Suppress warnings (CLI mode)")
    return ap


def main():
    ap = build_argparser()
    args = ap.parse_args()

    if args.config:
        cfg = load_config_file(args.config)
        results = run_from_config(cfg)
        print("Done. Runs:")
        for r in results:
            print(r)
        return

    # CLI single-run mode
    if not args.est_input_json:
        raise SystemExit("Provide est_input_json positional arg, or use --config.")
    if args.lam is None or args.mu is None:
        raise SystemExit("CLI mode requires --lam and --mu, or use --config.")

    info = solve_lbfgsb_and_save(
        args.est_input_json,
        lam=float(args.lam),
        mu=float(args.mu),
        eps=float(args.eps),
        eta=float(args.eta),
        R0=float(args.R0),
        maxiter=int(args.maxiter),
        ftol=float(args.ftol),
        gtol=float(args.gtol),
        maxls=int(args.maxls),
        npz_out=args.out,
        warn=not args.quiet,
    )
    print("Done.")
    print(info)


if __name__ == "__main__":
    main()
