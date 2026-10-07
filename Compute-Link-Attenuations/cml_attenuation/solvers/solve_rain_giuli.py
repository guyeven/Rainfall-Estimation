"""Giuli (1991) attenuation-space quadratic reconstruction.

Sparse, exactly integrated bilinear tents; stencil D and its exact adjoint.
No dense link-by-pixel matrix, B, or Hessian is constructed.
"""
from __future__ import annotations

import time
import numpy as np
from scipy.sparse import csr_matrix
from scipy.optimize import minimize


def positive(name, value, allow_zero=False):
    value = float(value)
    if not np.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        raise ValueError(f"{name} must be finite and {'nonnegative' if allow_zero else 'positive'}")
    return value


def grid_shape(shape):
    if len(shape) != 2 or any(int(n) != n or n < 1 for n in shape):
        raise ValueError('shape must contain two positive integers')
    return tuple(map(int, shape))


def tent_matrix(endpoints, shape, pixel_size_m):
    """Integrals of pixel-center bilinear tents along straight links (km).

    Coordinates are patch-local meters, x right, y down. Split at all crossed
    center lines (piecewise quadratic along a link), then use exact two-point
    Gauss integration. Outer tents taper to zero outside their centers, as in
    the paper; no boundary renormalization is applied.
    """
    h, w = grid_shape(shape)
    delta = positive('pixel_size_m', pixel_size_m)
    ends = np.asarray(endpoints, dtype=float)
    if ends.ndim != 2 or ends.shape[1] != 4 or not np.all(np.isfinite(ends)):
        raise ValueError('endpoints must be a finite (m,4) array')
    if np.any(ends < 0) or np.any(ends[:, [0,2]] > w*delta) or np.any(ends[:, [1,3]] > h*delta):
        raise ValueError('link endpoints must lie inside the patch')
    rows, cols, values = [], [], []
    for m, (x0,y0,x1,y1) in enumerate(ends):
        dx, dy = x1-x0, y1-y0
        length = np.hypot(dx,dy)/1000
        if length == 0:
            continue
        breaks = [np.array([0.,1.])]
        for origin, direction, count in [(x0,dx,w),(y0,dy,h)]:
            if direction != 0:
                t = ((np.arange(count)+.5)*delta-origin)/direction
                breaks.append(t[(t>0)&(t<1)])
        t = np.unique(np.concatenate(breaks))
        mid, half = (t[1:]+t[:-1])/2, np.diff(t)/2
        samples = (mid[:,None]+half[:,None]*np.array([-1.,1.])/np.sqrt(3)).ravel()
        weights = np.repeat(half*length,2)
        x, y = (x0+dx*samples)/delta-.5, (y0+dy*samples)/delta-.5
        left, top = np.floor(x).astype(int), np.floor(y).astype(int)
        for di in (0,1):
            for dj in (0,1):
                i,j = top+di,left+dj
                valid = (i>=0)&(i<h)&(j>=0)&(j<w)
                val = weights*(1-np.abs(x-j))*(1-np.abs(y-i))
                valid &= val>0
                rows.extend(np.full(np.sum(valid),m)); cols.extend((i[valid]*w+j[valid]).tolist())
                values.extend(val[valid].tolist())
    a = csr_matrix((values,(rows,cols)),shape=(len(ends),h*w))
    a.sum_duplicates()
    return a


class NeighborDeviation:
    """D: interior value minus mean of eight neighbors; B = D.T D."""
    def __init__(self, shape):
        self.shape = grid_shape(shape)
        self.inner = (max(0,self.shape[0]-2),max(0,self.shape[1]-2))

    def forward(self, x):
        a = np.asarray(x).reshape(self.shape)
        h,w = self.inner
        out = a[1:1+h,1:1+w].copy()
        for di in range(3):
            for dj in range(3):
                if (di,dj)!=(1,1):
                    out -= a[di:di+h,dj:dj+w]/8
        return out

    def adjoint(self, z):
        z = np.asarray(z).reshape(self.inner)
        h,w = self.inner
        out = np.zeros(self.shape)
        out[1:1+h,1:1+w] += z
        for di in range(3):
            for dj in range(3):
                if (di,dj)!=(1,1):
                    out[di:di+h,dj:dj+w] -= z/8
        return out.ravel()


def solve_giuli(a, observations, shape, *, data_weight=2.5, smoothness_weight=15.,
                initial_attenuation=0., maxiter=5000, gtol=1e-6):
    """Min .5||k||² + .5*b||Dk||² + .5*a||Ak-p||² subject to k>=0.

    L-BFGS-B is a scalable numerical replacement for the paper's projected
    gradient iteration. Success requires a projected-gradient KKT tolerance,
    not merely small objective changes. Parameters follow printed Eq. (19).
    """
    shape = grid_shape(shape)
    a = csr_matrix(a,dtype=float)
    y = np.asarray(observations,dtype=float)
    n = int(np.prod(shape))
    if a.shape != (y.size,n) or y.ndim != 1 or not np.all(np.isfinite(y)) or np.any(y<0):
        raise ValueError('incompatible dimensions or invalid observations')
    if not np.all(np.isfinite(a.data)) or np.any(a.data<0):
        raise ValueError('A must contain finite nonnegative line integrals')
    dw = positive('data_weight',data_weight,True)
    sw = positive('smoothness_weight',smoothness_weight,True)
    tol = positive('gtol',gtol)
    if int(maxiter)!=maxiter or maxiter<1:
        raise ValueError('maxiter must be a positive integer')
    start = np.broadcast_to(np.asarray(initial_attenuation,dtype=float),shape).ravel().copy()
    if not np.all(np.isfinite(start)) or np.any(start<0):
        raise ValueError('initial_attenuation must be finite and nonnegative')
    d = NeighborDeviation(shape)
    def objective(x):
        residual, deviation = a@x-y,d.forward(x)
        value = .5*(x@x+sw*np.sum(deviation**2)+dw*(residual@residual))
        grad = x+sw*d.adjoint(deviation)+dw*(a.T@residual)
        return value,grad
    initial_objective = float(objective(start)[0])
    started = time.perf_counter()
    result = minimize(objective,start,jac=True,method='L-BFGS-B',bounds=[(0,None)]*n,
                      options=dict(maxiter=int(maxiter),gtol=tol,ftol=0.,maxls=40,maxcor=10))
    value,grad = objective(result.x)
    projected = np.where((result.x<=0)&(grad>0),0,grad)
    pg = float(np.max(np.abs(projected)))
    success = bool(pg<=tol)
    diag = dict(success=success,status=0 if success else 1,
                stop_reason='projected_gradient' if success else ('maxiter' if result.nit>=maxiter else 'optimizer_stopped'),
                message=str(result.message),nit=int(result.nit),fun=float(value),
                initial_objective=initial_objective,proj_grad_inf=pg,gtol=tol,
                data_weight=dw,smoothness_weight=sw,maxiter=int(maxiter),
                optimizer_seconds=time.perf_counter()-started,optimizer='L-BFGS-B',
                method='giuli_convex',nnz=int(a.nnz),
                operator_bytes=int(a.data.nbytes+a.indices.nbytes+a.indptr.nbytes))
    return result.x.reshape(shape),diag
