# Batch pipeline: multi-solver rainfall estimation + analysis

This repo supports a two-stage workflow:

1. **Run multiple solvers** on a set of `est_input_*.json` patches and write one `_solution.npz` per patch per solver.
2. **Analyze** the outputs against ground truth (GT) and produce:
   - an Excel workbook with per-bin statistics
   - two “distance-profile” plots (rainy vs non-rainy) comparing GT vs each solver

The workflow is designed so that **IDW is treated like any other solver**: you run it once to produce `.npz` outputs, then feed those outputs into the analyzer.

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
```

**Path convention:** relative paths in the YAML are interpreted **relative to the config file’s location**.

---

## 2) Analyze multiple solver outputs: `batch_analyze_multi.py`

### What it does
`batch_analyze_multi.py`:
- loads GT patches from `gt_dir`
- loads solver results from each solver’s `sol_dir`
- computes per-bin statistics for:
  - **coverage bins** (how many links intersect a pixel)
  - **distance bins** (distance to the 3rd nearest link)
- produces:
  - an Excel workbook with sheets for `GT vs <solver>`
  - two summary plots:
    1. **rainy pixels**: distance-profile using *relative absolute error*
    2. **non-rainy pixels**: distance-profile using *absolute error*

The plots show, per distance bin:
- the **median** error per patch
- aggregated across patches via **IQR** (interquartile range: p25–p75)

### Command
```bash
python batch_analyze_multi.py --config <path/to/analyze_multi.yaml>
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

---

## 3) Example run: `TenPatches/`

Up to this commit, the folder `TenPatches/` contains a complete example run using three methods:

- **OPT_0.1**: L-BFGS-B solver with \(R_0\) initialised to a constant **0.1**
- **OPT_IDW**: L-BFGS-B solver with \(R_0\) initialised from **IDW**
- **IDW**: inverse-distance weighting baseline

The workflow is:

1) Run solvers:
```bash
python batch_solve_multi.py --config TenPatches/batch_solve_multi_config.yaml
```

2) Analyze outputs:
```bash
python batch_analyze_multi.py --config TenPatches/analyze_multi.yaml
```

Outputs are written under the `out_dir` specified in the analyzer config:
- Excel workbook (per-solver sheets)
- 2 distance-profile plots:
  - rainy pixels
  - non-rainy pixels
