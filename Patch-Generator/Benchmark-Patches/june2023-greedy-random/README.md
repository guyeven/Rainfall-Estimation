# Random-order greedy June 2023 benchmark

`selected-patches.june2023.jsonl` is the Explorer-compatible patch list.
`review-*.png` show those crops in the same order. Source paths are relative
to the repository root; pixel bounds are inclusive. The image scale saturates
at 30 mm/hour; titles show actual maxima. Axes are kilometres.

All 720 June hourly HDF5 maps are screened using fixed criteria: Explorer's
4x4 smoothing and 3 mm threshold; 8-connected regions with width and height
50–94 km; raw peak 15–150 mm; coefficient of variation >=0.8; fraction of
pixels >=1 mm <=0.85; fraction >=10 mm >=0.005; missing fraction <=0.01.
These identify convective-looking patterns, not confirmed convection.
There are no subjective exclusions or rankings by convection score, and no
solver results enter selection. Numerical screening does not rule out all
radar artifacts.

Candidates are ordered by source filename and connected-component index,
then permuted once with NumPy PCG64, seed **202306**. A candidate is accepted
only if it is at least four hours apart AND its centre is at least 75 km
away from every previously accepted patch. Selection stops at 300 or when
the candidate pool is exhausted. Four-hour spacing caps the possible count
at 180 for this month; the greedy result may be smaller and is not a
maximum-cardinality selection. No alternate seeds are tried to improve count.

`sampling-manifest.json` records the count, stopping condition, seed, NumPy
version, candidate hash, screening parameters and verified minimum pairwise
separations. `random-seed.txt` contains the seed alone.
`eligible-candidates.jsonl` preserves the complete sampling frame and
screening measurements. `selection-audit.jsonl` records each visited candidate's
priority, decision and first conflicting accepted patch.

The sample has unequal inclusion probabilities: densely conflicting candidates
have less opportunity to survive. It is a randomized separated benchmark,
not a simple random sample. Separation reduces dependence but does not
establish independence of method-performance differences across patches.

To use with `Compute-Link-Attenuations/main.py`, supply the selected patch list
and `patch-attributes.june2023.jsonl`. The attributes file includes all selected
IDs so the default ID filter retains them. Annotation approval indicates
inclusion by the screening procedure, not independent meteorological review.
The patch list follows **random acceptance order**: selecting the first k rows
retains a prefix of this same random procedure, without chronological bias.

Reproduce from the repository root:

```sh
MPLCONFIGDIR=/private/tmp/rain-june-mpl Patch-Generator/backend/.venv/bin/python Patch-Generator/Tools/sample_june_greedy.py --seed 202306 --cap 300
```

Add `--reuse-candidates` to skip detection using the saved sampling frame.
Use the same environment/version to reproduce the permutation. This script
writes only this new benchmark folder; the curated `june2023-convective` set
is preserved. Review sheets, seed and exports are regenerated on rerun.
