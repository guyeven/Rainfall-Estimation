# Compute-Link-Attenuations

This folder contains the rainfall-reconstruction pipeline and the reusable Python package used by it. Before running either workflow, set up the Python environment described in [Python Environment](#python-environment). After that, there are two common workflows:

- To create a new patch benchmark, start with [How To Create Patch Inputs](#how-to-create-patch-inputs).
- To run the already-existing 100-patch benchmark, skip to [How To Run The Existing 100-Patch Benchmark](#how-to-run-the-existing-100-patch-benchmark).

## Main Components

- `main.py` is the interactive patch-input generator. It builds per-patch microwave-link attenuation JSONL files from OPERA rainfall patches and 4TU link records.
- `batch_solve_multi.py` runs one or more solvers over a set of `est_input_*.json` patch files.
- `batch_analyze_multi.py` compares solver outputs against ground truth and produces analysis caches, tables, and plot inputs.
- `render_analysis_report.py` renders the cached analysis outputs into figures and spreadsheets.
- `cml_attenuation/` is the reusable Python package used by the entry points. It contains rainfall preprocessing, link geometry, segment-pixel intersections, attenuation/ITU utilities, IDW/ILDW baselines, and optimization solvers. The YAML configs use package-qualified module names such as `cml_attenuation.idw_baseline` and `cml_attenuation.solvers.solve_rain_lbfgsb_normalized_ildw_multipliers`.
- `HundredPatches/` contains the existing 100-patch benchmark inputs, pipeline configuration, solutions, and report artifacts.
- `Misc/` contains auxiliary debugging and synthetic-test artifacts that are not part of the maintained benchmark pipeline.

## Python Environment

The repository does not include a committed `.venv/` directory. Create a local environment before running the pipeline, then install the Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The main dependencies are NumPy, SciPy, h5py, pyproj, Matplotlib, PyYAML, and openpyxl.


## How To Create Patch Inputs

`main.py` and the patch-input generation utilities compute rain-induced microwave-link attenuation using OPERA rainfall patches and 4TU link data, following ITU-R P.838-3. This stage is what produces the `est_input_*.json` and `gt_*.npz` files later consumed by the solver pipeline.

Patch candidates are read from a patch-list JSONL file. Each patch record points back to an OPERA HDF5 source file through its `source_file` field. A second patch-attributes JSONL file is used during normal generation as an ID allow-list: only patch IDs that appear in that attributes file are processed. Some of those records contain manual annotations such as area type, rain type, intensity, notes, and an `approved` flag. The current `main.py` filtering step only checks whether a patch ID appears in the attributes file; it does not interpret the annotation fields or the `approved` value. If exact patch IDs are provided interactively, that attributes-file filter is bypassed.

For each selected rainfall patch, `main.py`:

1. Loads and preprocesses the OPERA rainfall crop referenced by the patch metadata.
2. Places the 4TU link geometry into the patch coordinate system.
3. Keeps only links whose endpoints lie inside the patch.
4. Computes rain attenuation for each retained link with ITU-R P.838-3.
5. Writes the generated benchmark inputs into structured output folders.

The interactive entry point is:

```bash
python main.py
```

It prompts for the patch-list JSONL, patch-attributes JSONL, 4TU links JSONL, output directory, number of patches, default polarization, and optional debug settings. In the normal path, the patch-attributes JSONL controls which patch IDs are eligible for processing; when exact patch IDs are entered manually, `main.py` processes those IDs directly.

For the existing 100-patch benchmark generation, the relevant input files are `../Patch-Generator/Benchmark-Patches/benchmark-500-files-758-patches.local.jsonl` for the patch list, `../Patch-Generator/Benchmark-Patches/Sorted-benchmark-500-files-758-patches_selected_with_attributes (1).jsonl` for the patch attributes/annotations, and `../Links-4TU-NL/LIST-OF-LINKS.jsonl` for the 4TU link records, when running from `Compute-Link-Attenuations/`.

For a chosen output directory, `main.py` writes:

- `est_dir/`: `est_input_*.json` files used by `batch_solve_multi.py`.
- `gt_dir/`: `gt_*.npz` ground-truth rainfall arrays, when ground-truth export is enabled.
- `patch_jsonl_files/`: `patch_*.jsonl` link-attenuation summaries and optional `debug_*.json` traces.

The existing 100-patch pipeline normally starts from the already-generated inputs in `HundredPatches/est_dir/`, the ground-truth files in `HundredPatches/gt_dir/`, and the patch JSONL files in `HundredPatches/patch_overview_generation/patch_jsonl_files/`.

When debug mode is enabled, `main.py` can also write a per-link debug JSON file containing intersected refined pixels, rainfall values, segment lengths, ITU specific attenuation, cumulative attenuation, and the total link attenuation. This is useful for validating geometry and attenuation calculations before scaling to many patches.

### Implementation Notes

The generated rainfa"ll arrays use image-style grid indices `[i, j]`, where `i` increases downward/southward and `j` increases rightward/eastward. The OPERA rainfall crop is refined from the native 2 km grid to a 125 m grid and then smoothed with a Gaussian filter (`sigma = 1` refined pixel, `mode = "nearest"`) before link attenuations are simulated. The smoothing is implemented by [`smooth_refined_gaussian()`](cml_attenuation/rainfall_processing.py#L113) in `cml_attenuation/rainfall_processing.py`. Link geometry is handled in EPSG:28992 (RD New) meter coordinates; the 4TU link network is placed into each selected patch coordinate system using a fixed anchor, and link lengths are converted to kilometers before applying the ITU-R P.838-3 attenuation model.

## How To Run The Existing 100-Patch Benchmark

The repository already contains the generated inputs for the 100-patch benchmark under `HundredPatches/`. You do not need to run `main.py` again for this existing benchmark unless you want to regenerate or change those inputs. Run the 100-patch comparison from this directory:

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

This compares the solver outputs against `HundredPatches/gt_dir/` and writes analysis artifacts to `HundredPatches/pipeline/batch_analyze_output/`. With the current configuration, the spreadsheet is `stats.xlsx` and the default cache is `stats_report_cache.json`. The spreadsheet is a human-facing inspection artifact; it is not consumed by later pipeline stages. The cache is the machine-readable artifact used by `render_analysis_report.py` to generate the report figures and outputs.

The generated `batch_analyze_output/` folder is intentionally not committed because the cache can exceed GitHub's normal 100 MB file limit. If code or configuration changes require the cache to be refreshed, rerun this stage locally before rendering the report.

3. Render the report artifacts:

```bash
python render_analysis_report.py \
  --cache HundredPatches/pipeline/batch_analyze_output/stats_report_cache.json \
  --render-config HundredPatches/pipeline/render_report.yaml \
  --output-dir HundredPatches/pipeline/report
```

This renders the configured figures and writes report artifacts under `HundredPatches/pipeline/report/`.
