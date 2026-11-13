import sys, json, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C, ops
t = time.time()
o = ops.build()
H, b = o['H'], o['b']
out = {'n_valid': o['n'], 'P': o['P'], 'kappa0': o['kap0'], 'alpha0': o['al0'], 'c_a': o['c_a'], 'H_nnz': int(H.nnz),
       'weights': o['w'], 'virtual_info': {k: (float(v) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in dict(o['info']).items()} if isinstance(o['info'], dict) else str(o['info'])}
rng = np.random.default_rng(0)
zs = np.load(C.CONVEX_NPZ)
cases = {'stored_R_hat': zs['R_hat'].astype(float).ravel(), 'uniform_0_5': rng.uniform(0, 5, o['P']), 'const_0p6': np.full(o['P'], 0.6)}
chk = {}
for k, R in cases.items():
    fq = 0.5 * R @ (H @ R) - b @ R + o['const']
    fc = float(o['fun'](R)); gq = H @ R - b; gc = o['jac'](R)
    chk[k] = {'f_code': fc, 'f_quadratic': float(fq), 'rel_diff_f': abs(fc - fq) / abs(fc),
              'rel_diff_grad_inf': float(np.max(np.abs(gc - gq)) / np.max(np.abs(gc)))}
out['quadratic_vs_code'] = chk
out['link_rain_virtual_vs_npz_link_rain_equivalent_maxdiff'] = float(np.max(np.abs(o['r'] - zs['link_rain_equivalent'][zs['valid_links']])))
r_ep = C.req(C.A)[o['valid']]
out['r_in_grid_vs_endpoint_length'] = {'max_abs_diff': float(np.max(np.abs(o['r'] - r_ep))), 'n_diff_gt_1e-6': int((np.abs(o['r'] - r_ep) > 1e-6).sum()),
                                       'max_rel_diff': float(np.max(np.abs(o['r'] - r_ep) / np.maximum(r_ep, 1e-12)))}
out['r_range_valid'] = [float(o['r'].min()), float(o['r'].max())]
out['seconds'] = time.time() - t
(C.OUT / 'results_ops_check.json').write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
