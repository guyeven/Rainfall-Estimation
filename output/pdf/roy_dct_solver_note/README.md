# Roy DCT solver technical note

Compile the self-contained LaTeX and figures:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error roy_dct_solver_note.tex
```

The note has 18 pages covering the objective, paper connection, parameters, numerical method, stopping tests, saved diagnostics, statistical comparisons, timing, and Taylor diagrams. No solver was rerun and existing reports were not changed.

`analyze_saved_runs.py` regenerates the numerical audit, extracted comparison tables and convergence figure when run at its current location inside the repository. It requires the original saved results, timing files and Roy-inclusive journal outputs. It does not regenerate the manually authored explanatory LaTeX prose. After changing data, check that prose statistics still agree with the generated summary.

`per_patch_diagnostics.csv` contains all 100 final convergence margins and runtime records. `run_summary.json` contains aggregate statistics and source hashes. `taylor_statistics.json` contains the existing Taylor point values. `implementation_snapshot/` preserves the solver, run configuration, and dependency declarations as inspected for this note; it is a reference snapshot, not a standalone runnable project.

Runtimes of IDW, ILDW and Convex come from separately saved benchmarks. Solver(ILDW), Solver(GT), and Homotopy timings were not available. Roy timings cover optimization, not end-to-end batch runtime. All Roy outer loops stopped at the iteration limit despite inner ADMM convergence.

The revised PDF has clickable contents entries and a Contents return link on every page. Initialization is written per pixel to avoid confusing the vector of ones with an extra decimal digit.
