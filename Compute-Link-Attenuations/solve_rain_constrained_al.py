#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize

from solve_rain_lbfgsb import (
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


def _collinear_triplets(H: int, W: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    p_idx: List[int] = []
    q_idx: List[int] = []
    r_idx: List[int] = []
    for i in range(H):
        base = i * W
        for j in range(W - 2):
            p_idx.append(base + j)
            q_idx.append(base + j + 1)
            r_idx.append(base + j + 2)
    for i in range(H - 2):
        b0 = i * W
        b1 = (i + 1) * W
        b2 = (i + 2) * W
        for j in range(W):
            p_idx.append(b0 + j)
            q_idx.append(b1 + j)
            r_idx.append(b2 + j)
    if not p_idx:
        z = np.zeros(0, dtype=np.int64)
        return z, z, z
    return np.asarray(p_idx, dtype=np.int64), np.asarray(q_idx, dtype=np.int64), np.asarray(r_idx, dtype=np.int64)


def _atten_term_and_grad(prob, R_flat: np.ndarray) -> Tuple[float, np.ndarray, np.ndarray]:
    R = np.asarray(R_flat, dtype=np.float64).ravel()
    pix = prob.pix_idx
    li = prob.link_idx
    ds = prob.ds_km
    valid = prob.valid_links
    n_valid = float(max(1, int(np.sum(valid))))

    Rp = R[pix]
    pow_a = np.power(Rp, prob.alpha[li], where=(Rp > 0), out=np.zeros_like(Rp))
    contrib = ds * prob.k[li] * pow_a
    A_hat = np.bincount(li, weights=contrib, minlength=prob.L).astype(np.float64)

    diff = np.zeros(prob.L, dtype=np.float64)
    diff[valid] = A_hat[valid] - prob.A_obs[valid]
    J_att = float(np.sum((diff[valid] ** 2) / prob.L_km[valid]) / n_valid)

    dJ_dAhat = np.zeros(prob.L, dtype=np.float64)
    dJ_dAhat[valid] = (2.0 / n_valid) * (diff[valid] / prob.L_km[valid])

    Rp_safe = np.maximum(Rp, 1e-12)
    dA_dR_nnz = ds * prob.k[li] * prob.alpha[li] * np.power(Rp_safe, prob.alpha[li] - 1.0)
    g_att = np.bincount(pix, weights=(dJ_dAhat[li] * dA_dR_nnz), minlength=prob.P).astype(np.float64)
    return J_att, g_att, A_hat


def _smooth1_term_and_grad(prob, R_flat: np.ndarray) -> Tuple[float, np.ndarray]:
    R = np.asarray(R_flat, dtype=np.float64).ravel()
    P = float(prob.P)
    du = R[prob.n_u] - R[prob.n_v]
    J = float(np.dot(du, du) / P)
    w = (2.0 / P) * du
    g = np.bincount(prob.n_u, weights=w, minlength=prob.P) - np.bincount(prob.n_v, weights=w, minlength=prob.P)
    return J, g.astype(np.float64)


def _smooth2_term_and_grad(triplets, P: int, R_flat: np.ndarray) -> Tuple[float, np.ndarray]:
    t_p, t_q, t_r = triplets
    R = np.asarray(R_flat, dtype=np.float64).ravel()
    if t_p.size == 0:
        return 0.0, np.zeros(P, dtype=np.float64)
    P_f = float(P)
    t = R[t_p] - 2.0 * R[t_q] + R[t_r]
    J = float(np.dot(t, t) / P_f)
    g = (
        np.bincount(t_p, weights=(2.0 / P_f) * t, minlength=P)
        + np.bincount(t_q, weights=(-4.0 / P_f) * t, minlength=P)
        + np.bincount(t_r, weights=(2.0 / P_f) * t, minlength=P)
    ).astype(np.float64)
    return J, g


def _total_term_and_grad(P: int, R_flat: np.ndarray) -> Tuple[float, np.ndarray]:
    R = np.asarray(R_flat, dtype=np.float64).ravel()
    P_f = float(P)
    J = float(np.dot(R, R) / P_f)
    g = (2.0 / P_f) * R
    return J, g


def _resolve_initial_field(
    est_input_json: str | Path,
    *,
    R0: float,
    R0_from_IDW: bool,
    R0_from_ILDW: bool,
    idw_r_max_m: float,
    idw_power: float,
    idw_eps_m: float,
    idw_default_value: float,
    P: int,
) -> Tuple[np.ndarray, str, np.ndarray, np.ndarray]:
    if idw_field_from_est_input is None:
        raise RuntimeError("idw_baseline.py is required for constrained AL solver (IDW baseline and threshold).")
    if ildw_field_from_est_input is None:
        raise RuntimeError("ildw_baseline.py is required for constrained AL solver (ILDW init and weight normalization).")

    idw_field, _ = idw_field_from_est_input(
        Path(est_input_json),
        r_max_m=float(idw_r_max_m),
        power=float(idw_power),
        eps_m=float(idw_eps_m),
        default_value=float(idw_default_value),
    )
    ildw_field, _ = ildw_field_from_est_input(
        Path(est_input_json),
        r_max_m=float(idw_r_max_m),
        power=float(idw_power),
        eps_m=float(idw_eps_m),
        default_value=float(idw_default_value),
    )

    if R0_from_IDW and R0_from_ILDW:
        raise ValueError("Choose exactly one of R0_from_ILDW or R0_from_IDW.")

    if R0_from_IDW:
        return np.asarray(idw_field, dtype=np.float64).reshape(P), "idw", np.asarray(idw_field, dtype=np.float64), np.asarray(ildw_field, dtype=np.float64)
    if R0_from_ILDW:
        return np.asarray(ildw_field, dtype=np.float64).reshape(P), "ildw", np.asarray(idw_field, dtype=np.float64), np.asarray(ildw_field, dtype=np.float64)
    return np.full(P, float(R0), dtype=np.float64), "constant", np.asarray(idw_field, dtype=np.float64), np.asarray(ildw_field, dtype=np.float64)


def solve_lbfgsb_and_save(
    est_input_json: str | Path,
    *,
    # compatibility args (ignored by this method unless noted)
    lam: float | None = None,
    mu: float | None = None,
    eps: float = 0.01,
    eta: float | None = None,
    j2_w: float | None = None,
    j3_w: float | None = None,
    j4_w: float | None = None,
    use_linear_j3: bool | None = None,
    # generic optimizer args
    R0: float = 0.0,
    maxiter: int = 300,
    ftol: float = 1e-8,
    gtol: float = 1e-7,
    maxls: int = 20,
    npz_out: str | Path = "solution.npz",
    warn: bool = True,
    R0_from_IDW: bool = False,
    R0_from_ILDW: bool = True,
    idw_r_max_m: float = 15000.0,
    idw_power: float = 2.0,
    idw_eps_m: float = 1.0,
    idw_default_value: float = 0.0,
    optinfo_out: str | Path | None = None,
    # constrained AL controls
    constraint_ratio: float = 0.1,
    constraint_tol: float = 1e-8,
    outer_maxiter: int = 8,
    rho_init: float = 10.0,
    rho_growth: float = 2.0,
    rho_max: float = 1.0e8,
    min_progress_ratio: float = 0.9,
    weight_floor: float = 1.0e-12,
    scale_1d: float = 1.0,
    scale_2d: float = 1.0,
    scale_total: float = 1.0,
    enforce_feasible_output: bool = True,
    fail_on_infeasible: bool = False,
) -> dict:
    prob = load_est_input_json(est_input_json, warn=warn)
    triplets = _collinear_triplets(prob.H, prob.W)

    x0, init_method, idw_field, ildw_field = _resolve_initial_field(
        est_input_json,
        R0=R0,
        R0_from_IDW=bool(R0_from_IDW),
        R0_from_ILDW=bool(R0_from_ILDW),
        idw_r_max_m=float(idw_r_max_m),
        idw_power=float(idw_power),
        idw_eps_m=float(idw_eps_m),
        idw_default_value=float(idw_default_value),
        P=prob.P,
    )

    idw_flat = idw_field.reshape(prob.P)
    ildw_flat = ildw_field.reshape(prob.P)

    Jatt_idw, _, _ = _atten_term_and_grad(prob, idw_flat)
    Jatt_ildw, _, _ = _atten_term_and_grad(prob, ildw_flat)

    tau = float(constraint_ratio) * float(Jatt_idw)
    c_ildw = float(Jatt_ildw - tau)
    Jatt_x0, _, _ = _atten_term_and_grad(prob, x0)
    c_x0 = float(Jatt_x0 - tau)

    J1d_ildw, _ = _smooth1_term_and_grad(prob, ildw_flat)
    J2d_ildw, _ = _smooth2_term_and_grad(triplets, prob.P, ildw_flat)
    Jt_ildw, _ = _total_term_and_grad(prob.P, ildw_flat)

    a1 = float(scale_1d) / max(float(J1d_ildw), float(weight_floor))
    a2 = 0.5 * float(scale_2d) / max(float(J2d_ildw), float(weight_floor))
    at = float(scale_total) / max(float(Jt_ildw), float(weight_floor))

    outer_history: List[Dict[str, Any]] = []
    iter_trace: List[Dict[str, Any]] = []
    f_history: List[float] = []
    x_cur = np.maximum(x0, 0.0)
    lam_k = 0.0
    rho_k = float(rho_init)

    final_res = None
    final_obj = np.nan
    final_constraint = np.nan
    best_feasible_x: np.ndarray | None = None
    best_feasible_c: float = np.inf
    best_feasible_obj: float = np.inf

    c_prev: float | None = None

    # Keep a feasible incumbent from the start if available.
    if c_x0 <= float(constraint_tol):
        best_feasible_x = np.asarray(x0, dtype=np.float64).ravel().copy()
        best_feasible_c = float(c_x0)
        J1d0, _ = _smooth1_term_and_grad(prob, best_feasible_x)
        J2d0, _ = _smooth2_term_and_grad(triplets, prob.P, best_feasible_x)
        Jt0, _ = _total_term_and_grad(prob.P, best_feasible_x)
        best_feasible_obj = float(a1 * J1d0 + a2 * J2d0 + at * Jt0)

    for outer_idx in range(int(max(1, outer_maxiter))):

        def al_fun_and_jac(x: np.ndarray) -> Tuple[float, np.ndarray]:
            x = np.asarray(x, dtype=np.float64).ravel()
            J1d, g1d = _smooth1_term_and_grad(prob, x)
            J2d, g2d = _smooth2_term_and_grad(triplets, prob.P, x)
            Jt, gt = _total_term_and_grad(prob.P, x)
            f_reg = a1 * J1d + a2 * J2d + at * Jt
            g_reg = a1 * g1d + a2 * g2d + at * gt

            Jatt, g_att, _ = _atten_term_and_grad(prob, x)
            c = float(Jatt - tau)
            viol = max(0.0, c)

            phi = f_reg + lam_k * viol + 0.5 * rho_k * (viol ** 2)
            if c > 0.0:
                g = g_reg + (lam_k + rho_k * c) * g_att
            else:
                g = g_reg
            return float(phi), np.asarray(g, dtype=np.float64)

        def _fun(x: np.ndarray) -> float:
            return al_fun_and_jac(x)[0]

        def _jac(x: np.ndarray) -> np.ndarray:
            return al_fun_and_jac(x)[1]

        inner_hist: List[float] = [float(_fun(x_cur))]

        def _cb(xk: np.ndarray):
            inner_hist.append(float(_fun(xk)))

        res = minimize(
            _fun,
            x_cur,
            method="L-BFGS-B",
            jac=_jac,
            callback=_cb,
            bounds=[(0.0, None)] * prob.P,
            options={
                "maxiter": int(maxiter),
                "ftol": float(ftol),
                "gtol": float(gtol),
                "maxls": int(maxls),
            },
        )

        x_cur = np.maximum(np.asarray(res.x, dtype=np.float64).ravel(), 0.0)
        final_res = res
        final_obj = float(res.fun)
        f_history.extend(inner_hist if len(inner_hist) >= 2 else [float(_fun(x_cur))])

        Jatt_cur, _, _ = _atten_term_and_grad(prob, x_cur)
        J1d_cur, _ = _smooth1_term_and_grad(prob, x_cur)
        J2d_cur, _ = _smooth2_term_and_grad(triplets, prob.P, x_cur)
        Jt_cur, _ = _total_term_and_grad(prob.P, x_cur)
        c_k = float(Jatt_cur - tau)
        final_constraint = c_k
        if c_k <= float(constraint_tol):
            if final_obj < best_feasible_obj:
                best_feasible_x = x_cur.copy()
                best_feasible_c = float(c_k)
                best_feasible_obj = float(final_obj)

        outer_history.append(
            {
                "outer_iter": int(outer_idx),
                "lambda": float(lam_k),
                "rho": float(rho_k),
                "Jatt": float(Jatt_cur),
                "tau": float(tau),
                "constraint_residual": float(c_k),
                "success_inner": bool(res.success),
                "status_inner": int(res.status),
                "nit_inner": int(getattr(res, "nit", -1)),
                "fun_inner": float(res.fun),
                "message_inner": str(res.message),
            }
        )
        iter_trace.append(
            {
                "iter": int(outer_idx + 1),
                "outer_iter": int(outer_idx),
                "feasible": bool(c_k <= float(constraint_tol)),
                "constraint_residual": float(c_k),
                "constraint_tol": float(constraint_tol),
                "J_atten": float(Jatt_cur),
                "J_1d": float(J1d_cur),
                "J_2d": float(J2d_cur),
                "J_total": float(Jt_cur),
                "w_1d": float(a1),
                "w_2d": float(a2),
                "w_total": float(at),
                "weighted_J_1d": float(a1 * J1d_cur),
                "weighted_J_2d": float(a2 * J2d_cur),
                "weighted_J_total": float(at * Jt_cur),
                "J_native_total": float(a1 * J1d_cur + a2 * J2d_cur + at * Jt_cur),
                "AL_fun_inner": float(res.fun),
                "success_inner": bool(res.success),
                "status_inner": int(res.status),
                "nit_inner": int(getattr(res, "nit", -1)),
                "message_inner": str(res.message),
            }
        )

        if c_k <= float(constraint_tol):
            break

        lam_k = max(0.0, lam_k + rho_k * c_k)
        if c_prev is not None and c_k > float(min_progress_ratio) * c_prev:
            rho_k = min(float(rho_max), float(rho_growth) * rho_k)
        c_prev = c_k

    if final_res is None:
        raise RuntimeError("AL outer loop did not execute.")

    fallback_used = False
    fallback_source = "none"
    if final_constraint > float(constraint_tol):
        if bool(enforce_feasible_output):
            if best_feasible_x is not None and np.isfinite(best_feasible_c):
                x_cur = np.asarray(best_feasible_x, dtype=np.float64).ravel()
                final_constraint = float(best_feasible_c)
                fallback_used = True
                fallback_source = "best_feasible"
            elif c_ildw <= float(constraint_tol):
                x_cur = np.asarray(ildw_flat, dtype=np.float64).ravel()
                final_constraint = float(c_ildw)
                fallback_used = True
                fallback_source = "ildw"
            elif c_x0 <= float(constraint_tol):
                x_cur = np.asarray(x0, dtype=np.float64).ravel()
                final_constraint = float(c_x0)
                fallback_used = True
                fallback_source = "x0"
        if final_constraint > float(constraint_tol) and bool(fail_on_infeasible):
            raise RuntimeError(
                f"Final solution infeasible: c={final_constraint:.6e} > tol={float(constraint_tol):.6e}"
            )

    R_hat = x_cur.reshape(prob.H, prob.W).astype(np.float32)
    A_hat, r = forward_Ahat_and_r(prob, x_cur)

    npz_out = Path(npz_out)
    npz_out.parent.mkdir(parents=True, exist_ok=True)
    if optinfo_out is None:
        optinfo_path = npz_out.with_name(f"{npz_out.stem}_optinfo.json")
    else:
        optinfo_path = Path(optinfo_out)

    opt_diag = _write_opt_diagnostics(
        optinfo_path,
        res=final_res,
        x_star=x_cur,
        jac_fn=lambda x: _smooth1_term_and_grad(prob, x)[1],
        f_history=f_history if len(f_history) >= 2 else [float(final_obj), float(final_obj)],
        maxiter=maxiter,
        ftol=ftol,
        gtol=gtol,
        maxls=maxls,
    )

    alinfo_path = npz_out.with_name(f"{npz_out.stem}_alinfo.json")
    alinfo_path.write_text(json.dumps(outer_history, indent=2), encoding="utf-8")
    feasible_count = int(sum(1 for it in iter_trace if bool(it.get("feasible", False))))
    infeasible_count = int(len(iter_trace) - feasible_count)
    if iter_trace:
        best_idx = int(np.argmin([float(it.get("J_native_total", np.inf)) for it in iter_trace]))
        best_iter = int(iter_trace[best_idx]["iter"])
        best_obj = float(iter_trace[best_idx]["J_native_total"])
    else:
        best_iter = -1
        best_obj = float("nan")
    itertrace_path = npz_out.with_name(f"{npz_out.stem}_itertrace.json")
    itertrace_payload = {
        "summary": {
            "solver": "constrained_augmented_lagrangian",
            "total_iterations": int(len(iter_trace)),
            "feasible_iterations": int(feasible_count),
            "infeasible_iterations": int(infeasible_count),
            "best_iteration_by_native_total": int(best_iter),
            "best_native_total": float(best_obj),
        },
        "iterations": iter_trace,
    }
    itertrace_path.write_text(json.dumps(itertrace_payload, indent=2), encoding="utf-8")

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
        # convergence
        meta_success=bool(final_res.success),
        meta_status=int(final_res.status),
        meta_message=str(final_res.message),
        meta_nit=int(getattr(final_res, "nit", -1)),
        meta_fun=float(final_obj),
        # dimensions
        meta_H=int(prob.H),
        meta_W=int(prob.W),
        meta_L=int(prob.L),
        meta_P=int(prob.P),
        meta_nnz=int(prob.pix_idx.size),
        # solver method & config
        meta_method="constrained_augmented_lagrangian",
        meta_constraint_ratio=float(constraint_ratio),
        meta_constraint_tau=float(tau),
        meta_constraint_residual=float(final_constraint),
        meta_constraint_tol=float(constraint_tol),
        meta_constraint_feasible=bool(final_constraint <= float(constraint_tol)),
        meta_enforce_feasible_output=bool(enforce_feasible_output),
        meta_fail_on_infeasible=bool(fail_on_infeasible),
        meta_fallback_used=bool(fallback_used),
        meta_fallback_source=str(fallback_source),
        meta_outer_maxiter=int(outer_maxiter),
        meta_outer_iters_done=int(len(outer_history)),
        meta_rho_init=float(rho_init),
        meta_rho_final=float(rho_k),
        meta_lambda_final=float(lam_k),
        meta_rho_growth=float(rho_growth),
        meta_rho_max=float(rho_max),
        meta_min_progress_ratio=float(min_progress_ratio),
        meta_alphas_1d=float(a1),
        meta_alphas_2d=float(a2),
        meta_alphas_total=float(at),
        meta_scale_1d=float(scale_1d),
        meta_scale_2d=float(scale_2d),
        meta_scale_total=float(scale_total),
        meta_Jatt_IDW=float(Jatt_idw),
        meta_Jatt_ILDW=float(Jatt_ildw),
        meta_J1d_ILDW=float(J1d_ildw),
        meta_J2d_ILDW=float(J2d_ildw),
        meta_Jtotal_ILDW=float(Jt_ildw),
        meta_eps=float(eps),
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
        meta_alinfo_json=str(alinfo_path),
        meta_itertrace_json=str(itertrace_path),
        meta_feasible_outer_iters=int(feasible_count),
        meta_infeasible_outer_iters=int(infeasible_count),
        meta_best_outer_iter_by_native_total=int(best_iter),
    )

    return {
        "success": bool(final_res.success),
        "status": int(final_res.status),
        "message": str(final_res.message),
        "nit": int(getattr(final_res, "nit", -1)),
        "fun": float(final_obj),
        "constraint_residual": float(final_constraint),
        "constraint_feasible": bool(final_constraint <= float(constraint_tol)),
        "fallback_used": bool(fallback_used),
        "fallback_source": str(fallback_source),
        "out_npz": str(npz_out),
        "optinfo_json": str(optinfo_path),
        "alinfo_json": str(alinfo_path),
        "itertrace_json": str(itertrace_path),
        "init_method": str(init_method),
    }


def solve_and_save(est_input_json: str | Path, out_npz: str | Path, cfg: dict) -> dict:
    opt = cfg.get("optimization", {}) or {}
    tol = cfg.get("tolerances", {}) or {}
    idw = cfg.get("idw", {}) or {}
    al = cfg.get("augmented_lagrangian", {}) or {}

    return solve_lbfgsb_and_save(
        est_input_json,
        R0=float(opt.get("R0", 0.0)),
        maxiter=int(opt.get("maxiter", 300)),
        ftol=float(tol.get("ftol", 1e-8)),
        gtol=float(tol.get("gtol", 1e-7)),
        maxls=int(tol.get("maxls", 20)),
        npz_out=out_npz,
        warn=bool(cfg.get("warn", True)),
        R0_from_IDW=bool(opt.get("R0_from_IDW", False)),
        R0_from_ILDW=bool(opt.get("R0_from_ILDW", True)),
        idw_r_max_m=float(idw.get("r_max_m", 15000.0)),
        idw_power=float(idw.get("power", 2.0)),
        idw_eps_m=float(idw.get("eps_m", 1.0)),
        idw_default_value=float(idw.get("default_value", 0.0)),
        constraint_ratio=float(al.get("constraint_ratio", 0.1)),
        constraint_tol=float(al.get("constraint_tol", 1e-8)),
        outer_maxiter=int(al.get("outer_maxiter", 8)),
        rho_init=float(al.get("rho_init", 10.0)),
        rho_growth=float(al.get("rho_growth", 2.0)),
        rho_max=float(al.get("rho_max", 1.0e8)),
        min_progress_ratio=float(al.get("min_progress_ratio", 0.9)),
        weight_floor=float(al.get("weight_floor", 1.0e-12)),
        scale_1d=float(al.get("scale_1d", 1.0)),
        scale_2d=float(al.get("scale_2d", 1.0)),
        scale_total=float(al.get("scale_total", 1.0)),
        enforce_feasible_output=bool(al.get("enforce_feasible_output", True)),
        fail_on_infeasible=bool(al.get("fail_on_infeasible", False)),
    )
