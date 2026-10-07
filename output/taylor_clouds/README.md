# Taylor clouds and paired reconstruction differences

This analysis uses the saved rainfall fields for all 100 benchmark patches and all six methods. No solvers were rerun and no manuscript classification was changed.

## Figures

- `solver_taylor_clouds.png` / `.svg`: one cloud of 100 patch points per method, on identical normalized Taylor axes. Black diamonds are combined points using the existing equal-patch aggregation. The two manuscript case studies are highlighted.
- `paired_taylor_groups.png` / `.svg`: Solver(GT) and convex points joined by patch, coloured by the existing ordinary-RMSE ratio. The first panel contains all 100 pairs; the other panels repeat them separately by group. These are magnifications in the same Euclidean Taylor plane. Segment lengths are not direct map discrepancies.
- `field_disagreement_vs_ratio.png` / `.svg`: direct pixelwise discrepancy against the RMSE ratio, in normalized and physical units. Both axes are logarithmic. No discrepancy threshold has been chosen.

## Definitions

For each patch, `q = RMSE(Convex against GT) / RMSE(Solver(GT) against GT)`.

The groups are `q <= 2` (76 patches) and `q > 2` (24 patches). There is no patch at exactly 2. Taylor metrics are centered and normalized by that patch's ground-truth SD; the ratio uses ordinary, uncentered RMSE.

Direct disagreement is `D = sqrt(mean((Convex field - Solver(GT) field)^2))`, in mm/h. Unlike the Taylor statistics, D retains differences in the reconstructed means. The normalized version is D divided by the patch's ground-truth spatial SD. It measures disagreement relative to rainfall variability, not percentage error in rainfall amount.

## Results

| Quantity | q <= 2 (76 patches) | q > 2 (24 patches) |
|---|---:|---:|
| Median q | 1.0116 | 5.9297 |
| Median D (mm/h) | 0.0458 | 1.0166 |
| Interquartile range of D (mm/h) | 0.0251-0.0741 | 0.6585-1.5906 |
| Median normalized D | 0.0270 | 0.3371 |
| Interquartile range of normalized D | 0.0197-0.0392 | 0.2923-0.3935 |
| Range of normalized D | 0.0107-0.3302 | 0.1870-0.5720 |
| Median correlation between reconstructed maps | 0.99958 | 0.94262 |

Typical direct field disagreement is substantially smaller in the lower-ratio group, consistent with the case-study interpretation for many patches. This is descriptive evidence from the same benchmark, not independent validation of the ratio threshold or proof of two natural populations. Both diagnostics depend on the same reconstructed fields. In particular, the triangle inequality bounds D between the absolute difference and the sum of the two RMSEs against ground truth.

The two case studies are:

| Patch | q | D (mm/h) | Normalized D |
|---|---:|---:|---:|
| 202301280900_patch000 (Case I) | 6.8998 | 0.6763 | 0.2955 |
| 202301310900_patch000 (Case II) | 1.0248 | 0.1015 | 0.0662 |

There are 65 patches whose two RMSEs differ by at most 5% of Solver(GT)'s RMSE. Their median normalized direct disagreement is 0.0245, with a maximum of 0.1147. This is an additional descriptive check, not a replacement grouping.

## Four lower-ratio patches worth inspecting

These patches have normalized D at least as large as the minimum in the q > 2 group (0.1870). This is a range-overlap diagnostic, not a scientific threshold for dissimilar maps.

| Patch | q | D (mm/h) | Normalized D |
|---|---:|---:|---:|
| 202301180900_patch002 | 1.9767 | 0.7452 | 0.3302 |
| 202301190800_patch002 | 1.5575 | 1.4276 | 0.2416 |
| 202301260600_patch000 | 1.9611 | 2.5497 | 0.3219 |
| 202301302200_patch002 | 1.2414 | 0.4579 | 0.1926 |

Because the normalized-D ranges overlap, no single threshold on normalized D can reproduce the current ratio labels perfectly. Calling all 76 lower-ratio patches 'similar reconstructions' would be too strong. Keep the precise relative-error definition, and use direct disagreement to characterize similarity of the fields. Similar Taylor points alone do not establish similar maps or explain objective-function behaviour.

## Data and reproduction

`patch_metrics.json` contains all 600 method/patch metric records and the 100 paired comparisons. `summary.json` contains group quantiles, case-study values, and range-overlap details. Each record is keyed by patch identifier; no rainfall arrays are copied into the output.

Run `build_taylor_clouds.py` with Python, NumPy, and Matplotlib from the original repository environment. The script reads the six saved solution directories under `Compute-Link-Attenuations/HundredPatches/pipeline/solutions` and the matching `gt_dir` files.

Checks cover all 100 common patches, field shapes, finite pixels, positive reference and reconstruction SDs, per-patch Taylor identities, RMSE/bias decomposition, direct-disagreement triangle bounds, and inclusion of every paired point within the magnified figure. No pixels were excluded. Population moments use denominator N within each patch.
