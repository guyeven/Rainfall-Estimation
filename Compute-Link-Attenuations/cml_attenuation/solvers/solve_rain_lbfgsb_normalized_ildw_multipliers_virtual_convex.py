#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize

from cml_attenuation.solvers.solve_rain_lbfgsb import _write_opt_diagnostics, forward_Ahat_and_r, load_est_input_json
from cml_attenuation.solvers.solve_rain_lbfgsb_normalized_ildw_multipliers import (
    _build_collinear_triplets,
    _compute_instance_multipliers,
    _compute_terms_and_grads,
    make_objective,
)
from cml_attenuation.virtual_link_utils import make_virtual_problem

try:
    from cml_attenuation.idw_baseline import idw_field_from_est_input  # type: ignore
except Exception:
    idw_field_from_est_input = None  # type: ignore

try:
    from cml_attenuation.ildw_baseline import ildw_field_from_est_input  # type: ignore
except Exception:
    ildw_field_from_est_input = None  # type: ignore


def _build_initial_guess(
    est_input_json: str | Path,
    prob,
    *,
    R0: float,
    R0_from_IDW: bool,
    R0_from_ILDW: bool,
    rain_init_mode: str,
    rain_init_value: float | None,
    rain_init_multiplier: float,
    idw_r_max_m: float,
    idw_power: float,
    idw_eps_m: float,
    idw_default_value: float,
    ildw_flat: np.ndarray,
) -> Tuple[np.ndarray, str, float]:
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
        x0 = ildw_flat.copy()
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
    return x0, init_method, effective_r0


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
    num_total_divide_by_num_pixels: bool = False,
    virtual_freq_ghz: float | None = None,
) -> Dict[str, Any]:
    _ = lam
    _ = mu
    _ = eta
    _ = float(eps)
    _ = bool(use_linear_j3)

    prob_real = load_est_input_json(est_input_json, warn=warn)
    t_p, t_q, t_r = _build_collinear_triplets(prob_real.H, prob_real.W)
    prob_virtual, virtual_info = make_virtual_problem(
        prob_real,
        virtual_freq_ghz=(None if virtual_freq_ghz is None else float(virtual_freq_ghz)),
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
    mult = _compute_instance_multipliers(
        prob_virtual,
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
        prob_virtual,
        alpha_atten=float(mult["alpha_atten"]),
        alpha_1d=float(mult["alpha_1d"]),
        alpha_2d=float(mult["alpha_2d"]),
        alpha_total=float(mult["alpha_total"]),
        t_p=t_p,
        t_q=t_q,
        t_r=t_r,
    )

    x0, init_method, effective_r0 = _build_initial_guess(
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

    a_att = float(mult["alpha_atten"])
    a_1d = float(mult["alpha_1d"])
    a_2d = float(mult["alpha_2d"])
    a_tot = float(mult["alpha_total"])

    def _trace_row(xk: np.ndarray, *, iteration: int) -> Dict[str, Any]:
        Rk = np.asarray(xk, dtype=np.float64).ravel()
        Jv_atten, Jv_1d, Jv_2d, Jv_total, _, _, _, _ = _compute_terms_and_grads(
            prob_virtual, Rk, t_p=t_p, t_q=t_q, t_r=t_r
        )
        Jr_atten, _, _, _, _, _, _, _ = _compute_terms_and_grads(
            prob_real, Rk, t_p=t_p, t_q=t_q, t_r=t_r
        )
        w_atten = a_att * float(Jv_atten)
        w_1d = a_1d * float(Jv_1d)
        w_2d = a_2d * float(Jv_2d)
        w_total = a_tot * float(Jv_total)
        return {
            "iter": int(iteration),
            "feasible": True,
            "constraint_residual": 0.0,
            "J_weighted_sum": float(w_atten + w_1d + w_2d + w_total),
            "J_atten": float(Jv_atten),
            "J_atten_virtual": float(Jv_atten),
            "J_atten_real": float(Jr_atten),
            "J_1d": float(Jv_1d),
            "J_2d": float(Jv_2d),
            "J_total": float(Jv_total),
            "weighted_J_atten": float(w_atten),
            "weighted_J_1d": float(w_1d),
            "weighted_J_2d": float(w_2d),
            "weighted_J_total": float(w_total),
            "alpha_atten": float(a_att),
            "alpha_1d": float(a_1d),
            "alpha_2d": float(a_2d),
            "alpha_total": float(a_tot),
            "attenuation_model_domain": "virtual",
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

    optimizer_started = time.perf_counter()
    res = minimize(
        fun,
        x0,
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
    optimizer_seconds = time.perf_counter() - optimizer_started

    r_hat = res.x.reshape(prob_real.H, prob_real.W).astype(np.float32)
    a_hat_real, r_real = forward_Ahat_and_r(prob_real, res.x)
    a_hat_virtual, r_virtual = forward_Ahat_and_r(prob_virtual, res.x)

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
    opt_diag["optimizer_seconds"] = float(optimizer_seconds)
    optinfo_path.write_text(json.dumps(opt_diag, indent=2), encoding="utf-8")

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
    freq_summary = _virtual_freq_summary(virtual_info["virtual_freq_ghz"])
    itertrace_payload = {
        "summary": {
            "solver": "lbfgsb_normalized_ildw_multipliers_virtual_convex",
            "total_iterations": int(len(iter_trace)),
            "feasible_iterations": int(feasible_count),
            "infeasible_iterations": int(infeasible_count),
            "best_iteration_by_weighted_sum": int(best_iter),
            "best_weighted_sum": float(best_obj),
            **freq_summary,
        },
        "iterations": iter_trace,
    }
    itertrace_path.write_text(json.dumps(itertrace_payload, indent=2), encoding="utf-8")

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
        meta_success=bool(res.success),
        meta_status=int(res.status),
        meta_message=str(res.message),
        meta_nit=int(getattr(res, "nit", -1)),
        meta_fun=float(res.fun),
        meta_optimizer_seconds=float(optimizer_seconds),
        meta_H=int(prob_real.H),
        meta_W=int(prob_real.W),
        meta_L=int(prob_real.L),
        meta_P=int(prob_real.P),
        meta_nnz=int(prob_real.pix_idx.size),
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
        meta_virtual_link_mode="fixed_virtual_frequency",
        meta_virtual_freq_ghz=(
            float(virtual_freq_ghz)
            if virtual_freq_ghz is not None
            else np.nan
        ),
        meta_virtual_freq_auto_alpha1=(virtual_freq_ghz is None),
        meta_attenuation_fit_primary_domain="virtual",
    )

    return {
        "success": bool(res.success),
        "status": int(res.status),
        "message": str(res.message),
        "nit": int(getattr(res, "nit", -1)),
        "fun": float(res.fun),
        "nfev": int(getattr(res, "nfev", -1)),
        "njev": int(getattr(res, "njev", -1)),
        "stop_reason": str(opt_diag.get("stop_reason", "other")),
        "optimizer_seconds": float(optimizer_seconds),
        "H": int(prob_real.H),
        "W": int(prob_real.W),
        "num_pixels": int(prob_real.P),
        "num_links": int(prob_real.L),
        "num_valid_links": int(np.sum(prob_real.valid_links)),
        "out_npz": str(npz_out),
        "optinfo_json": str(optinfo_path),
        "itertrace_json": str(itertrace_path),
        "init_method": str(init_method),
    }
