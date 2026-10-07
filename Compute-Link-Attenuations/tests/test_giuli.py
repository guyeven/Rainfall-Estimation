"""Independent geometry, adjoint, optimum, and large-grid checks."""
import sys
from pathlib import Path
import unittest
import numpy as np
from scipy.integrate import quad
from scipy.optimize import nnls
from scipy.sparse import csr_matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cml_attenuation.solvers.solve_rain_giuli import tent_matrix, NeighborDeviation, solve_giuli


class GiuliTests(unittest.TestCase):
    def test_exact_tent_integrals_and_reversed_paths(self):
        endpoints = np.array([[0,1500,3000,1500],[240,170,2760,2830]])
        a = tent_matrix(endpoints,(3,3),1000).toarray()
        self.assertAlmostEqual(a[0,4],1.)
        for row,(x0,y0,x1,y1) in enumerate(endpoints):
            length=np.hypot(x1-x0,y1-y0)/1000
            for i in range(3):
                for j in range(3):
                    def f(t):
                        return max(1-abs((x0+(x1-x0)*t)/1000-(j+.5)),0)*max(1-abs((y0+(y1-y0)*t)/1000-(i+.5)),0)*length
                    expected=quad(f,0,1,epsabs=1e-9,points=np.linspace(0,1,101),limit=300)[0]
                    self.assertAlmostEqual(a[row,i*3+j],expected,places=7)
        np.testing.assert_allclose(a,tent_matrix(endpoints[:,[2,3,0,1]],(3,3),1000).toarray(),atol=1e-14)

    def test_stencil_adjoint_including_small_grids(self):
        rng=np.random.default_rng(6)
        for shape in [(1,4),(2,2),(3,3),(4,7)]:
            d=NeighborDeviation(shape)
            x=rng.normal(size=np.prod(shape));z=rng.normal(size=d.inner)
            self.assertAlmostEqual(np.sum(d.forward(x)*z),x@d.adjoint(z),places=12)

    def test_solution_matches_nnls_and_initialization_independent(self):
        rng=np.random.default_rng(41);shape=(4,5);n=20
        a=rng.uniform(size=(8,n));y=rng.uniform(0,5,8)
        d=NeighborDeviation(shape)
        dense_d=np.column_stack([d.forward(v).ravel() for v in np.eye(n)])
        design=np.vstack([np.eye(n),np.sqrt(3)*dense_d,np.sqrt(2)*a])
        target=np.r_[np.zeros(n+dense_d.shape[0]),np.sqrt(2)*y]
        expected,_=nnls(design,target)
        for init in [0.,.2,10.]:
            field,info=solve_giuli(a,y,shape,data_weight=2,smoothness_weight=3,initial_attenuation=init,gtol=1e-6)
            self.assertTrue(info['success'],info)
            np.testing.assert_allclose(field.ravel(),expected,atol=2e-6)

    def test_large_grid_sparse_and_nonconvergence(self):
        a=tent_matrix([[0,30000,62500,30000]],(500,500),125)
        self.assertLess(a.nnz,2000)
        self.assertLess(a.data.nbytes+a.indices.nbytes+a.indptr.nbytes,50000)
        field,info=solve_giuli(a,[10],(500,500),maxiter=1,initial_attenuation=.2)
        self.assertEqual(field.shape,(500,500));self.assertFalse(info['success'])
        self.assertEqual(info['stop_reason'],'maxiter')

    def test_invalid_input(self):
        for kwargs in [dict(data_weight=-1),dict(gtol=0),dict(initial_attenuation=-1)]:
            with self.assertRaises(ValueError):solve_giuli(csr_matrix([[1]]),[1],(1,1),**kwargs)
        with self.assertRaises(ValueError):tent_matrix([[-1,0,1,1]],(3,3),1)
