"""GMZ-style iterative virtual gauges with ITU attenuation normalization.

This is the project's adaptation, not an exact reproduction of GMZ (2009).
Gauges are kept independent until final rasterization using the IDW pixel rule.
"""
from __future__ import annotations

import json
from array import array
import time
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree

from cml_attenuation.idw_baseline import (
    idw_truncated, midpoint_links_by_pixel, pixel_centers_local_xy,
)
from .solve_rain_lbfgsb import load_est_input_json, forward_Ahat_and_r


def neighbor_operator(xy, owners, radius, power):
    """Sparse normalized IDW; exclude the entire target link, including self.

    Coincident gauges from other links share all weight equally. Empty rows
    signal that the existing gauge value should be retained.
    """
    tree = cKDTree(xy)
    indices, data, indptr = array('i'), array('d'), [0]
    for i, point in enumerate(xy):
        js = np.asarray(tree.query_ball_point(point, radius), dtype=int)
        js = js[owners[js] != owners[i]]
        if js.size:
            d = np.linalg.norm(xy[js] - point, axis=1)
            exact = d <= 1e-12
            if exact.any():
                js, weights = js[exact], np.ones(exact.sum())
            else:
                weights = (d.min() / d) ** power
            indices.extend(js)
            data.extend(weights / weights.sum())
        indptr.append(len(indices))
    return csr_matrix((np.frombuffer(data, dtype=np.float64),
                       np.frombuffer(indices, dtype=np.int32), np.asarray(indptr, dtype=np.int64)),
                      shape=(len(xy), len(xy)))


def solve_and_save(est_input_json, out_npz, cfg):
    started = time.perf_counter()
    defaults = dict(segment_length_m=125.0, r_max_m=15000.0, power=2.0,
                    maxiter=300, damping=0.5, rtol=1e-5, atol=1e-6)
    supplied = cfg.get('gmz', {}) or {}
    unknown = set(supplied) - set(defaults)
    if unknown:
        raise ValueError(f'Unknown GMZ settings: {sorted(unknown)}')
    settings = defaults | supplied
    for key, value in settings.items():
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f'{key} must be finite and positive')
    if settings['damping'] > 1 or int(settings['maxiter']) != settings['maxiter']:
        raise ValueError('damping must be <= 1 and maxiter must be an integer')
    payload = json.loads(Path(est_input_json).read_text())
    links = sorted(payload['links'], key=lambda rec: rec['link_index'])
    if [rec['link_index'] for rec in links] != list(range(len(links))):
        raise ValueError('link_index must be unique and contiguous from zero')
    prob = load_est_input_json(est_input_json, warn=False)
    if (not np.all(np.isfinite(prob.A_obs)) or np.any(prob.A_obs < 0)
            or not np.all(np.isfinite(prob.k)) or np.any(prob.k <= 0)
            or not np.all(np.isfinite(prob.alpha)) or np.any(prob.alpha <= 0)):
        raise ValueError('Expected finite nonnegative attenuation and positive ITU coefficients')
    points, owners, lengths = [], [], []
    header = payload['header']
    bounds = np.array([prob.W, prob.H]) * float(header['pixel_size_m'])
    for li, rec in enumerate(links):
        start = np.array([rec['x0_m'], rec['y0_m']], dtype=float)
        end = np.array([rec['x1_m'], rec['y1_m']], dtype=float)
        if (not np.all(np.isfinite([start, end])) or np.any(start < 0)
                or np.any(end < 0) or np.any(start > bounds) or np.any(end > bounds)):
            raise ValueError('GMZ requires finite link endpoints inside the patch')
        length = np.linalg.norm(end-start) / 1000
        if length == 0 and prob.L_km[li] == 0 and prob.A_obs[li] == 0:
            continue
        if length <= 0 or not np.isclose(length, prob.L_km[li], rtol=1e-5, atol=1e-8):
            raise ValueError('GMZ requires positive full-link geometry matching pixel intersections')
        count = max(1, int(np.ceil(length * 1000 / settings['segment_length_m'])))
        points.extend(start + ((np.arange(count)+0.5)/count)[:, None]*(end-start))
        owners.extend([li]*count)
        lengths.extend([length/count]*count)
    xy = np.asarray(points, dtype=float).reshape(-1, 2)
    owner = np.asarray(owners, dtype=int)
    ds = np.asarray(lengths)
    uniform = np.zeros(prob.L)
    valid = prob.valid_links
    uniform[valid] = (prob.A_obs[valid] / (prob.k[valid] * prob.L_km[valid])) ** (1/prob.alpha[valid])
    z = uniform[owner].copy()
    operator = neighbor_operator(xy, owner, settings['r_max_m'], settings['power'])
    isolated = np.diff(operator.indptr) == 0

    def prediction(values):
        return np.bincount(owner, weights=ds*prob.k[owner]*values**prob.alpha[owner], minlength=prob.L)

    history = []
    success = False
    for iteration in range(1, int(settings['maxiter'])+1):
        proposal = operator @ z
        proposal[isolated] = z[isolated]
        # Damp BEFORE normalization so every completed iterate preserves A_obs.
        proposal = (1-settings['damping'])*z + settings['damping']*proposal
        predicted = prediction(proposal)
        empty = (predicted == 0) & (prob.A_obs > 0)
        proposal[empty[owner]] = uniform[owner[empty[owner]]]
        predicted = prediction(proposal)
        scale = np.zeros(prob.L)
        wet = predicted > 0
        scale[wet] = (prob.A_obs[wet]/predicted[wet]) ** (1/prob.alpha[wet])
        updated = proposal*scale[owner]
        if not np.all(np.isfinite(updated)):
            raise FloatingPointError('Nonfinite GMZ iterate')
        change = float(np.max(np.abs(updated-z), initial=0))
        threshold = settings['atol'] + settings['rtol']*float(np.max(np.abs(z), initial=0))
        z = updated
        history.append(change)
        if change <= threshold:
            success = True
            break
    occupied = midpoint_links_by_pixel(header, xy)
    empty_pixels = np.array([not gauges for gauges in occupied])
    field = np.zeros(prob.P)
    queries = pixel_centers_local_xy(header)
    empty_indices = np.flatnonzero(empty_pixels)
    # Bound the KD-tree neighbor lists instead of allocating all pixel pairs.
    for offset in range(0, len(empty_indices), 256):
        batch = empty_indices[offset:offset+256]
        field[batch] = idw_truncated(xy, z, queries[batch],
                          r_max_m=settings['r_max_m'], power=settings['power'])
    for pixel, gauges in enumerate(occupied):
        if gauges:
            field[pixel] = np.mean(z[gauges])
    field = field.reshape(prob.H, prob.W)
    A_hat, residual = forward_Ahat_and_r(prob, field.ravel())
    A_virtual = prediction(z)
    diag = dict(method='gmz_itu_adaptation', success=success, status=0 if success else 1,
                stop_reason='tolerance' if success else 'maxiter', nit=iteration,
                message='Gauge update tolerance reached' if success else 'Iteration limit reached',
                settings=settings, num_gauges=len(z), num_isolated_gauges=int(isolated.sum()),
                virtual_attenuation_rmse_db=float(np.sqrt(np.mean((A_virtual-prob.A_obs)**2))) if prob.L else 0.0,
                raster_attenuation_rmse_db=float(np.sqrt(np.mean((A_hat-prob.A_obs)**2))) if prob.L else 0.0,
                optimizer_seconds=time.perf_counter()-started, max_update_history=history)
    out = Path(out_npz)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, R_hat=field, A_hat=A_hat, A_obs=prob.A_obs, r=residual,
                        A_virtual=A_virtual, gauge_xy=xy, gauge_rain=z, gauge_link_index=owner,
                        gauge_length_km=ds, valid_links=prob.valid_links, L_km=prob.L_km,
                        k=prob.k, alpha=prob.alpha, meta=json.dumps(diag),
                        meta_success=success, meta_nit=iteration, meta_method=diag['method'])
    info = out.with_name(out.stem+'_optinfo.json')
    info.write_text(json.dumps(diag, indent=2)+'\n')
    return {k: v for k, v in diag.items() if k != 'max_update_history'} | dict(out_npz=str(out), optinfo_out=str(info))
