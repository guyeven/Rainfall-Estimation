from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from batch_analyze_multi import (
    assign_bin_labels,
    compute_dk_maps,
    compute_dk_maps_sampled_points,
    parse_bins,
)


def _resolve_path(p: str | Path, *, base_dir: Optional[Path]) -> Path:
    pp = Path(p)
    if pp.is_absolute():
        return pp
    if base_dir is None:
        return pp.resolve()
    return (base_dir / pp).resolve()


def _load_npz_field(path: Path) -> np.ndarray:
    with np.load(path, allow_pickle=True) as z:
        if "R_hat" in z:
            return np.asarray(z["R_hat"], dtype=np.float64)
        # fallback: first array
        for k in z.files:
            return np.asarray(z[k], dtype=np.float64)
    raise ValueError(f"No arrays found in {path}")


def solve_and_save(est_input_json: str | Path, out_npz: str | Path, cfg: dict) -> None:
    """
    Hybrid solver A:
      1) Load base solver output (e.g., OPT_0p6) and form rainy mask (base > threshold).
      2) Compute distance bins (k-th closest link).
      3) For each bin, select a solver output and assemble pixel-wise field.
      4) Zero-out non-rainy pixels based on base solver mask.
    """
    base_dir = Path(cfg.get("_base_dir")) if cfg.get("_base_dir") else None
    hybrid = cfg.get("hybrid", {}) or {}

    base_solver = str(hybrid.get("base_solver", "OPT_0p6"))
    threshold = float(hybrid.get("threshold_mmph", 0.6))

    dist_cfg = hybrid.get("distance", {}) or {}
    k_val = int(dist_cfg.get("k", 3))
    bin_edges = list(dist_cfg.get("bin_edges_m", [125, 375, 750, 1500, 3125, 6000, 9000]))
    dist_method = str(dist_cfg.get("method", "sampled_points")).strip().lower()
    sample_spacing_m = float(dist_cfg.get("sample_spacing_m", 250.0))
    k_query_samples = int(dist_cfg.get("k_query_samples", 48))
    chunk_size = int(dist_cfg.get("chunk_size", 8000))
    max_samples_per_link = int(dist_cfg.get("max_samples_per_link", 200))
    max_candidates = int(dist_cfg.get("max_candidates", 64))

    bin_solver_map = hybrid.get("bin_solver_map", {}) or {}
    default_solver = str(hybrid.get("default_solver", "OPT_IDW"))
    solver_outputs = hybrid.get("solver_outputs", {}) or {}

    if base_solver not in solver_outputs:
        raise ValueError(f"base_solver '{base_solver}' missing from hybrid.solver_outputs")

    # resolve solver output dirs
    solver_dirs: Dict[str, Path] = {}
    for name, p in solver_outputs.items():
        solver_dirs[str(name)] = _resolve_path(str(p), base_dir=base_dir)

    est_input_json = Path(est_input_json)
    out_npz = Path(out_npz)

    # load base solver output
    base_npz = solver_dirs[base_solver] / out_npz.name
    if not base_npz.exists():
        raise FileNotFoundError(f"Base solver output not found: {base_npz}")
    base_field = _load_npz_field(base_npz)

    rainy = base_field > threshold

    # load est_input for distance computation
    with est_input_json.open("r", encoding="utf-8") as f:
        est = json.load(f)

    dist_bins = parse_bins(bin_edges)
    if dist_method in ("sampled_points", "sampled", "samples"):
        dk_maps, _ = compute_dk_maps_sampled_points(
            est,
            [k_val],
            sample_spacing_m=sample_spacing_m,
            k_query_samples=k_query_samples,
            chunk_size=chunk_size,
            max_samples_per_link=max_samples_per_link,
            debug_label=str(est_input_json.name),
        )
    else:
        dk_maps, _ = compute_dk_maps(
            est,
            [k_val],
            max_candidates=max_candidates,
        )

    d_map = dk_maps[k_val]
    d_labels = assign_bin_labels(d_map.ravel(), dist_bins).reshape(d_map.shape)

    # load solver outputs as needed
    solver_cache: Dict[str, np.ndarray] = {}

    def get_solver_field(name: str) -> np.ndarray:
        if name in solver_cache:
            return solver_cache[name]
        if name not in solver_dirs:
            raise ValueError(f"Solver '{name}' not found in hybrid.solver_outputs")
        npz_path = solver_dirs[name] / out_npz.name
        if not npz_path.exists():
            raise FileNotFoundError(f"Solver output not found: {npz_path}")
        solver_cache[name] = _load_npz_field(npz_path)
        return solver_cache[name]

    out = np.zeros_like(base_field, dtype=np.float64)

    for _, _, bin_lab in dist_bins:
        solver_name = str(bin_solver_map.get(bin_lab, default_solver))
        field = get_solver_field(solver_name)
        mask = d_labels == bin_lab
        out[mask] = field[mask]

    # apply rainy mask from base solver
    out[~rainy] = 0.0

    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_npz, R_hat=out.astype(np.float32))
