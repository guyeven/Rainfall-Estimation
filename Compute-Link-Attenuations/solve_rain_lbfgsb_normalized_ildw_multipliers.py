#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize

from solve_rain_lbfgsb import (  # type: ignore
    _write_opt_diagnostics,
    forward_Ahat_and_r,
    load_est_input_json,
)

try:
    from idw_baseline import idw_field_from_est_input  # type: ignore
except Exception:
    idw_field_from_est_input = None  # type: ignore

try:
    from ildw_baseline import ildw_field_from_est_input  # type: ignore
except Exception:
    ildw_field_from_est_input = None  # type: ignore


def _build_collinear_triplets(h: int, w: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    p_idx: List[int] = []
    q_idx: List[int] = []
    r_idx: List[int] = []

    for i in range(h):
        base = i * w
        for j in range(w - 2):
            p_idx.append(base + j)
            q_idx.append(base + j + 1)
            r_idx.append(base + j + 2)

    for i in range(h - 2):
        base0 = i * w
        base1 = (i + 1) * w
        base2 = (i + 2) * w
        for j in range(w):
            p_idx.append(base0 + j)
            q_idx.append(base1 + j)
            r_idx.append(base2 + j)

    if not p_idx:
        z = np.zeros(0, dtype=np.int64)
        return z, z, z

    return (
        np.asarray(p_idx, dtype=np.int64),
        np.asarray(q_idx, dtype=np.int64),
        np.asarray(r_idx, dtype=np.int64),
    )


def _compute_terms_and_grads(
    prob,
    R: np.ndarray,
    *,
    t_p: np.ndarray,
    t_q: np.ndarray,
    t_r: np.ndarray,
) -> Tuple[float, float, float, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pix = prob.pix_idx
    li = prob.link_idx
    ds = prob.ds_km
    a = prob.alpha
    k = prob.k
    A_obs = prob.A_obs
    L_km = prob.L_km
    valid = prob.valid_links
    n_u = prob.n_u
    n_v = prob.n_v
    n_valid = float(max(1, int(np.sum(valid))))
    n_pix = float(prob.P)

    Rp = R[pix]
    pow_a = np.power(Rp, a[li], where=(Rp > 0.0), out=np.zeros_like(Rp))
    contrib = ds * k[li] * pow_a
    A_hat = np.bincount(li, weights=contrib, minlength=prob.L).astype(np.float64)
    diff = np.zeros(prob.L, dtype=np.float64)
    diff[valid] = A_hat[valid] - A_obs[valid]
    J_atten = float(np.sum((diff[valid] ** 2) / L_km[valid]) / n_valid)

    dJ_dAhat = np.zeros(prob.L, dtype=np.float64)
    dJ_dAhat[valid] = (2.0 / n_valid) * (diff[valid] / L_km[valid])
    Rp_safe = np.maximum(Rp, 1e-12)
    dAhat_dR = ds * k[li] * a[li] * np.power(Rp_safe, a[li] - 1.0)
    g_atten = np.bincount(
        pix,
        weights=dJ_dAhat[li] * dAhat_dR,
        minlength=prob.P,
    ).astype(np.float64)

    du = R[n_u] - R[n_v]
    J_1d = float(np.dot(du, du) / n_pix)
    w = (2.0 / n_pix) * du
    g_1d = np.bincount(n_u, weights=w, minlength=prob.P) - np.bincount(
        n_v, weights=w, minlength=prob.P
    )

    if t_p.size > 0:
        t = (R[t_q] - R[t_p]) - (R[t_r] - R[t_q])
        J_2d = float(np.dot(t, t) / n_pix)
        g_2d = (
            np.bincount(t_q, weights=(4.0 / n_pix) * t, minlength=prob.P)
            + np.bincount(t_p, weights=(-2.0 / n_pix) * t, minlength=prob.P)
            + np.bincount(t_r, weights=(-2.0 / n_pix) * t, minlength=prob.P)
        ).astype(np.float64)
    else:
        J_2d = 0.0
        g_2d = np.zeros(prob.P, dtype=np.float64)

    J_total = float(np.dot(R, R) / n_pix)
    g_total = (2.0 / n_pix) * R

    return J_atten, J_1d, J_2d, J_total, g_atten, g_1d, g_2d, g_total


def _safe_inverse(x: float, *, eps: float = 1e-12) -> float:
    return 1.0 / max(float(eps), abs(float(x)))


def _compute_instance_multipliers(
    prob,
    *,
    R_ildw_flat: np.ndarray,
    t_p: np.ndarray,
    t_q: np.ndarray,
    t_r: np.ndarray,
    num_atten: float = 1.0,
    num_1d: float = 1.0,
    num_2d: float = 0.5,
    num_total: float = 1.0,
    num_total_divide_by_num_pixels: bool = False,
) -> Dict[str, float]:
    J_atten, J_1d, J_2d, J_total, _, _, _, _ = _compute_terms_and_grads(
        prob, R_ildw_flat, t_p=t_p, t_q=t_q, t_r=t_r
    )
    beta_atten = _safe_inverse(J_atten)
    beta_1d = _safe_inverse(J_1d)
    beta_2d = _safe_inverse(J_2d)
    beta_total = _safe_inverse(J_total)
    effective_num_total = float(num_total)
    if bool(num_total_divide_by_num_pixels):
        effective_num_total /= float(max(1, int(prob.P)))

    alpha_atten = float(num_atten) * beta_atten
    alpha_1d = float(num_1d) * beta_1d
    alpha_2d = float(num_2d) * beta_2d
    alpha_total = float(effective_num_total) * beta_total

    return {
        "J_atten_ildw": float(J_atten),
        "J_1d_ildw": float(J_1d),
        "J_2d_ildw": float(J_2d),
        "J_total_ildw": float(J_total),
        "num_atten": float(num_atten),
        "num_1d": float(num_1d),
        "num_2d": float(num_2d),
        "num_total": float(num_total),
        "num_total_effective": float(effective_num_total),
        "num_total_divide_by_num_pixels": bool(num_total_divide_by_num_pixels),
        "beta_atten": float(beta_atten),
        "beta_1d": float(beta_1d),
        "beta_2d": float(beta_2d),
        "beta_total": float(beta_total),
        "alpha_atten": float(alpha_atten),
        "alpha_1d": float(alpha_1d),
        "alpha_2d": float(alpha_2d),
        "alpha_total": float(alpha_total),
    }


def make_objective(
    prob,
    *,
    alpha_atten: float,
    alpha_1d: float,
    alpha_2d: float,
    alpha_total: float,
    t_p: np.ndarray,
    t_q: np.ndarray,
    t_r: np.ndarray,
):
    def f_and_g(r_flat: np.ndarray) -> Tuple[float, np.ndarray]:
        R = np.asarray(r_flat, dtype=np.float64).ravel()
        J_atten, J_1d, J_2d, J_total, g_atten, g_1d, g_2d, g_total = _compute_terms_and_grads(
            prob, R, t_p=t_p, t_q=t_q, t_r=t_r
        )
        J_obj = (
            alpha_atten * J_atten
            + alpha_1d * J_1d
            + alpha_2d * J_2d
            + alpha_total * J_total
        )
        g_obj = (
            alpha_atten * g_atten
            + alpha_1d * g_1d
            + alpha_2d * g_2d
            + alpha_total * g_total
        )
        return float(J_obj), np.asarray(g_obj, dtype=np.float64)

    def fun(x: np.ndarray) -> float:
        return f_and_g(x)[0]

    def jac(x: np.ndarray) -> np.ndarray:
        return f_and_g(x)[1]

    return fun, jac


def solve_lbfgsb_and_save(
    est_input_json: str | Path,
    *,
    eps: float = 0.01,
    use_linear_j3: bool = True,
    R0: float = 0.0,
    maxiter: int = 80,
    ftol: float = 1e-9,
    gtol: float = 1e-6,
    maxls: int = 20,
    npz_out: str | Path = "solution.npz",
    warn: bool = True,
    R0_from_IDW: bool = False,
    R0_from_ILDW: bool = False,
    rain_init_mode: str = "fixed",
    rain_init_value: float | None = None,
    rain_init_multiplier: float = 1.0,
    idw_r_max_m: float = 3125.0,
    idw_power: float = 2.0,
    idw_eps_m: float = 1.0,
    idw_default_value: float = 0.0,
    optinfo_out: str | Path | None = None,
    lam: float | None = None,
    mu: float | None = None,
    eta: float | None = None,
    num_atten: float = 1.0,
    num_1d: float = 1.0,
    num_2d: float = 0.5,
    num_total: float = 1.0,
    num_total_divide_by_num_pixels: bool = False,
) -> Dict[str, Any]:
    # Legacy weights are accepted but ignored: this solver uses per-instance ILDW multipliers.
    _ = lam
    _ = mu
    _ = eta
    _ = float(eps)  # accepted for API compatibility but intentionally unused in linear mode.
    _ = bool(use_linear_j3)  # always linear in this module.

    prob = load_est_input_json(est_input_json, warn=warn)
    t_p, t_q, t_r = _build_collinear_triplets(prob.H, prob.W)

    if ildw_field_from_est_input is None:
        raise RuntimeError("ILDW baseline is required for per-instance alpha scaling but ildw_baseline.py is unavailable.")
    R_ildw_grid, _ = ildw_field_from_est_input(
        Path(est_input_json),
        r_max_m=float(idw_r_max_m),
        power=float(idw_power),
        eps_m=float(idw_eps_m),
        default_value=float(idw_default_value),
    )
    R_ildw_flat = np.asarray(R_ildw_grid, dtype=np.float64).reshape(prob.P)
    mult = _compute_instance_multipliers(
        prob,
        R_ildw_flat=R_ildw_flat,
        t_p=t_p,
        t_q=t_q,
        t_r=t_r,
        num_atten=float(num_atten),
        num_1d=float(num_1d),
        num_2d=float(num_2d),
        num_total=float(num_total),
        num_total_divide_by_num_pixels=bool(num_total_divide_by_num_pixels),
    )

    fun, jac = make_objective(
        prob,
        alpha_atten=float(mult["alpha_atten"]),
        alpha_1d=float(mult["alpha_1d"]),
        alpha_2d=float(mult["alpha_2d"]),
        alpha_total=float(mult["alpha_total"]),
        t_p=t_p,
        t_q=t_q,
        t_r=t_r,
    )

    init_method = "constant"
    if R0_from_ILDW and R0_from_IDW:
        raise ValueError("Choose exactly one of R0_from_ILDW or R0_from_IDW.")
    if rain_init_mode not in {"fixed", "idw_mean"}:
        raise ValueError(f"Unsupported rain_init_mode={rain_init_mode!r}; expected 'fixed' or 'idw_mean'.")
    if rain_init_value is None:
        rain_init_value = float(R0)
    if (R0_from_ILDW or R0_from_IDW) and rain_init_mode != "fixed":
        raise ValueError("rain_init.mode='idw_mean' is only supported for constant-field initialization.")

    effective_r0 = float(rain_init_value)

    if R0_from_ILDW:
        init_method = "ildw"
        x0 = R_ildw_flat.copy()
    elif R0_from_IDW:
        init_method = "idw"
        if idw_field_from_est_input is None:
            raise RuntimeError("R0_from_IDW=True but idw_baseline.py unavailable.")
        r0_grid, _ = idw_field_from_est_input(
            Path(est_input_json),
            r_max_m=float(idw_r_max_m),
            power=float(idw_power),
            eps_m=float(idw_eps_m),
            default_value=float(idw_default_value),
        )
        x0 = np.asarray(r0_grid, dtype=np.float64).reshape(prob.P)
    else:
        if rain_init_mode == "idw_mean":
            init_method = "idw_mean"
            if idw_field_from_est_input is None:
                raise RuntimeError("rain_init.mode='idw_mean' but idw_baseline.py unavailable.")
            r0_grid, _ = idw_field_from_est_input(
                Path(est_input_json),
                r_max_m=float(idw_r_max_m),
                power=float(idw_power),
                eps_m=float(idw_eps_m),
                default_value=float(idw_default_value),
            )
            idw_vals = np.asarray(r0_grid, dtype=np.float64).reshape(prob.P)
            finite_vals = idw_vals[np.isfinite(idw_vals)]
            if finite_vals.size == 0:
                raise RuntimeError("rain_init.mode='idw_mean' produced no finite IDW values.")
            effective_r0 = float(rain_init_multiplier) * float(np.mean(finite_vals))
        x0 = np.full(prob.P, float(effective_r0), dtype=np.float64)

    a_att = float(mult["alpha_atten"])
    a_1d = float(mult["alpha_1d"])
    a_2d = float(mult["alpha_2d"])
    a_tot = float(mult["alpha_total"])

    def _trace_row(xk: np.ndarray, *, iteration: int) -> Dict[str, Any]:
        Rk = np.asarray(xk, dtype=np.float64).ravel()
        J_atten, J_1d, J_2d, J_total, _, _, _, _ = _compute_terms_and_grads(
            prob, Rk, t_p=t_p, t_q=t_q, t_r=t_r
        )
        w_atten = a_att * float(J_atten)
        w_1d = a_1d * float(J_1d)
        w_2d = a_2d * float(J_2d)
        w_total = a_tot * float(J_total)
        return {
            "iter": int(iteration),
            "feasible": True,
            "constraint_residual": 0.0,
            "J_weighted_sum": float(w_atten + w_1d + w_2d + w_total),
            "J_atten": float(J_atten),
            "J_1d": float(J_1d),
            "J_2d": float(J_2d),
            "J_total": float(J_total),
            "weighted_J_atten": float(w_atten),
            "weighted_J_1d": float(w_1d),
            "weighted_J_2d": float(w_2d),
            "weighted_J_total": float(w_total),
            "alpha_atten": float(a_att),
            "alpha_1d": float(a_1d),
            "alpha_2d": float(a_2d),
            "alpha_total": float(a_tot),
        }

    iter_trace: List[Dict[str, Any]] = []
    iter_trace.append(_trace_row(x0, iteration=0))
    f_history: List[float] = [float(iter_trace[0]["J_weighted_sum"])]
    iter_idx = 0

    def _callback(xk: np.ndarray):
        nonlocal iter_idx
        iter_idx += 1
        row = _trace_row(xk, iteration=iter_idx)
        iter_trace.append(row)
        f_history.append(float(row["J_weighted_sum"]))

    res = minimize(
        fun,
        x0,
        method="L-BFGS-B",
        jac=jac,
        callback=_callback,
        bounds=[(0.0, None)] * prob.P,
        options={
            "maxiter": int(maxiter),
            "ftol": float(ftol),
            "gtol": float(gtol),
            "maxls": int(maxls),
        },
    )

    r_hat = res.x.reshape(prob.H, prob.W).astype(np.float32)
    a_hat, r_link = forward_Ahat_and_r(prob, res.x)

    npz_out = Path(npz_out)
    npz_out.parent.mkdir(parents=True, exist_ok=True)
    optinfo_path = (
        npz_out.with_name(f"{npz_out.stem}_optinfo.json")
        if optinfo_out is None
        else Path(optinfo_out)
    )
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

    # Ensure final iterate is present in itertrace (robust to callback behavior differences).
    final_iter = int(getattr(res, "nit", iter_idx))
    if not iter_trace or int(iter_trace[-1].get("iter", -1)) != final_iter:
        row = _trace_row(res.x, iteration=final_iter)
        iter_trace.append(row)
        f_history.append(float(row["J_weighted_sum"]))

    feasible_count = int(sum(1 for it in iter_trace if bool(it.get("feasible", False))))
    infeasible_count = int(len(iter_trace) - feasible_count)
    best_idx = int(np.argmin([float(it.get("J_weighted_sum", np.inf)) for it in iter_trace]))
    best_iter = int(iter_trace[best_idx].get("iter", -1))
    best_obj = float(iter_trace[best_idx].get("J_weighted_sum", np.nan))
    itertrace_path = npz_out.with_name(f"{npz_out.stem}_itertrace.json")
    itertrace_payload = {
        "summary": {
            "solver": "lbfgsb_normalized_ildw_multipliers",
            "total_iterations": int(len(iter_trace)),
            "feasible_iterations": int(feasible_count),
            "infeasible_iterations": int(infeasible_count),
            "best_iteration_by_weighted_sum": int(best_iter),
            "best_weighted_sum": float(best_obj),
        },
        "iterations": iter_trace,
    }
    itertrace_path.write_text(json.dumps(itertrace_payload, indent=2), encoding="utf-8")

    np.savez(
        npz_out,
        R_hat=r_hat,
        A_hat=a_hat.astype(np.float64),
        A_obs=prob.A_obs.astype(np.float64),
        r=r_link.astype(np.float64),
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
        meta_use_linear_j3=True,
        meta_J_atten_ildw=float(mult["J_atten_ildw"]),
        meta_J_1d_ildw=float(mult["J_1d_ildw"]),
        meta_J_2d_ildw=float(mult["J_2d_ildw"]),
        meta_J_total_ildw=float(mult["J_total_ildw"]),
        meta_beta_atten=float(mult["beta_atten"]),
        meta_beta_1d=float(mult["beta_1d"]),
        meta_beta_2d=float(mult["beta_2d"]),
        meta_beta_total=float(mult["beta_total"]),
        meta_num_atten=float(mult["num_atten"]),
        meta_num_1d=float(mult["num_1d"]),
        meta_num_2d=float(mult["num_2d"]),
        meta_num_total=float(mult["num_total"]),
        meta_num_total_effective=float(mult["num_total_effective"]),
        meta_num_total_divide_by_num_pixels=bool(mult["num_total_divide_by_num_pixels"]),
        meta_alpha_atten=float(mult["alpha_atten"]),
        meta_alpha_1d=float(mult["alpha_1d"]),
        meta_alpha_2d=float(mult["alpha_2d"]),
        meta_alpha_total=float(mult["alpha_total"]),
        meta_R0=float(effective_r0),
        meta_rain_init_mode=str(rain_init_mode),
        meta_rain_init_value=float(rain_init_value),
        meta_rain_init_multiplier=float(rain_init_multiplier),
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
        meta_rel_decrease=float(
            opt_diag.get("rel_decrease")
            if opt_diag.get("rel_decrease") is not None
            else np.nan
        ),
        meta_optinfo_json=str(optinfo_path),
        meta_itertrace_json=str(itertrace_path),
    )

    return {
        "success": bool(res.success),
        "status": int(res.status),
        "message": str(res.message),
        "nit": int(getattr(res, "nit", -1)),
        "fun": float(res.fun),
        "out_npz": str(npz_out),
        "optinfo_json": str(optinfo_path),
        "itertrace_json": str(itertrace_path),
        "init_method": str(init_method),
    }
