# Robustness analysis on the largest patch (journal revision)

This directory holds the scripts and outputs behind the numerical results of
Section 8, "Robustness Analysis" (`sec:robustness`), of `Journal_200patches.tex`:
Table 12 (`tab:robust-idw`), Table 13 (`tab:robust-convex`) and the numbers
quoted in the text around them. Table numbers are those of the 13 November 2026
build.

Patch: `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202306192200_patch006` (summer,
19 June 2023, 22:00), the largest benchmark patch: 752 x 704 pixels of 125 m,
2093 links. Link 899 has identical endpoints (zero length), and its rain-rate
equivalent is zero in all runs.

## Error models

Errors e are added to the simulated attenuations A (dB per link). A + e >= 0 always.

| Name | Definition | Random draws |
|---|---|---|
| N1 | abs(e) <= 0.5 dB | e = min(0.5, A)(2u - 1), u uniform on [0, 1] |
| N2 | 0 <= e <= 2.3 dB on wet links | e = 2.3u |
| N2const | e = 2.3 dB on every wet link | (deterministic, the worst case of N2 for IDW) |

The draws use `numpy.random.default_rng(seed)`. IDW is evaluated on seeds
0-19. The Convex Solver (no shrinkage) is run on seeds 0-4 and on N2const,
each with fixed weights (F, the noise-free weights in `fixed_weights.json`)
and with weights recomputed from the noisy ILDW field (R). The solver
settings are in `run_convex.py` (L-BFGS-B, ftol 1e-6, gtol 1e-6, maxiter
2000). `nf` is a noise-free rerun with these settings, and it reproduces the
stored benchmark solution exactly. `nf_tight` uses ftol 1e-12, gtol 1e-9 and
maxiter 15000.

## Layout

```
common.py            patch data, rain-rate equivalent, error draws, IDW operator
inputs_lib.py        noisy input files and cached ILDW fields
prep.py              noise-free weights -> fixed_weights.json
step2_idw.py         IDW bound, exact worst case and random draws -> results_idw.json,
                     idw_fields.npz, idw_link_vectors.npy
step4_check_ops.py   check of the quadratic objective against the solver code -> results_ops_check.json
precompute_ildw.py   noisy inputs -> inputs/, ILDW fields -> ildw_cache/
run_convex.py        one Convex Solver run -> runs/<name>/
run_all.sh           all runs in runlist.txt, in parallel
step4_lmin.py        smallest Hessian eigenvalue and condition number -> results_lmin.json, lmin.npz
analyze.py           statistics of the Convex runs -> results_convex.json
make_summary.py      -> results.json, summary.md
paper_numbers.py     numbers quoted in the text that need a further step -> paper_numbers.json
memprobe.py          memory probe used to choose the number of parallel runs (not needed)
runs/<name>/         e.npy (error vector), solution.npz (R_hat), solution_itertrace.json,
                     solution_optinfo.json, result.json
*.log, runs/log_*    console output of the original runs
```

The weights are stored as `alpha_atten`, `alpha_1d` and `alpha_2d`. The paper
writes them as w_atten, w_1d and w_2d.

Proposition 2 in the paper is the form with the factor 2. The fields
`claim_*` in `runs/*/result.json` and `results_convex.json` hold the form
without it. `paper_numbers.py` converts them: the ratio in the paper equals
2 `claim_ratio_noise_free_H` - `cor_i_ratio`.

## Reproducing

The scripts need a checkout of `Compute-Link-Attenuations/` (it provides
the `cml_attenuation` package, the patch input and the stored benchmark
solutions). By default `common.py` uses the one in this repository, three
levels up. Set `CLA_REPO` to use another checkout. The original runs used
branch `oct26`, commit `c7a485d`, with Python 3.14, NumPy 2.4 and SciPy 1.16.

Run from this directory, in this order:

```
python prep.py
python step2_idw.py               # about 1.5 min
python step4_check_ops.py
python precompute_ildw.py         # about 26 min (12 ILDW fields)
PY=python NPAR=6 ./run_all.sh     # 24 runs of 3 to 24 min each
python step4_lmin.py              # about 6 min
python analyze.py
python make_summary.py
python paper_numbers.py           # about 1 min
```

`inputs/` and `ildw_cache/` (88 MB) are not tracked. `precompute_ildw.py`
regenerates them, and `run_convex.py` checks each input against the stored
error vector. The original batch ran `nf_tight` first and then
`runlist_rest.txt`. Paths recorded inside `result.json` and the logs refer to
the temporary folder where the runs were made.
