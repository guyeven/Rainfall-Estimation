# HundredPatches review sheets

Five sheets, each with four rows and five columns, cover all 100 patches in chronological filename order. Labels include review number, timestamp, source patch suffix, nearest city, and actual maximum rainfall. Axes are kilometres, with the north/top edge at y=0.

Plots use the saved `gt_dir` ground-truth fields (125 m refinement and Gaussian smoothing), which are the benchmark inputs. The shared turbo color scale is 0–30 mm/hour, matching the greedy review sheets; values above 30 saturate. `patch-index.csv` maps each review number to the full patch ID and source NPZ.

Regenerate from the repository root:

```sh
MPLCONFIGDIR=/private/tmp/rain-review-mpl Patch-Generator/backend/.venv/bin/python Compute-Link-Attenuations/HundredPatches/patch_overview_generation/make_review_sheets.py
```
