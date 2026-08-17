# Large-artifact storage and history migration

The current checkout mixes source code with immutable source data, benchmark
inputs, solver outputs, caches, and rendered reports. At the time this policy
was introduced, the tracked `HEAD` tree was approximately 3.26 GiB and the Git
object database approximately 7.8 GiB. Ordinary Git is not an efficient
distribution mechanism for this material.

## Target layout

Keep these items in Git:

- source code, configuration, lock files, documentation, and CI;
- a tiny synthetic fixture sufficient for unit and end-to-end tests;
- artifact manifests containing paths, byte sizes, and SHA-256 digests;
- small final figures when they materially improve the documentation.

Publish these as immutable external bundles:

1. `opera-source-inputs`: redistributed upstream HDF5 inputs, or preferably a
   downloader plus the upstream DOI when redistribution is unnecessary;
2. `hundred-patch-benchmark-inputs`: estimator JSON, ground-truth NPZ, patch
   metadata, and link records needed to rerun the benchmark;
3. `hundred-patch-solver-results`: solution NPZ files and timing outputs;
4. `hundred-patch-report`: analysis cache, spreadsheets, figures, and PDFs;
5. `auxiliary-analysis`: synthetic outputs and distance caches not required by
   the maintained pipeline.

For immutable research releases, a DOI-bearing archive such as Zenodo or
4TU.ResearchData is preferred. DVC with an institutional object-store remote
is a good choice when the data change frequently. Git LFS is suitable only if
the repository owner has confirmed sufficient storage and bandwidth quota.

## Create and verify manifests

Create a manifest before packaging or uploading a directory:

```bash
python scripts/artifact_manifest.py create \
  Compute-Link-Attenuations/HundredPatches/est_dir \
  artifacts/local/hundred-patch-est-inputs.manifest.json
```

Verify a restored directory:

```bash
python scripts/artifact_manifest.py verify \
  Compute-Link-Attenuations/HundredPatches/est_dir \
  artifacts/local/hundred-patch-est-inputs.manifest.json
```

Copy finalized manifests out of `artifacts/local/` into a tracked
`artifacts/manifests/` directory and record the archive DOI or immutable URL in
the README before removing the corresponding tracked files.

## Coordinated history cutover

History rewriting changes commit IDs and must be coordinated with every clone.
Do it only after all bundles have been uploaded and independently verified.
Create a protected mirror backup first. Then use `git filter-repo` to remove
the agreed artifact paths from every revision. Historical directories that no
longer exist in `HEAD`, such as old calculator/link-generator copies, should be
included in the same reviewed path list.

After checking the rewritten repository size, tags, licenses, and a fresh
clone, force-push branches and tags with `--force-with-lease`. Existing clones
should be replaced with fresh clones rather than merged into rewritten
history. Never perform this cutover from an unreviewed working tree.

This repository intentionally does not contain an automatic force-push script.
The destructive step should remain a short, visible, operator-controlled
procedure.
