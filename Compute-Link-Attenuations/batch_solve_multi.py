#!/usr/bin/env python3
"""
batch_solve_multi.py

Run multiple "solvers" over the same set of est_input_*.json files and write an output .npz per solver.

Supports solvers as either:
  - a YAML list:
      solvers:
        - name: ...
          ...
  - or a YAML mapping (no dash bullets):
      solvers:
        solA:
          name: ...
          ...
        solB:
          ...

Relative paths are resolved relative to the config file.
"""

from __future__ import annotations

import argparse
import os
import importlib
import importlib.util
import inspect
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np


def load_config_file(path: str | Path) -> dict:
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except Exception as e:
            raise RuntimeError("YAML config requires PyYAML: pip install pyyaml") from e
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return {} if cfg is None else cfg

    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    raise ValueError("Config must be .yaml/.yml or .json")


def deep_get(d: dict, path: str, default=None):
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def resolve_path(p: str | Path | None, *, base_dir: Path) -> Optional[Path]:
    if p is None:
        return None
    pp = Path(str(p))
    if pp.is_absolute():
        return pp
    return (base_dir / pp).resolve()


def import_module_from_spec(module_spec: str, *, base_dir: Path):
    """
    module_spec can be:
      - "solve_rain_lbfgsb" (import by name)
      - "path/to/solve_rain_lbfgsb.py" (import from file)
    """
    ms = str(module_spec)
    if ms.endswith(".py") or ("/" in ms) or ("\\" in ms):
        p = resolve_path(ms, base_dir=base_dir)
        if p is None or not p.exists():
            raise FileNotFoundError(f"Solver module path not found: {ms}")
        mod_name = p.stem
        spec = importlib.util.spec_from_file_location(mod_name, p)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not import module from {p}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        return mod
    return importlib.import_module(ms)


def list_est_inputs(est_dir: Path, pattern: str, recursive: bool) -> List[Path]:
    if recursive:
        return sorted(est_dir.rglob(pattern))
    return sorted(est_dir.glob(pattern))


def normalize_solvers_cfg(solvers_cfg: Any) -> List[dict]:
    """
    Accept solvers as list[dict] or dict[str, dict].
    Returns a list of dicts.
    """
    if solvers_cfg is None:
        return []
    if isinstance(solvers_cfg, list):
        out = []
        for s in solvers_cfg:
            if not isinstance(s, dict):
                raise ValueError("Each solvers[] entry must be a dict")
            out.append(s)
        return out
    if isinstance(solvers_cfg, dict):
        out = []
        for key, val in solvers_cfg.items():
            if not isinstance(val, dict):
                raise ValueError("Each solvers.<key> entry must be a dict")
            d = dict(val)
            d.setdefault("name", str(key))
            out.append(d)
        return out
    raise ValueError("solvers must be a list or a mapping")


def save_npz(out_npz: Path, *, R_hat: np.ndarray, meta: Dict[str, Any]):
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_npz, R_hat=R_hat.astype(np.float32), meta=json.dumps(meta))


def _filtered_kwargs(func, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep only kwargs accepted by func (unless it has **kwargs).
    """
    sig = inspect.signature(func)
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if has_var_kw:
        return kwargs
    allowed = set(sig.parameters.keys())
    return {k: v for k, v in kwargs.items() if k in allowed}


def solve_with_lbfgsb_module(mod, *, est_json: Path, out_npz: Path, solver_cfg: dict):
    """
    Calls mod.solve_lbfgsb_and_save(...) using the parameter names in YOUR solve_rain_lbfgsb.py.

    Expected signature (yours):
      solve_lbfgsb_and_save(est_input_json, *, lam, mu, eps, R0, maxiter, ftol, gtol, maxls, npz_out, warn,
                            R0_from_IDW, idw_r_max_m, idw_power, idw_eps_m, idw_default_value,
                            rain_init_mode, rain_init_value, rain_init_multiplier)
    """
    if not hasattr(mod, "solve_lbfgsb_and_save"):
        raise AttributeError("module has no solve_lbfgsb_and_save()")

    f = getattr(mod, "solve_lbfgsb_and_save")

    opt = solver_cfg.get("optimization", {}) or {}
    tol = solver_cfg.get("tolerances", {}) or {}
    idw = solver_cfg.get("idw", {}) or {}
    rain_init = opt.get("rain_init", {}) or {}

    kwargs = {
        "est_input_json": est_json,
        "lam": float(opt.get("w_smooth", opt.get("lambda", opt.get("lam", 0.01)))),
        "mu": float(opt.get("w_shrink", opt.get("mu", 1e-6))),
        "eps": float(opt.get("epsilon", opt.get("eps", 0.01))),
        "eta": float(opt.get("w_second_der", opt.get("eta", 0.0))),
        "num_atten": float(opt.get("num_atten", 1.0)),
        "num_1d": float(opt.get("num_1d", 1.0)),
        "num_2d": float(opt.get("num_2d", 0.5)),
        "num_total": float(opt.get("num_total", 1.0)),
        "virtual_freq_ghz": (
            None
            if opt.get("virtual_freq_ghz", None) is None
            else float(opt.get("virtual_freq_ghz"))
        ),
        "beta_delta": float(opt.get("beta_delta", 0.1)),
        "j2_w": float(opt.get("w_shrink", opt.get("j2_w", opt.get("w_j2", 0.01)))),
        "j3_w": float(
            opt.get(
                "w_lin_neighbors",
                opt.get("w_log_neighbors", opt.get("w_neighbors", opt.get("j3_w", opt.get("w_j3", 1e-6)))),
            )
        ),
        "j4_w": float(opt.get("w_second_der", opt.get("j4_w", opt.get("w_j4", 1e-6)))),
        "use_linear_j3": bool(opt.get("use_linear_j3", False)),
        "R0": float(opt.get("R0", 0.1)),
        "rain_init_mode": str(rain_init.get("mode", "fixed")),
        "rain_init_value": float(rain_init.get("value", opt.get("R0", 0.1))),
        "rain_init_multiplier": float(rain_init.get("multiplier", 1.0)),
        "maxiter": int(opt.get("maxiter", 300)),
        "ftol": float(tol.get("ftol", 1e-5)),
        "gtol": float(tol.get("gtol", 1e-4)),
        "maxls": int(tol.get("maxls", 20)),
        "npz_out": out_npz,
        "optinfo_out": out_npz.with_name(f"{out_npz.stem}_optinfo.json"),
        "warn": bool(solver_cfg.get("warn", True)),
        # optional IDW init:
        "R0_from_IDW": bool(opt.get("R0_from_IDW", False)),
        "R0_from_ILDW": bool(opt.get("R0_from_ILDW", False)),
        "idw_r_max_m": float(idw.get("r_max_m", 3125.0)),
        "idw_power": float(idw.get("power", 2.0)),
        "idw_eps_m": float(idw.get("eps_m", 1.0)),
        "idw_default_value": float(idw.get("default_value", 0.0)),
    }

    kwargs = _filtered_kwargs(f, kwargs)
    f(**kwargs)


def solve_with_idw_module(mod, *, est_json: Path, out_npz: Path, solver_cfg: dict):
    """
    Expected in module:
      idw_field_from_est_input(est_input_json, *, r_max_m, power, eps_m, default_value, ...) -> (field, link_vals)
    """
    if not hasattr(mod, "idw_field_from_est_input"):
        raise AttributeError("module has no idw_field_from_est_input()")

    f = getattr(mod, "idw_field_from_est_input")

    idw = solver_cfg.get("idw", {}) or {}
    kwargs = {
        "est_input_json": est_json,
        "r_max_m": float(idw.get("r_max_m", 3125.0)),
        "power": float(idw.get("power", 2.0)),
        "eps_m": float(idw.get("eps_m", 1.0)),
        "default_value": float(idw.get("default_value", 0.0)),
    }
    kwargs = _filtered_kwargs(f, kwargs)

    res = f(**kwargs)
    # allow either array or (array, aux)
    if isinstance(res, tuple) or isinstance(res, list):
        field = np.asarray(res[0], dtype=np.float64)
    else:
        field = np.asarray(res, dtype=np.float64)

    meta = {
        "method": "idw",
        "r_max_m": float(idw.get("r_max_m", 3125.0)),
        "power": float(idw.get("power", 2.0)),
        "eps_m": float(idw.get("eps_m", 1.0)),
        "default_value": float(idw.get("default_value", 0.0)),
        "est_input_json": est_json.name,
    }
    save_npz(out_npz, R_hat=field, meta=meta)


def run_solver_batch(
    solver_cfg: dict,
    *,
    est_files: List[Path],
    base_dir: Path,
) -> Tuple[str, int, int]:
    label = str(solver_cfg.get("label") or solver_cfg.get("name") or "solver")
    module_spec = solver_cfg.get("module", None)
    if module_spec is None:
        raise RuntimeError(f"Solver {label}: missing 'module'")
    out_dir = resolve_path(solver_cfg.get("out_dir", None), base_dir=base_dir)
    if out_dir is None:
        raise RuntimeError(f"Solver {label}: missing 'out_dir'")
    out_dir.mkdir(parents=True, exist_ok=True)

    mod = import_module_from_spec(str(module_spec), base_dir=base_dir)

    solver_type = str(solver_cfg.get("type", "")).lower().strip()
    if not solver_type:
        if hasattr(mod, "idw_field_from_est_input"):
            solver_type = "idw"
        elif hasattr(mod, "solve_lbfgsb_and_save"):
            solver_type = "lbfgsb"
        else:
            solver_type = "custom"

    print(f"[{label}] type={solver_type} module={module_spec} -> {out_dir}")

    failures = 0
    n_total = len(est_files)
    progress_step = max(1, n_total // 20)  # ~5% steps
    for i, est_path in enumerate(est_files, 1):
        out_npz = out_dir / (est_path.stem + "_solution.npz")
        try:
            if solver_type == "idw":
                solve_with_idw_module(mod, est_json=est_path, out_npz=out_npz, solver_cfg=solver_cfg)
            elif solver_type == "lbfgsb":
                solve_with_lbfgsb_module(mod, est_json=est_path, out_npz=out_npz, solver_cfg=solver_cfg)
            else:
                if not hasattr(mod, "solve_and_save"):
                    raise AttributeError("custom solver requires solve_and_save(est_input_json, out_npz, cfg)")
                s_with_base = dict(solver_cfg)
                s_with_base["_base_dir"] = str(base_dir)
                mod.solve_and_save(est_path, out_npz, s_with_base)  # type: ignore
        except Exception as e:
            failures += 1
            print(f"[{label}] [{i}/{len(est_files)}] FAIL {est_path.name}: {e}")
        if i == 1 or i == n_total or (i % progress_step == 0):
            pct = (100.0 * float(i) / float(n_total)) if n_total > 0 else 100.0
            print(f"[{label}] progress {i}/{n_total} ({pct:.1f}%) | failures={failures}")

    if failures:
        print(f"[{label}] finished with failures: {failures}/{len(est_files)}")
    else:
        print(f"[{label}] finished OK ({len(est_files)} files).")

    return label, failures, len(est_files)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = load_config_file(cfg_path)
    base_dir = cfg_path.resolve().parent

    est_dir = resolve_path(deep_get(cfg, "input.est_dir", None), base_dir=base_dir)
    if est_dir is None:
        raise SystemExit("Config missing input.est_dir")
    pattern = str(deep_get(cfg, "input.file_pattern", "est_input_*.json"))
    recursive = bool(deep_get(cfg, "input.recursive", False))

    est_files = list_est_inputs(est_dir, pattern, recursive)
    if not est_files:
        raise SystemExit(f"No files found under {est_dir} with pattern {pattern} (recursive={recursive}).")

    solvers_cfg_raw = deep_get(cfg, "solvers", None)
    solvers = normalize_solvers_cfg(solvers_cfg_raw)
    if not solvers:
        raise SystemExit("Config must include 'solvers:' (list or mapping)")

    print(f"Found {len(est_files)} est_input file(s). Running {len(solvers)} solver(s).")
    workers_cfg = deep_get(cfg, "parallel.solver_workers", None)
    if workers_cfg is None:
        solver_workers = min(len(solvers), max(1, os.cpu_count() or 1))
    else:
        solver_workers = max(1, int(workers_cfg))
        solver_workers = min(solver_workers, len(solvers))

    if solver_workers <= 1:
        for s in solvers:
            run_solver_batch(s, est_files=est_files, base_dir=base_dir)
    else:
        print(f"Running solvers in parallel with {solver_workers} worker(s).")
        futures = {}
        with ThreadPoolExecutor(max_workers=solver_workers) as ex:
            for s in solvers:
                fut = ex.submit(run_solver_batch, s, est_files=est_files, base_dir=base_dir)
                futures[fut] = str(s.get("label") or s.get("name") or "solver")
            for fut in as_completed(futures):
                label = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    print(f"[{label}] ABORTED: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
