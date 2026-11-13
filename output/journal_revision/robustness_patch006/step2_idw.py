"""STEP 2: IDW noise propagation on patch006 (exact worst case, per-pixel bound, random draws)."""
import json, sys, time
from pathlib import Path
import numpy as np
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import common as C

t0 = time.time()
res = {'assertions': {}}
ok = C.OK
R0 = C.req(C.A)
inv, LK, K = C.INV, C.LKM, C.K


def bound(E, mask):
    """b_l = (E/(k L))^(1/a) if 1/a <= 1, else (1/a)((A+E)/(k L))^(1/a-1) E/(k L). Zero off mask."""
    b = np.zeros(C.NL)
    m = mask & (inv <= 1)
    b[m] = (E / (K[m] * LK[m])) ** inv[m]
    m = mask & (inv > 1)
    b[m] = inv[m] * ((C.A[m] + E) / (K[m] * LK[m])) ** (inv[m] - 1) * E / (K[m] * LK[m])
    return b

# N1: admissible set |e| <= E, A+e >= 0, i.e. e in [-min(E,A), E]; random draws are the symmetric subset
E1 = 0.5
up1 = np.where(ok, C.req(C.A + E1) - R0, 0.0)
dn1 = np.where(ok, R0 - C.req(np.maximum(C.A - E1, 0.0)), 0.0)
b1 = bound(E1, ok)
d1 = np.stack([np.where(ok, C.req(C.A + C.noise(s, 'N1', E1)) - R0, 0.0) for s in range(20)], 1)
# N2: e in [0, E] on wet links only
E2 = 2.3
up2 = np.where(C.WET, C.req(C.A + E2) - R0, 0.0)
b2 = bound(E2, C.WET)
d2 = np.stack([np.where(C.WET, C.req(C.A + C.noise(s, 'N2', E2)) - R0, 0.0) for s in range(20)], 1)

tol = 1e-12
res['assertions']['N1 per-link b >= max(up,dn)'] = bool(np.all(b1 + tol * (1 + b1) >= np.maximum(up1, dn1)))
res['assertions']['N1 per-link b >= |random change|'] = bool(np.all(b1[:, None] + tol * (1 + b1[:, None]) >= np.abs(d1)))
res['assertions']['N2 per-link b >= up'] = bool(np.all(b2 + tol * (1 + b2) >= up2))
res['assertions']['N2 random change >= 0'] = bool(np.all(d2 >= 0))
res['assertions']['A+e >= 0 (all 40 draws, asserted inside noise())'] = True
res['link_ratio_max_exact_over_b'] = {'N1': float(np.max(np.maximum(up1, dn1)[ok] / b1[ok])),
                                       'N2': float(np.max(up2[C.WET] / b2[C.WET]))}

V = np.column_stack([R0, up1, dn1, b1, d1, up2, b2, d2])
G = C.idw_apply(V)
print('idw_apply done', round(time.time() - t0), flush=True)
idw0 = G[..., 0]
stored = np.load(C.IDW_NPZ)['R_hat'].astype(float)
res['idw_reproduction'] = {'max_abs_diff_vs_stored_float32': float(np.max(np.abs(idw0 - stored))),
                           'max_abs_diff_vs_stored_after_float32_cast': float(np.max(np.abs(idw0.astype(np.float32).astype(float) - stored))),
                           'stored_max': float(stored.max())}
# repository IDW kernel on a random pixel subset (full-grid call avoided: KD-tree neighbour lists are memory heavy)
from cml_attenuation.idw_baseline import idw_truncated, link_midpoints_xy, pixel_centers_local_xy, midpoint_links_by_pixel, link_rain_from_attenuation
mids = link_midpoints_xy(C.LINKS); q = pixel_centers_local_xy(C.HDR)
vals = link_rain_from_attenuation(C.A, C.LKM, C.K, C.ALPHA, invalid_to_zero=True)
res['idw_reproduction']['link_values_max_abs_diff_vs_mine'] = float(np.max(np.abs(vals - R0)))
sub = np.random.default_rng(123).choice(C.H * C.W, 20000, replace=False)
rep = idw_truncated(mids, vals, q[sub], r_max_m=15000.0, power=2.0, default_value=0.0)
mp = midpoint_links_by_pixel(C.HDR, mids)
for t, idx in enumerate(sub):
    if mp[idx]:
        rep[t] = float(np.mean(vals[mp[idx]]))
allmp = [i for i, lst in enumerate(mp) if lst]
rep_mp = np.array([np.mean(vals[mp[i]]) for i in allmp])
res['idw_reproduction']['max_abs_diff_mine_vs_repo_kernel_20000_random_pixels'] = float(np.max(np.abs(idw0.ravel()[sub] - rep)))
res['idw_reproduction']['max_abs_diff_mine_vs_repo_midpoint_rule_pixels'] = float(np.max(np.abs(idw0.ravel()[allmp] - rep_mp)))
res['idw_reproduction']['n_midpoint_rule_pixels'] = len(allmp)
# pixel coverage: any link within r_max or midpoint rule
cov = C.idw_apply(np.ones(C.NL)) > 0.5
res['pixels_covered_by_idw'] = int(cov.sum())

W1 = np.maximum(G[..., 1], G[..., 2]); B1 = G[..., 3]; D1 = G[..., 4:24]
W2 = G[..., 24]; B2 = G[..., 25]; D2 = G[..., 26:46]
eps = 1e-10
res['assertions']['N1 random <= worst <= bound per pixel'] = bool(np.all(np.abs(D1) <= W1[..., None] + eps) and np.all(W1 <= B1 + eps))
res['assertions']['N2 random <= worst <= bound per pixel'] = bool(np.all(D2 <= W2[..., None] + eps) and np.all(W2 <= B2 + eps))


def seedstats(D):
    s = [C.stats(D[..., i]) for i in range(D.shape[-1])]
    rms = [x['rms'] for x in s]
    return {'max_over_seeds_of_max': max(x['max'] for x in s), 'mean_rms': float(np.mean(rms)),
            'rms_range': [min(rms), max(rms)], 'mean_median': float(np.mean([x['median'] for x in s])),
            'mean_signed_shift_mean_over_seeds': float(np.mean(D.mean(axis=(0, 1)))),
            'per_seed': s}


def geo(b, mask):
    i = int(np.argmax(np.where(mask, b, -1)))
    return {'max_l_b_l': float(b[i]), 'link': i, 'freq_ghz': float(C.F[i]), 'pol': str(C.POL[i]), 'L_km': float(LK[i]),
            'A_db': float(C.A[i]), 'inv_alpha': float(inv[i]), 'k': float(K[i])}

res['N1'] = {'E_db': E1, 'random_20_seeds': seedstats(D1), 'worst_case': C.stats(W1), 'pixel_bound': C.stats(B1),
             'geometry_free': geo(b1, ok), 'worst_over_bound_max': float(np.max(np.where(B1 > 0, W1 / np.where(B1 > 0, B1, 1), 0)))}
res['N2'] = {'E_db': E2, 'random_20_seeds': seedstats(D2), 'worst_case_eq_const_2p3_on_wet': C.stats(W2),
             'worst_mean_signed_shift': float(W2.mean()), 'pixel_bound': C.stats(B2), 'geometry_free': geo(b2, C.WET),
             'worst_over_bound_max': float(np.max(np.where(B2 > 0, W2 / np.where(B2 > 0, B2, 1), 0)))}
np.savez_compressed(OUT / 'idw_fields.npz', idw0=idw0, W1=W1, B1=B1, W2=W2, B2=B2, D1_s0=D1[..., 0], D2_s0=D2[..., 0])
np.save(OUT / 'idw_link_vectors.npy', np.column_stack([R0, up1, dn1, b1, up2, b2]))

# patch facts
LSEG = C.LSEG
facts = {'H': C.H, 'W': C.W, 'pixel_size_m': C.PX, 'pixels': C.H * C.W, 'links': C.NL,
         'zero_endpoint_length': int((~ok).sum()), 'zero_in_grid_length': int((LSEG <= 0).sum()),
         'zero_in_grid_length_links': np.where(LSEG <= 0)[0].tolist(),
         'wet_A_gt_0_positive_length': int(C.WET.sum()), 'dry_A_eq_0_positive_length': int((ok & (C.A <= 0)).sum()),
         'A_le_0_any': int((C.A <= 0).sum()), 'A_lt_0': int((C.A < 0).sum()),
         'min_endpoint_length_m_positive': float(LK[ok].min() * 1000), 'n_endpoint_lt_100m': int((ok & (LK < 0.1)).sum()),
         'n_endpoint_lt_500m': int((ok & (LK < 0.5)).sum()), 'max_endpoint_length_km': float(LK.max()),
         'median_endpoint_length_km': float(np.median(LK[ok])),
         'inv_alpha_range': [float(inv.min()), float(inv.max())], 'n_inv_alpha_gt_1': int((inv > 1).sum()),
         'n_inv_alpha_le_1': int((inv <= 1).sum()), 'freq_range_ghz': [float(C.F.min()), float(C.F.max())],
         'pols': {p: int((C.POL == p).sum()) for p in np.unique(C.POL)},
         'A_db_median': float(np.median(C.A)), 'A_db_max': float(C.A.max()), 'A_db_mean': float(C.A.mean()),
         'A_db_median_wet': float(np.median(C.A[C.WET])),
         'idw_noise_free_mean': float(idw0.mean()), 'idw_noise_free_max': float(idw0.max()),
         'R_link_endpoint_range': [float(R0[ok].min()), float(R0[ok].max())], 'R_link_endpoint_median': float(np.median(R0[ok])),
         'length_mismatch_endpoint_minus_in_grid_km': {'n_gt_1m': int((LK - LSEG > 1e-3).sum()), 'n_lt_minus_1m': int((LK - LSEG < -1e-3).sum()),
                                                        'max_km': float((LK - LSEG).max()), 'min_km': float((LK - LSEG).min())}}
facts['inv_alpha_by_link_count_lt_1'] = int((inv < 1).sum())
res['patch_facts'] = facts
res['seconds'] = time.time() - t0
(OUT / 'results_idw.json').write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k not in ('N1', 'N2')}, indent=1))
for m in ('N1', 'N2'):
    r = dict(res[m]); r['random_20_seeds'] = {k: v for k, v in r['random_20_seeds'].items() if k != 'per_seed'}
    print(m, json.dumps(r, indent=1))
