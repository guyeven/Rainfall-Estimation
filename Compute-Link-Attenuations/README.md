# Compute-Link-Attenuations

This folder contains the maintained rainfall-reconstruction pipeline and the Python modules used by it.

## Main Components

- `batch_solve_multi.py` runs one or more solvers over a set of `est_input_*.json` patch files.
- `batch_analyze_multi.py` compares solver outputs against ground truth and produces analysis caches, tables, and plot inputs.
- `render_analysis_report.py` renders the cached analysis outputs into figures and spreadsheets.
- `idw_baseline.py` and `ildw_baseline.py` implement interpolation baselines.
- `solve_rain_lbfgsb_normalized_ildw_multipliers*.py` implement the optimization-based solver variants.
- `itu_model.py`, `attenuation.py`, and `link_geometry.py` contain shared forward-model and geometry utilities.
- `HundredPatches/` contains the maintained benchmark configuration and report artifacts.

Older exploratory folders may still exist, but the maintained path is `HundredPatches/pipeline/`.
