# June 2023 Hundred-Patch benchmark

The active 100-patch roster is recorded in `benchmark-patches.review-order.jsonl`. Its numbers refer to the June 2023 random-order review sheets in `Patch-Generator/Benchmark-Patches/june2023-greedy-random/`.

The roster excludes review entries 023, 032, and 107, and includes 014, 016, and 042. The removed entries, plus the already-excluded candidate 024, are preserved under `bad_patches/` with their selection records and generated artifacts. The active `patch_jsonl_files/`, `est_dir/`, `gt_dir/`, and June solver directories correspond to the revised 100-patch roster.

The existing aggregate analysis caches and rendered reports were produced for the previous roster. They have not been regenerated for this swap; rerun the analysis pipeline before treating those summaries as results for the revised roster.
