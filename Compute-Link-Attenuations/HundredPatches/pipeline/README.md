# HundredPatches Pipeline

This directory contains the maintained 100-patch multi-solver configuration.

## Files

- `batch_solve_config.yaml`: runs the six maintained solver outputs.
- `analyze.yaml`: compares the six solver outputs against the ground-truth rainfall patches.
- `render_report.yaml`: renders figures and spreadsheet outputs from the analysis cache/report artifacts.
- `report/`: committed report artifacts and figures produced by the maintained configuration.
- `solutions/`: expected location for solver outputs. This directory may be restored or regenerated separately.

## Solver Set

The maintained comparison uses:

1. `IDW`
2. `ILDW`
3. `Solver(ILDW)`
4. `Convex Solver`
5. `Homotopy Solver`
6. `Solver(GT)`

## Running

From `Compute-Link-Attenuations/`:

```bash
python batch_solve_multi.py --config HundredPatches/pipeline/batch_solve_config.yaml
python batch_analyze_multi.py --config HundredPatches/pipeline/analyze.yaml --analyze-only
python render_analysis_report.py --cache HundredPatches/pipeline/batch_analyze_output/stats_report_cache.json --render-config HundredPatches/pipeline/render_report.yaml --output-dir HundredPatches/pipeline/report
```

The generated `batch_analyze_output/` folder is ignored because the cache file can exceed GitHub's normal 100 MB file limit. If code or configuration changes require the cache to be refreshed, rerun `batch_analyze_multi.py` with `analyze.yaml` to recreate it locally.
