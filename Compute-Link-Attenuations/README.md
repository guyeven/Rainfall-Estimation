# Compute-Link-Attenuations

This folder contains the maintained rainfall-reconstruction pipeline and the Python modules used by it. The current benchmark path is `HundredPatches/pipeline/`.

## Main Components

- `main.py` is the interactive patch-input generator. It builds per-patch microwave-link attenuation JSONL files from OPERA rainfall patches and 4TU link records.
- `batch_solve_multi.py` runs one or more solvers over a set of `est_input_*.json` patch files.
- `batch_analyze_multi.py` compares solver outputs against ground truth and produces analysis caches, tables, and plot inputs.
- `render_analysis_report.py` renders the cached analysis outputs into figures and spreadsheets.
- `cml_attenuation/` is the reusable Python package used by the entry points. It contains geometry, rainfall preprocessing, attenuation/ITU utilities, interpolation baselines, and optimization solvers.
- `cml_attenuation/solvers/` contains the L-BFGS-B solver implementations used by the maintained configuration.
- `HundredPatches/` contains the maintained benchmark configuration and report artifacts.

Older exploratory folders may still exist, but the maintained path is `HundredPatches/pipeline/`.

## Python Package Layout

The reusable implementation lives in `cml_attenuation/` so that command-line entry points can stay small and the same code can be imported consistently from batch jobs, reports, and tests. The main package modules are:

- `cml_attenuation/rainfall_processing.py`: rainfall crop refinement, NaN handling, and smoothing.
- `cml_attenuation/link_geometry.py` and `cml_attenuation/intersection.py`: patch geometry, link placement, and segment-pixel intersections.
- `cml_attenuation/attenuation.py`, `cml_attenuation/itu_model.py`, and `cml_attenuation/itu_r_p_8383.py`: forward attenuation model and ITU-R P.838-3 coefficients.
- `cml_attenuation/idw_baseline.py` and `cml_attenuation/ildw_baseline.py`: interpolation baselines.
- `cml_attenuation/solvers/`: optimization-based reconstruction modules.

The YAML configs use these package-qualified module names directly, for example `cml_attenuation.idw_baseline` and `cml_attenuation.solvers.solve_rain_lbfgsb_normalized_ildw_multipliers`. Run the CLIs from `Compute-Link-Attenuations/` so Python can find the local package without installation.

## Inputs And Patch Generation

The patch-input generation code computes rain-induced microwave-link attenuation using OPERA rainfall patches and 4TU link data, following ITU-R P.838-3. The patch generator records patch selections as JSONL metadata; each selected patch points back to an OPERA HDF5 source file through its `source_file` field. For each selected rainfall patch, the attenuation generator:

1. Loads the OPERA rainfall HDF5 file referenced by the patch metadata.
2. Crops the rainfall field to the patch extent.
3. Replaces missing or NaN rainfall values with zero.
4. Refines the OPERA grid from 2 km resolution to 125 m resolution by 16-by-16 inheritance.
5. Smooths the refined rainfall field with a Gaussian filter using `sigma = 1` refined pixel and `mode = "nearest"`. Here `sigma = 1` means the Gaussian kernel is measured in the 125 m refined-grid pixels, and `mode = "nearest"` means values outside the grid boundary are handled by extending the nearest edge value.
6. Places the 4TU link geometry into the patch coordinate system using a fixed anchor.
7. Keeps only links whose endpoints lie inside the patch.
8. Computes rain attenuation for each retained link with ITU-R P.838-3.
9. Writes the generated benchmark inputs into structured output folders.

The interactive entry point is:

```bash
python main.py
```

It prompts for the patch-list JSONL, patch-attributes JSONL, 4TU links JSONL, output directory, number of patches, default polarization, and optional debug settings. This is the tool used to generate the benchmark input folders consumed by the maintained solver pipeline. For a chosen output directory, it writes:

- `est_dir/`: `est_input_*.json` files used by `batch_solve_multi.py`.
- `gt_dir/`: `gt_*.npz` ground-truth rainfall arrays, when ground-truth export is enabled.
- `patch_jsonl_files/`: `patch_*.jsonl` link-attenuation summaries and optional `debug_*.json` traces.

The maintained 100-patch pipeline normally starts from the already-generated inputs in `HundredPatches/est_dir/`, the ground-truth files in `HundredPatches/gt_dir/`, and the patch JSONL files in `HundredPatches/patch_overview_generation/patch_jsonl_files/`.

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

The repository does not include a committed `.venv/` directory. Create a local environment before running the pipeline, then install the Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The main dependencies are NumPy, SciPy, h5py, pyproj, Matplotlib, PyYAML, and openpyxl.
