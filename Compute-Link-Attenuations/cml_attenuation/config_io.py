"""Shared configuration loading and path resolution for pipeline CLIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config_file(path: str | Path) -> dict[str, Any]:
    """Load a mapping from JSON or YAML, returning an empty mapping for null."""
    config_path = Path(path)
    suffix = config_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - dependency error path
            raise RuntimeError("YAML configuration requires PyYAML.") from exc
        with config_path.open("r", encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
    elif suffix == ".json":
        with config_path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    else:
        raise ValueError("Configuration must be a .yaml, .yml, or .json file.")

    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Configuration must contain a mapping at the top level.")
    return value


def deep_get(mapping: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    """Read a dotted path from nested dictionaries."""
    current: Any = mapping
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def resolve_path(
    value: str | Path | None,
    *,
    base_dir: Path,
) -> Path | None:
    """Resolve relative configuration paths against the configuration directory."""
    if value is None:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else (base_dir / path).resolve()
