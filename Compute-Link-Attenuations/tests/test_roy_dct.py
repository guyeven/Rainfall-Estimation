from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, minimize
from scipy.sparse import csr_matrix, eye

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cml_attenuation.solvers.solve_rain_roy_dct import (
    DCTBasis, LinkModel, solve_roy_dct, solve_and_save,
)


class RoyDCTTests(unittest.TestCase):
    def test_initial_field_is_used_and_validated(self):
        start = np.arange(6, dtype=float).reshape(2, 3) / 2
        original = start.copy()
        _, info = solve_roy_dct(eye(6), np.ones(6), (2, 3),
                              initial_field=start, inner_maxiter=1,
                              noise_variance=.4, lam=1.3)
        expected = np.sum((start-1)**2)/.4 + 1.3*np.abs(DCTBasis((2, 3)).analysis(start)).sum()
        self.assertAlmostEqual(info["history"][0]["objective"], expected)
        self.assertEqual(info["init_method"], "provided_field")
        self.assertIsNone(info["settings"]["initial_rain"])
        np.testing.assert_array_equal(start, original)
        for bad in [np.ones((3, 2)), np.full((2, 3), -1), np.full((2, 3), np.nan)]:
            with self.assertRaises(ValueError):
                solve_roy_dct(eye(6), np.ones(6), (2, 3), initial_field=bad)

    def test_transform_adjoint_and_inverse(self):
        rng = np.random.default_rng(42)
        for layout in ("1d", "2d"):
            basis = DCTBasis((3, 4), layout)
            u, z = rng.normal(size=(2, 12))
            np.testing.assert_allclose(basis.synthesis(basis.analysis(u)), u, atol=1e-14)
            self.assertAlmostEqual(np.dot(basis.analysis(u), z), np.dot(u, basis.synthesis(z)), places=12)

    def test_linear_solution_matches_independent_dense_qp(self):
        # Dense SLSQP epigraph formulation is used ONLY as a tiny test oracle.
        rng = np.random.default_rng(321)
        a = rng.uniform(0, 1, (18, 12))
        truth = rng.uniform(0, 3, 12)
        truth[::3] = 0
        y = a @ truth + rng.normal(0, 0.4, 18)
        lam, variance = 1.3, 0.4
        for layout in ("1d", "2d"):
            basis = DCTBasis((3, 4), layout)
            d = np.column_stack([basis.analysis(v) for v in np.eye(12)])
            constraints = LinearConstraint(np.block([[-d, np.eye(12)], [d, np.eye(12)]]), 0, np.inf)
            def fun(x):
                r = a @ x[:12]-y
                return np.dot(r,r)/variance + lam*x[12:].sum()
            def grad(x):
                return np.r_[2*a.T@(a@x[:12]-y)/variance, np.full(12, lam)]
            start = np.r_[np.ones(12), np.abs(d@np.ones(12)) + 1]
            oracle = minimize(fun, start, jac=grad, method="SLSQP", constraints=constraints,
                              bounds=Bounds(np.zeros(24), np.full(24, np.inf)),
                              options={"ftol": 1e-11, "maxiter": 2000})
            self.assertTrue(oracle.success, oracle.message)
            field, info = solve_roy_dct(csr_matrix(a), y, (3, 4), lam=lam,
                noise_variance=variance, dct_layout=layout, inner_maxiter=10000,
                inner_atol=1e-9, inner_rtol=1e-8, cg_rtol=1e-11)
            self.assertTrue(info["success"], info)
            self.assertAlmostEqual(info["fun"], oracle.fun, places=5)
            np.testing.assert_allclose(field.ravel(), oracle.x[:12], atol=1e-4)
            self.assertGreaterEqual(field.min(), 0)
            # This solution actually uses negative coefficients: z>=0 is wrong.
            self.assertLess(basis.analysis(field).min(), -0.01)

    def test_noise_weighting_and_no_hidden_half_factor(self):
        n, level, lam, variance = 12, 2.0, 3.0, 0.4
        expected = level-lam*variance/(2*np.sqrt(n))
        field, info = solve_roy_dct(eye(n), np.full(n,level), (3,4), lam=lam,
                                  noise_variance=variance, inner_atol=1e-9, inner_rtol=1e-9)
        self.assertTrue(info["success"])
        np.testing.assert_allclose(field, expected, atol=1e-7)
        zero, info = solve_roy_dct(eye(n), np.full(n,level), (3,4), lam=100,
                                 noise_variance=variance, inner_atol=1e-9, inner_rtol=1e-9)
        self.assertTrue(info["success"])
        np.testing.assert_allclose(zero, 0, atol=1e-7)

    def test_250000_pixel_matrix_free_dc_solution(self):
        # This size would require 500 GB for a dense float64 DCT basis.
        n = 250000
        lengths = csr_matrix((np.full(n, 1/np.sqrt(n)),
                              (np.zeros(n, dtype=int), np.arange(n))), shape=(1, n))
        field, info = solve_roy_dct(lengths, np.array([10.]), (500, 500),
            lam=.2, noise_variance=.01, initial_rain=0,
            inner_atol=1e-10, inner_rtol=1e-7, cg_rtol=1e-10)
        self.assertTrue(info["success"], info)
        np.testing.assert_allclose(field, (10-.2*.01/2)/np.sqrt(n), atol=1e-8)

    def test_nonlinear_jacobian_and_objective_descent(self):
        rng = np.random.default_rng(123)
        a = csr_matrix(rng.uniform(0,1,(15,6)))
        k, alpha = np.linspace(.1,.4,15), np.linspace(.8,1.3,15)
        model = LinkModel(a,k,alpha)
        u = rng.uniform(.5,2,6)
        direction = rng.normal(size=6)
        h = 1e-6
        numerical = (model.forward(u+h*direction)-model.forward(u-h*direction))/(2*h)
        np.testing.assert_allclose(model.jacobian(u,1e-6)@direction, numerical, rtol=1e-7, atol=1e-8)
        y = model.forward(u)
        field, info = solve_roy_dct(a,y,(2,3), k=k,alpha=alpha, lam=.1,
            noise_variance=.1, inner_maxiter=6000, inner_atol=1e-9, inner_rtol=1e-8,
            outer_rtol=1e-5, max_outer=100, damping=.001)
        self.assertTrue(info["success"], info)
        values = np.array([row["objective"] for row in info["history"]])
        self.assertTrue(np.all(np.diff(values) <= 1e-12))
        self.assertLess(values[-1], values[0]*.01)
        self.assertGreaterEqual(field.min(),0)
        self.assertEqual(info["method"],"roy_dct_nonlinear")

    def test_nonconvergence_and_invalid_inputs(self):
        _, info = solve_roy_dct(eye(6), np.ones(6), (2,3), inner_maxiter=1)
        self.assertFalse(info["success"])
        self.assertEqual(info["stop_reason"],"inner_maxiter")
        for kwargs in ({"noise_variance":0}, {"lam":-1}, {"initial_rain":-1},
                       {"dct_layout":"bad"}, {"inner_maxiter":0}, {"alpha":np.nan}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                solve_roy_dct(eye(6),np.ones(6),(2,3),**kwargs)

    def test_batch_adapter_and_linear_input_guard(self):
        payload = {
            "header":{"H":1,"W":2},
            "links":[{"link_index":0,"freq_ghz":38,"pol":"H","A_db":1.0}],
            "segments_by_link":{"0":[{"i":0,"j":0,"ds_m":1000}, {"i":0,"j":1,"ds_m":1000}]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/"input.json", Path(tmp)/"solution.npz"
            src.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError,"separately generated"):
                solve_and_save(src,dst,{"measurement_model":"paper_linear"})
            result = solve_and_save(src,dst,{"optimization":{"noise_variance":.1,"lam":.1,"inner_maxiter":5000}})
            self.assertTrue(result["success"], result)
            with np.load(dst) as output:
                self.assertEqual(output["R_hat"].shape,(1,2))
                self.assertEqual(str(output["meta_measurement_model"]),"itu_nonlinear")
                model = LinkModel(csr_matrix([[1.,1.]]), output["k"], output["alpha"])
                np.testing.assert_allclose(output["A_hat"],model.forward(output["R_hat"].ravel()))
            self.assertTrue(dst.with_name("solution_optinfo.json").exists())
            initial = np.array([[.3, 1.7]])
            with patch("cml_attenuation.ildw_baseline.ildw_field_from_est_input",
                       return_value=(initial, np.array([1.]))) as initialize:
                cfg = {"initialization": {"method": "ildw", "r_max_m": 12000},
                       "optimization": {"noise_variance": .1, "lam": .1, "inner_maxiter": 5000}}
                result = solve_and_save(src, dst, cfg)
                initialize.assert_called_once_with(src, r_max_m=12000., power=2., default_value=0.)
            saved = json.loads(dst.with_name("solution_optinfo.json").read_text())
            expected = np.sum((model.forward(initial.ravel())-1)**2)/.1 + .1*np.abs(DCTBasis((1, 2)).analysis(initial)).sum()
            self.assertAlmostEqual(saved["history"][0]["objective"], expected)
            self.assertEqual(result["init_method"], "ildw")
            self.assertIsNone(saved["settings"]["initial_rain"])
            with np.load(dst) as output:
                self.assertEqual(str(output["meta_init_method"]), "ildw")


if __name__ == "__main__":
    unittest.main()
