# Compute-Link-Attenuations

This folder contains the maintained rainfall-reconstruction pipeline and the Python modules used by it. The current benchmark path is `HundredPatches/pipeline/`.

## Main Components

- `batch_solve_multi.py` runs one or more solvers over a set of `est_input_*.json` patch files.
- `batch_analyze_multi.py` compares solver outputs against ground truth and produces analysis caches, tables, and plot inputs.
- `render_analysis_report.py` renders the cached analysis outputs into figures and spreadsheets.
- `main.py` is the interactive patch-input generator. It builds per-patch microwave-link attenuation JSONL files from OPERA rainfall patches and 4TU link records.
- `idw_baseline.py` and `ildw_baseline.py` implement interpolation baselines.
- `solve_rain_lbfgsb_normalized_ildw_multipliers*.py` implement the optimization-based solver variants.
- `itu_model.py`, `attenuation.py`, and `link_geometry.py` contain shared forward-model and geometry utilities.
- `HundredPatches/` contains the maintained benchmark configuration and report artifacts.

Older exploratory folders may still exist, but the maintained path is `HundredPatches/pipeline/`.

## Inputs And Patch Generation

The patch-input generation code computes rain-induced microwave-link attenuation using OPERA rainfall patches and 4TU link data, following ITU-R P.838-3. For each selected rainfall patch, the generator:

1. Loads the rainfall field from the patch HDF5 source file.
2. Crops the rainfall field to the patch extent.
3. Replaces missing or NaN rainfall values with zero.
4. Refines the OPERA grid from 2 km resolution to 125 m resolution by 16-by-16 inheritance.
5. Smooths the refined rainfall field with a Gaussian filter using `sigma = 1` refined pixel and `mode = "nearest"`.
6. Places the 4TU link geometry into the patch coordinate system using a fixed anchor.
7. Keeps only links whose endpoints lie inside the patch.
8. Computes rain attenuation for each retained link with ITU-R P.838-3.
9. Writes one JSONL file per patch with the resulting link-attenuation observations.

The interactive entry point is:

```bash
python main.py
```

It prompts for the patch-list JSONL, patch-attributes JSONL, 4TU links JSONL, output directory, number of patches, default polarization, and optional debug settings. The maintained 100-patch pipeline normally starts from the already-generated inputs in `HundredPatches/est_dir/` and the ground-truth files in `HundredPatches/gt_dir/`.

When debug mode is enabled, `main.py` can also write a per-link debug JSON file containing intersected refined pixels, rainfall values, segment lengths, ITU specific attenuation, cumulative attenuation, and the total link attenuation. This is useful for validating geometry and attenuation calculations before scaling to many patches.

Coordinate conventions used by the generator:

- Rainfall grids are indexed as `[i, j]`, with `i` increasing southward and `j` increasing eastward.
- Geometry calculations use EPSG:28992 (RD New) in meters.
- Link lengths are converted to kilometers before applying the ITU attenuation model.

## Maintained Batch Pipeline

Run the maintained 100-patch comparison from this directory:

```bash
cd Compute-Link-Attenuations
```

The pipeline has three main stages.

1. Produce solution files:

```bash
python batch_solve_multi.py --config HundredPatches/pipeline/batch_solve_config.yaml
```

This reads the estimator inputs from `HundredPatches/est_dir/` and writes solver outputs under `HundredPatches/pipeline/solutions/`. The maintained solver set is IDW, ILDW, Solver(ILDW), Convex Solver, Homotopy Solver, and Solver(GT).

2. Produce the analysis cache and spreadsheet:

```bash
python batch_analyze_multi.py \
  --config HundredPatches/pipeline/analyze.yaml \
  --analyze-only
```

This compares the solver outputs against `HundredPatches/gt_dir/` and writes analysis artifacts to `HundredPatches/pipeline/batch_analyze_output/`. With the current configuration, the spreadsheet is `stats.xlsx` and the default cache is `stats_report_cache.json`.

The generated `batch_analyze_output/` folder is intentionally not committed because the cache can exceed GitHub's normal 100 MB file limit. If code or configuration changes require the cache to be refreshed, rerun this stage locally before rendering the report.

3. Render the report artifacts:

```bash
python render_analysis_report.py \
  --cache HundredPatches/pipeline/batch_analyze_output/stats_report_cache.json \
  --render-config HundredPatches/pipeline/render_report.yaml \
  --output-dir HundredPatches/pipeline/report
```

This renders the configured figures and writes report artifacts under `HundredPatches/pipeline/report/`.

## Python Environment

Install the Python dependencies before running the pipeline:

```bash
python -m pip install -r requirements.txt
```

The main dependencies are NumPy, SciPy, h5py, pyproj, Matplotlib, PyYAML, and openpyxl.
