# Repository verification scripts

This directory contains small maintenance utilities used to verify the thesis
repository and its research artifacts. They are not part of the rainfall
reconstruction algorithms themselves.

## Contents

- `artifact_manifest.py` creates or verifies a SHA-256 manifest for a directory
  of research artifacts.
- `verify_artifact_catalog.py` verifies every local bundle listed in
  `../artifacts/catalog.json` against its manifest.
- `check_repository_hygiene.py` checks tracked files for common packaging
  problems, including oversized Git blobs, backup copies, Python bytecode, and
  unpinned `latest` npm dependencies.

From the repository root, verify the included artifact bundles with:

```bash
python3 scripts/verify_artifact_catalog.py
```

Run the repository-hygiene check with:

```bash
python3 scripts/check_repository_hygiene.py
```

See `../docs/artifact-storage.md` for the artifact-storage policy and examples
of creating and verifying individual manifests.
