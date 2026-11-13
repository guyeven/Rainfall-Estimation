"""One Convex Solver (no shrinkage) run on patch006 with optional noise and fixed weights.
usage: run_convex.py NAME MODEL SEED VARIANT [FTOL GTOL MAXITER]
MODEL in none, N1 (E=0.5 dB), N2 (e=2.3u on wet links), N2const (2.3 dB on wet links).
VARIANT R: weights recomputed from the noisy ILDW (pipeline as is). F: weights fixed at the noise-free values.
The ILDW field is loaded from a cache computed by the repository's ildw_field_from_est_input on the same file
(sha256-checked), to keep the peak memory of parallel runs low. Nothing else in the solver is changed."""
import json, sys, time, resource
from pathlib import Path
import numpy as np
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import common as C
import inputs_lib as IL
import cml_attenuation.solvers.solve_rain_lbfgsb_normalized_ildw_multipliers_virtual_convex as M

name, model, seed, variant = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
ftol, gtol, maxiter = (float(sys.argv[5]), float(sys.argv[6]), int(sys.argv[7])) if len(sys.argv) > 5 else (1e-6, 1e-6, 2000)
run = OUT / 'runs' / name
run.mkdir(parents=True, exist_ok=True)
est = IL.input_path(model, seed)
e = IL.noise_vec(model, seed)
d = json.loads(Path(est).read_text())
assert np.allclose([l['A_db'] for l in d['links']], C.A + e, rtol=0, atol=1e-12), 'input file does not match noise vector'
np.save(run / 'e.npy', e)
M.ildw_field_from_est_input = IL.cached_ildw
captured = {}
orig_mult = M._compute_instance_multipliers
if variant == 'F':
    fixed = json.loads((OUT / 'fixed_weights.json').read_text())
    def _mult(prob, **kw):
        captured['recomputed_would_be'] = orig_mult(prob, **kw)
        return dict(fixed)
elif variant == 'R':
    def _mult(prob, **kw):
        m = orig_mult(prob, **kw)
        captured['recomputed_would_be'] = m
        return m
else:
    raise SystemExit('variant must be R or F')
M._compute_instance_multipliers = _mult
t = time.time()
res = M.solve_lbfgsb_and_save(est, eps=0.01, R0=0.6, maxiter=maxiter, ftol=ftol, gtol=gtol, maxls=20,
    npz_out=run / 'solution.npz', warn=True, R0_from_IDW=False, R0_from_ILDW=False, rain_init_mode='fixed',
    rain_init_value=0.6, rain_init_multiplier=2.0, idw_r_max_m=15000.0, idw_power=2.0, idw_eps_m=1.0,
    idw_default_value=0.0, num_atten=1.0, num_1d=1.0, num_2d=0.5, num_total=0.0,
    num_total_divide_by_num_pixels=True, virtual_freq_ghz=None)
res['wall_seconds'] = time.time() - t
res['maxrss_MB'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
res.update(name=name, model=model, seed=seed, variant=variant, ftol=ftol, gtol=gtol, maxiter=maxiter, input=str(est))
res['weights_recomputed_from_noisy_ildw'] = {k: captured['recomputed_would_be'][k] for k in ('alpha_atten', 'alpha_1d', 'alpha_2d', 'alpha_total')}
used = np.load(run / 'solution.npz')
res['weights_used'] = {k: float(used[f'meta_{k}']) for k in ('alpha_atten', 'alpha_1d', 'alpha_2d', 'alpha_total') if f'meta_{k}' in used.files}
oi = json.loads((run / 'solution_optinfo.json').read_text())
res['proj_grad_inf'] = oi.get('proj_grad_inf')
(run / 'result.json').write_text(json.dumps(res, indent=1, default=str))
print(name, res['stop_reason'], res['nit'], round(res['wall_seconds']), 'MB', round(res['maxrss_MB']), flush=True)
