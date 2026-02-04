#!/usr/bin/env python3
"""
batch_solve_rain_lbfgsb.py

Directory-based batch runner for solve_rain_lbfgsb.py.

What it does
------------
- Reads a YAML/JSON config that specifies:
    input.est_dir   : directory containing estimator input JSONs (est_input_*.json)
    output.out_dir  : directory to write one .npz per input JSON
    optimization.*  : same parameters as solve_rain_lbfgsb.py (lambda, mu, epsilon, R0, maxiter)
    tolerances.*    : same parameters as solve_rain_lbfgsb.py (ftol, gtol, maxls)
- Iterates all matching JSON files (sorted) and:
    - prints to stdout which file is currently being solved
    - runs the solver once per file
    - writes <out_dir>/<stem>_solution.npz

Usage
-----
  python batch_solve_rain_lbfgsb.py --config batch_solve_config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional


def _import_solver():
    """Import solve_rain_lbfgsb.py from the same folder (or PYTHONPATH)."""
    this_dir = Path(__file__).resolve().parent
    if str(this_dir) not in sys.path:
        sys.path.insert(0, str(this_dir))
    try:
        import solve_rain_lbfgsb as solver  # type: ignore
    except Exception as e:
        raise ImportError(
            "Could not import solve_rain_lbfgsb.py. "
            "Make sure batch_solve_rain_lbfgsb.py is in the same folder as solve_rain_lbfgsb.py "
            "or that solve_rain_lbfgsb is on PYTHONPATH."
        ) from e
    return solver


def _list_est_files(est_dir: Path, pattern: str, recursive: bool) -> List[Path]:
    if not est_dir.exists():
        raise FileNotFoundError(f"input.est_dir does not exist: {est_dir}")
    if not est_dir.is_dir():
        raise NotADirectoryError(f"input.est_dir is not a directory: {est_dir}")

    if recursive:
        files = sorted(est_dir.rglob(pattern))
    else:
        files = sorted(est_dir.glob(pattern))

    return [p for p in files if p.is_file()]


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Batch runner for solve_rain_lbfgsb.py (directory mode).")
    ap.add_argument("--config", required=True, help="Path to YAML/JSON config (directory-batch style).")
    ap.add_argument(
        "--pattern",
        default=None,
        help="Optional override for input.file_pattern (e.g., 'est_input_*.json' or '*.json').",
    )
    ap.add_argument(
        "--recursive",
        action="store_true",
        help="If set, search input.est_dir recursively (overrides input.recursive).",
    )
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_argparser().parse_args(argv)

    solver = _import_solver()
    cfg = solver.load_config_file(args.config)

    # Required: directories
    est_dir = solver.deep_get(cfg, "input.est_dir")
    out_dir = solver.deep_get(cfg, "output.out_dir")
    if not est_dir:
        raise ValueError("Missing required config key: input.est_dir")
    if not out_dir:
        raise ValueError("Missing required config key: output.out_dir")

    est_dir_p = Path(est_dir).expanduser()
    out_dir_p = Path(out_dir).expanduser()
    out_dir_p.mkdir(parents=True, exist_ok=True)

    # File discovery options
    pattern = args.pattern or solver.deep_get(cfg, "input.file_pattern", "est_input_*.json")
    recursive = bool(args.recursive or solver.deep_get(cfg, "input.recursive", False))

    est_files = _list_est_files(est_dir_p, pattern=pattern, recursive=recursive)
    if not est_files:
        print(f"No estimator JSON files found in {est_dir_p} with pattern='{pattern}' (recursive={recursive}).")
        return 2

    # Optimization parameters (same names as solve_rain_lbfgsb.py config)
    lam = solver.deep_get(cfg, "optimization.lambda")
    mu = solver.deep_get(cfg, "optimization.mu")
    if lam is None or mu is None:
        raise ValueError("Missing required optimization params: optimization.lambda and/or optimization.mu")

    eps = float(solver.deep_get(cfg, "optimization.epsilon", 0.01))
    R0 = float(solver.deep_get(cfg, "optimization.R0", 0.0))
    maxiter = int(solver.deep_get(cfg, "optimization.maxiter", 80))

    ftol = float(solver.deep_get(cfg, "tolerances.ftol", 1e-9))
    gtol = float(solver.deep_get(cfg, "tolerances.gtol", 1e-6))
    maxls = int(solver.deep_get(cfg, "tolerances.maxls", 20))

    warn = bool(solver.deep_get(cfg, "output.warn", True))

    print(f"Found {len(est_files)} files in {est_dir_p} (pattern='{pattern}', recursive={recursive}).")
    print(f"Writing outputs to: {out_dir_p}")

    # Run loop
    failures = 0
    for i, est_path in enumerate(est_files, start=1):
        out_npz = out_dir_p / f"{est_path.stem}_solution.npz"
        print(f"[{i}/{len(est_files)}] Solving: {est_path}")
        try:
            solver.solve_lbfgsb_and_save(
                str(est_path),
                lam=float(lam),
                mu=float(mu),
                eps=eps,
                R0=R0,
                maxiter=maxiter,
                ftol=ftol,
                gtol=gtol,
                maxls=maxls,
                npz_out=str(out_npz),
                warn=warn,
            )
        except Exception as e:
            failures += 1
            print(f"  !! FAILED on {est_path.name}: {e}")

    if failures:
        print(f"Done with failures: {failures}/{len(est_files)} runs failed.")
        return 1

    print("Done. All runs succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
