# Patch Overview Generation

This folder groups helper inputs for generating patch-overview maps and summaries for the 100-patch benchmark.

## Contents

- `patch_jsonl_files/`: per-patch JSONL geometry files used by overview/map-generation helpers.

These files sit upstream of the maintained pipeline in `../pipeline/`: they describe benchmark patch geometry and are useful for visualization and inspection, but the solver and report workflow itself is configured from `../pipeline/`.
