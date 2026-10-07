"""Lightweight semantic validation for pipeline configuration documents."""

from __future__ import annotations

from typing import Any

from .config_io import deep_get


def _positive_integer(value: Any, path: str) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{path} must be a positive integer")
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must be a positive integer") from exc
    if converted < 1 or converted != value:
        raise ValueError(f"{path} must be a positive integer")


def _nonzero_integer(value: Any, path: str) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{path} must be a nonzero integer")
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must be a nonzero integer") from exc
    if converted == 0 or converted != value:
        raise ValueError(f"{path} must be a nonzero integer")


def _entries(value: Any, path: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        entries = value
    elif isinstance(value, dict):
        entries = list(value.values())
    else:
        raise ValueError(f"{path} must be a non-empty list or mapping")
    if not entries or not all(isinstance(entry, dict) for entry in entries):
        raise ValueError(f"{path} must contain configuration mappings")
    return entries


def validate_batch_solve_config(config: dict[str, Any]) -> None:
    if not isinstance(deep_get(config, "input.est_dir"), (str, type(None))):
        raise ValueError("input.est_dir must be a path string")
    if not str(deep_get(config, "input.est_dir", "")).strip():
        raise ValueError("input.est_dir is required")
    solvers = _entries(deep_get(config, "solvers"), "solvers")
    for index, solver in enumerate(solvers):
        if not str(solver.get("name") or solver.get("label") or "").strip():
            raise ValueError(f"solvers entry {index} requires name or label")
    for path in ("parallel.solver_workers", "parallel.patch_workers"):
        value = deep_get(config, path)
        if value is not None:
            _positive_integer(value, path)


def validate_analysis_config(config: dict[str, Any]) -> None:
    for path in ("input.gt_dir", "input.est_input_dir"):
        if not str(deep_get(config, path, "")).strip():
            raise ValueError(f"{path} is required")
    solvers = _entries(deep_get(config, "input.solvers"), "input.solvers")
    for index, solver in enumerate(solvers):
        if not str(solver.get("sol_dir", "")).strip():
            raise ValueError(f"input.solvers entry {index} requires sol_dir")
    workers = deep_get(config, "analysis.n_jobs", deep_get(config, "n_jobs"))
    if workers is not None:
        _nonzero_integer(workers, "analysis.n_jobs")
