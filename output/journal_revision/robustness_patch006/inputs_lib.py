"""Noisy input JSONs and cached ILDW fields (computed with the repository's ildw_field_from_est_input)."""
import hashlib, json
from pathlib import Path
import numpy as np
import common as C

ILDW_KW = dict(r_max_m=15000.0, power=2.0, eps_m=1.0, default_value=0.0)
CACHE = C.OUT / 'ildw_cache'


def key(model, seed):
    return 'none' if model == 'none' else ('N2const' if model == 'N2const' else f'{model}_s{seed}')


def noise_vec(model, seed):
    if model == 'none':
        return np.zeros(C.NL)
    if model == 'N2const':
        e = np.where(C.WET, 2.3, 0.0)
        assert np.all(C.A + e >= 0)
        return e
    return C.noise(seed, model, 2.3 if model == 'N2' else 0.5)


def input_path(model, seed):
    if model == 'none':
        return C.EST
    return C.OUT / 'inputs' / f'est_input_{C.P}_{key(model, seed)}.json'


def write_input(model, seed):
    p = input_path(model, seed)
    if model == 'none':
        return p
    d = json.loads(C.EST.read_text())
    e = noise_vec(model, seed)
    for l in d['links']:
        l['A_db'] = float(C.A[l['link_index']] + e[l['link_index']])
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(d))
    return p


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cached_ildw(p, **kw):
    import time
    assert kw == ILDW_KW, kw
    for _ in range(240):  # wait up to 20 min for the sequential precompute
        if (CACHE / f'{Path(p).stem}.json').exists():
            break
        time.sleep(5)
    m = json.loads((CACHE / f'{Path(p).stem}.json').read_text())
    assert m['sha256'] == sha(p), 'ILDW cache does not match input file'
    return np.load(CACHE / f'{Path(p).stem}.npy'), None
