# Batch pipeline: multi-solver rainfall estimation + cache-based report rendering

This repo supports a two-stage workflow:

1. **Run multiple solvers** on a set of `est_input_*.json` patches and write one `_solution.npz` per patch per solver.
2. **Analyze** the outputs against ground truth (GT), write a cache JSON, and optionally render a report from that cache.

The workflow is designed so that **IDW is treated like any other solver**: you run it once to produce `.npz` outputs, then feed those outputs into the analyzer. The main benefit of the cache split is that you can iterate on plots and Excel output with `render_analysis_report.py` without re-running the expensive statistics pass in `batch_analyze_multi.py`.

---

## 0) Inputs at a glance

You’ll typically have:

- **Ground truth (GT)**: per-pixel rainfall field, stored as `.npz` files  
  Example folder: `.../gt_dir/gt_*.npz`

- **Estimated-input patches (`est_input_*.json`)**: link geometry + link observations for each patch  
  Example folder: `.../est_dir/est_input_*.json`

- **Solver outputs**: one folder per solver, containing `est_input_*_solution.npz` files  
  Example folders:
  - `.../sol_dir_opt_0p1/`
  - `.../sol_dir_opt_idw/`
  - `.../sol_dir_idw/`

---

## 1) Run multiple solvers: `batch_solve_multi.py`

### What it does
`batch_solve_multi.py`:
- reads all `est_input_*.json` files in `est_dir`
- runs each solver specified in the config
- writes a `_solution.npz` per patch into each solver’s `out_dir`

### Command
```bash
python batch_solve_multi.py --config <path/to/batch_solve_multi.yaml>
```

### Config: high-level structure
A typical config specifies:
- where to find the input patches (`est_dir`)
- which solvers to run
- output directory per solver
- solver-specific parameters

Example (high-level):

```yaml
input:
  est_dir: "est_dir"
  file_pattern: "est_input_*.json"
  recursive: false

solvers:
  OPT_0p1:
    label: "OPT_0p1"
    type: "lbfgsb"
    module: "solve_rain_lbfgsb"
    out_dir: "sol_dir_opt_0p1"
    optimization: { ... }
    tolerances:  { ... }

  OPT_IDW:
    label: "OPT_IDW"
    type: "lbfgsb"
    module: "solve_rain_lbfgsb"
    out_dir: "sol_dir_opt_idw"
    optimization: { R0_from_IDW: true, ... }
    idw: { r_max_m: ..., power: ..., ... }   # used for IDW init

  IDW:
    label: "IDW"
    type: "idw"
    module: "idw_baseline"
    out_dir: "sol_dir_idw"
    idw: { r_max_m: ..., power: ..., ... }

  OPT_ILDW_CONSTR_AL:
    label: "OPT_ILDW_CONSTR_AL"
    type: "custom"
    module: "solve_rain_constrained_al"
    out_dir: "sol_dir_opt_ildw_constr_al"

    optimization:
      maxiter: 300
      R0_from_ILDW: true

    tolerances:
      ftol: 1.0e-08
      gtol: 1.0e-07
      maxls: 20

    idw:
      r_max_m: 15000.0
      power: 2.0
      eps_m: 1.0
      default_value: 0.0

    augmented_lagrangian:
      constraint_ratio: 0.1      # tau = 0.1 * J_atten(IDW)
      constraint_tol: 1.0e-08
      outer_maxiter: 8
      rho_init: 10.0
      rho_growth: 2.0
      rho_max: 1.0e8
      min_progress_ratio: 0.9
      weight_floor: 1.0e-12
      scale_1d: 1.0
      scale_2d: 1.0
      scale_total: 1.0
```

**Path convention:** relative paths in the YAML are interpreted **relative to the config file’s location**.

`solve_rain_constrained_al.py` writes standard `R_hat` solver outputs plus `meta_*` fields and `*_alinfo.json`; `batch_analyze_multi.py` works without changes.

---

## 2) Analyze multiple solver outputs: `batch_analyze_multi.py`

### What it does
`batch_analyze_multi.py`:
- loads GT patches from `gt_dir`
- loads solver results from each solver’s `sol_dir`
- computes per-bin statistics for:
  - **coverage bins** (how many links intersect a pixel)
  - **distance bins** (distance to the 3rd nearest link)
- writes a cache JSON containing:
  - ordered Excel-sheet payloads
  - per-patch distributions used by the aggregate plots
  - optional plot jobs for patch-map rendering
- by default, immediately calls `render_analysis_report.py` afterward unless you pass `--analyze-only`

### Command
```bash
python batch_analyze_multi.py --config <path/to/analyze_multi.yaml>
```

### Analyze-only command
If you want to stop after the cache is written and render later:

```bash
python batch_analyze_multi.py --config <path/to/analyze_multi.yaml> --analyze-only
```

### Config: high-level structure
A typical analyzer config specifies:
- `gt_dir` (ground truth)
- `est_input_dir` (needed for link geometry and distance-to-links binning)
- a list/dict of solvers and where their outputs are
- output directory for plots + Excel
- distance bin edges (meters) and rain threshold

Example (high-level):

```yaml
input:
  gt_dir: "gt_dir"
  est_input_dir: "est_dir"

  solvers:
    OPT_0p1:
      label: "OPT_0p1"
      sol_dir: "sol_dir_opt_0p1"

    OPT_IDW:
      label: "OPT_IDW"
      sol_dir: "sol_dir_opt_idw"

    IDW:
      label: "IDW"
      sol_dir: "sol_dir_idw"

rain:
  threshold_mmph: 1.0

distance:
  bin_edges_m: [125, 375, 750, 1500, 3125, 6000, 9000, 12000]
  method: sampled_points   # matches old behavior; endpoints_midpoints is faster

output:
  out_dir: "batch_analyze_output_multi"
  excel_filename: "coverage_stats_long_multi.xlsx"
```

### What gets written
The analyzer writes its main cache to:

```text
<output.out_dir>/<excel_filename_without_suffix>_report_cache.json
```

For example, if:
- `out_dir = "batch_analyze_output_multi"`
- `excel_filename = "stats_multi_new_solver.xlsx"`

then the cache path is:

```text
batch_analyze_output_multi/stats_multi_new_solver_report_cache.json
```

---

## 3) Render a report from an existing cache: `render_analysis_report.py`

### What it does
`render_analysis_report.py`:
- reads the cache JSON produced by `batch_analyze_multi.py`
- writes the Excel workbook
- renders the configured plots into the report output directory

This is the command you use when you want to regenerate plots and Excel from cached analysis results, without recomputing the statistics.

### Command
```bash
python render_analysis_report.py \
  --cache <path/to/*_report_cache.json> \
  --output-dir <path/to/report_dir> \
  --render-config <path/to/render_report.yaml>
```

### Example: HundredPatches
```bash
python render_analysis_report.py \
  --cache HundredPatches/norm_post_refactor/batch_analyze_output_multi/stats_multi_new_solver_report_cache.json \
  --output-dir HundredPatches/norm_post_refactor/report \
  --render-config HundredPatches/norm_post_refactor/render_report.yaml
```

If `--render-config` is omitted, the renderer tries to auto-discover `render_report.yaml` next to the analysis config recorded in the cache. If that file is not present, it falls back to built-in defaults.

---

## 4) The two main experiment directories

The two directories that currently matter most are:

- [TenPatches](/Users/isoto/Documents/MPI/Research/RainfallMap/Compute-Link-Attenuations/TenPatches)
  Contains experiments built from **10 patches**.

- [HundredPatches](/Users/isoto/Documents/MPI/Research/RainfallMap/Compute-Link-Attenuations/HundredPatches)
  Contains experiments built from **100 patches**.

In practice, these are the two scales you will most often compare when testing solver behavior, report rendering, and runtime.

---

## 5) Example runs

### TenPatches

The workflow is:

1. Run solvers:
```bash
python batch_solve_multi.py --config TenPatches/batch_solve_multi_config.yaml
```

2. Analyze outputs and render immediately:
```bash
python batch_analyze_multi.py --config TenPatches/analyze_multi.yaml
```

3. Or analyze first, then rerender from cache later:
```bash
python batch_analyze_multi.py --config TenPatches/norm_post_refactor/analyze_multi.yaml --analyze-only

python render_analysis_report.py \
  --cache TenPatches/norm_post_refactor/batch_analyze_output_multi/stats_multi_new_solver_report_cache.json \
  --output-dir TenPatches/norm_post_refactor/report \
  --render-config TenPatches/norm_post_refactor/render_report.yaml
```

### HundredPatches

```bash
python batch_analyze_multi.py --config HundredPatches/norm_post_refactor/analyze_multi.yaml --analyze-only

python render_analysis_report.py \
  --cache HundredPatches/norm_post_refactor/batch_analyze_output_multi/stats_multi_new_solver_report_cache.json \
  --output-dir HundredPatches/norm_post_refactor/report \
  --render-config HundredPatches/norm_post_refactor/render_report.yaml
```

Outputs are written under the `out_dir` and report directory you provide:
- cache JSON
- Excel workbook
- aggregate plots
- optional patch error maps, if the cache contains `patch_plot_jobs`
