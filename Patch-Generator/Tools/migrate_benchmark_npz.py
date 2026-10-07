#!/usr/bin/env python3
"""Convert a trusted legacy object-array benchmark NPZ to safe string arrays."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np


STRING_FIELDS = {"ids", "source_files", "timestamps", "nearest_cities"}


def migrate(source: Path, destination: Path) -> None:
    # This opt-in migration command is the only place that intentionally loads
    # legacy pickled arrays. Never run it on an untrusted archive.
    values: dict[str, np.ndarray] = {}
    with np.load(source, allow_pickle=True) as legacy:
        for name in legacy.files:
            value = np.asarray(legacy[name])
            if name in STRING_FIELDS:
                values[name] = np.asarray(value, dtype=np.str_)
            elif value.dtype != object:
                values[name] = value
            elif all(isinstance(item, np.ndarray) for item in value.flat):
                # Variable-shaped arrays cannot share one ordinary ndarray.
                # Preserve each item as its own non-object member.
                for index, item in enumerate(value.flat):
                    values[f"{name}_{index:05d}"] = np.asarray(item)
            else:
                raise ValueError(f"cannot safely migrate object field {name!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination, **values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="trusted legacy benchmark .npz")
    parser.add_argument("destination", type=Path, nargs="?", help="new safe .npz")
    parser.add_argument("--in-place", action="store_true", help="replace the source atomically")
    args = parser.parse_args()
    if args.in_place == (args.destination is not None):
        parser.error("choose exactly one of destination or --in-place")
    if args.in_place:
        with tempfile.TemporaryDirectory(dir=args.source.parent) as directory:
            temporary = Path(directory) / args.source.name
            migrate(args.source, temporary)
            temporary.replace(args.source)
    else:
        migrate(args.source, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
