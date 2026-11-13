"""Quadratic form of the Convex Solver objective on the virtual problem (code normalization).
f(R) = a_att*J_atten + a_1d*J_1d + a_2d*J_2d (a_total = 0) = 0.5 R'HR - b'R + const, with
H = c_a G'D^-1 G + S, c_a = 2 a_att kappa0^2 / n_valid, S = 2(a_1d/P) D1'D1 + 2(a_2d/P) D2'D2, b = c_a G' r,
G_lp = ds_lp [km] (valid links), D = diag(L_km in-grid), r_l = virtual link rain equivalent = A_obs_virtual/(kappa0 L)."""
import json
from pathlib import Path
import numpy as np
import scipy.sparse as sp
import common as C
from cml_attenuation.solvers.solve_rain_lbfgsb import load_est_input_json
from cml_attenuation.solvers.solve_rain_lbfgsb_normalized_ildw_multipliers import _build_collinear_triplets, make_objective
from cml_attenuation.virtual_link_utils import make_virtual_problem


def build(est=C.EST, weights=None):
    pr = load_est_input_json(est, warn=False)
    tp, tq, tr = _build_collinear_triplets(pr.H, pr.W)
    pv, info = make_virtual_problem(pr, virtual_freq_ghz=None)
    w = weights or json.loads((C.OUT / 'fixed_weights.json').read_text())
    v = pv.valid_links
    n = int(v.sum()); P = pr.P
    kap = np.unique(pv.k[v]); al = np.unique(pv.alpha[v])
    assert kap.size == 1 and al.size == 1
    kap0, al0 = float(kap[0]), float(al[0])
    G = sp.csr_matrix((pv.ds_km, (pv.link_idx, pv.pix_idx)), shape=(pr.L, P))[np.where(v)[0]]
    Lk = pv.L_km[v]
    assert np.allclose(np.asarray(G.sum(1)).ravel(), Lk, rtol=1e-12, atol=1e-12)
    r = pv.A_obs[v] / (kap0 * Lk)
    E = pv.n_u.size
    D1 = sp.csr_matrix((np.r_[np.ones(E), -np.ones(E)], (np.r_[np.arange(E), np.arange(E)], np.r_[pv.n_u, pv.n_v])), shape=(E, P))
    T = tp.size
    D2 = sp.csr_matrix((np.r_[-np.ones(T), 2 * np.ones(T), -np.ones(T)],
                        (np.r_[np.arange(T), np.arange(T), np.arange(T)], np.r_[tp, tq, tr])), shape=(T, P))
    c_a = 2 * w['alpha_atten'] * kap0 ** 2 / n
    S = (2 * w['alpha_1d'] / P) * (D1.T @ D1) + (2 * w['alpha_2d'] / P) * (D2.T @ D2)
    Dinv = sp.diags(1.0 / Lk)
    H = (c_a * (G.T @ Dinv @ G) + S).tocsc()
    H = ((H + H.T) * 0.5).tocsc()
    b = c_a * (G.T @ r)
    const = 0.5 * c_a * float(np.sum(Lk * r ** 2))
    fun, jac = make_objective(pv, alpha_atten=w['alpha_atten'], alpha_1d=w['alpha_1d'], alpha_2d=w['alpha_2d'],
                              alpha_total=w['alpha_total'], t_p=tp, t_q=tq, t_r=tr)
    return dict(pr=pr, pv=pv, G=G, Lk=Lk, r=r, D1=D1, D2=D2, S=S, H=H, b=b, const=const, c_a=c_a, kap0=kap0,
                al0=al0, n=n, P=P, valid=v, fun=fun, jac=jac, w=w, info=info)


def link_rain_virtual(npz):
    """r_l from a saved solution: A_obs_virtual/(kappa0 L) on valid links."""
    z = np.load(npz)
    v = z['valid_links_virtual']
    return z['A_obs_virtual'][v] / (z['k_virtual'][v] * z['L_km_virtual'][v]), z
