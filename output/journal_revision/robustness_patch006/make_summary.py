import json, sys
from pathlib import Path
import numpy as np
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import common as C
J = lambda n: json.loads((OUT / n).read_text()) if (OUT / n).exists() else None
idw, opc, lm, cv = J('results_idw.json'), J('results_ops_check.json'), J('results_lmin.json'), J('results_convex.json')
v = C.OK
extra = {'n_inv_alpha_gt_1_positive_length': int((C.INV[v] > 1).sum()), 'n_inv_alpha_le_1_positive_length': int((C.INV[v] <= 1).sum()),
         'inv_alpha_range_positive_length': [float(C.INV[v].min()), float(C.INV[v].max())],
         'freq_link899_ghz': float(C.F[899]), 'unique_freqs_ghz': sorted(set(np.round(C.F, 3).tolist()))}
allres = {'idw': idw, 'ops_check': opc, 'lambda_min': lm, 'convex': cv, 'extra_facts': extra}
(OUT / 'results.json').write_text(json.dumps(allres, indent=1))
f = lambda x, n=3: f'{x:.{n}g}'
L = ['# patch006 robustness runs', '', f'Patch: {C.P}', '']
pf = idw['patch_facts']
L += ['## Patch facts', '', '| quantity | value |', '|---|---|']
for k in ('H', 'W', 'pixels', 'links', 'wet_A_gt_0_positive_length', 'dry_A_eq_0_positive_length', 'zero_endpoint_length', 'min_endpoint_length_m_positive',
          'n_endpoint_lt_100m', 'n_endpoint_lt_500m', 'median_endpoint_length_km', 'max_endpoint_length_km', 'freq_range_ghz', 'pols', 'A_db_median', 'A_db_max',
          'idw_noise_free_mean'):
    L.append(f'| {k} | {pf[k]} |')
for k, x in extra.items():
    if k != 'unique_freqs_ghz':
        L.append(f'| {k} | {x} |')
if cv:
    L.append(f"| convex_noise_free_mean (nf rerun) | {cv['max_principle_noise_free']['nf']['mean']} |")
L += ['', '## IDW (20 seeds each)', '', '| model | random max | random RMS (mean, range) | random median | mean signed | exact worst max / RMS / median | pixel bound max / RMS / median | max_l b_l (link) |', '|---|---|---|---|---|---|---|---|']
for m, wk in (('N1', 'worst_case'), ('N2', 'worst_case_eq_const_2p3_on_wet')):
    r = idw[m]; rs = r['random_20_seeds']; w = r[wk]; b = r['pixel_bound']; g = r['geometry_free']
    L.append(f"| {m} | {f(rs['max_over_seeds_of_max'])} | {f(rs['mean_rms'])} ({f(rs['rms_range'][0])}–{f(rs['rms_range'][1])}) | {f(rs['mean_median'])} | {f(rs['mean_signed_shift_mean_over_seeds'])} | "
             f"{f(w['max'])} / {f(w['rms'])} / {f(w['median'])} | {f(b['max'])} / {f(b['rms'])} / {f(b['median'])} | {f(g['max_l_b_l'])} (link {g['link']}, {g['L_km']*1000:.0f} m, {g['freq_ghz']} GHz) |")
L += ['', 'IDW assertions: ' + ', '.join(f'{k}: {"PASS" if x else "FAIL"}' for k, x in idw['assertions'].items()), '',
      f"IDW reproduction: {idw['idw_reproduction']}", '']
if cv:
    L += ['## Convex runs (reference: noise-free rerun nf, ftol 1e-6)', '',
          '| run | nit | stop | opt s | proj grad inf | |dR| max | RMS | median | mean signed | claim ratio (H0) | cor (i) ratio | own-H ratio | pixels |dR|>max|dr| | RMS bound (ii) |',
          '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in cv['runs']:
        L.append(f"| {r['name']} | {r['nit']} | {r['stop_reason']} | {r['optimizer_seconds']:.0f} | {f(r['proj_grad_inf'])} | {f(r['dR']['max'])} | {f(r['dR']['rms'])} | {f(r['dR']['median'])} | {f(r['mean_signed_shift'])} | "
                 f"{f(r['claim_ratio_noise_free_H'], 4)} | {f(r['cor_i_ratio'], 4)} | {f(r['claim_ratio_own_H_and_c_a'], 4) if 'claim_ratio_own_H_and_c_a' in r else '–'} | {r['n_pix_abs_dR_gt_max_abs_dr']} | {f(r['cor_ii_rms_bound']) if 'cor_ii_rms_bound' in r else '–'} |")
    L += ['', f"Noise-free runs: {json.dumps(cv['noise_free_runs'])}", '', f"Noise-free comparisons: {json.dumps(cv['noise_free'])}", '',
          f"Max principle (noise-free): {json.dumps(cv['max_principle_noise_free'])}", '']
if lm:
    L += ['## lambda_min(H)', '', '```', json.dumps(lm, indent=1), '```', '']
L += ['## Quadratic form check', '', '```', json.dumps({k: opc[k] for k in ('n_valid', 'P', 'kappa0', 'alpha0', 'c_a', 'H_nnz', 'quadratic_vs_code', 'r_in_grid_vs_endpoint_length')}, indent=1), '```']
(OUT / 'summary.md').write_text('\n'.join(L) + '\n')
print('\n'.join(L))
