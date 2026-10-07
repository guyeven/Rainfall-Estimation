#!/usr/bin/env python3
"""Fail CI when common repository-hygiene regressions are introduced."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_GIT_BLOB_BYTES = 50 * 1024 * 1024
BACKUP_PATTERN = re.compile(
    r"(?:^|/)(?:src_backup[^/]*|Trash)(?:/|$)|(?:\.py|\.jsx)?-V\d+$"
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    problems: list[str] = []
    for path in tracked_files():
        # A local pre-commit run may see paths staged for deletion.
        if not path.exists():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if BACKUP_PATTERN.search(relative):
            problems.append(f"tracked backup copy: {relative}")
        if path.suffix == ".pyc":
            problems.append(f"tracked Python bytecode: {relative}")
        if path.is_file() and path.stat().st_size > MAX_GIT_BLOB_BYTES:
            problems.append(
                f"Git blob exceeds 50 MiB: {relative} ({path.stat().st_size} bytes)"
            )
        if path.name == "package.json":
            package = json.loads(path.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies"):
                for name, version in package.get(section, {}).items():
                    if version == "latest":
                        problems.append(f"unpinned latest dependency: {relative}: {name}")

    if problems:
        print("Repository hygiene check failed:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
