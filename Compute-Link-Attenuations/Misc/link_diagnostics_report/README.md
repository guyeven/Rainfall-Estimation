# Link Diagnostics Report

This folder contains `link_diagnostics_report.py`, an auxiliary diagnostic script for inspecting per-link attenuation errors. It was used for debugging and exploratory analysis, not as a required stage of the maintained benchmark pipeline.

The script compares observed and reconstructed attenuation link by link, then writes an Excel workbook and plots such as Pareto curves, crowding/error summaries, IDW-vs-ILDW comparisons, and maps highlighting high-error links.

## Expected Inputs

The script expects already-generated estimator inputs and solver outputs, for example:

- an `est_dir/` containing `est_input_*.json` files,
- one or more solution directories containing `est_input_*_solution.npz` files.

Those are downstream artifacts from the normal solver pipeline in `../../HundredPatches/pipeline/`.

## Status

Treat this as an optional debugging tool. It may need path arguments or small updates before reuse if the surrounding pipeline layout changes.
