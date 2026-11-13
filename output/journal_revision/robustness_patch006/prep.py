import json, sys, time
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
from cml_attenuation.solvers.solve_rain_lbfgsb import load_est_input_json
from cml_attenuation.solvers.solve_rain_lbfgsb_normalized_ildw_multipliers import _build_collinear_triplets, _compute_instance_multipliers
from cml_attenuation.virtual_link_utils import make_virtual_problem
from cml_attenuation.ildw_baseline import ildw_field_from_est_input
z = np.load(C.CONVEX_NPZ, allow_pickle=True)
meta = {k: z[k].item() for k in z.files if k.startswith('meta_')}
print(json.dumps({k: (v if not isinstance(v, (np.generic,)) else v.item()) for k, v in meta.items()}, default=str, indent=0)[:4000])
t = time.time()
prob = load_est_input_json(C.EST, warn=True)
tp, tq, tr = _build_collinear_triplets(prob.H, prob.W)
pv, info = make_virtual_problem(prob)
Rild, _ = ildw_field_from_est_input(C.EST, r_max_m=15000.0, power=2.0, eps_m=1.0, default_value=0.0)
st = np.load(C.SOL / 'sol_dir_ildw' / f'est_input_{C.P}_solution.npz')['R_hat']
print('ILDW recomputed vs stored max abs diff', float(np.abs(Rild - st).max()))
mult = _compute_instance_multipliers(pv, R_ildw_flat=np.asarray(Rild, float).reshape(prob.P), t_p=tp, t_q=tq, t_r=tr,
                                     num_atten=1.0, num_1d=1.0, num_2d=0.5, num_total=0.0, num_total_divide_by_num_pixels=True)
print('weights', {k: mult[k] for k in ['alpha_atten', 'alpha_1d', 'alpha_2d', 'alpha_total']})
print('stored ', {k: meta['meta_' + k] for k in ['alpha_atten', 'alpha_1d', 'alpha_2d', 'alpha_total']})
print('virtual freq', np.unique(np.round(np.atleast_1d(info['virtual_freq_ghz']), 9)), 'alpha_virtual range', pv.alpha.min(), pv.alpha.max(), 'k0', np.unique(pv.k))
print('seconds', time.time() - t)
Path('fixed_weights.json').write_text(json.dumps(mult, indent=1))
