# 200-patch review sheets

Ten sheets contain 20 ground-truth rainfall maps each in a 4-by-5 grid. The first five sheets show the 100 winter patches (15–31 January 2023), followed by five sheets for the 100 summer patches (June 2023). Each page has a season/date header; panel labels show the overall patch number, timestamp, source patch suffix, nearest city, and maximum rainfall.

Plots use the saved benchmark ground-truth fields at 125 m spacing, with a shared 0–30 mm/h color scale. The accompanying `patch-index.csv` maps every displayed patch to its source NPZ.

Regenerate from the repository root with:

```sh
MPLCONFIGDIR=/private/tmp/rain-review-mpl Patch-Generator/backend/.venv/bin/python output/journal_revision/tools/make_200_patch_review_sheets.py
```
