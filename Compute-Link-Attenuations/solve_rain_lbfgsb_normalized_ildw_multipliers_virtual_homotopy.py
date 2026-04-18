#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize

from solve_rain_lbfgsb import _write_opt_diagnostics, forward_Ahat_and_r, load_est_input_json
from solve_rain_lbfgsb_normalized_ildw_multipliers import (
    _build_collinear_triplets,
    _compute_instance_multipliers,
    _compute_terms_and_grads,
    make_objective,
)
from solve_rain_lbfgsb_normalized_ildw_multipliers_virtual_convex import _build_initial_guess
from virtual_link_utils import compute_link_rain_equivalent, make_beta_problem, make_virtual_problem

try:
    from ildw_baseline import ildw_field_from_est_input  # type: ignore
except Exception:
    ildw_field_from_est_input = None  # type: ignore


def _beta_schedule(delta: float) -> List[float]:
    delta = float(delta)
    if delta <= 0.0:
        raise ValueError("beta_delta must be positive.")
    betas: List[float] = []
    beta = 0.0
    while beta < 1.0:
        betas.append(float(beta))
        beta += delta
    if not betas or betas[-1] != 1.0:
        betas.append(1.0)
    return betas


def _virtual_freq_summary(value: Any) -> Dict[str, Any]:
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim == 0 or arr.size == 1:
        val = float(arr.reshape(()))
        return {
            "virtual_freq_ghz": val,
            "virtual_freq_ghz_min": val,
            "virtual_freq_ghz_max": val,
        }
    return {
        "virtual_freq_ghz_min": float(np.min(arr)),
        "virtual_freq_ghz_max": float(np.max(arr)),
    }


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
    virtual_freq_ghz: float | None = None,
    beta_delta: float = 0.1,
) -> Dict[str, Any]:
    _ = lam
    _ = mu
    _ = eta
    _ = float(eps)
    _ = bool(use_linear_j3)

    prob_real = load_est_input_json(est_input_json, warn=warn)
    t_p, t_q, t_r = _build_collinear_triplets(prob_real.H, prob_real.W)
    link_rain_equiv = compute_link_rain_equivalent(prob_real)
    prob_virtual, virtual_info = make_virtual_problem(
        prob_real,
        virtual_freq_ghz=(None if virtual_freq_ghz is None else float(virtual_freq_ghz)),
        link_rain_equivalent=link_rain_equiv,
    )

    if ildw_field_from_est_input is None:
        raise RuntimeError("ILDW baseline is required for per-instance alpha scaling but ildw_baseline.py is unavailable.")
    R_ildw_grid, _ = ildw_field_from_est_input(
        Path(est_input_json),
        r_max_m=float(idw_r_max_m),
        power=float(idw_power),
        eps_m=float(idw_eps_m),
        default_value=float(idw_default_value),
    )
    R_ildw_flat = np.asarray(R_ildw_grid, dtype=np.float64).reshape(prob_real.P)

    x_cur, init_method, effective_r0 = _build_initial_guess(
        est_input_json,
        prob_real,
        R0=float(R0),
        R0_from_IDW=bool(R0_from_IDW),
        R0_from_ILDW=bool(R0_from_ILDW),
        rain_init_mode=str(rain_init_mode),
        rain_init_value=rain_init_value,
        rain_init_multiplier=float(rain_init_multiplier),
        idw_r_max_m=float(idw_r_max_m),
        idw_power=float(idw_power),
        idw_eps_m=float(idw_eps_m),
        idw_default_value=float(idw_default_value),
        ildw_flat=R_ildw_flat,
    )

    iter_trace: List[Dict[str, Any]] = []
    f_history: List[float] = []
    global_iter = 0
    stage_summaries: List[Dict[str, Any]] = []
    betas = _beta_schedule(float(beta_delta))
    last_res = None
    last_jac = None
    last_fun = None
    last_mult: Dict[str, float] | None = None
    last_prob = prob_real

    def _trace_row(prob_stage, mult: Dict[str, float], xk: np.ndarray, *, iteration: int, stage: int, beta: float) -> Dict[str, Any]:
        Rk = np.asarray(xk, dtype=np.float64).ravel()
        Jb_atten, Jb_1d, Jb_2d, Jb_total, _, _, _, _ = _compute_terms_and_grads(
            prob_stage, Rk, t_p=t_p, t_q=t_q, t_r=t_r
        )
        Jr_atten, _, _, _, _, _, _, _ = _compute_terms_and_grads(
            prob_real, Rk, t_p=t_p, t_q=t_q, t_r=t_r
        )
        w_atten = float(mult["alpha_atten"]) * float(Jb_atten)
        w_1d = float(mult["alpha_1d"]) * float(Jb_1d)
        w_2d = float(mult["alpha_2d"]) * float(Jb_2d)
        w_total = float(mult["alpha_total"]) * float(Jb_total)
        return {
            "iter": int(iteration),
            "stage": int(stage),
            "beta": float(beta),
            "feasible": True,
            "constraint_residual": 0.0,
            "J_weighted_sum": float(w_atten + w_1d + w_2d + w_total),
            "J_atten": float(Jb_atten),
            "J_atten_beta": float(Jb_atten),
            "J_atten_real": float(Jr_atten),
            "J_1d": float(Jb_1d),
            "J_2d": float(Jb_2d),
            "J_total": float(Jb_total),
            "weighted_J_atten": float(w_atten),
            "weighted_J_1d": float(w_1d),
            "weighted_J_2d": float(w_2d),
            "weighted_J_total": float(w_total),
            "alpha_atten": float(mult["alpha_atten"]),
            "alpha_1d": float(mult["alpha_1d"]),
            "alpha_2d": float(mult["alpha_2d"]),
            "alpha_total": float(mult["alpha_total"]),
            "attenuation_model_domain": "beta_stage",
        }

    for stage_idx, beta in enumerate(betas):
        prob_beta, _ = make_beta_problem(
            prob_real,
            beta=float(beta),
            virtual_freq_ghz=(None if virtual_freq_ghz is None else float(virtual_freq_ghz)),
            link_rain_equivalent=link_rain_equiv,
        )
        mult = _compute_instance_multipliers(
            prob_beta,
            R_ildw_flat=R_ildw_flat,
            t_p=t_p,
            t_q=t_q,
            t_r=t_r,
            num_atten=float(num_atten),
            num_1d=float(num_1d),
            num_2d=float(num_2d),
            num_total=float(num_total),
        )
        fun, jac = make_objective(
            prob_beta,
            alpha_atten=float(mult["alpha_atten"]),
            alpha_1d=float(mult["alpha_1d"]),
            alpha_2d=float(mult["alpha_2d"]),
            alpha_total=float(mult["alpha_total"]),
            t_p=t_p,
            t_q=t_q,
            t_r=t_r,
        )

        if stage_idx == 0:
            row0 = _trace_row(prob_beta, mult, x_cur, iteration=0, stage=stage_idx, beta=float(beta))
            iter_trace.append(row0)
            f_history.append(float(row0["J_weighted_sum"]))

        stage_local_iter = 0

        def _callback(xk: np.ndarray):
            nonlocal global_iter, stage_local_iter
            stage_local_iter += 1
            global_iter += 1
            row = _trace_row(prob_beta, mult, xk, iteration=global_iter, stage=stage_idx, beta=float(beta))
            iter_trace.append(row)
            f_history.append(float(row["J_weighted_sum"]))

        res = minimize(
            fun,
            x_cur,
            method="L-BFGS-B",
            jac=jac,
            callback=_callback,
            bounds=[(0.0, None)] * prob_real.P,
            options={
                "maxiter": int(maxiter),
                "ftol": float(ftol),
                "gtol": float(gtol),
                "maxls": int(maxls),
            },
        )
        x_cur = np.asarray(res.x, dtype=np.float64).ravel()
        if stage_local_iter == 0 or not iter_trace or int(iter_trace[-1].get("stage", -1)) != stage_idx:
            global_iter += 1
            row = _trace_row(prob_beta, mult, x_cur, iteration=global_iter, stage=stage_idx, beta=float(beta))
            iter_trace.append(row)
            f_history.append(float(row["J_weighted_sum"]))

        stage_summaries.append(
            {
                "stage": int(stage_idx),
                "beta": float(beta),
                "success": bool(res.success),
                "status": int(res.status),
                "message": str(res.message),
                "nit": int(getattr(res, "nit", -1)),
                "fun": float(res.fun),
                "alpha_atten": float(mult["alpha_atten"]),
                "alpha_1d": float(mult["alpha_1d"]),
                "alpha_2d": float(mult["alpha_2d"]),
                "alpha_total": float(mult["alpha_total"]),
            }
        )
        last_res = res
        last_jac = jac
        last_fun = fun
        last_mult = mult
        last_prob = prob_beta

    if last_res is None or last_jac is None or last_fun is None or last_mult is None:
        raise RuntimeError("Homotopy solver did not execute any stages.")

    r_hat = x_cur.reshape(prob_real.H, prob_real.W).astype(np.float32)
    a_hat_real, r_real = forward_Ahat_and_r(prob_real, x_cur)
    a_hat_virtual, r_virtual = forward_Ahat_and_r(prob_virtual, x_cur)

    npz_out = Path(npz_out)
    npz_out.parent.mkdir(parents=True, exist_ok=True)
    optinfo_path = (
        npz_out.with_name(f"{npz_out.stem}_optinfo.json")
        if optinfo_out is None
        else Path(optinfo_out)
    )
    opt_diag = _write_opt_diagnostics(
        optinfo_path,
        res=last_res,
        x_star=x_cur,
        jac_fn=last_jac,
        f_history=f_history if len(f_history) >= 2 else [float(last_fun(x_cur)), float(last_res.fun)],
        maxiter=maxiter,
        ftol=ftol,
        gtol=gtol,
        maxls=maxls,
    )

    feasible_count = int(sum(1 for it in iter_trace if bool(it.get("feasible", False))))
    infeasible_count = int(len(iter_trace) - feasible_count)
    best_idx = int(np.argmin([float(it.get("J_weighted_sum", np.inf)) for it in iter_trace]))
    best_iter = int(iter_trace[best_idx].get("iter", -1))
    best_obj = float(iter_trace[best_idx].get("J_weighted_sum", np.nan))
    stage_iteration_counts = [int(max(0, s.get("nit", 0))) for s in stage_summaries]
    total_inner_iterations = int(sum(stage_iteration_counts))
    outer_iterations = int(len(stage_summaries))
    final_stage_iterations = int(stage_iteration_counts[-1]) if stage_iteration_counts else 0
    itertrace_path = npz_out.with_name(f"{npz_out.stem}_itertrace.json")
    freq_summary = _virtual_freq_summary(virtual_info["virtual_freq_ghz"])
    itertrace_payload = {
        "summary": {
            "solver": "lbfgsb_normalized_ildw_multipliers_virtual_homotopy",
            "total_iterations": int(len(iter_trace)),
            "feasible_iterations": int(feasible_count),
            "infeasible_iterations": int(infeasible_count),
            "best_iteration_by_weighted_sum": int(best_iter),
            "best_weighted_sum": float(best_obj),
            **freq_summary,
            "beta_delta": float(beta_delta),
            "n_stages": int(len(stage_summaries)),
            "outer_iterations": outer_iterations,
            "total_inner_iterations": total_inner_iterations,
            "final_stage_iterations": final_stage_iterations,
            "stage_iteration_counts": stage_iteration_counts,
            "init_method": str(init_method),
        },
        "stages": stage_summaries,
        "iterations": iter_trace,
    }
    itertrace_path.write_text(json.dumps(itertrace_payload, indent=2), encoding="utf-8")

    opt_diag.update(
        {
            "outer_iterations": outer_iterations,
            "total_inner_iterations": total_inner_iterations,
            "final_stage_iterations": final_stage_iterations,
            "stage_iteration_counts": stage_iteration_counts,
            "iteration": total_inner_iterations,
            "nit": total_inner_iterations,
            "init_method": str(init_method),
        }
    )
    optinfo_path.write_text(json.dumps(opt_diag, indent=2), encoding="utf-8")

    np.savez(
        npz_out,
        R_hat=r_hat,
        A_hat=a_hat_real.astype(np.float64),
        A_obs=prob_real.A_obs.astype(np.float64),
        r=r_real.astype(np.float64),
        valid_links=prob_real.valid_links.astype(bool),
        L_km=prob_real.L_km.astype(np.float64),
        freq_ghz=prob_real.freq_ghz.astype(np.float64),
        pol=np.array(prob_real.pol, dtype="U1"),
        k=prob_real.k.astype(np.float64),
        alpha=prob_real.alpha.astype(np.float64),
        A_hat_virtual=a_hat_virtual.astype(np.float64),
        A_obs_virtual=prob_virtual.A_obs.astype(np.float64),
        r_virtual=r_virtual.astype(np.float64),
        valid_links_virtual=prob_virtual.valid_links.astype(bool),
        L_km_virtual=prob_virtual.L_km.astype(np.float64),
        freq_ghz_virtual=prob_virtual.freq_ghz.astype(np.float64),
        k_virtual=prob_virtual.k.astype(np.float64),
        alpha_virtual=prob_virtual.alpha.astype(np.float64),
        link_rain_equivalent=virtual_info["link_rain_equivalent"].astype(np.float64),
        beta_schedule=np.asarray(betas, dtype=np.float64),
        meta_success=bool(last_res.success),
        meta_status=int(last_res.status),
        meta_message=str(last_res.message),
        meta_nit=int(total_inner_iterations),
        meta_nit_last_stage=int(getattr(last_res, "nit", -1)),
        meta_fun=float(last_res.fun),
        meta_H=int(prob_real.H),
        meta_W=int(prob_real.W),
        meta_L=int(prob_real.L),
        meta_P=int(prob_real.P),
        meta_nnz=int(prob_real.pix_idx.size),
        meta_eps=float(eps),
        meta_use_linear_j3=True,
        meta_J_atten_ildw=float(last_mult["J_atten_ildw"]),
        meta_J_1d_ildw=float(last_mult["J_1d_ildw"]),
        meta_J_2d_ildw=float(last_mult["J_2d_ildw"]),
        meta_J_total_ildw=float(last_mult["J_total_ildw"]),
        meta_beta_atten=float(last_mult["beta_atten"]),
        meta_beta_1d=float(last_mult["beta_1d"]),
        meta_beta_2d=float(last_mult["beta_2d"]),
        meta_beta_total=float(last_mult["beta_total"]),
        meta_num_atten=float(last_mult["num_atten"]),
        meta_num_1d=float(last_mult["num_1d"]),
        meta_num_2d=float(last_mult["num_2d"]),
        meta_num_total=float(last_mult["num_total"]),
        meta_alpha_atten=float(last_mult["alpha_atten"]),
        meta_alpha_1d=float(last_mult["alpha_1d"]),
        meta_alpha_2d=float(last_mult["alpha_2d"]),
        meta_alpha_total=float(last_mult["alpha_total"]),
        meta_R0=float(effective_r0),
        meta_rain_init_mode=str(rain_init_mode),
        meta_rain_init_value=float(rain_init_value if rain_init_value is not None else R0),
        meta_rain_init_multiplier=float(rain_init_multiplier),
        meta_maxiter=int(maxiter),
        meta_ftol=float(ftol),
        meta_gtol=float(gtol),
        meta_maxls=int(maxls),
        meta_est_input_json=str(Path(est_input_json)),
        meta_num_valid_links=int(np.sum(prob_real.valid_links)),
        meta_num_invalid_links=int(np.sum(~prob_real.valid_links)),
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
        meta_itertrace_json=str(itertrace_path),
        meta_virtual_link_mode="beta_homotopy",
        meta_virtual_freq_ghz=(
            float(virtual_freq_ghz)
            if virtual_freq_ghz is not None
            else np.nan
        ),
        meta_virtual_freq_auto_alpha1=(virtual_freq_ghz is None),
        meta_beta_delta=float(beta_delta),
        meta_num_beta_stages=int(len(stage_summaries)),
        meta_outer_iterations=int(outer_iterations),
        meta_total_inner_iterations=int(total_inner_iterations),
        meta_final_stage_iterations=int(final_stage_iterations),
        meta_attenuation_fit_primary_domain="real",
    )

    return {
        "success": bool(last_res.success),
        "status": int(last_res.status),
        "message": str(last_res.message),
        "nit": int(getattr(last_res, "nit", -1)),
        "fun": float(last_res.fun),
        "out_npz": str(npz_out),
        "optinfo_json": str(optinfo_path),
        "itertrace_json": str(itertrace_path),
        "init_method": str(init_method),
    }
