# Case studies I and II (journal revision)

This directory holds the inputs, solver outputs, figures and scripts for the
two case studies in `Journal_200patches.tex`. Each case is one benchmark
patch. Everything needed to redraw the figures and recompute the quoted
values is here. Rerunning the solvers also needs `Compute-Link-Attenuations/`
from this repository.

| Case | Season | Patch | Location | Paper figures |
|---|---|---|---|---|
| I | summer | `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202306120300_patch036` (12 June 2023, 03:00) | Piedmont, Italy | Fig. 7 (`fig:case_gt_convex_202301280900`), Fig. 8 (`fig:jtrace_gt_convex_202301280900`) |
| II | winter | `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301252200_patch000` (25 January 2023, 22:00) | English Channel off northern France | Fig. 9 (`fig:case_gt_convex_202301310900`), Fig. 10 (`fig:jtrace_gt_convex_202301310900`) |

The figure numbers are those of the 12 November 2026 build. The LaTeX labels
still carry the dates of earlier case-study patches.

Case I is the patch where the Convex Solver does worst relative to
Solver(GT). Case II is the patch where it does best.

## Layout

```
case_studies/
  case1_summer_202306120300_patch036/
    inputs/      est_input_<patch>.json   links, frequencies, simulated attenuations
                 gt_<patch>.npz           ground-truth rainfall R_gt (mm/h, 125 m pixels)
    solutions/   sol_dir_idw/                       IDW reconstruction (npz)
                 sol_dir_solver_gt_no_shrinkage/    Solver(GT): npz, itertrace, optinfo
                 sol_dir_convex_no_shrinkage/       Convex Solver: npz, itertrace, optinfo
    figures/     <patch>.png                  composite panel (Fig. 7)
                 case1-gt-iterations.png      objective trace, Solver(GT) (Fig. 8 left)
                 case1-convex-iterations.png  objective trace, Convex Solver (Fig. 8 right)
                 map_case1.png                map panel alone
  case2_winter_202301252200_patch000/   same structure (Figs. 9 and 10)
  osm_tiles_z7/            OpenStreetMap zoom-7 tiles used for the map panels
  objective_values.json    output of scripts/compute_objective_values.py
  scripts/                 see "Reproducing" below
  ATTRIBUTION.md           data sources, licences and required credits
```

Each solution `.npz` holds the reconstructed field `R_hat`. The `itertrace`
files hold one row per L-BFGS-B iteration with the objective terms and the
weights. The weights are stored as `alpha_atten`, `alpha_1d` and `alpha_2d`.
The paper writes them as w_atten, w_1d and w_2d.

## Provenance

- **Case I**: all inputs and solutions are copied unchanged from branch `oct26`,
  `Compute-Link-Attenuations/June2023HundredPatches/` (`est_dir/`, `gt_dir/` and
  `pipeline/solutions/sol_dir_{idw,solver_gt_no_shrinkage,convex_no_shrinkage}/`).
- **Case II**: the inputs and the IDW solution are copied unchanged from
  `Compute-Link-Attenuations/HundredPatches/` (`est_dir/`, `gt_dir/`,
  `pipeline/solutions/sol_dir_idw/`) as committed on branch `main`. The winter
  no-shrinkage solver outputs were never committed, so Solver(GT) and the
  Convex Solver were rerun on 2026-11-12 with the settings in
  `scripts/solver_settings.yaml`. The environment was Python 3.13.5,
  NumPy 2.5.0, SciPy 1.18.0 and Matplotlib 3.11.0. The whole-patch RMSEs of the
  rerun outputs match the per-patch metrics behind the paper
  (`d3_patch_metrics_200.csv`).
- **Control**: rerunning both solvers on Case I in the same environment
  reproduced the stored `oct26` solutions bit for bit (max |ΔR| = 0, same
  iteration counts, same final J).
- **Figures**: produced by `scripts/render_case_figures.py`. The panel layout
  follows `output/journal_revision/tools/render_case_studies_no_shrinkage.py`.
  The objective traces use `scripts/jplot_w.py`, a copy of `plot_j_behavior`
  from `Compute-Link-Attenuations/render_analysis_report.py` in which only the
  legend labels were changed from α to w. Rerunning the script reproduces the
  stored PNGs byte for byte in the environment above.

## Objective values and RMSE

J = w_atten J_atten + w_1d J_1d + w_2d J_2d, with each weight equal to 1/J_k
at the ILDW field and w_2d halved. Values from `objective_values.json`, rounded:

| Quantity | Case I | Case II |
|---|---:|---:|
| J at the ground truth | 5.4863 | 2.0992 |
| J, Solver(GT), final | 3.7120 | 0.2205 |
| Solver(GT) iterations | 12 | 566 |
| J, Convex Solver, surrogate (final row of its trace) | 0.2776 | 0.2221 |
| J, Convex Solver, original objective | 0.2976 | 0.2237 |
| Convex Solver iterations | 862 | 676 |
| RMSE IDW (mm/h) | 3.0472 | 0.6099 |
| RMSE Solver(GT) (mm/h) | 0.2115 | 0.3264 |
| RMSE Convex Solver (mm/h) | 2.4767 | 0.3206 |

The Convex Solver trace records a surrogate objective. It is evaluated on
virtual links, with w_atten recomputed on those links. The original objective
at the Convex Solver solution is w_atten (real links) × `J_atten_real` +
w_1d J_1d + w_2d J_2d at the last row of the trace. The RMSEs are over all
pixels of the patch.

The J-trace legends include a w_total · J_total entry. It is identically zero
because `num_total` is 0 in the solver settings.

## Reproducing

Requirements: Python 3 with NumPy, Matplotlib and Pillow. Rerunning the
solvers also needs SciPy and PyYAML. Run from any directory.

```bash
# Objective values and RMSEs -> objective_values.json
python scripts/compute_objective_values.py

# All eight figures. Use --out to avoid overwriting the stored copies.
python scripts/render_case_figures.py --out /tmp/case_figures

# Rerun Solver(GT) and the Convex Solver on both cases.
# The stored solutions are not touched. Results go to rerun_output/<case>/solutions/.
python scripts/rerun_solvers.py --repo ../../../Compute-Link-Attenuations --out rerun_output

# Only if tiles are missing: download them from tile.openstreetmap.org.
python scripts/fetch_osm_tiles.py
```

The `--repo` path above assumes the command is run from this directory.
The map panels need no network access because the tiles are stored in
`osm_tiles_z7/`. Tiles downloaded later may differ, because OpenStreetMap
data change.

## Credits

Ground truth derived from EURADCLIM v3.0 (KNMI, CC BY 4.0), based on
EUMETNET/OPERA radar data and ECA&D rain-gauge data. Link geometry from the
4TU commercial microwave-link dataset, version 1 (CC BY 4.0). Map data ©
OpenStreetMap contributors, available under the Open Database License
(<https://www.openstreetmap.org/copyright>). Full details, DOIs and the changes
made are in [`ATTRIBUTION.md`](ATTRIBUTION.md).
