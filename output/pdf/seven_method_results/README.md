# Seven-method rainfall results

The report analyzes the 100 matched saved patches for IDW, ILDW, Solver(ILDW),
Convex, Homotopy, GMZ (ITU adaptation), and Roy DCT (ILDW initialization, 300 outer
cap). It excludes the old Roy run and Solver(GT). It does not rerun solvers.

## Files

- `seven_method_results.tex` and `seven_method_results.pdf`: editable report and compiled PDF.
- `figures/` and `tables/`: figure assets and generated LaTeX tables.
- `report_numbers.tex`: numerical interpretations generated from verified summaries.
- `results_summary.json`: statistics, timing metadata, stopping counts, and selected source hashes.
- `per_patch_metrics.csv`: 700 matched method/patch records.
- `build_results.py`: reads saved fields/cache/diagnostics and generates statistics and figures.
- `write_numbers.py`: generates numerical report text.
- `build_d3.py`: renders rainy and non-rainy third-closest-link box-and-whisker profiles (quartile boxes, median lines, min/max whiskers; full-range and detail views) from the existing cache.
- `d3_statistics.json`: D3 bin counts, medians, quartiles, and the source cache hash.
- `implementation_snapshot/`: GMZ/Roy code and configurations as read for this report.

## Compile the existing source bundle

With a LaTeX installation providing the standard packages used in the document,
run these commands from this directory:

```bash
pdflatex -interaction=nonstopmode -halt-on-error seven_method_results.tex
pdflatex -interaction=nonstopmode -halt-on-error seven_method_results.tex
```

All required figure/table assets are in the source archive. The report can be
compiled without the original cache. The Python builders require the original
repository data and its Python environment, and expect this directory to be at
`output/pdf/seven_method_results` within that repository:

```bash
Compute-Link-Attenuations/.venv/bin/python output/pdf/seven_method_results/build_results.py
Compute-Link-Attenuations/.venv/bin/python output/pdf/seven_method_results/write_numbers.py
Compute-Link-Attenuations/.venv/bin/python output/pdf/seven_method_results/build_d3.py
```

## Interpretation

- Means weight patches equally; sample SD is across patches.
- Taylor aggregate points pool within-patch moments; clouds normalize each patch
  by its own reference SD. Mean bias is excluded from Taylor distances.
- Every optimization panel has 100 real traces. Thin lines stop at their saved
  endpoints. Thick median curves retain all 100 patches by carrying final values
  forward; dashed median segments flag this convention.
- IDW and ILDW are direct baselines, without iterative optimization histories.
- Runtime is not available for Solver(ILDW) or Homotopy. Available runtime records
  were collected in different benchmark sessions; hardware equivalence is not
  established for the newer GMZ/Roy measurements.
- GMZ virtual-gauge attenuation constraints do not survive rasterization exactly.
- Roy has 52 successful outer stops and 48 cap-limited runs; GMZ has 15 tolerance
  stops and 85 cap-limited runs. Output completion is not convergence.
