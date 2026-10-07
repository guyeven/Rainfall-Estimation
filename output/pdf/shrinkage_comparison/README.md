# Shrinkage comparison report

Six methods on 100 matched patches: IDW, ILDW, and Solver(ILDW)/Convex with light or no shrinkage. Figures use shortened labels `light` and `none`.

## Rebuild from repository root

```bash
Compute-Link-Attenuations/.venv/bin/python output/pdf/shrinkage_comparison/build_results.py
Compute-Link-Attenuations/.venv/bin/python output/pdf/shrinkage_comparison/build_d3.py
cd output/pdf/shrinkage_comparison
pdflatex -interaction=nonstopmode -halt-on-error shrinkage_comparison.tex
pdflatex -interaction=nonstopmode -halt-on-error shrinkage_comparison.tex
```

LaTeX compilation only requires the included figures and tables. The builders require the saved repository outputs and the new `batch_analyze_output_shrinkage_comparison/stats_report_cache.json`. No solver reruns or standard renderer pass are required.

- `results_summary.json`: equal-patch statistics, Taylor moments, stopping records, timing metadata and source hashes.
- `per_patch_metrics.csv`: 600 method/patch rows, checked against the analysis cache.
- `d3_statistics.json`: wet/dry boxplot counts and summaries; min/max whiskers.
- `figures/`: vector PDF and PNG assets, including four combined 100-patch convergence figures.

Runtime limitation: Solver(ILDW) no shrinkage has no recorded runtime. Convex no shrinkage records optimizer-only time, shown separately from end-to-end benchmarks. Benchmark sessions are not controlled paired comparisons.
