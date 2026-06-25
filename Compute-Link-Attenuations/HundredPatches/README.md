# HundredPatches

This folder contains the maintained 100-patch benchmark workflow.

## Contents

- `gt_dir/`: ground-truth rainfall arrays for the selected patches.
- `est_dir/`: estimator input JSON files containing link geometry and simulated link observations for each patch.
- `pipeline/`: the maintained solver, analysis, and report-rendering configuration.
- `patch_overview_generation/`: helper inputs for generating patch-overview maps and summaries.

## Typical Order

1. Inspect the patch and link inputs in `gt_dir/` and `est_dir/`.
2. Run or restore solver outputs using `pipeline/batch_solve_config.yaml`.
3. Run the analyzer using `pipeline/analyze.yaml`.
4. Render figures and spreadsheet artifacts using `pipeline/render_report.yaml`.

The link geometries are used as realistic CML network geometries and frequencies placed into the selected patch coordinate systems; the observed attenuations are simulated from the corresponding radar-derived rainfall fields.
