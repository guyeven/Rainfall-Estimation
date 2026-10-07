# Roy DCT reconstruction

Reference: Roy, Gishkori & Leus (2016), *Dynamic rainfall monitoring using
microwave links*, Sections 4.1 and 5.3.3, Eqs. (26)–(27).
https://doi.org/10.1186/s13634-016-0367-6

## Objective and design decisions

The paper's no-dynamics experiment solves, independently at each snapshot,

    min over u >= 0: ||y - Phi u||² / sigma_e² + lambda ||D u||_1,

where D is orthonormal and Psi = D.T. This is equivalent to their coefficient
formulation u=Psi z. Phi contains intersection lengths in km, with a=b=1.

| Decision | Paper / implementation |
| --- | --- |
| Temporal information | None; no previous snapshot, state covariance, or dynamics penalty. |
| Link model | Paper: linear, a=b=1. Our default: actual ITU k_i and alpha_i in sum_j k_i length_ij u_j^alpha_i, explicitly a nonlinear adaptation. |
| Measurement weighting | Squared residual weighted by R^-1, with R=sigma_e² I. No length normalization, link-count averaging, or pixel-count averaging in the objective. |
| Sparse representation | Orthonormal DCT, all coefficients available; no learned basis, spatial covariance, or frequency truncation. |
| DCT convention | Explicit implementation choice: orthonormal DCT-II, separable 2D by default; `1d` supports a flattened row-major vector. Paper does not unambiguously specify this distinction. |
| Sparsity | lambda times sum of absolute coefficients, including DC; no smoothing approximation, L2, TV, or frequency-dependent weights. |
| Non-negativity | Constrained rainfall u>=0 within optimization; coefficients can have either sign. |
| Hyperparameters | lambda=2, sigma_e²=1e-5 from Section 5.3.3. These values are not tuned for our larger grids, rainfall units, or nonlinear ITU data. |
| Grid | Use the existing patch grid. No resampling to the paper's 25x25 example and no hidden unit conversion of rainfall. |
| Numerical solver | Matrix-free ADMM/CG instead of CVX/SeDuMi; same linear objective. The nonlinear extension uses damped successive linearization and backtracking. |

The repository uses its own rainfall units and ITU forward model; transferring
lambda and noise variance does not reproduce the paper's experiment or establish
optimal settings. Keep both values in the run metadata and tune them explicitly
if doing a new experiment.

## Numerical method

Multiplying the whole objective by sigma_e²/2 gives

    .5 ||y-F(u)||² + beta ||D u||_1, beta=lambda*sigma_e²/2.

This common scaling preserves minimizers and avoids large inverse-variance
weights. Reported objective values use the original unscaled convention.

For each nonlinear outer step, form the sparse Jacobian J and target
b=y-F(u0)+J u0. The subproblem is

    .5 ||J u-b||² + beta ||D u||_1 + .5 damping ||u-u0||², u>=0.

Damping is a step-selection device; it is not added to the reported/original
objective. The exact linear case uses zero damping and one subproblem.
ADMM splits z=D u and v=u, v>=0. The u step uses preconditioned CG on
J.T J + (2 rho+damping) I through operator products. The z step is soft
thresholding; the v step projects onto the nonnegative orthant. This projection
is inside ADMM, not clipping an unconstrained final reconstruction.

No dense Psi, Phi Psi, or N-by-N Hessian is created. Storage is O(N+nnz+M),
plus sparse Jacobian and segment work arrays. DCTs cost O(N log N); CG iterations
cost O(nnz+N). Runtime/convergence is still data-dependent at large sizes.

For alpha<1, the derivative at zero is infinite. `derivative_floor` evaluates
only the Jacobian at max(u,floor); the actual forward model and objective are
unchanged. For alpha>1 this also avoids an all-zero derivative at dry pixels.
This numerical safeguard and positive initialization are additional nonlinear
implementation choices, not specified by Roy's linear experiment. At the
boundary the modified derivative means no claim of exact nonlinear stationarity.

Accepted nonlinear steps must decrease the original nonsmooth objective.
`local_fixed_point` means a converged convex subproblem proposed a sufficiently
small full step. It is not a global optimality certificate. ADMM/CG iteration
limits are reported as failures; a small backtracking step alone cannot declare
convergence. Inspect `meta_success` and the `_optinfo.json` history.

## Run through the existing batch interface

From Compute-Link-Attenuations:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements-lock.txt
    python batch_solve_multi.py --config HundredPatches/pipeline/batch_solve_roy_dct.yaml

NumPy and SciPy provide the numerical solver; PyYAML loads the batch configuration.
These dependencies are already declared in `requirements.txt` and pinned in
`requirements-lock.txt`. SciPy >=1.12 is required for the CG `rtol` argument.
CVXPY, OSQP, and SeDuMi are not dependencies of this implementation or its tests.
Use the project environment above rather than the temporary validation environment.

This opt-in configuration leaves the existing six-method benchmark untouched.
The solver uses the existing `type: custom` / `solve_and_save` interface. To
include it in another batch, copy its solver entry. Normal solution NPZ keys
(`R_hat`, `A_hat`, `A_obs`, `r`, metadata) are compatible with the analysis loader.
`r` is length-normalized for repository output compatibility ONLY; the objective
uses unnormalized attenuation residuals. Zero-length link rows contribute only
constant residual cost and do not constrain rainfall.

To add to an analysis config under `input.solvers`:

    roy_dct_nonlinear:
      name: roy_dct_nonlinear
      label: "Roy DCT (nonlinear adaptation)"
      sol_dir: solutions/sol_dir_roy_dct_nonlinear
      sol_prefix: est
      sol_key_preference: [R_hat]

The direct function `solve_roy_dct(lengths, y, (H,W))` defaults to a=b=1 for
linear reference work. The batch adapter defaults to ITU, as explicitly chosen
for this repository. `measurement_model: paper_linear` requires separately
generated linear observations and the input header marker
`measurement_model: roy_linear_a1_b1`; ordinary nonlinear A_db values are never
silently treated as linear measurements. No ground truth is read by this solver.

## Validation

`tests/test_roy_dct.py` checks DCT inverse/adjoint identities, both layouts against
an independent dense SLSQP epigraph QP, exact analytic shrinkage (including noise
weighting and the factor of two), nonlinear Jacobian finite differences,
nonlinear objective descent, non-convergence reporting, and batch output loading.
A 500x500 / 250,000-pixel analytic DC case checks the matrix-free path at scale.

A bounded smoke run on `202301220000_patch001` used 286,720 pixels and 1,400 links.
Both subproblems converged in a total of 667 ADMM iterations; two nonlinear
steps reduced the original objective to approximately 430,650. That run was
intentionally capped at two outer steps and reports `max_outer`, not success.
It does not establish full-patch convergence or reconstruction quality. The
100-patch benchmark has not been run for this new method.

## ILDW-initialized experiment

`HundredPatches/pipeline/batch_solve_roy_dct_ildw_outer300.yaml` recomputes the
existing ILDW baseline from each input's measurements (15 km radius, power 2,
zero fallback), then supplies that nonnegative grid as the DCT optimizer's
initial field. It uses 300 outer iterations and a 2000 ADMM iteration cap per
outer iteration. Objective weights, damping and tolerances are unchanged from
the constant-initialized 300-outer configuration. No ground truth is used.

```sh
python batch_solve_multi.py --config HundredPatches/pipeline/batch_solve_roy_dct_ildw_outer300.yaml
```

Results and timing files go to separate `sol_dir_roy_dct_ildw_outer300` and
`timing/roy_dct_ildw_outer300` directories. The matching
`analyze_with_roy_dct_ildw_outer300.yaml` writes a separate analysis cache.
ILDW preparation is included in end-to-end time, not optimizer time.
Diagnostics record `init_method`, the ILDW settings, initial-field min/max/mean
and a SHA-256 digest of its row-major little-endian float64 values. The old
constant `initial_rain` setting is recorded as null when a grid is supplied.

The Python solver also accepts an `initial_field` array exactly matching the
(H,W) grid; invalid shape, negative values, and nonfinite values are rejected.
The array is copied rather than modified. Existing configurations without an
`initialization` section retain constant initialization.
