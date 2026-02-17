#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Any, Optional, List

import numpy as np
from scipy.optimize import minimize

from solve_rain_lbfgsb import (  # type: ignore
    load_est_input_json,
    forward_Ahat_and_r,
    _write_opt_diagnostics,
)

try:
    from idw_baseline import idw_field_from_est_input  # type: ignore
except Exception:
    idw_field_from_est_input = None  # type: ignore

try:
    from ildw_baseline import ildw_field_from_est_input  # type: ignore
except Exception:
    ildw_field_from_est_input = None  # type: ignore


def _collinear_triplets(H: int, W: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    p_idx: List[int] = []
    q_idx: List[int] = []
    r_idx: List[int] = []
    for i in range(H):
        base = i * W
        for j in range(W - 2):
            p = base + j
            q = base + j + 1
            r = base + j + 2
            p_idx.append(p); q_idx.append(q); r_idx.append(r)
    for i in range(H - 2):
        base0 = i * W
        base1 = (i + 1) * W
        base2 = (i + 2) * W
        for j in range(W):
            p = base0 + j
            q = base1 + j
            r = base2 + j
            p_idx.append(p); q_idx.append(q); r_idx.append(r)
    if not p_idx:
        z = np.zeros(0, dtype=np.int64)
        return z, z, z
    return (
        np.asarray(p_idx, dtype=np.int64),
        np.asarray(q_idx, dtype=np.int64),
        np.asarray(r_idx, dtype=np.int64),
    )


def make_objective(
    prob,
    *,
    eps: float,
    j2_w: float,
    j3_w: float,
    j4_w: float,
    use_linear_j3: bool,
):
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
    P = float(prob.P)
    n_valid = float(max(1, int(np.sum(valid))))
    t_p, t_q, t_r = _collinear_triplets(prob.H, prob.W)

    def f_and_g(R_flat: np.ndarray) -> Tuple[float, np.ndarray]:
        R = np.asarray(R_flat, dtype=np.float64).ravel()

        # J1: mean over valid links of (A_obs - A_hat)^2 / |l|
        Rp = R[pix]
        pow_a = np.power(Rp, a[li], where=(Rp > 0), out=np.zeros_like(Rp))
        contrib = ds * k[li] * pow_a
        A_hat = np.bincount(li, weights=contrib, minlength=prob.L).astype(np.float64)
        diff = np.zeros(prob.L, dtype=np.float64)
        diff[valid] = A_hat[valid] - A_obs[valid]
        J1 = float(np.sum((diff[valid] ** 2) / L_km[valid]) / n_valid)

        dJ_dAhat = np.zeros(prob.L, dtype=np.float64)
        dJ_dAhat[valid] = (2.0 / n_valid) * (diff[valid] / L_km[valid])
        Rp_safe = np.maximum(Rp, 1e-12)
        dA_dR_nnz = ds * k[li] * a[li] * np.power(Rp_safe, a[li] - 1.0)
        g1 = np.bincount(pix, weights=(dJ_dAhat[li] * dA_dR_nnz), minlength=prob.P).astype(np.float64)

        # J2: (1/P) * sum R^2
        J2 = float(np.dot(R, R) / P)
        g2 = (2.0 / P) * R

        # J3: (1/P) * smoothness, log or linear
        if use_linear_j3:
            du = R[n_u] - R[n_v]
            J3 = float(np.dot(du, du) / P)
            w = (2.0 / P) * du
            g3 = np.bincount(n_u, weights=w, minlength=prob.P) - np.bincount(n_v, weights=w, minlength=prob.P)
        else:
            R_eps = R + eps
            u = np.log(R_eps)
            du = u[n_u] - u[n_v]
            J3 = float(np.dot(du, du) / P)
            w = (2.0 / P) * du
            g_u = np.bincount(n_u, weights=w, minlength=prob.P) - np.bincount(n_v, weights=w, minlength=prob.P)
            g3 = g_u / R_eps

        # J4: (1/P) * sum ((Rq-Rp)-(Rr-Rq))^2 for collinear triplets
        if t_p.size > 0:
            t = (R[t_q] - R[t_p]) - (R[t_r] - R[t_q])
            J4 = float(np.dot(t, t) / P)
            g4 = (
                np.bincount(t_q, weights=(4.0 / P) * t, minlength=prob.P)
                + np.bincount(t_p, weights=(-2.0 / P) * t, minlength=prob.P)
                + np.bincount(t_r, weights=(-2.0 / P) * t, minlength=prob.P)
            ).astype(np.float64)
        else:
            J4 = 0.0
            g4 = np.zeros(prob.P, dtype=np.float64)

        J = J1 + j2_w * J2 + j3_w * J3 + j4_w * J4
        g = g1 + j2_w * g2 + j3_w * g3 + j4_w * g4
        return J, g

    def fun(x: np.ndarray) -> float:
        return f_and_g(x)[0]

    def jac(x: np.ndarray) -> np.ndarray:
        return f_and_g(x)[1]

    return fun, jac


def solve_lbfgsb_and_save(
    est_input_json: str | Path,
    *,
    eps: float = 0.01,
    j2_w: float = 0.01,
    j3_w: float = 1e-6,
    j4_w: float = 1e-6,
    use_linear_j3: bool = False,
    R0: float = 0.0,
    maxiter: int = 80,
    ftol: float = 1e-9,
    gtol: float = 1e-6,
    maxls: int = 20,
    npz_out: str | Path = "solution.npz",
    warn: bool = True,
    R0_from_IDW: bool = False,
    R0_from_ILDW: bool = False,
    idw_r_max_m: float = 3125.0,
    idw_power: float = 2.0,
    idw_eps_m: float = 1.0,
    idw_default_value: float = 0.0,
    optinfo_out: str | Path | None = None,
) -> dict:
    prob = load_est_input_json(est_input_json, warn=warn)
    fun, jac = make_objective(
        prob,
        eps=float(eps),
        j2_w=float(j2_w),
        j3_w=float(j3_w),
        j4_w=float(j4_w),
        use_linear_j3=bool(use_linear_j3),
    )

    init_method = "constant"
    if R0_from_ILDW and R0_from_IDW:
        raise ValueError("Choose exactly one of R0_from_ILDW or R0_from_IDW.")
    if R0_from_ILDW:
        init_method = "ildw"
        if ildw_field_from_est_input is None:
            raise RuntimeError("R0_from_ILDW=True but ildw_baseline.py unavailable.")
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
            raise RuntimeError("R0_from_IDW=True but idw_baseline.py unavailable.")
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

    f_history: List[float] = [float(fun(x0))]

    def _cb(xk: np.ndarray):
        f_history.append(float(fun(xk)))

    res = minimize(
        fun,
        x0,
        method="L-BFGS-B",
        jac=jac,
        callback=_cb,
        bounds=[(0.0, None)] * prob.P,
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
        meta_eps=float(eps),
        meta_j2_w=float(j2_w),
        meta_j3_w=float(j3_w),
        meta_j4_w=float(j4_w),
        meta_use_linear_j3=bool(use_linear_j3),
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

