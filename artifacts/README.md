# Artifact catalog

[`catalog.json`](catalog.json) records each large artifact bundle, its current
repository path, license scope, exact manifest, and eventual immutable archive
URL. The SHA-256 manifests in `manifests/` describe the repository state before
the external-storage migration.

Verify all currently local bundles with `make verify-artifacts`.

All `archive_url` values intentionally remain `null` until a bundle is uploaded
and verified independently. Do not remove a tracked artifact directory merely
because its manifest exists. Complete the external archive and history-cutover
procedure in [`../docs/artifact-storage.md`](../docs/artifact-storage.md) first.
