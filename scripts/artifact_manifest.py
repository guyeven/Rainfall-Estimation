#!/usr/bin/env python3
"""Create or verify deterministic SHA-256 manifests for artifact directories."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CHUNK_SIZE = 1024 * 1024


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            value.update(chunk)
    return value.hexdigest()


def build_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"artifact root is not a directory: {root}")
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
        )
    return {
        "manifest_version": 1,
        "algorithm": "sha256",
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }


def verify(root: Path, manifest: dict[str, Any]) -> list[str]:
    expected = {item["path"]: item for item in manifest.get("files", [])}
    actual = build_manifest(root)
    observed = {item["path"]: item for item in actual["files"]}
    problems = []
    for name in sorted(expected.keys() - observed.keys()):
        problems.append(f"missing: {name}")
    for name in sorted(observed.keys() - expected.keys()):
        problems.append(f"unexpected: {name}")
    for name in sorted(expected.keys() & observed.keys()):
        if expected[name].get("bytes") != observed[name]["bytes"]:
            problems.append(f"size mismatch: {name}")
        if expected[name].get("sha256") != observed[name]["sha256"]:
            problems.append(f"digest mismatch: {name}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("root", type=Path)
        command.add_argument("manifest", type=Path)
    args = parser.parse_args()

    if args.command == "create":
        manifest = build_manifest(args.root)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(
            f"Wrote {args.manifest}: {manifest['file_count']} files, "
            f"{manifest['total_bytes']} bytes"
        )
        return 0

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    problems = verify(args.root, manifest)
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print(f"Verified {args.root} against {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
