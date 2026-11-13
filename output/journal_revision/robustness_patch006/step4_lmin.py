"""lambda_min(H) by shift-invert Lanczos (eigsh, sigma=0) with a sparse LU of H; checks and unconstrained minimizer."""
import sys, json, time, resource
from pathlib import Path
import numpy as np
from scipy.sparse.linalg import splu, eigsh, LinearOperator
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C, ops
mb = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
out = {}
t = time.time()
o = ops.build(); H = o['H']; P = o['P']
out['H_nnz'] = int(H.nnz)
t1 = time.time()
lu = splu(H, permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
out['splu'] = {'seconds': time.time() - t1, 'L_nnz': int(lu.L.nnz), 'U_nnz': int(lu.U.nnz), 'maxrss_MB_after': mb(),
               'ordering': 'MMD_AT_PLUS_A, diag_pivot_thresh 0, SymmetricMode'}
print('splu', out['splu'], flush=True)
rng = np.random.default_rng(1)
y = rng.standard_normal(P); x = lu.solve(y)
out['splu']['solve_rel_residual_random_rhs'] = float(np.linalg.norm(H @ x - y) / np.linalg.norm(y))
OP = LinearOperator((P, P), matvec=lu.solve, dtype=float)
res = {}
for tol in (1e-8, 1e-12):
    t2 = time.time()
    vals, vecs = eigsh(H, k=4, sigma=0.0, which='LM', OPinv=OP, tol=tol, v0=np.ones(P))
    order = np.argsort(vals); vals = vals[order]; vecs = vecs[:, order]
    resid = [float(np.linalg.norm(H @ vecs[:, i] - vals[i] * vecs[:, i]) / (abs(vals[i]) * np.linalg.norm(vecs[:, i]))) for i in range(4)]
    rq = [float(vecs[:, i] @ (H @ vecs[:, i]) / (vecs[:, i] @ vecs[:, i])) for i in range(4)]
    res[f'tol_{tol:g}'] = {'eigs_smallest4': vals.tolist(), 'rel_residuals': resid, 'rayleigh_quotients': rq, 'seconds': time.time() - t2}
    print(tol, res[f'tol_{tol:g}'], flush=True)
out['eigsh_shift_invert'] = res
lam = float(vals[0]); v = vecs[:, 0]
# independent check: inverse power iteration with the same LU from a different start
z = rng.standard_normal(P)
for it in range(300):
    z = lu.solve(z); z /= np.linalg.norm(z)
out['inverse_iteration_300_steps_rayleigh'] = float(z @ (H @ z))
one = np.ones(P) / np.sqrt(P)
out['rayleigh_constant_vector_upper_bound'] = float(one @ (H @ one))
out['lambda_min'] = lam
out['lambda_min_eigvec'] = {'abs_max': float(np.max(np.abs(v))), 'sign_uniform': bool(np.all(v >= 0) or np.all(v <= 0)),
                            'participation_ratio_over_P': float((v @ v) ** 2 / np.sum(v ** 4) / P)}
t3 = time.time()
lmax = eigsh(H, k=1, which='LA', tol=1e-6, return_eigenvectors=False)
out['lambda_max'] = float(lmax[0]); out['lambda_max_seconds'] = time.time() - t3
out['condition_number'] = out['lambda_max'] / lam
# unconstrained minimizer H^-1 b, compared with the L-BFGS-B solutions
xu = lu.solve(o['b'])
f = lambda R: 0.5 * R @ (H @ R) - o['b'] @ R + o['const']
out['unconstrained_minimizer'] = {'min': float(xu.min()), 'n_negative': int((xu < 0).sum()), 'n_below_minus_1e-6': int((xu < -1e-6).sum()),
                                  'f': float(f(xu)), 'max': float(xu.max())}
for nm, pth in [('stored', C.CONVEX_NPZ), ('nf', C.OUT / 'runs/nf/solution.npz'), ('nf_tight', C.OUT / 'runs/nf_tight/solution.npz')]:
    if Path(pth).exists():
        R = np.load(pth)['R_hat'].astype(float).ravel()
        out['unconstrained_minimizer'][f'f_{nm}'] = float(f(R))
        out['unconstrained_minimizer'][f'max_abs_diff_vs_{nm}'] = float(np.max(np.abs(R - xu)))
        out['unconstrained_minimizer'][f'rms_diff_vs_{nm}'] = float(np.sqrt(np.mean((R - xu) ** 2)))
np.savez_compressed(C.OUT / 'lmin.npz', v=v.reshape(C.H, C.W), xu=xu.reshape(C.H, C.W))
out['maxrss_MB'] = mb(); out['seconds'] = time.time() - t
(C.OUT / 'results_lmin.json').write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
