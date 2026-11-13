"""STEPS 3-5: metrics of the Convex runs, analytic H-norm check, max-principle check."""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C, ops
OUT = C.OUT
o0 = ops.build()
lmin = json.loads((OUT / 'results_lmin.json').read_text())['lambda_min'] if (OUT / 'results_lmin.json').exists() else None


def load(name):
    z = np.load(OUT / 'runs' / name / 'solution.npz')
    v = z['valid_links_virtual']
    r = z['A_obs_virtual'][v] / (z['k_virtual'][v] * z['L_km_virtual'][v])
    return z['R_hat'].astype(float).ravel(), r, json.loads((OUT / 'runs' / name / 'result.json').read_text())


def hq(o, x):
    return float(x @ (o['H'] @ x))


Rnf, rnf, inf_nf = load('nf')
Rt, rt, inf_t = load('nf_tight')
zs = np.load(C.CONVEX_NPZ)
Rs = zs['R_hat'].astype(float).ravel()
res = {'reference': 'nf (noise-free rerun, ftol 1e-6)', 'lambda_min': lmin}
res['noise_free'] = {
    'nf_vs_stored': C.stats(Rnf - Rs), 'nf_tight_vs_stored': C.stats(Rt - Rs),
    'stopping_error_nf_vs_tight': C.stats(Rnf - Rt), 'stopping_error_mean_signed_nf_minus_tight': float(np.mean(Rnf - Rt)),
    'stored_vs_tight': C.stats(Rs - Rt),
    'f_nf': inf_nf['fun'], 'f_tight': inf_t['fun'], 'f_stored': float(zs['meta_fun']),
    'H_norm_sq_nf_minus_tight': hq(o0, Rnf - Rt), 'H_norm_sq_stored_minus_tight': hq(o0, Rs - Rt),
    'r_identical_nf_tight': bool(np.array_equal(rnf, rt)),
}
# Step 5: max principle on the noise-free solutions
rmin, rmax = float(rnf.min()), float(rnf.max())
mp = {'r_l_range': [rmin, rmax]}
for nm, R in (('stored', Rs), ('nf', Rnf), ('nf_tight', Rt)):
    mp[nm] = {'R_min': float(R.min()), 'R_max': float(R.max()), 'n_above_max_r': int((R > rmax).sum()),
              'n_below_min_r': int((R < rmin).sum()), 'n_zero': int((R == 0).sum()), 'mean': float(R.mean()),
              'max_excess_above_max_r': float(max(0.0, R.max() - rmax))}
res['max_principle_noise_free'] = mp
runs = []
for d in sorted((OUT / 'runs').glob('*/result.json')):
    name = d.parent.name
    if name in ('nf', 'nf_tight'):
        continue
    R, r, info = load(name)
    dR, dr = R - Rnf, r - rnf
    L = o0['Lk']
    rhs = o0['c_a'] * float(np.sum(L * dr ** 2))
    Gd = o0['G'] @ dR
    lhs_i = float(np.sum(Gd ** 2 / L)); rhs_i = float(np.sum(L * dr ** 2))
    row = {'name': name, 'model': info['model'], 'seed': info['seed'], 'variant': info['variant'],
           'nit': info['nit'], 'stop_reason': info['stop_reason'], 'optimizer_seconds': info['optimizer_seconds'],
           'wall_seconds': info['wall_seconds'], 'proj_grad_inf': info['proj_grad_inf'], 'fun': info['fun'],
           'weights_used': info['weights_used'], 'weights_from_noisy_ildw': info['weights_recomputed_from_noisy_ildw'],
           'dR': C.stats(dR), 'mean_signed_shift': float(dR.mean()), 'dr': C.stats(dr), 'mean_signed_dr': float(dr.mean()),
           'claim_lhs_noise_free_H': hq(o0, dR), 'claim_rhs': rhs, 'claim_ratio_noise_free_H': hq(o0, dR) / rhs,
           'cor_i_lhs': lhs_i, 'cor_i_rhs': rhs_i, 'cor_i_ratio': lhs_i / rhs_i,
           'n_pix_abs_dR_gt_max_abs_dr': int((np.abs(dR) > np.max(np.abs(dr))).sum()), 'max_abs_dr': float(np.max(np.abs(dr))),
           'R_max': float(R.max()), 'n_above_max_r_run': int((R > r.max()).sum())}
    if info['variant'] == 'R':
        o1 = ops.build(weights=dict(info['weights_used'], **{k: v for k, v in o0['w'].items() if k not in info['weights_used']}))
        rhs1 = o1['c_a'] * float(np.sum(L * dr ** 2))
        row['claim_ratio_own_H_and_c_a'] = hq(o1, dR) / rhs1
        row['weight_rel_change'] = {k: info['weights_used'][k] / o0['w'][k] - 1 for k in ('alpha_atten', 'alpha_1d', 'alpha_2d')}
    if lmin:
        row['cor_ii_rms_bound'] = float(np.sqrt(rhs / lmin / o0['P']))
        row['cor_ii_rms_actual'] = row['dR']['rms']
    runs.append(row)
    print(name, row['nit'], row['stop_reason'], round(row['optimizer_seconds']), 'dR', {k: round(v, 4) for k, v in row['dR'].items()},
          'claim', round(row['claim_ratio_noise_free_H'], 4), 'cor_i', round(row['cor_i_ratio'], 4), flush=True)
res['runs'] = runs
res['noise_free_runs'] = {nm: {k: i[k] for k in ('nit', 'stop_reason', 'optimizer_seconds', 'wall_seconds', 'proj_grad_inf', 'fun', 'ftol', 'gtol', 'maxiter', 'maxrss_MB')}
                          for nm, i in (('nf', inf_nf), ('nf_tight', inf_t))}
res['noise_free_runs']['stored'] = {'nit': int(zs['meta_nit']), 'stop_reason': str(zs['meta_stop_reason']), 'optimizer_seconds': float(zs['meta_optimizer_seconds']),
                                    'proj_grad_inf': float(zs['meta_proj_grad_inf'])}
(OUT / 'results_convex.json').write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != 'runs'}, indent=1))
