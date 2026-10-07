
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Rain attenuation model (existing project module)
from itu_r_p8383 import gamma_specific, Pol

app = FastAPI()


# -----------------------------
# Models
# -----------------------------
class InputParams(BaseModel):
    # Geometry
    w: float = Field(10.0, description="Patch width (km)")
    h: float = Field(10.0, description="Patch height (km)")
    l: float = Field(2.0, description="Grid scale / star length scale (km)")

    # Grid / inner cell
    inner_cell_frac: float = Field(1.0 / 3.0, description="Inner cell side length fraction of grid cell side length")

    # Star angles
    theta_total_min: float = Field(30.0, description="Min total star sweep angle (deg)")
    theta_total_max: float = Field(360.0, description="Max total star sweep angle (deg)")
    theta_mean: float = Field(45.0, description="Mean per-segment angle (deg)")
    theta_dev: float = Field(math.sqrt(45.0), description="Allowed deviation around mean per-segment angle (deg)")
    dirichlet_alpha: float = Field(1.0, description="Dirichlet concentration for theta_i weights")

    # Length policy
    link_length_min: float = Field(5.0, description="Hard minimum link length (km)")
    link_pref_min: float = Field(10.0, description="Preferred minimum link length (km)")
    link_pref_max: float = Field(15.0, description="Preferred maximum link length (km)")
    link_length_max: float = Field(27.0, description="Hard maximum link length (km)")
    length_noise_sigma: float = Field(1.0, description="Sigma in l*(1+N(0,sigma))")

    # Ring links
    ring_center_scale: float = Field(1.0, description="Scale for ring center count: round(scale*sqrt(l_w*l_h))")

    # Frequency feasibility inputs (kept compatible)
    frequencies: List[float] = Field(default_factory=list, description="Candidate frequencies (GHz)")
    Rmax: float = Field(25.0, description="Maximum rain rate (mm/h)")
    attenuation_max: float = Field(5.0, description="Maximum allowed attenuation (dB)")
    polarization: Pol = Field("horizontal", description="Polarization: horizontal|vertical|circular")

    # Optional: reproducibility
    seed: Optional[int] = Field(None, description="Optional RNG seed for reproducibility")


class GridOut(BaseModel):
    nx: int
    ny: int
    l_w: float
    l_h: float
    inner_cell_frac: float


class PointOut(BaseModel):
    id: int
    x: float
    y: float
    cell_i: int
    cell_j: int
    type: str = "center"


class LinkOut(BaseModel):
    id: int
    type: str  # "star" | "ring"
    from_point_id: Optional[int]  # center id for star/ring
    to_point_id: Optional[int]    # center id for ring, None for star leaf endpoints
    from_coord: Tuple[float, float]
    to_coord: Tuple[float, float]
    length: float
    max_allowed_frequency: Optional[float] = None
    assigned_frequency: Optional[float] = None


class OutputData(BaseModel):
    w: float
    h: float
    l: float
    grid: GridOut
    frequencies: List[float]
    points: List[PointOut]
    links: List[LinkOut]


# -----------------------------
# Helpers: grid
# -----------------------------
def compute_grid(w: float, h: float, l: float) -> Tuple[int, int, float, float]:
    if w <= 0 or h <= 0:
        raise ValueError("w and h must be positive")
    if l <= 0:
        raise ValueError("l must be positive")

    nx = int(math.ceil(w / (2.0 * l)))
    ny = int(math.ceil(h / (2.0 * l)))
    nx = max(1, nx)
    ny = max(1, ny)
    l_w = w / nx
    l_h = h / ny
    return nx, ny, l_w, l_h


def inner_cell_bounds(i: int, j: int, l_w: float, l_h: float, inner_frac: float) -> Tuple[float, float, float, float]:
    x0, x1 = i * l_w, (i + 1) * l_w
    y0, y1 = j * l_h, (j + 1) * l_h
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    iw, ih = inner_frac * l_w, inner_frac * l_h
    return cx - iw / 2.0, cx + iw / 2.0, cy - ih / 2.0, cy + ih / 2.0


# -----------------------------
# Helpers: angles (Dirichlet)
# -----------------------------
def dirichlet(alpha: float, k: int) -> List[float]:
    """Simple Dirichlet sampler using Gamma."""
    if k <= 0:
        raise ValueError("k must be positive")
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    xs = [random.gammavariate(alpha, 1.0) for _ in range(k)]
    s = sum(xs)
    if s <= 0:
        # extremely unlikely; fall back to uniform
        return [1.0 / k] * k
    return [x / s for x in xs]


def choose_k(theta_total: float, a: float, b: float) -> int:
    """
    Choose a feasible k such that k*a <= theta_total <= k*b.
    Default: choose the smallest feasible k (more stable leaf count).
    """
    k_min = int(math.ceil(theta_total / b))
    k_max = int(math.floor(theta_total / a))
    if k_max < 1 or k_min > k_max:
        raise ValueError("No feasible k for theta_total with given bounds")
    return max(1, k_min)


def sample_theta_increments(theta_total: float, theta_mean: float, theta_dev: float, alpha: float) -> List[float]:
    """
    Sample a sequence {theta_i} such that:
      - sum(theta_i) == theta_total
      - each theta_i in [theta_mean-theta_dev, theta_mean+theta_dev]
    Primary method: scaled Dirichlet (user spec), with robust k-search.
    Fallback: deterministic bounded composition (guaranteed if feasible).
    """
    a = theta_mean - theta_dev
    b = theta_mean + theta_dev
    if a <= 0:
        raise ValueError("theta_mean - theta_dev must be > 0")
    if theta_total <= 0:
        raise ValueError("theta_total must be > 0")
    if b <= a:
        raise ValueError("theta_mean + theta_dev must be > theta_mean - theta_dev")

    # Feasible k range for bounded parts:
    # k*a <= theta_total <= k*b  <=>  theta_total/b <= k <= theta_total/a
    k_min = int(math.ceil(theta_total / b))
    k_max = int(math.floor(theta_total / a))
    if k_max < 1:
        raise ValueError("No feasible k (theta_total too small for bounds)")
    k_min = max(1, k_min)
    if k_min > k_max:
        raise ValueError("No feasible k for bounded theta increments")

    # Pick a preferred k near theta_total/theta_mean, then explore neighbors.
    k0 = int(round(theta_total / max(1e-9, theta_mean)))
    k0 = min(max(k0, k_min), k_max)

    # Build trial order: k0, k0±1, k0±2, ... within [k_min,k_max]
    trial_ks = [k0]
    for d in range(1, (k_max - k_min) + 1):
        if k0 - d >= k_min:
            trial_ks.append(k0 - d)
        if k0 + d <= k_max:
            trial_ks.append(k0 + d)
        if len(trial_ks) >= (k_max - k_min + 1):
            break

    # Dirichlet rejection sampling: robust attempts per k (bounded)
    # Increase attempts for tight bounds; but cap to avoid runaway.
    width = max(1e-9, (b - a))
    tightness = min(50.0, max(1.0, theta_mean / width))
    base_tries = 4000
    tries_per_k = int(min(50000, base_tries * tightness))

    for k in trial_ks:
        for _ in range(tries_per_k):
            p = dirichlet(alpha, k)
            incs = [theta_total * pi for pi in p]
            if all(a <= t <= b for t in incs):
                return incs

    # Fallback: deterministic bounded composition (guaranteed if feasible)
    # Start near equal split, clamp to bounds, then redistribute residual.
    k = k0
    vals = [theta_total / k] * k
    vals = [min(max(v, a), b) for v in vals]
    s = sum(vals)
    diff = theta_total - s

    # Redistribute diff within available slack
    # If diff>0: add up to (b - val). If diff<0: subtract up to (val - a).
    max_iters = 10000
    it = 0
    while abs(diff) > 1e-9 and it < max_iters:
        it += 1
        if diff > 0:
            # indices with room to increase
            idxs = [i for i, v in enumerate(vals) if v < b - 1e-12]
            if not idxs:
                break
            per = diff / len(idxs)
            for i in idxs:
                add = min(per, b - vals[i])
                vals[i] += add
                diff -= add
        else:
            # indices with room to decrease
            idxs = [i for i, v in enumerate(vals) if v > a + 1e-12]
            if not idxs:
                break
            per = (-diff) / len(idxs)
            for i in idxs:
                sub = min(per, vals[i] - a)
                vals[i] -= sub
                diff += sub

    # Final sanity
    if not (abs(sum(vals) - theta_total) < 1e-6 and all(a - 1e-6 <= t <= b + 1e-6 for t in vals)):
        raise ValueError("Failed to sample bounded theta_i via scaled Dirichlet (and fallback failed)")
    # Small numerical cleanup: enforce exact sum by adjusting last element within bounds
    residual = theta_total - sum(vals[:-1])
    vals[-1] = min(max(residual, a), b)
    # Fix any tiny sum drift again
    drift = theta_total - sum(vals)
    vals[-1] = min(max(vals[-1] + drift, a), b)
    return vals


# -----------------------------
# Helpers: lengths
# -----------------------------
def normal(mu: float, sigma: float) -> float:
    return random.gauss(mu, sigma)


def sample_length_truncated(mu: float, sigma: float, lo: float, hi: float, tries: int = 2000) -> float:
    if hi < lo:
        raise ValueError("Invalid truncation range")
    if sigma <= 0:
        # degenerate
        return min(hi, max(lo, mu))
    for _ in range(tries):
        x = normal(mu, sigma)
        if lo <= x <= hi:
            return x
    # fallback: clamp
    return min(hi, max(lo, mu))


def sample_star_length(l: float, sigma_unitless: float,
                      hard_min: float, pref_min: float, pref_max: float, hard_max: float) -> float:
    """
    Implements:
      - hard bounds [hard_min, hard_max] with resampling
      - preference: most in [pref_min,pref_max], very few below, few above
    Uses the raw model L = l*(1 + N(0,sigma_unitless)).
    """
    if l <= 0:
        raise ValueError("l must be positive")
    if hard_min <= 0 or hard_max <= 0:
        raise ValueError("Length bounds must be positive")
    if hard_max < hard_min:
        raise ValueError("hard_max must be >= hard_min")

    # Mixture probabilities (constants; can be exposed later)
    p_pref = 0.80
    p_short = 0.10
    p_long = 0.10

    r = random.random()
    if r < p_pref:
        lo, hi = pref_min, pref_max
    elif r < p_pref + p_short:
        lo, hi = hard_min, max(hard_min, pref_min)
    else:
        lo, hi = min(hard_max, pref_max), hard_max

    lo = max(lo, hard_min)
    hi = min(hi, hard_max)

    # Convert unitless sigma to km sigma around mu=l
    mu = l
    sigma_km = abs(l) * max(0.0, sigma_unitless)

    # Rejection-sample the raw model by sampling in the chosen band:
    # we approximate by truncated normal around mu within [lo,hi]
    L = sample_length_truncated(mu, sigma_km, lo, hi)

    # Hard resampling if still outside bounds (shouldn't happen, but keep strict)
    if not (hard_min <= L <= hard_max):
        return sample_star_length(l, sigma_unitless, hard_min, pref_min, pref_max, hard_max)
    return L


# -----------------------------
# Helpers: geometry and containment
# -----------------------------
def endpoint_from_polar(x: float, y: float, angle_deg: float, length: float) -> Tuple[float, float]:
    ang = math.radians(angle_deg)
    return x + length * math.cos(ang), y + length * math.sin(ang)


def inside_patch(x: float, y: float, w: float, h: float) -> bool:
    return (0.0 <= x <= w) and (0.0 <= y <= h)


def clip_ray_to_patch(x: float, y: float, angle_deg: float, w: float, h: float) -> Tuple[float, float]:
    """
    Clip a ray starting at (x,y) in direction angle_deg to the patch boundary.
    Returns the first intersection point with the rectangle boundary in that direction.
    Assumes start is inside.
    """
    ang = math.radians(angle_deg)
    dx, dy = math.cos(ang), math.sin(ang)

    ts = []
    eps = 1e-12

    # x=0 and x=w
    if abs(dx) > eps:
        t0 = (0.0 - x) / dx
        tw = (w - x) / dx
        if t0 > 0: ts.append(t0)
        if tw > 0: ts.append(tw)

    # y=0 and y=h
    if abs(dy) > eps:
        t0 = (0.0 - y) / dy
        th = (h - y) / dy
        if t0 > 0: ts.append(t0)
        if th > 0: ts.append(th)

    # choose smallest positive t that lands on boundary within box
    t_best = None
    xb = yb = None
    for t in sorted(ts):
        xx = x + t * dx
        yy = y + t * dy
        if -1e-9 <= xx <= w + 1e-9 and -1e-9 <= yy <= h + 1e-9:
            t_best = t
            xb, yb = xx, yy
            break

    if t_best is None:
        # fallback: no movement
        return x, y
    return float(xb), float(yb)


def euclid(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# -----------------------------
# Frequencies
# -----------------------------
def sanitize_frequencies(freqs: List[float]) -> List[float]:
    cleaned = []
    for f in freqs or []:
        try:
            ff = float(f)
        except Exception:
            continue
        if ff > 0.0 and math.isfinite(ff):
            cleaned.append(ff)
    cleaned = sorted(set(cleaned))
    if not cleaned:
        cleaned = list(range(1, 101, 3))
    return cleaned


def compute_max_freq(length_km: float, freqs: List[float], Rmax: float, att_max: float, pol: str) -> Optional[float]:
    max_ok: Optional[float] = None
    for f in freqs:
        gamma = gamma_specific(f, Rmax, pol)
        if gamma * length_km <= att_max:
            max_ok = f
    return max_ok


# -----------------------------
# Ring selection + MST (Prim)
# -----------------------------
def largest_component(points: List[int], coords: List[Tuple[float, float]], max_edge: float) -> List[int]:
    if len(points) <= 1:
        return points[:]
    # build adjacency by threshold
    adj = {pid: [] for pid in points}
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            a = points[i]
            b = points[j]
            if euclid(coords[a], coords[b]) <= max_edge:
                adj[a].append(b)
                adj[b].append(a)

    seen = set()
    best = []
    for p in points:
        if p in seen:
            continue
        stack = [p]
        comp = []
        seen.add(p)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        if len(comp) > len(best):
            best = comp
    return best


def mst_prim(nodes: List[int], coords: List[Tuple[float, float]]) -> List[Tuple[int, int, float]]:
    """Return MST edges (u,v,dist) over nodes using Prim."""
    if len(nodes) < 2:
        return []
    in_tree = set([nodes[0]])
    edges: List[Tuple[int, int, float]] = []

    # maintain best connection for each outside node
    best = {}
    for v in nodes[1:]:
        best[v] = (nodes[0], euclid(coords[nodes[0]], coords[v]))

    while len(in_tree) < len(nodes):
        # pick outside node with smallest dist
        v_min = None
        u_min = None
        d_min = float("inf")
        for v, (u, d) in best.items():
            if v not in in_tree and d < d_min:
                v_min, u_min, d_min = v, u, d
        if v_min is None or u_min is None:
            break
        in_tree.add(v_min)
        edges.append((u_min, v_min, d_min))
        # update best distances
        for v in nodes:
            if v in in_tree:
                continue
            d = euclid(coords[v_min], coords[v])
            if v not in best or d < best[v][1]:
                best[v] = (v_min, d)
    return edges


# -----------------------------
# Main endpoint
# -----------------------------
@app.post("/generate_links", response_model=OutputData)
def generate_links(params: InputParams) -> OutputData:
    # seed
    if params.seed is not None:
        random.seed(int(params.seed))

    w = float(params.w)
    h = float(params.h)
    l = float(params.l)

    if w <= 0 or h <= 0 or l <= 0:
        raise HTTPException(status_code=422, detail="w, h, l must be positive")

    # sanitize inputs
    inner_frac = float(params.inner_cell_frac)
    inner_frac = max(0.0, min(1.0, inner_frac))

    # grid
    nx, ny, l_w, l_h = compute_grid(w, h, l)
    grid_out = GridOut(nx=nx, ny=ny, l_w=l_w, l_h=l_h, inner_cell_frac=inner_frac)

    # frequencies
    freqs = sanitize_frequencies(params.frequencies)

    # compute angle bounds
    a = float(params.theta_mean) - float(params.theta_dev)
    b = float(params.theta_mean) + float(params.theta_dev)
    if a <= 0:
        raise HTTPException(status_code=422, detail="theta_mean - theta_dev must be > 0")
    if params.theta_total_min >= params.theta_total_max:
        raise HTTPException(status_code=422, detail="theta_total_min must be < theta_total_max")

    # centers: one per cell (id matches index in coords list)
    centers: List[PointOut] = []
    coords: List[Tuple[float, float]] = []

    cid = 0
    for j in range(ny):
        for i in range(nx):
            xmin, xmax, ymin, ymax = inner_cell_bounds(i, j, l_w, l_h, inner_frac)
            x = random.uniform(xmin, xmax)
            y = random.uniform(ymin, ymax)
            centers.append(PointOut(id=cid, x=x, y=y, cell_i=i, cell_j=j))
            coords.append((x, y))
            cid += 1

    links: List[LinkOut] = []
    lid = 0

    # star links
    for c in centers:
        cx, cy = c.x, c.y

        # sample feasible theta_total
        theta_total = None
        for _ in range(2000):
            t = random.uniform(params.theta_total_min, params.theta_total_max)
            # feasibility requires existence of k s.t. k*a <= t <= k*b
            k_min = int(math.ceil(t / b))
            k_max = int(math.floor(t / a))
            if k_max >= max(1, k_min):
                theta_total = t
                break
        if theta_total is None:
            # fallback: clamp to nearest feasible by trying t=params.theta_total_max
            theta_total = float(params.theta_total_max)

        # sample theta increments
        try:
            theta_incs = sample_theta_increments(theta_total, params.theta_mean, params.theta_dev, params.dirichlet_alpha)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"theta increments sampling failed: {e}")

        k = len(theta_incs)
        delta = k + 1
        offset = random.uniform(0.0, 360.0)

        running = 0.0
        for i_link in range(1, delta + 1):
            if i_link <= k:
                running += theta_incs[i_link - 1]
            angle = offset + running

            # sample length and angle until endpoint inside patch
            x2 = y2 = None
            L = None
            for _ in range(2000):
                L_try = sample_star_length(
                    l,
                    params.length_noise_sigma,
                    params.link_length_min,
                    params.link_pref_min,
                    params.link_pref_max,
                    params.link_length_max,
                )
                # allow resampling angle too for containment
                angle_try = angle if _ < 50 else random.uniform(0.0, 360.0)
                xx, yy = endpoint_from_polar(cx, cy, angle_try, L_try)
                if inside_patch(xx, yy, w, h):
                    x2, y2, L = xx, yy, L_try
                    angle = angle_try
                    break

            if x2 is None or y2 is None or L is None:
                # last-resort: clip ray to boundary and set L accordingly
                x2, y2 = clip_ray_to_patch(cx, cy, angle, w, h)
                L = euclid((cx, cy), (x2, y2))
                # if clip length violates min, just skip this link
                if L < params.link_length_min:
                    continue

            length = euclid((cx, cy), (x2, y2))

            max_f = compute_max_freq(length, freqs, params.Rmax, params.attenuation_max, str(params.polarization)) if freqs else None
            assigned = max_f

            links.append(
                LinkOut(
                    id=lid,
                    type="star",
                    from_point_id=c.id,
                    to_point_id=None,
                    from_coord=(cx, cy),
                    to_coord=(float(x2), float(y2)),
                    length=float(length),
                    max_allowed_frequency=max_f,
                    assigned_frequency=assigned,
                )
            )
            lid += 1

    # ring centers selection
    n_ring = int(round(params.ring_center_scale * math.sqrt(l_w * l_h)))
    n_ring = max(0, min(n_ring, len(centers)))

    ring_links: List[Tuple[int, int, float]] = []
    if n_ring >= 2:
        selected = random.sample([c.id for c in centers], n_ring)
        kept = largest_component(selected, coords, params.link_length_max)
        if len(kept) >= 2:
            mst_edges = mst_prim(kept, coords)
            for u, v, d in mst_edges:
                if d <= params.link_length_max:
                    ring_links.append((u, v, d))

    for u, v, d in ring_links:
        cu = coords[u]
        cv = coords[v]
        max_f = compute_max_freq(d, freqs, params.Rmax, params.attenuation_max, str(params.polarization)) if freqs else None
        assigned = max_f
        links.append(
            LinkOut(
                id=lid,
                type="ring",
                from_point_id=u,
                to_point_id=v,
                from_coord=(float(cu[0]), float(cu[1])),
                to_coord=(float(cv[0]), float(cv[1])),
                length=float(d),
                max_allowed_frequency=max_f,
                assigned_frequency=assigned,
            )
        )
        lid += 1

    return OutputData(
        w=w,
        h=h,
        l=l,
        grid=grid_out,
        frequencies=freqs,
        points=centers,
        links=links,
    )
