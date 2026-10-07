# June 2023 pipeline

`batch_solve_config.yaml` runs eight methods on `../est_dir/est_input_*.json`:
IDW, ILDW, Solver(ILDW), Convex Solver with light and no shrinkage,
Homotopy Solver with light and no shrinkage, and Roy DCT with ILDW initialization.
Each method writes to its own `solutions/sol_dir_<name>/` folder inside this
pipeline directory. Paths resolve relative to the YAML, independent of shell
working directory. Output directories are created by the batch runner.

From the repository root:

```sh
Compute-Link-Attenuations/.venv/bin/python Compute-Link-Attenuations/batch_solve_multi.py --config Compute-Link-Attenuations/June2023HundredPatches/pipeline/batch_solve_config.yaml
```

Optimization-based L-BFGS-B methods use `maxiter: 2000`. Homotopy uses
`beta_delta: 0.1` (11 stages, beta 0 to 1); its iteration cap applies per stage.
Roy DCT uses the existing nonlinear ITU configuration, ILDW initialization,
`max_outer: 300`, and `inner_maxiter: 2000`. These are upper limits: convergence
can stop iterations earlier. Other numerical settings match HundredPatches.

Light shrinkage means `num_total: 1.0` with
`num_total_divide_by_num_pixels: true`. No shrinkage means `num_total: 0.0`;
attenuation and spatial regularization remain enabled. Solver(ILDW) retains
the existing light shrinkage setting. IDW and ILDW have no optimizer cap.

The runner uses one solver worker and two patch workers, as in the maintained
HundredPatches baseline. Running the full batch can be expensive, particularly
Roy DCT. To run fewer methods, use a separate YAML containing the selected
entries from `solvers`; preserve the desired output directories.

The analysis cache contains both per-patch records and aggregate statistics.
Changing the included patch set requires rerunning analysis against the saved
solutions so all statistics are recomputed consistently; deleting individual
cache records is insufficient. Solver comparisons can also be reduced by
regenerating the analysis with only the desired methods. Neither operation
requires rerunning the solvers when their outputs are already available.
Keep the original cache and write subset analyses to a separate output path.
