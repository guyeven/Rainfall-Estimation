import json
import sys
from pathlib import Path

import numpy as np
import unittest
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cml_attenuation.idw_baseline import itu838_k_alpha, idw_field_from_est_input
from cml_attenuation.solvers.solve_rain_gmz import solve_and_save, neighbor_operator


def fixture(tmp_path, rain=(2., 8.)):
    k, a = itu838_k_alpha(30., 'H')
    links = [dict(link_index=i, x0_m=0., x1_m=300., y0_m=50.+100*i,
                  y1_m=50.+100*i, freq_ghz=30., pol='H',
                  A_db=float(k[0]*.3*r**a[0])) for i, r in enumerate(rain)]
    payload = dict(header=dict(H=3, W=3, pixel_size_m=100.), links=links,
                   segments_by_link={str(i): [dict(i=i, j=j, ds_m=100.) for j in range(3)] for i in range(len(links))})
    path = tmp_path/'input.json'
    path.write_text(json.dumps(payload))
    return path


def run(tmp_path, rain=(2., 8.), **settings):
    path = fixture(tmp_path, rain)
    out = tmp_path/'solution.npz'
    info = solve_and_save(path, out, dict(gmz=settings))
    return np.load(out), info, path



class GMZTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.tmp_path = Path(folder.name)

    def test_single_gauge_reduces_to_idw(self):
        tmp_path = self.tmp_path
        saved, info, path = run(tmp_path, segment_length_m=1000.)
        expected, _ = idw_field_from_est_input(path, r_max_m=15000.)
        np.testing.assert_allclose(saved['R_hat'], expected, rtol=1e-10)
        assert info['success']


    def test_nonlinear_attenuation_and_pixel_average(self):
        tmp_path = self.tmp_path
        saved, _, _ = run(tmp_path, segment_length_m=40.)
        np.testing.assert_allclose(saved['A_virtual'], saved['A_obs'], atol=1e-12)
        xy, z = saved['gauge_xy'], saved['gauge_rain']
        for i in range(2):
            for j in range(3):
                mask = (xy[:, 0] >= 100*j) & (xy[:, 0] < 100*(j+1)) & (xy[:, 1] == 50+100*i)
                np.testing.assert_allclose(saved['R_hat'][i, j], z[mask].mean())
        assert np.isfinite(saved['R_hat']).all() and (saved['R_hat'] >= 0).all()


    def test_dry_and_isolated_links(self):
        tmp_path = self.tmp_path
        saved, info, _ = run(tmp_path, rain=(0., 8.), r_max_m=1.)
        assert info['success']
        np.testing.assert_allclose(saved['gauge_rain'], np.where(saved['gauge_link_index'] == 0, 0., 8.))
        np.testing.assert_allclose(saved['A_virtual'], saved['A_obs'], atol=1e-12)
        assert info['num_isolated_gauges'] == len(saved['gauge_rain'])


    def test_zero_proposals_recover_wet_link(self):
        tmp_path = self.tmp_path
        saved, _, _ = run(tmp_path, rain=(0., 8.), damping=1.)
        np.testing.assert_allclose(saved['A_virtual'], saved['A_obs'], atol=1e-12)
        assert np.isfinite(saved['gauge_rain']).all()


    def test_coincident_neighbors_exclude_own_link(self):
        xy = np.array([[0., 0.], [0., 0.], [0., 0.], [1., 0.]])
        owners = np.array([0, 0, 1, 2])
        matrix = neighbor_operator(xy, owners, 2., 2.).toarray()
        np.testing.assert_array_equal(matrix[0], [0, 0, 1, 0])
        np.testing.assert_array_equal(matrix[2], [.5, .5, 0, 0])


    def test_iteration_limit_is_not_convergence(self):
        tmp_path = self.tmp_path
        path = fixture(tmp_path, rain=(2., 8., 0.))
        payload = json.loads(path.read_text())
        # Shift the second link one pixel right and shorten it: asymmetric neighbors.
        payload['links'][1]['x0_m'] = 100.
        payload['links'][1]['A_db'] *= 2/3
        payload['segments_by_link']['1'] = payload['segments_by_link']['1'][1:]
        path.write_text(json.dumps(payload))
        info = solve_and_save(path, tmp_path/'out.npz', dict(gmz=dict(maxiter=1)))
        assert not info['success'] and info['stop_reason'] == 'maxiter'


    def test_bad_settings(self):
        tmp_path = self.tmp_path
        for settings in [dict(power=0), dict(damping=2), dict(maxiter=1.5), dict(typo=1)]:
            with unittest.TestCase().assertRaises(ValueError):
                run(tmp_path, **settings)


    def test_degenerate_zero_link_is_excluded(self):
        tmp_path = self.tmp_path
        path = fixture(tmp_path)
        payload = json.loads(path.read_text())
        payload['links'][0]['x1_m'] = 0.
        payload['links'][0]['A_db'] = 0.
        payload['segments_by_link']['0'] = []
        path.write_text(json.dumps(payload))
        out = tmp_path/'out.npz'
        solve_and_save(path, out, {})
        with np.load(out) as saved:
            assert (saved['gauge_link_index'] == 1).all()
            np.testing.assert_allclose(saved['A_virtual'], saved['A_obs'], atol=1e-12)


    def test_empty_network(self):
        tmp_path = self.tmp_path
        saved, info, _ = run(tmp_path, rain=())
        assert info['success']
        assert np.count_nonzero(saved['R_hat']) == 0
