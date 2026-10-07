#!/usr/bin/env python3
"""Verify every local bundle in artifacts/catalog.json."""

from __future__ import annotations

import json
from pathlib import Path

from artifact_manifest import verify


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    catalog_path = ROOT / "artifacts" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    failed = False
    for bundle in catalog["bundles"]:
        artifact_root = ROOT / bundle["root"]
        manifest_path = ROOT / bundle["manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        problems = verify(artifact_root, manifest)
        if problems:
            failed = True
            print(f"{bundle['id']}: FAILED")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"{bundle['id']}: verified ({manifest['file_count']} files)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
