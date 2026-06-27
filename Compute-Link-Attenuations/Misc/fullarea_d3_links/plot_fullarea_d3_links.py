#!/usr/bin/env python3
"""
Build one full-area d3-bin map from many patch est_input JSON files and overlay links.

d3 at a pixel = distance to the 3rd-closest link segment (meters), computed per patch
in the patch-local frame, then mosaicked into a global RD grid.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import matplotlib.pyplot as plt

try:
    from scipy.spatial import cKDTree  # type: ignore
except Exception:
    cKDTree = None


def load_config_file(path: str | Path) -> dict:
    path = Path(path)
    suf = path.suffix.lower()
    if suf in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except Exception as e:
            raise RuntimeError("YAML config requires PyYAML (pip install pyyaml).") from e
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return {} if cfg is None else cfg
    if suf == ".json":
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {} if cfg is None else cfg
    raise ValueError("Config must be .yaml/.yml or .json")


def deep_get(d: dict, path: str, default=None):
    cur: Any = d
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def parse_distance_bins_m(edges: Sequence[float]) -> Tuple[np.ndarray, List[str]]:
    e = np.asarray(list(edges), dtype=np.float64)
    e = e[np.isfinite(e)]
    e = np.unique(e)
    e = e[e > 0]
    if e.size == 0:
        return np.zeros((0,), dtype=np.float64), [">=0"]
    labels: List[str] = [f"≤{int(e[0])}"]
    for i in range(1, len(e)):
        labels.append(f"({int(e[i-1])},{int(e[i])}]")
    labels.append(f">{int(e[-1])}")
    return e.astype(np.float64), labels


def list_est_input_files(cfg: dict, *, base_dir: Path) -> List[Path]:
    est_glob = deep_get(cfg, "input.est_input_glob", None)
    est_dir = deep_get(cfg, "input.est_input_dir", None)
    est_prefix = str(deep_get(cfg, "input.est_input_prefix", "est_input"))

    files: List[Path] = []
    if est_glob:
        pat = Path(str(est_glob))
        if pat.is_absolute():
            files = sorted(pat.parent.glob(pat.name))
        else:
            files = sorted((base_dir / pat.parent).glob(pat.name))
    elif est_dir:
        d = Path(str(est_dir))
        if not d.is_absolute():
            d = (base_dir / d).resolve()
        files = sorted(d.glob("*.json"))
    else:
        raise SystemExit("Provide input.est_input_glob or input.est_input_dir in config.")

    files = [p for p in files if p.name.startswith(est_prefix)]
    if not files:
        raise SystemExit("No est_input files found after applying input prefix/filter.")
    return files


def load_links_and_header(est_json_path: Path) -> Tuple[np.ndarray, dict]:
    with est_json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    header = payload["header"]
    links = payload.get("links", [])
    if not links:
        return np.zeros((0, 4), dtype=np.float64), header
    segs = np.zeros((len(links), 4), dtype=np.float64)
    for i, lnk in enumerate(links):
        segs[i, 0] = float(lnk["x0_m"])
        segs[i, 1] = float(lnk["y0_m"])
        segs[i, 2] = float(lnk["x1_m"])
        segs[i, 3] = float(lnk["y1_m"])
    return segs, header


def point_to_segments_distance(px: float, py: float, segs: np.ndarray, idxs: np.ndarray) -> np.ndarray:
    s = segs[idxs]
    x0 = s[:, 0]
    y0 = s[:, 1]
    x1 = s[:, 2]
    y1 = s[:, 3]
    dx = x1 - x0
    dy = y1 - y0
    den = dx * dx + dy * dy
    den = np.where(den == 0.0, 1e-12, den)
    t = ((px - x0) * dx + (py - y0) * dy) / den
    t = np.clip(t, 0.0, 1.0)
    cx = x0 + t * dx
    cy = y0 + t * dy
    return np.sqrt((px - cx) ** 2 + (py - cy) ** 2)


def compute_d3_distance_map(
    est_json_path: Path,
    *,
    sample_spacing_m: float = 250.0,
    k_query_samples: int = 48,
    chunk_size: int = 8000,
    max_samples_per_link: int = 200,
) -> np.ndarray:
    if cKDTree is None:
        raise RuntimeError("scipy is required (pip install scipy).")

    segs, header = load_links_and_header(est_json_path)
    h = int(header["H"])
    w = int(header["W"])
    if segs.shape[0] < 3:
        return np.full((h, w), np.nan, dtype=np.float64)

    pix = float(header.get("pixel_size_m", 125.0))
    xs = (np.arange(w, dtype=np.float64) + 0.5) * pix
    ys = (np.arange(h, dtype=np.float64) + 0.5) * pix
    xg, yg = np.meshgrid(xs, ys)
    pts = np.stack([xg.ravel(), yg.ravel()], axis=1)

    dx = segs[:, 2] - segs[:, 0]
    dy = segs[:, 3] - segs[:, 1]
    lens = np.sqrt(dx * dx + dy * dy)
    spacing = max(1.0, float(sample_spacing_m))

    sample_pts: List[np.ndarray] = []
    sample_to_link: List[np.ndarray] = []
    for li in range(segs.shape[0]):
        ll = float(lens[li])
        n = max(2, int(math.ceil(ll / spacing)) + 1)
        n = min(n, int(max_samples_per_link))
        t = np.linspace(0.0, 1.0, n, dtype=np.float64)
        x = segs[li, 0] + t * dx[li]
        y = segs[li, 1] + t * dy[li]
        sample_pts.append(np.stack([x, y], axis=1))
        sample_to_link.append(np.full((n,), li, dtype=np.int32))

    sample_xy = np.concatenate(sample_pts, axis=0)
    sample_link = np.concatenate(sample_to_link, axis=0)
    tree = cKDTree(sample_xy)

    d3 = np.full((pts.shape[0],), np.nan, dtype=np.float64)
    kq = max(12, int(k_query_samples))
    kq = min(kq, sample_xy.shape[0])

    for s in range(0, pts.shape[0], int(chunk_size)):
        e = min(pts.shape[0], s + int(chunk_size))
        q = pts[s:e]
        _, nn_idx = tree.query(q, k=kq, workers=-1)
        if nn_idx.ndim == 1:
            nn_idx = nn_idx[:, None]
        for bi in range(q.shape[0]):
            cand = np.unique(sample_link[nn_idx[bi]])
            if cand.size < 3:
                kq2 = min(sample_xy.shape[0], kq * 4)
                _, nn2 = tree.query(q[bi], k=kq2, workers=-1)
                cand = np.unique(sample_link[np.atleast_1d(nn2)])
            if cand.size == 0:
                continue
            ds = point_to_segments_distance(float(q[bi, 0]), float(q[bi, 1]), segs, cand)
            d3[s + bi] = float(np.partition(ds, 2)[2]) if ds.size >= 3 else float(np.nanmax(ds))
    return d3.reshape(h, w)


def patch_bounds_rd(header: dict) -> Tuple[float, float, float, float, float, int, int]:
    h = int(header["H"])
    w = int(header["W"])
    pix = float(header.get("pixel_size_m", 125.0))
    origin = header.get("origin_rd_m", {})
    x_min = float(origin["x_min"])
    y_max = float(origin["y_max"])
    x_max = x_min + w * pix
    y_min = y_max - h * pix
    return x_min, x_max, y_min, y_max, pix, h, w


def rd_from_local_xy(x_local: np.ndarray, y_local: np.ndarray, header: dict) -> Tuple[np.ndarray, np.ndarray]:
    origin = header.get("origin_rd_m", {})
    x_min = float(origin["x_min"])
    y_max = float(origin["y_max"])
    return x_min + x_local, y_max - y_local


def link_key_rd(x0: float, y0: float, x1: float, y1: float, tol_m: float) -> Tuple[int, ...]:
    q = max(1e-9, float(tol_m))
    a = (int(round(x0 / q)), int(round(y0 / q)))
    b = (int(round(x1 / q)), int(round(y1 / q)))
    if a <= b:
        return (a[0], a[1], b[0], b[1])
    return (b[0], b[1], a[0], a[1])


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot one global d3-bin map + links from patch est_input files.")
    ap.add_argument("--config", type=str, required=True, help="Path to YAML/JSON config.")
    args = ap.parse_args()

    cfg_path = Path(args.config).resolve()
    cfg = load_config_file(cfg_path)
    base_dir = cfg_path.parent

    est_files = list_est_input_files(cfg, base_dir=base_dir)
    bins_m = [float(v) for v in deep_get(cfg, "distance.bins_m", [125.0, 375.0, 750.0, 1500.0, 3125.0])]
    edges, labels = parse_distance_bins_m(bins_m)
    sample_spacing_m = float(deep_get(cfg, "distance.sample_spacing_m", 250.0))
    k_query_samples = int(deep_get(cfg, "distance.k_query_samples", 48))
    chunk_size = int(deep_get(cfg, "distance.chunk_size", 8000))
    max_samples_per_link = int(deep_get(cfg, "distance.max_samples_per_link", 200))

    overlap_mode = str(deep_get(cfg, "merge.overlap_mode", "min")).strip().lower()
    if overlap_mode not in {"min", "first"}:
        raise SystemExit("merge.overlap_mode must be one of: min, first")
    link_dedup_tol_m = float(deep_get(cfg, "merge.link_dedup_tol_m", 1.0))

    out_dir = Path(str(deep_get(cfg, "output.out_dir", "fullarea_output")))
    if not out_dir.is_absolute():
        out_dir = (base_dir / out_dir).resolve()
    images_subdir = str(deep_get(cfg, "output.images_subdir", "images"))
    out_png_name = str(deep_get(cfg, "output.filename", "fullarea_d3_bins_with_links.png"))
    out_png = out_dir / images_subdir / out_png_name

    dpi = int(deep_get(cfg, "plots.dpi", 150))
    show = bool(deep_get(cfg, "plots.show", False))

    # Pass 1: extents + pixel size consistency.
    headers: Dict[Path, dict] = {}
    xmins: List[float] = []
    xmaxs: List[float] = []
    ymins: List[float] = []
    ymaxs: List[float] = []
    pix_vals: List[float] = []
    for p in est_files:
        _, hdr = load_links_and_header(p)
        headers[p] = hdr
        x0, x1, y0, y1, pix, _, _ = patch_bounds_rd(hdr)
        xmins.append(x0); xmaxs.append(x1); ymins.append(y0); ymaxs.append(y1)
        pix_vals.append(pix)
    pix_ref = float(np.median(np.array(pix_vals, dtype=np.float64)))
    if np.max(np.abs(np.array(pix_vals, dtype=np.float64) - pix_ref)) > 1e-6:
        raise SystemExit("Inconsistent pixel_size_m across patches; cannot build one regular mosaic.")

    x_min_g = float(min(xmins))
    x_max_g = float(max(xmaxs))
    y_min_g = float(min(ymins))
    y_max_g = float(max(ymaxs))
    w_g = int(round((x_max_g - x_min_g) / pix_ref))
    h_g = int(round((y_max_g - y_min_g) / pix_ref))
    if w_g <= 0 or h_g <= 0:
        raise SystemExit("Computed global grid has invalid dimensions.")

    d3_global = np.full((h_g, w_g), np.nan, dtype=np.float64)
    seen_count = np.zeros((h_g, w_g), dtype=np.int32)

    link_unique: Dict[Tuple[int, ...], Tuple[float, float, float, float]] = {}

    # Pass 2: compute per-patch d3 and merge; collect deduplicated RD links.
    print(f"Est patches: {len(est_files)}")
    for i, p in enumerate(est_files, 1):
        hdr = headers[p]
        d3_patch = compute_d3_distance_map(
            p,
            sample_spacing_m=sample_spacing_m,
            k_query_samples=k_query_samples,
            chunk_size=chunk_size,
            max_samples_per_link=max_samples_per_link,
        )
        h, w = d3_patch.shape

        # map patch pixels to global indices
        xs_local = (np.arange(w, dtype=np.float64) + 0.5) * pix_ref
        ys_local = (np.arange(h, dtype=np.float64) + 0.5) * pix_ref
        x_local, y_local = np.meshgrid(xs_local, ys_local)
        x_rd, y_rd = rd_from_local_xy(x_local, y_local, hdr)
        jg = np.rint((x_rd - x_min_g) / pix_ref - 0.5).astype(np.int64)
        ig = np.rint((y_max_g - y_rd) / pix_ref - 0.5).astype(np.int64)

        inside = (ig >= 0) & (ig < h_g) & (jg >= 0) & (jg < w_g) & np.isfinite(d3_patch)
        ii = ig[inside]
        jj = jg[inside]
        vv = d3_patch[inside]
        if overlap_mode == "first":
            empty = np.isnan(d3_global[ii, jj])
            d3_global[ii[empty], jj[empty]] = vv[empty]
        else:
            cur = d3_global[ii, jj]
            upd = np.isnan(cur) | (vv < cur)
            d3_global[ii[upd], jj[upd]] = vv[upd]
        seen_count[ii, jj] += 1

        segs, _ = load_links_and_header(p)
        if segs.size > 0:
            x0, y0 = rd_from_local_xy(segs[:, 0], segs[:, 1], hdr)
            x1, y1 = rd_from_local_xy(segs[:, 2], segs[:, 3], hdr)
            for k in range(segs.shape[0]):
                kk = link_key_rd(float(x0[k]), float(y0[k]), float(x1[k]), float(y1[k]), link_dedup_tol_m)
                if kk not in link_unique:
                    link_unique[kk] = (float(x0[k]), float(y0[k]), float(x1[k]), float(y1[k]))
        if i == 1 or i % 10 == 0 or i == len(est_files):
            print(f"  merged {i}/{len(est_files)}")

    # Bin to discrete indices for display.
    finite = np.isfinite(d3_global)
    if edges.size == 0:
        bin_idx = np.zeros_like(d3_global, dtype=np.int32)
    else:
        bin_idx = np.digitize(d3_global, edges, right=True).astype(np.int32)
    bin_plot = np.ma.masked_where(~finite, bin_idx)

    from matplotlib.colors import ListedColormap  # type: ignore

    n_bins = len(labels)
    cmap_vals = plt.cm.plasma(np.linspace(0.08, 0.95, max(1, n_bins)))
    cmap = ListedColormap(cmap_vals)
    cmap.set_bad(color="#d9d9d9")

    fig, ax = plt.subplots(figsize=(11, 9), dpi=dpi)
    im = ax.imshow(
        bin_plot,
        cmap=cmap,
        vmin=-0.5,
        vmax=max(0, n_bins - 1) + 0.5,
        origin="upper",
        extent=(x_min_g, x_max_g, y_min_g, y_max_g),
        interpolation="nearest",
        aspect="equal",
    )

    for x0, y0, x1, y1 in link_unique.values():
        ax.plot([x0, x1], [y0, y1], color="black", linewidth=0.5, alpha=0.55)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_ticks(np.arange(n_bins))
    cbar.set_ticklabels(labels)
    cbar.ax.set_ylabel("d3 distance bin (m)")

    overlap_cells = int(np.sum(seen_count > 1))
    ax.set_title(
        "Full-area d3-bin mosaic with links\n"
        f"patches={len(est_files)}, unique_links={len(link_unique)}, overlap_cells={overlap_cells}"
    )
    ax.set_xlabel("RD x (m)")
    ax.set_ylabel("RD y (m)")
    ax.grid(False)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi)
    if show:
        plt.show()
    plt.close(fig)
    print(f"Wrote: {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

