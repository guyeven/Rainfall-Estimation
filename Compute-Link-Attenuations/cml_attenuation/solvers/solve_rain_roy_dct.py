"""Roy et al. (2016), Eq. (26), and an explicitly nonlinear extension.

min_{u >= 0} ||y - F(u)||^2 / noise_variance + lam * ||D u||_1

D is an orthonormal DCT analysis operator (Psi = D.T). No dense basis,
Phi @ Psi, pixel Hessian, or covariance matrix is constructed. Convex
linearized subproblems use ADMM with matrix-free preconditioned CG.
"""
from __future__ import annotations

import json
import hashlib
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.fft import dct, dctn, idct, idctn
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import LinearOperator, cg

from .solve_rain_lbfgsb import load_est_input_json


def _atomic_savez_compressed(path: Path, **arrays: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp_npz = Path(str(tmp) + ".npz")
    try:
        np.savez_compressed(tmp, **arrays)
        os.replace(tmp_npz, path)
    finally:
        tmp_npz.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class DCTBasis:
    """Orthonormal DCT-II analysis and its inverse; row-major pixel layout."""

    def __init__(self, shape: tuple[int, int], layout: str = "2d"):
        if len(shape) != 2 or any(int(n) != n or n <= 0 for n in shape):
            raise ValueError("shape must contain two positive integers")
        if layout not in {"1d", "2d"}:
            raise ValueError("dct_layout must be '1d' or '2d'")
        self.shape = tuple(map(int, shape))
        self.layout = layout
        self.size = int(np.prod(self.shape))

    def analysis(self, u: np.ndarray) -> np.ndarray:
        if self.layout == "1d":
            return dct(np.asarray(u).reshape(self.size), type=2, norm="ortho")
        return dctn(np.asarray(u).reshape(self.shape), type=2, norm="ortho").ravel()

    def synthesis(self, z: np.ndarray) -> np.ndarray:
        if self.layout == "1d":
            return idct(np.asarray(z).reshape(self.size), type=2, norm="ortho")
        return idctn(np.asarray(z).reshape(self.shape), type=2, norm="ortho").ravel()


class LinkModel:
    """F_i(u) = k_i sum_j length_ij * u_j ** alpha_i."""

    def __init__(self, lengths, k=1.0, alpha=1.0):
        self.lengths = csr_matrix(lengths, dtype=np.float64, copy=True)
        self.lengths.sum_duplicates()
        self.lengths.eliminate_zeros()
        if not np.all(np.isfinite(self.lengths.data)) or np.any(self.lengths.data < 0):
            raise ValueError("link lengths must be finite and nonnegative")
        m, self.size = self.lengths.shape
        self.k = np.broadcast_to(np.asarray(k, dtype=float), (m,)).copy()
        self.alpha = np.broadcast_to(np.asarray(alpha, dtype=float), (m,)).copy()
        if any(not np.all(np.isfinite(a)) or np.any(a <= 0) for a in (self.k, self.alpha)):
            raise ValueError("k and alpha must be finite and positive")
        coo = self.lengths.tocoo()
        self.rows, self.cols = coo.row, coo.col
        self.weights = coo.data * self.k[self.rows]
        self.exponents = self.alpha[self.rows]
        self.linear = bool(np.all(self.alpha == 1.0))

    def forward(self, u: np.ndarray) -> np.ndarray:
        return np.bincount(
            self.rows, weights=self.weights * np.power(u[self.cols], self.exponents),
            minlength=self.lengths.shape[0],
        )

    def jacobian(self, u: np.ndarray, derivative_floor: float) -> csr_matrix:
        # alpha < 1 has an infinite derivative at zero. Only derivative evaluation
        # uses this floor; forward predictions and the objective use unmodified u.
        values = self.weights * self.exponents * np.power(
            np.maximum(u[self.cols], derivative_floor), self.exponents - 1.0
        )
        return csr_matrix((values, (self.rows, self.cols)), shape=self.lengths.shape)


def _positive(name: str, value: float, *, zero: bool = False) -> float:
    value = float(value)
    if not np.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}")
    return value


def _integer(name: str, value: int) -> int:
    if int(value) != value or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def solve_convex_subproblem(
    jac: csr_matrix, target: np.ndarray, basis: DCTBasis, *, beta: float,
    anchor: np.ndarray, damping: float = 0.0, rho: float = 1.0,
    maxiter: int = 2000, atol: float = 1e-6, rtol: float = 1e-5,
    cg_rtol: float = 1e-8, cg_maxiter: int = 500,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve .5||J u-target||² + beta||D u||1 + .5*damping||u-anchor||².

    Split z=D u and v=u, with v>=0. CG uses J.T@(J@x), never J.T@J.
    Return feasible v, and report ADMM primal/dual residuals. A stopped CG
    or iteration limit is explicitly not reported as convergence.
    """
    n = basis.size
    x = anchor.copy()
    v = np.maximum(x, 0.0)
    z = basis.analysis(x)
    dz, dv = np.zeros(n), np.zeros(n)
    jt_target = np.asarray(jac.T @ target).ravel() + damping * anchor
    diagonal = np.asarray(jac.power(2).sum(axis=0)).ravel() + damping
    success = False
    reason = "maxiter"
    cg_iterations = 0
    primal = dual = eps_primal = eps_dual = float("inf")
    for iteration in range(1, maxiter + 1):
        hessian = LinearOperator((n, n), matvec=lambda a: jac.T @ (jac @ a) + (2*rho+damping)*a)
        preconditioner = LinearOperator((n, n), matvec=lambda a: a / (diagonal + 2*rho))
        rhs = jt_target + rho * (basis.synthesis(z-dz) + v-dv)
        counter = [0]
        def count(_):
            counter[0] += 1
        x, info = cg(hessian, rhs, x0=x, M=preconditioner, rtol=cg_rtol,
                     atol=0.0, maxiter=cg_maxiter, callback=count)
        cg_iterations += counter[0]
        if info != 0 or not np.all(np.isfinite(x)):
            reason = "cg_failed"
            break
        dx = basis.analysis(x)
        old_z, old_v = z, v
        w = dx + dz
        z = np.sign(w) * np.maximum(np.abs(w) - beta/rho, 0.0)
        v = np.maximum(x + dv, 0.0)
        dz += dx-z
        dv += x-v
        primal = float(np.hypot(np.linalg.norm(dx-z), np.linalg.norm(x-v)))
        dual = float(rho * np.linalg.norm(basis.synthesis(z-old_z) + v-old_v))
        eps_primal = float(np.sqrt(2*n)*atol + rtol*max(
            np.sqrt(2)*np.linalg.norm(x), np.hypot(np.linalg.norm(z), np.linalg.norm(v))))
        eps_dual = float(np.sqrt(n)*atol + rtol*rho*np.linalg.norm(basis.synthesis(dz)+dv))
        if primal <= eps_primal and dual <= eps_dual:
            success, reason = True, "admm_residuals"
            break
        # Residual balancing changes algorithmic steps, not the objective.
        if iteration % 25 == 0:
            new_rho = rho
            if primal > 10*dual:
                new_rho = min(rho*2, 1e8)
            elif dual > 10*primal:
                new_rho = max(rho/2, 1e-10)
            dz *= rho/new_rho
            dv *= rho/new_rho
            rho = new_rho
    def finite_or_none(value):
        return float(value) if np.isfinite(value) else None
    return v, dict(success=success, stop_reason=reason, nit=iteration,
                   primal_residual=finite_or_none(primal), dual_residual=finite_or_none(dual),
                   primal_tolerance=finite_or_none(eps_primal), dual_tolerance=finite_or_none(eps_dual),
                   cg_iterations=cg_iterations, rho=rho)


def solve_roy_dct(
    lengths, observations, shape, *, k=1.0, alpha=1.0, lam: float = 2.0,
    noise_variance: float = 1e-5, dct_layout: str = "2d", initial_rain: float = 0.6,
    initial_field: np.ndarray | None = None,
    max_outer: int = 50, inner_maxiter: int = 2000, outer_rtol: float = 1e-5,
    inner_atol: float = 1e-6, inner_rtol: float = 1e-5,
    cg_rtol: float = 1e-8, cg_maxiter: int = 500, rho: float = 1.0,
    damping: float = 1e-3, derivative_floor: float = 1e-6,
    max_backtracks: int = 30, verbose: bool = False,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve exact linear Roy objective, or a nonlinear ITU adaptation.

    Nonlinear mode uses damped successive linearization with backtracking on
    the true nonsmooth objective. No global optimality claim is made for it.
    Internally multiply the full objective by noise_variance/2, giving
    beta=lam*noise_variance/2 (no change in minimizers).
    """
    basis = DCTBasis(tuple(shape), dct_layout)
    model = LinkModel(lengths, k=k, alpha=alpha)
    y = np.asarray(observations, dtype=float)
    if model.size != basis.size or y.shape != (model.lengths.shape[0],) or not np.all(np.isfinite(y)):
        raise ValueError("observations/operator/grid dimensions must agree and observations must be finite")
    lam = _positive("lam", lam, zero=True)
    noise_variance = _positive("noise_variance", noise_variance)
    initial_rain = _positive("initial_rain", initial_rain, zero=True)
    damping = _positive("damping", damping)
    derivative_floor = _positive("derivative_floor", derivative_floor)
    rho = _positive("rho", rho)
    for name, value in [("outer_rtol", outer_rtol), ("inner_atol", inner_atol),
                        ("inner_rtol", inner_rtol), ("cg_rtol", cg_rtol)]:
        _positive(name, value)
    max_outer = _integer("max_outer", max_outer)
    inner_maxiter = _integer("inner_maxiter", inner_maxiter)
    cg_maxiter = _integer("cg_maxiter", cg_maxiter)
    max_backtracks = _integer("max_backtracks", max_backtracks)
    beta = lam * noise_variance / 2
    def objective(u):
        residual = model.forward(u)-y
        return float(0.5*np.dot(residual, residual) + beta*np.abs(basis.analysis(u)).sum())
    if initial_field is None:
        u = np.full(basis.size, initial_rain)
    else:
        field = np.asarray(initial_field, dtype=float)
        if field.shape != basis.shape:
            raise ValueError("initial_field must match the rainfall grid shape")
        if not np.all(np.isfinite(field)) or np.any(field < 0):
            raise ValueError("initial_field must be finite and nonnegative")
        u = field.ravel().copy()
    initial_summary = dict(min=float(u.min()), max=float(u.max()), mean=float(u.mean()),
                           sha256=hashlib.sha256(u.astype('<f8').tobytes()).hexdigest())
    current = objective(u)
    if not np.isfinite(current):
        raise ValueError("initial objective is nonfinite; check input scales")
    history = [dict(iter=0, objective=2*current/noise_variance)]
    success, stop_reason = False, "max_outer"
    total_inner = total_cg = 0
    started = time.perf_counter()
    for outer in range(1, (1 if model.linear else max_outer)+1):
        jac = model.jacobian(u, derivative_floor)
        if not np.all(np.isfinite(jac.data)):
            stop_reason = "nonfinite_jacobian"
            break
        target = y - model.forward(u) + jac @ u
        local_damping = 0.0 if model.linear else damping
        candidate, info = solve_convex_subproblem(
            jac, target, basis, beta=beta, anchor=u, damping=local_damping,
            rho=rho, maxiter=inner_maxiter, atol=inner_atol, rtol=inner_rtol,
            cg_rtol=cg_rtol, cg_maxiter=cg_maxiter,
        )
        total_inner += info["nit"]
        total_cg += info["cg_iterations"]
        direction = candidate-u
        relative_step = float(np.linalg.norm(direction)/max(1.0, np.linalg.norm(u)))
        residual = jac @ candidate-target
        predicted = current - (0.5*np.dot(residual, residual)
                    + beta*np.abs(basis.analysis(candidate)).sum()
                    + 0.5*local_damping*np.dot(direction, direction))
        step = 1.0
        accepted = False
        for _ in range(max_backtracks):
            trial = (1-step)*u + step*candidate  # feasible convex combination
            trial_value = objective(trial)
            if np.isfinite(trial_value) and trial_value <= current - 1e-4*step*max(0.0, predicted):
                accepted = True
                break
            step *= 0.5
        # A converged subproblem with a tiny full step is a local fixed point.
        # Do not mistake a tiny BACKTRACKED step for convergence.
        fixed_point = info["success"] and relative_step <= outer_rtol
        if accepted:
            u, current = trial, trial_value
        row = dict(iter=outer, objective=2*current/noise_variance,
                   accepted=accepted, step=step if accepted else 0.0,
                   relative_full_step=relative_step, inner=info)
        history.append(row)
        if verbose:
            print(f"[Roy DCT] outer={outer} objective={row['objective']:.8g} inner={info['stop_reason']}", flush=True)
        if not info["success"]:
            stop_reason = "inner_" + info["stop_reason"]
            break
        if (model.linear and accepted) or fixed_point:
            success, stop_reason = True, "linear_admm" if model.linear else "local_fixed_point"
            break
        if not accepted:
            stop_reason = "line_search_failed"
            break
    prediction = model.forward(u)
    residual = prediction-y
    coeff_l1 = float(np.abs(basis.analysis(u)).sum())
    diagnostics = dict(
        success=success, status=0 if success else 1, stop_reason=stop_reason,
        message=stop_reason, nit=outer, inner_iterations=total_inner,
        cg_iterations=total_cg, optimizer_seconds=time.perf_counter()-started,
        fun=float(np.dot(residual,residual)/noise_variance + lam*coeff_l1),
        data_term=float(np.dot(residual,residual)/noise_variance), coefficient_l1=coeff_l1,
        lam=lam, noise_variance=noise_variance, dct_layout=dct_layout,
        method="roy_dct_linear" if model.linear else "roy_dct_nonlinear",
        derivative_floor=derivative_floor, damping=0.0 if model.linear else damping,
        init_method="constant" if initial_field is None else "provided_field",
        initial_field_summary=initial_summary,
        settings=dict(initial_rain=initial_rain if initial_field is None else None, max_outer=max_outer,
                      inner_maxiter=inner_maxiter, outer_rtol=outer_rtol,
                      inner_atol=inner_atol, inner_rtol=inner_rtol,
                      cg_rtol=cg_rtol, cg_maxiter=cg_maxiter, rho=rho,
                      max_backtracks=max_backtracks),
        history=history,
    )
    return u.reshape(basis.shape), diagnostics


def solve_and_save(est_input_json: str | Path, out_npz: str | Path, cfg: dict) -> dict:
    """Custom-solver adapter for batch_solve_multi.py, using actual ITU inputs.

    A separate explicit paper_linear mode accepts only inputs whose header
    declares measurement_model='roy_linear_a1_b1'; it never reinterprets ITU
    attenuations as linear path integrals.
    """
    mode = cfg.get("measurement_model", "itu_nonlinear")
    if mode not in {"itu_nonlinear", "paper_linear"}:
        raise ValueError("measurement_model must be 'itu_nonlinear' or 'paper_linear'")
    if mode == "paper_linear":
        payload = json.loads(Path(est_input_json).read_text())
        if payload.get("header", {}).get("measurement_model") != "roy_linear_a1_b1":
            raise ValueError("paper_linear requires separately generated a=b=1 measurements marked in the input header")
    prob = load_est_input_json(est_input_json, warn=False)
    if bool(cfg.get("warn", True)) and np.any(~prob.valid_links):
        print(f"[Roy DCT] {np.sum(~prob.valid_links)} zero-length links contribute only constant residual cost.")
    lengths = csr_matrix((prob.ds_km, (prob.link_idx, prob.pix_idx)), shape=(prob.L, prob.P))
    k, alpha = (prob.k, prob.alpha) if mode == "itu_nonlinear" else (np.ones(prob.L), np.ones(prob.L))
    options = dict(cfg.get("optimization", {}) or {})
    initialization = dict(cfg.get("initialization", {}) or {})
    init_method = initialization.get("method", "constant")
    if init_method not in {"constant", "ildw"}:
        raise ValueError("initialization.method must be 'constant' or 'ildw'")
    if "initial_field" in options:
        raise ValueError("Use initialization.method in batch configurations, not optimization.initial_field")
    initialization_settings = {}
    if init_method == "ildw":
        if mode != "itu_nonlinear":
            raise ValueError("ILDW initialization requires itu_nonlinear measurements")
        from cml_attenuation.ildw_baseline import ildw_field_from_est_input
        initialization_settings = dict(
            r_max_m=float(initialization.get("r_max_m", 15000.0)),
            power=float(initialization.get("power", 2.0)),
            default_value=float(initialization.get("default_value", 0.0)),
        )
        initial_field, _ = ildw_field_from_est_input(Path(est_input_json), **initialization_settings)
        options["initial_field"] = initial_field
    field, diag = solve_roy_dct(lengths, prob.A_obs, (prob.H, prob.W), k=k, alpha=alpha, **options)
    diag.update(measurement_model=mode, input_file=str(est_input_json),
                init_method=init_method, initialization_settings=initialization_settings,
                H=prob.H, W=prob.W, num_pixels=prob.P, num_links=prob.L,
                num_valid_links=int(np.sum(prob.valid_links)))
    model = LinkModel(lengths, k=k, alpha=alpha)
    predicted = model.forward(field.ravel())
    normalized_residual = np.zeros(prob.L)
    normalized_residual[prob.valid_links] = (predicted-prob.A_obs)[prob.valid_links]/prob.L_km[prob.valid_links]
    out_npz = Path(out_npz)
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    _atomic_savez_compressed(
        out_npz, R_hat=field, A_hat=predicted, A_obs=prob.A_obs,
        r=normalized_residual, valid_links=prob.valid_links, L_km=prob.L_km,
        freq_ghz=prob.freq_ghz, pol=np.asarray(prob.pol, dtype="U1"), k=k, alpha=alpha,
        meta_success=diag["success"], meta_status=diag["status"], meta_message=diag["message"],
        meta_nit=diag["nit"], meta_fun=diag["fun"], meta_method=diag["method"],
        meta_optimizer_seconds=diag["optimizer_seconds"],
        meta_init_method=diag["init_method"],
        meta_H=prob.H, meta_W=prob.W, meta_P=prob.P, meta_L=prob.L,
        meta_lam=diag["lam"], meta_noise_variance=diag["noise_variance"],
        meta_dct_layout=diag["dct_layout"], meta_measurement_model=mode,
    )
    opt_path = out_npz.with_name(out_npz.stem + "_optinfo.json")
    _atomic_write_json(opt_path, diag)
    return {key: value for key, value in diag.items() if key != "history"} | {
        "out_npz": str(out_npz), "optinfo_out": str(opt_path),
    }
