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

Parallelism:
  - parallel.solver_workers runs different solver entries concurrently.
  - parallel.patch_workers runs different est_input patch files concurrently within each solver.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.util
import importlib.metadata
import inspect
import json
import os
import platform
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from cml_attenuation.config_io import deep_get, load_config_file, resolve_path
from cml_attenuation.pipeline_validation import validate_batch_solve_config


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


def duplicate_input_stems(paths: Iterable[Path]) -> Dict[str, List[Path]]:
    by_stem: Dict[str, List[Path]] = {}
    for path in paths:
        by_stem.setdefault(path.stem, []).append(path)
    return {stem: items for stem, items in by_stem.items() if len(items) > 1}


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


RUNTIME_FIELDS = [
    "patch_id",
    "input_file",
    "solver_name",
    "solver_label",
    "run_status",
    "solver_success",
    "stop_reason",
    "height",
    "width",
    "num_pixels",
    "num_links",
    "num_valid_links",
    "iterations",
    "nfev",
    "njev",
    "end_to_end_seconds",
    "optimizer_seconds",
    "output_npz",
    "error",
    "completed_at_utc",
    "solver_config_sha256",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _solver_config_sha256(solver_cfg: dict) -> str:
    payload = json.dumps(solver_cfg, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_")
    return cleaned.lower() or "solver"


def _patch_id(est_path: Path) -> str:
    prefix = "est_input_"
    return est_path.stem[len(prefix):] if est_path.stem.startswith(prefix) else est_path.stem


def _read_runtime_rows(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        return {row["input_file"]: dict(row) for row in csv.DictReader(f) if row.get("input_file")}


def _write_runtime_rows(path: Path, rows_by_input: Dict[str, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUNTIME_FIELDS)
        writer.writeheader()
        for row in sorted(rows_by_input.values(), key=lambda item: str(item.get("input_file", ""))):
            writer.writerow({field: row.get(field, "") for field in RUNTIME_FIELDS})
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _float_values(rows: Iterable[Dict[str, Any]], key: str) -> np.ndarray:
    values: List[float] = []
    for row in rows:
        if str(row.get("run_status", "")) != "completed":
            continue
        try:
            value = float(row.get(key, ""))
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            values.append(value)
    return np.asarray(values, dtype=np.float64)


def _runtime_stats(values: np.ndarray) -> Dict[str, Any]:
    if values.size == 0:
        return {
            "count": 0,
            "mean": None,
            "sample_std": None,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
            "min": None,
            "max": None,
            "total": None,
        }
    q1, median, q3 = np.percentile(values, [25.0, 50.0, 75.0])
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "sample_std": float(np.std(values, ddof=1)) if values.size > 1 else None,
        "median": float(median),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(q3 - q1),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "total": float(np.sum(values)),
    }


def _package_version(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _runtime_summary(
    *,
    rows_by_input: Dict[str, Dict[str, Any]],
    label: str,
    solver_name: str,
    expected_patches: int,
    timing_cfg: dict,
    config_path: Path,
    config_sha256: str,
    patch_workers: int,
    solver_workers: int,
) -> Dict[str, Any]:
    rows = list(rows_by_input.values())
    completed = [row for row in rows if str(row.get("run_status", "")) == "completed"]
    failed = [row for row in rows if str(row.get("run_status", "")) == "failed"]
    converged = [row for row in completed if str(row.get("solver_success", "")).lower() == "true"]
    return {
        "generated_at_utc": _utc_now(),
        "solver_name": solver_name,
        "solver_label": label,
        "timing_scope": str(
            timing_cfg.get(
                "scope",
                "End-to-end wall time includes input loading, initialization, optimization, diagnostics, and output writing.",
            )
        ),
        "hardware_note": str(timing_cfg.get("hardware_note", "")),
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scipy": _package_version("scipy"),
        },
        "configuration": {
            "config_file": str(config_path),
            "solver_config_sha256": config_sha256,
            "solver_workers": int(solver_workers),
            "patch_workers": int(patch_workers),
        },
        "patches": {
            "expected": int(expected_patches),
            "recorded": int(len(rows)),
            "completed": int(len(completed)),
            "failed": int(len(failed)),
            "optimizer_converged": int(len(converged)),
        },
        "end_to_end_seconds": _runtime_stats(_float_values(rows, "end_to_end_seconds")),
        "optimizer_seconds": _runtime_stats(_float_values(rows, "optimizer_seconds")),
    }


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


def solve_with_lbfgsb_module(mod, *, est_json: Path, out_npz: Path, solver_cfg: dict, base_dir: Path):
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
    gt_init = rain_init.get("gt", {}) or {}
    input_cfg = solver_cfg.get("input", {}) or {}

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
        "num_total_divide_by_num_pixels": bool(opt.get("num_total_divide_by_num_pixels", False)),
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
        "R0_from_GT": bool(opt.get("R0_from_GT", False)),
        "gt_dir": resolve_path(
            gt_init.get("dir", input_cfg.get("gt_dir", None)),
            base_dir=base_dir,
        ),
        "gt_prefix": str(gt_init.get("prefix", input_cfg.get("gt_prefix", "gt"))),
        "gt_key_preference": list(gt_init.get("key_preference", input_cfg.get("gt_key_preference", ["R_gt", "rain", "gt"]))),
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
    result = f(**kwargs)
    return dict(result) if isinstance(result, dict) else {}


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
    return {
        "success": True,
        "H": int(field.shape[0]) if field.ndim >= 1 else None,
        "W": int(field.shape[1]) if field.ndim >= 2 else None,
        "num_pixels": int(field.size),
        "out_npz": str(out_npz),
    }


def solve_one_patch(
    *,
    solver_cfg: dict,
    est_path: Path,
    out_dir: Path,
    base_dir: Path,
    module_spec: str,
    solver_type: str,
) -> Dict[str, Any]:
    mod = import_module_from_spec(module_spec, base_dir=base_dir)
    out_npz = out_dir / (est_path.stem + "_solution.npz")

    if solver_type == "idw":
        result = solve_with_idw_module(mod, est_json=est_path, out_npz=out_npz, solver_cfg=solver_cfg)
    elif solver_type == "lbfgsb":
        result = solve_with_lbfgsb_module(
            mod,
            est_json=est_path,
            out_npz=out_npz,
            solver_cfg=solver_cfg,
            base_dir=base_dir,
        )
    else:
        if not hasattr(mod, "solve_and_save"):
            raise AttributeError("custom solver requires solve_and_save(est_input_json, out_npz, cfg)")
        s_with_base = dict(solver_cfg)
        s_with_base["_base_dir"] = str(base_dir)
        custom_result = mod.solve_and_save(est_path, out_npz, s_with_base)  # type: ignore
        result = dict(custom_result) if isinstance(custom_result, dict) else {}

    result.setdefault("out_npz", str(out_npz))
    return result


def run_solver_batch(
    solver_cfg: dict,
    *,
    est_files: List[Path],
    base_dir: Path,
    patch_workers: int = 1,
    solver_workers: int = 1,
    timing_cfg: Optional[dict] = None,
    config_path: Optional[Path] = None,
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

    timing_cfg = timing_cfg or {}
    timing_enabled = bool(timing_cfg.get("enabled", False))
    timing_resume = bool(timing_cfg.get("resume", True))
    solver_name = str(solver_cfg.get("name") or label)
    solver_config_hash = _solver_config_sha256(solver_cfg)
    runtime_rows: Dict[str, Dict[str, Any]] = {}
    per_patch_csv: Optional[Path] = None
    summary_json: Optional[Path] = None
    if timing_enabled:
        timing_dir = resolve_path(timing_cfg.get("out_dir", "timing"), base_dir=base_dir)
        if timing_dir is None:
            raise RuntimeError("timing.out_dir could not be resolved")
        file_prefix = _safe_filename(
            str(solver_cfg.get("timing_file_prefix") or timing_cfg.get("file_prefix") or solver_name)
        )
        per_patch_csv = timing_dir / f"{file_prefix}_runtime_per_patch.csv"
        summary_json = timing_dir / f"{file_prefix}_runtime_summary.json"
        if timing_resume:
            runtime_rows = {
                input_file: row
                for input_file, row in _read_runtime_rows(per_patch_csv).items()
                if str(row.get("solver_config_sha256", "")) == solver_config_hash
            }
        print(f"[{label}] timing report -> {per_patch_csv}")

    failures = 0
    n_total = len(est_files)
    progress_step = max(1, n_total // 20)  # ~5% steps

    patch_workers = max(1, min(int(patch_workers), n_total))
    if timing_enabled and (patch_workers != 1 or solver_workers != 1):
        raise RuntimeError(
            "Runtime benchmarking requires parallel.patch_workers=1 and parallel.solver_workers=1 "
            "so per-patch wall times are not affected by resource contention."
        )
    completed_inputs = set()
    if timing_enabled and timing_resume:
        for input_file, row in runtime_rows.items():
            output_npz = Path(str(row.get("output_npz", "")))
            if (
                str(row.get("run_status", "")) == "completed"
                and str(row.get("solver_config_sha256", "")) == solver_config_hash
                and output_npz.is_file()
            ):
                completed_inputs.add(input_file)
        if completed_inputs:
            print(f"[{label}] resuming: {len(completed_inputs)} completed patch(es) will be skipped.")

    pending_files = [est_path for est_path in est_files if est_path.name not in completed_inputs]
    completed_count = len(est_files) - len(pending_files)

    def record_runtime(
        est_path: Path,
        *,
        result: Optional[Dict[str, Any]],
        elapsed_seconds: float,
        error: Optional[Exception] = None,
    ) -> None:
        if not timing_enabled or per_patch_csv is None or summary_json is None:
            return
        result = result or {}
        run_status = "failed" if error is not None else "completed"
        row = {
            "patch_id": _patch_id(est_path),
            "input_file": est_path.name,
            "solver_name": solver_name,
            "solver_label": label,
            "run_status": run_status,
            "solver_success": result.get("success", ""),
            "stop_reason": result.get("stop_reason", ""),
            "height": result.get("H", ""),
            "width": result.get("W", ""),
            "num_pixels": result.get("num_pixels", ""),
            "num_links": result.get("num_links", ""),
            "num_valid_links": result.get("num_valid_links", ""),
            "iterations": result.get("nit", ""),
            "nfev": result.get("nfev", ""),
            "njev": result.get("njev", ""),
            "end_to_end_seconds": float(elapsed_seconds),
            "optimizer_seconds": result.get("optimizer_seconds", ""),
            "output_npz": result.get("out_npz", str(out_dir / (est_path.stem + "_solution.npz"))),
            "error": "" if error is None else f"{type(error).__name__}: {error}",
            "completed_at_utc": _utc_now(),
            "solver_config_sha256": solver_config_hash,
        }
        runtime_rows[est_path.name] = row
        _write_runtime_rows(per_patch_csv, runtime_rows)
        _write_json_atomic(
            summary_json,
            _runtime_summary(
                rows_by_input=runtime_rows,
                label=label,
                solver_name=solver_name,
                expected_patches=n_total,
                timing_cfg=timing_cfg,
                config_path=config_path or base_dir,
                config_sha256=solver_config_hash,
                patch_workers=patch_workers,
                solver_workers=solver_workers,
            ),
        )

    if patch_workers <= 1:
        for est_path in pending_files:
            started = time.perf_counter()
            try:
                result = solve_one_patch(
                    solver_cfg=solver_cfg,
                    est_path=est_path,
                    out_dir=out_dir,
                    base_dir=base_dir,
                    module_spec=str(module_spec),
                    solver_type=solver_type,
                )
            except Exception as e:
                failures += 1
                result = {}
                record_runtime(est_path, result=result, elapsed_seconds=time.perf_counter() - started, error=e)
                print(f"[{label}] [{completed_count + 1}/{len(est_files)}] FAIL {est_path.name}: {e}")
            else:
                record_runtime(est_path, result=result, elapsed_seconds=time.perf_counter() - started)
            completed_count += 1
            if completed_count == 1 or completed_count == n_total or (completed_count % progress_step == 0):
                pct = (100.0 * float(completed_count) / float(n_total)) if n_total > 0 else 100.0
                print(f"[{label}] progress {completed_count}/{n_total} ({pct:.1f}%) | failures={failures}")
    else:
        print(f"[{label}] running patches in parallel with {patch_workers} worker(s).")
        futures = {}
        with ThreadPoolExecutor(max_workers=patch_workers) as ex:
            for est_path in pending_files:
                started = time.perf_counter()
                fut = ex.submit(
                    solve_one_patch,
                    solver_cfg=solver_cfg,
                    est_path=est_path,
                    out_dir=out_dir,
                    base_dir=base_dir,
                    module_spec=str(module_spec),
                    solver_type=solver_type,
                )
                futures[fut] = (est_path, started)
            for fut in as_completed(futures):
                completed_count += 1
                est_path, started = futures[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    failures += 1
                    result = {}
                    record_runtime(est_path, result=result, elapsed_seconds=time.perf_counter() - started, error=e)
                    print(f"[{label}] [{completed_count}/{len(est_files)}] FAIL {est_path.name}: {e}")
                else:
                    record_runtime(est_path, result=result, elapsed_seconds=time.perf_counter() - started)
                if completed_count == 1 or completed_count == n_total or (completed_count % progress_step == 0):
                    pct = (100.0 * float(completed_count) / float(n_total)) if n_total > 0 else 100.0
                    print(f"[{label}] progress {completed_count}/{n_total} ({pct:.1f}%) | failures={failures}")

    if failures:
        print(f"[{label}] finished with failures: {failures}/{len(est_files)}")
    else:
        print(f"[{label}] finished OK ({len(est_files)} files).")

    if timing_enabled and summary_json is not None:
        summary = _runtime_summary(
            rows_by_input=runtime_rows,
            label=label,
            solver_name=solver_name,
            expected_patches=n_total,
            timing_cfg=timing_cfg,
            config_path=config_path or base_dir,
            config_sha256=solver_config_hash,
            patch_workers=patch_workers,
            solver_workers=solver_workers,
        )
        _write_json_atomic(summary_json, summary)
        stats = summary["end_to_end_seconds"]
        if stats["count"]:
            print(
                f"[{label}] end-to-end runtime: mean={stats['mean']:.3f}s, "
                f"median={stats['median']:.3f}s, min={stats['min']:.3f}s, max={stats['max']:.3f}s"
            )

    return label, failures, len(est_files)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = load_config_file(cfg_path)
    validate_batch_solve_config(cfg)
    base_dir = cfg_path.resolve().parent

    est_dir = resolve_path(deep_get(cfg, "input.est_dir", None), base_dir=base_dir)
    if est_dir is None:
        raise SystemExit("Config missing input.est_dir")
    pattern = str(deep_get(cfg, "input.file_pattern", "est_input_*.json"))
    recursive = bool(deep_get(cfg, "input.recursive", False))

    est_files = list_est_inputs(est_dir, pattern, recursive)
    if not est_files:
        raise SystemExit(f"No files found under {est_dir} with pattern {pattern} (recursive={recursive}).")

    duplicate_stems = duplicate_input_stems(est_files)
    if duplicate_stems:
        separator = ", "
        examples = "; ".join(
            f"{stem}: {separator.join(str(path.relative_to(est_dir)) for path in paths)}"
            for stem, paths in sorted(duplicate_stems.items())
        )
        raise SystemExit(
            "Input files must have unique stems because solver outputs are written to a flat directory. "
            f"Duplicate stem(s): {examples}"
        )

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

    patch_workers = max(1, int(deep_get(cfg, "parallel.patch_workers", 1)))
    timing_cfg = deep_get(cfg, "timing", {}) or {}

    total_failures = 0
    if solver_workers <= 1:
        for s in solvers:
            _, failures, _ = run_solver_batch(
                s,
                est_files=est_files,
                base_dir=base_dir,
                patch_workers=patch_workers,
                solver_workers=solver_workers,
                timing_cfg=timing_cfg,
                config_path=cfg_path.resolve(),
            )
            total_failures += failures
    else:
        print(f"Running solvers in parallel with {solver_workers} worker(s).")
        futures = {}
        with ThreadPoolExecutor(max_workers=solver_workers) as ex:
            for s in solvers:
                fut = ex.submit(
                    run_solver_batch,
                    s,
                    est_files=est_files,
                    base_dir=base_dir,
                    patch_workers=patch_workers,
                    solver_workers=solver_workers,
                    timing_cfg=timing_cfg,
                    config_path=cfg_path.resolve(),
                )
                futures[fut] = str(s.get("label") or s.get("name") or "solver")
            for fut in as_completed(futures):
                label = futures[fut]
                try:
                    _, failures, _ = fut.result()
                    total_failures += failures
                except Exception as e:
                    total_failures += 1
                    print(f"[{label}] ABORTED: {e}")

    if total_failures:
        print(f"Batch completed with {total_failures} failed patch run(s) or aborted solver(s).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
