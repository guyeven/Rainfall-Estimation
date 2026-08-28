# Artifact catalog

This directory contains metadata for the large input datasets, benchmark
inputs, solver outputs, and generated reports used by the thesis. The actual
multi-gigabyte files remain in the component directories recorded in the
catalog; they are not duplicated here.

## Contents

- `catalog.json` lists each artifact bundle, its repository path, size, license
  scope, manifest, and optional external archive URL.
- `manifests/` contains per-file sizes and SHA-256 digests for verifying the
  corresponding artifact directories.
- `README.md` is this overview.

[`catalog.json`](catalog.json) records each large artifact bundle, its current
repository path, license scope, exact manifest, and eventual immutable archive
URL. The SHA-256 manifests in `manifests/` describe the repository state before
the external-storage migration.

Verify all currently local bundles with `make verify-artifacts`.

All `archive_url` values intentionally remain `null` until a bundle is uploaded
and verified independently. Do not remove a tracked artifact directory merely
because its manifest exists. Complete the external archive and history-cutover
procedure in [`../docs/artifact-storage.md`](../docs/artifact-storage.md) first.
